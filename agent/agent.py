import os
import threading
import anthropic
from collections import defaultdict
from agent.knowledge import SYSTEM_PROMPT
from agent.appointment_parser import extract_email_from_messages, parse_appointment_from_response
from agent.email_service import send_confirmation_email
from agent.reminder_service import schedule_whatsapp_reminder


class DentalAgent:
    """
    Agente recepcionista de clínica dental.
    Mantiene memoria de conversación por número de teléfono.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        # Historial de conversación por paciente (número WhatsApp)
        self.conversations: dict[str, list[dict]] = defaultdict(list)
        # Evitar enviar email/recordatorio dos veces por la misma cita
        self.confirmed_appointments: set[str] = set()

    def process_message(self, phone: str, message: str) -> str:
        """
        Procesa un mensaje entrante y devuelve la respuesta del agente.
        phone: número del paciente (ej: whatsapp:+34600000000)
        message: texto recibido
        """
        # Añadir mensaje del paciente al historial
        # Si el último mensaje ya es del usuario, fusionar en vez de añadir
        # (evita error de Claude API con dos mensajes "user" consecutivos)
        if self.conversations[phone] and self.conversations[phone][-1]["role"] == "user":
            self.conversations[phone][-1]["content"] += f"\n{message}"
        else:
            self.conversations[phone].append({
                "role": "user",
                "content": message
            })

        # Mantener últimos 20 turnos para no superar el contexto
        history = self.conversations[phone][-20:]

        # Llamada a Claude
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=history
        )

        reply = response.content[0].text.strip()

        # Guardar respuesta en historial
        self.conversations[phone].append({
            "role": "assistant",
            "content": reply
        })

        # Detectar confirmación de cita y lanzar email + recordatorio en segundo plano
        self._handle_appointment(phone, reply)

        return reply

    def _handle_appointment(self, phone: str, reply: str):
        """Lanza email y recordatorio en hilo separado para no bloquear la respuesta."""
        appointment = parse_appointment_from_response(reply)
        if not appointment:
            return

        appt_key = f"{phone}_{appointment.get('day')}_{appointment.get('time')}"
        if appt_key in self.confirmed_appointments:
            return
        self.confirmed_appointments.add(appt_key)

        # Copiar datos para el hilo (evitar race conditions)
        name = appointment.get('name', 'Paciente')
        day = appointment.get('day', '')
        time = appointment.get('time', '')
        reason = appointment.get('reason', 'Consulta dental')
        email = extract_email_from_messages(self.conversations[phone])

        # Ejecutar en hilo para no bloquear la respuesta a Twilio
        def background():
            try:
                if email:
                    send_confirmation_email(email, name, day, time, reason)
                if day and time:
                    schedule_whatsapp_reminder(phone, name, day, time, reason)
            except Exception as e:
                print(f"[BACKGROUND ERROR] {e}")

        t = threading.Thread(target=background, daemon=True)
        t.start()
