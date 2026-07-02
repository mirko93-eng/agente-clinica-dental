import os
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

        # Detectar confirmación de cita y enviar email + programar recordatorio
        self._handle_appointment(phone, reply)

        return reply

    def _handle_appointment(self, phone: str, reply: str):
        """Envía email de confirmación y programa recordatorio si la respuesta confirma cita."""
        appointment = parse_appointment_from_response(reply)
        if not appointment:
            return

        # Clave única para esta cita (evitar duplicados)
        appt_key = f"{phone}_{appointment.get('day')}_{appointment.get('time')}"
        if appt_key in self.confirmed_appointments:
            return
        self.confirmed_appointments.add(appt_key)

        name = appointment.get('name', 'Paciente')
        day = appointment.get('day', '')
        time = appointment.get('time', '')
        reason = appointment.get('reason', 'Consulta dental')

        # Enviar email si el paciente dio su correo
        email = extract_email_from_messages(self.conversations[phone])
        if email:
            send_confirmation_email(email, name, day, time, reason)

        # Programar recordatorio WhatsApp 4 horas antes
        if day and time:
            schedule_whatsapp_reminder(phone, name, day, time, reason)
