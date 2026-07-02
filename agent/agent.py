import os
import json
import threading
import anthropic
from collections import defaultdict
from agent.knowledge import SYSTEM_PROMPT
from agent.appointment_parser import extract_email_from_messages, parse_appointment_from_response
from agent.email_service import send_confirmation_email
from agent.reminder_service import schedule_whatsapp_reminder
from agent.calendar_service import create_calendar_event

DATA_FILE = "/app/data/patients.json"


def _load_data() -> dict:
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[DATA] Error cargando datos: {e}")
    return {}


def _save_data(data: dict):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DATA] Error guardando datos: {e}")


class DentalAgent:
    """
    Agente recepcionista de clínica dental.
    Mantiene memoria persistente de conversación por número de teléfono.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        raw = _load_data()
        # Restaurar conversaciones guardadas
        self.conversations: dict[str, list[dict]] = defaultdict(list, raw.get("conversations", {}))
        self.confirmed_appointments: set[str] = set(raw.get("confirmed_appointments", []))
        print(f"[DATA] Cargados {len(self.conversations)} pacientes en memoria")

    def _persist(self):
        """Guarda el estado actual en disco."""
        _save_data({
            "conversations": dict(self.conversations),
            "confirmed_appointments": list(self.confirmed_appointments)
        })

    def process_message(self, phone: str, message: str) -> str:
        # Si el último mensaje ya es del usuario, fusionar (evita error de Claude API)
        if self.conversations[phone] and self.conversations[phone][-1]["role"] == "user":
            self.conversations[phone][-1]["content"] += f"\n{message}"
        else:
            self.conversations[phone].append({"role": "user", "content": message})

        # Mantener últimos 20 turnos
        history = self.conversations[phone][-20:]

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=history
        )

        reply = response.content[0].text.strip()

        self.conversations[phone].append({"role": "assistant", "content": reply})

        # Guardar en disco tras cada mensaje
        self._persist()

        # Email + recordatorio en hilo para no bloquear
        self._handle_appointment(phone, reply)

        return reply

    def _handle_appointment(self, phone: str, reply: str):
        appointment = parse_appointment_from_response(reply)
        if not appointment:
            return

        appt_key = f"{phone}_{appointment.get('day')}_{appointment.get('time')}"
        if appt_key in self.confirmed_appointments:
            return
        self.confirmed_appointments.add(appt_key)
        self._persist()

        name = appointment.get('name', 'Paciente')
        day = appointment.get('day', '')
        time = appointment.get('time', '')
        reason = appointment.get('reason', 'Consulta dental')
        email = extract_email_from_messages(self.conversations[phone])

        def background():
            try:
                if email:
                    send_confirmation_email(email, name, day, time, reason)
                if day and time:
                    schedule_whatsapp_reminder(phone, name, day, time, reason)
                    create_calendar_event(name, day, time, reason, email)
            except Exception as e:
                print(f"[BACKGROUND ERROR] {e}")

        t = threading.Thread(target=background, daemon=True)
        t.start()
