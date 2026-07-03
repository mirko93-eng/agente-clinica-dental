import os
import re
import json
import threading
import anthropic
from collections import defaultdict
from agent.knowledge import SYSTEM_PROMPT
from agent.appointment_parser import (
    extract_email_from_messages,
    parse_appointment_from_response,
    parse_cancellation_from_response,
)
from agent.email_service import send_confirmation_email, send_cancellation_email
from agent.reminder_service import (
    schedule_whatsapp_reminder,
    cancel_whatsapp_reminder,
    send_cancellation_confirmation,
)
from agent.calendar_service import (
    create_calendar_event,
    get_available_slots,
    find_appointments_by_phone,
    get_event,
    delete_calendar_event,
)

DATA_FILE = "/app/data/patients.json"

_DAY_PATTERN = re.compile(
    r'\b(hoy|mañana|manana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b',
    re.IGNORECASE
)

_CANCEL_INTENT_PATTERN = re.compile(
    r'\b(cancelar|cancela|cancelaci[oó]n|anular|anula|no puedo ir|no podr[eé] ir|'
    r'no voy a poder|reprogramar|cambiar (mi )?cita|cambiar la cita|cambiar de (hora|d[ií]a))\b',
    re.IGNORECASE
)


def _detect_day_in_message(message: str) -> str | None:
    """Devuelve el primer día mencionado en el mensaje, en minúsculas."""
    m = _DAY_PATTERN.search(message)
    return m.group(0).lower() if m else None


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
    Consulta Google Calendar para ofrecer solo huecos disponibles.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        raw = _load_data()
        self.conversations: dict[str, list[dict]] = defaultdict(list, raw.get("conversations", {}))
        self.confirmed_appointments: set[str] = set(raw.get("confirmed_appointments", []))
        self.confirmed_cancellations: set[str] = set(raw.get("confirmed_cancellations", []))
        print(f"[DATA] Cargados {len(self.conversations)} pacientes en memoria")

    def _persist(self):
        """Guarda el estado actual en disco."""
        _save_data({
            "conversations": dict(self.conversations),
            "confirmed_appointments": list(self.confirmed_appointments),
            "confirmed_cancellations": list(self.confirmed_cancellations)
        })

    def _inject_availability(self, phone: str, raw_message: str):
        """
        Si el mensaje menciona un día, consulta Google Calendar e inyecta
        la disponibilidad en el contenido del último mensaje del usuario.
        Solo inyecta si la consulta al calendario tiene éxito.
        """
        day = _detect_day_in_message(raw_message)
        if not day:
            return

        try:
            slots = get_available_slots(day)
        except Exception as e:
            print(f"[AVAILABILITY ERROR] {e}")
            return

        if slots is None:
            # No se pudo consultar el calendario — Camila responde sin contexto de agenda
            return

        day_display = day.capitalize()
        if slots:
            context = f"[AGENDA-{day_display}: huecos libres: {', '.join(slots)}]\n"
        else:
            context = f"[AGENDA-{day_display}: sin huecos disponibles ese día]\n"

        # Inyectar al principio del último mensaje del usuario
        self.conversations[phone][-1]["content"] = (
            context + self.conversations[phone][-1]["content"]
        )
        print(f"[AVAILABILITY] Inyectado para {day}: {slots}")

    def _inject_cancellation_context(self, phone: str, raw_message: str):
        """
        Si el mensaje indica intención de cancelar/cambiar cita, busca en
        Google Calendar las citas futuras del paciente (por teléfono) e
        inyecta los resultados reales en el último mensaje del usuario, para
        que Camila pida confirmación explícita antes de borrar nada.
        """
        if not _CANCEL_INTENT_PATTERN.search(raw_message):
            return

        try:
            appointments = find_appointments_by_phone(phone)
        except Exception as e:
            print(f"[CANCEL LOOKUP ERROR] {e}")
            return

        if appointments is None:
            # No se pudo consultar el calendario — Camila responde sin contexto
            return

        if not appointments:
            context = "[CANCELACION-BUSQUEDA: sin citas encontradas]\n"
        elif len(appointments) == 1:
            a = appointments[0]
            context = (
                f"[CANCELACION-BUSQUEDA: 1 cita encontrada → "
                f"ID={a['event_id']} Día={a['day_display']} Hora={a['time_display']}]\n"
            )
        else:
            items = " · ".join(
                f"{i + 1}) ID={a['event_id']} Día={a['day_display']} Hora={a['time_display']}"
                for i, a in enumerate(appointments)
            )
            context = f"[CANCELACION-BUSQUEDA: {len(appointments)} citas encontradas → {items}]\n"

        self.conversations[phone][-1]["content"] = (
            context + self.conversations[phone][-1]["content"]
        )
        print(f"[CANCEL LOOKUP] {phone}: {len(appointments)} cita(s) encontrada(s)")

    def process_message(self, phone: str, message: str) -> str:
        # Fusionar mensajes consecutivos de usuario (evita error de Claude API)
        if self.conversations[phone] and self.conversations[phone][-1]["role"] == "user":
            self.conversations[phone][-1]["content"] += f"\n{message}"
        else:
            self.conversations[phone].append({"role": "user", "content": message})

        # Consultar disponibilidad e inyectar contexto si se menciona un día
        self._inject_availability(phone, message)

        # Buscar citas existentes e inyectar contexto si hay intención de cancelar
        self._inject_cancellation_context(phone, message)

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

        # Email + recordatorio + calendario en hilo para no bloquear
        self._handle_appointment(phone, reply)
        self._handle_cancellation(phone, reply)

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
                    create_calendar_event(name, day, time, reason, phone, email)
            except Exception as e:
                print(f"[BACKGROUND ERROR] {e}")

        t = threading.Thread(target=background, daemon=True)
        t.start()

    def _handle_cancellation(self, phone: str, reply: str):
        cancellation = parse_cancellation_from_response(reply)
        if not cancellation:
            return

        event_id = cancellation.get('event_id')
        if not event_id or event_id in self.confirmed_cancellations:
            return
        self.confirmed_cancellations.add(event_id)
        self._persist()

        name = cancellation.get('name', 'Paciente')
        day = cancellation.get('day', '')
        time = cancellation.get('time', '')
        email = extract_email_from_messages(self.conversations[phone])

        def background():
            try:
                event = get_event(event_id)
                delete_calendar_event(event_id)
                if event and event.get('start'):
                    cancel_whatsapp_reminder(phone, event['start'])
                send_cancellation_confirmation(phone, name, day, time)
                if email:
                    send_cancellation_email(email, name, day, time)
                print(
                    f"[CANCEL] Cita cancelada — evento={event_id} paciente={name} "
                    f"teléfono={phone} día={day} hora={time}"
                )
            except Exception as e:
                print(f"[CANCEL BACKGROUND ERROR] {e}")

        t = threading.Thread(target=background, daemon=True)
        t.start()
