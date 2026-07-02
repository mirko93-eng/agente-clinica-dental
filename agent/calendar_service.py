import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pytz

SPAIN_TZ = pytz.timezone('Europe/Madrid')

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")

DAY_MAP = {
    'lunes': 0, 'martes': 1,
    'miércoles': 2, 'miercoles': 2,
    'jueves': 3, 'viernes': 4,
    'sábado': 5, 'sabado': 5,
    'domingo': 6,
}

# Horario de la clínica: weekday (0=lun) → (hora_inicio, hora_fin) o None si cerrado
WORKING_HOURS = {
    0: (9, 20),
    1: (9, 20),
    2: (9, 20),
    3: (9, 20),
    4: (9, 20),
    5: (9, 14),
    6: None,
}


def _get_access_token() -> str | None:
    """Obtiene un access token usando el refresh token."""
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        print("[CALENDAR] Credenciales de Google no configuradas")
        return None

    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
            return tokens.get("access_token")
    except Exception as e:
        print(f"[CALENDAR ERROR] Token: {e}")
        return None


def _parse_day_to_date(day: str) -> datetime | None:
    """Convierte un nombre de día en un objeto datetime (hora 0:00, zona España)."""
    now = datetime.now(SPAIN_TZ)
    day_lower = day.lower().strip()

    if day_lower in ('hoy', 'today'):
        return now
    elif day_lower in ('mañana', 'manana', 'tomorrow'):
        return now + timedelta(days=1)
    else:
        target = DAY_MAP.get(day_lower)
        if target is None:
            return None
        days_ahead = target - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return now + timedelta(days=days_ahead)


def _parse_appointment_datetime(day: str, time_str: str):
    """Convierte día y hora en datetime de España."""
    import re
    base = _parse_day_to_date(day)
    if base is None:
        return None, None

    m = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if not m:
        return None, None

    hour, minute = int(m.group(1)), int(m.group(2))
    start = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start, end


def get_available_slots(day: str) -> list | None:
    """
    Consulta Google Calendar y devuelve los huecos libres de 1h para el día dado.
    - Retorna None si no se puede consultar (credenciales ausentes o error de red).
    - Retorna [] si el día está cerrado o sin huecos libres.
    - Retorna lista de strings ["09:00", "10:00", ...] con los huecos disponibles.
    """
    access_token = _get_access_token()
    if not access_token:
        return None

    appt_date = _parse_day_to_date(day)
    if not appt_date:
        return None

    hours = WORKING_HOURS.get(appt_date.weekday())
    if hours is None:
        return []  # cerrado

    start_hour, end_hour = hours
    day_start = appt_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    day_end = appt_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)

    payload = json.dumps({
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "items": [{"id": "primary"}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/freeBusy",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            busy_raw = data.get("calendars", {}).get("primary", {}).get("busy", [])
    except Exception as e:
        print(f"[CALENDAR ERROR] freeBusy: {e}")
        return None

    # Convertir periodos ocupados a timezone España
    busy_periods = []
    for b in busy_raw:
        b_start = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(SPAIN_TZ)
        b_end = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(SPAIN_TZ)
        busy_periods.append((b_start, b_end))

    # Calcular huecos libres de 1 hora
    free_slots = []
    current = day_start
    while current + timedelta(hours=1) <= day_end:
        slot_end = current + timedelta(hours=1)
        is_busy = any(
            not (slot_end <= b_start or current >= b_end)
            for b_start, b_end in busy_periods
        )
        if not is_busy:
            free_slots.append(current.strftime("%H:%M"))
        current = slot_end

    print(f"[CALENDAR] Disponibilidad {day}: {free_slots if free_slots else 'sin huecos'}")
    return free_slots


def create_calendar_event(name: str, day: str, time_str: str, reason: str, email: str = None) -> bool:
    """Crea un evento en Google Calendar."""
    access_token = _get_access_token()
    if not access_token:
        return False

    start, end = _parse_appointment_datetime(day, time_str)
    if not start:
        print(f"[CALENDAR] No se pudo parsear la fecha: {day} {time_str}")
        return False

    event = {
        "summary": f"🦷 Cita — {name}",
        "description": f"Motivo: {reason}\nPaciente: {name}",
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "Europe/Madrid"
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "Europe/Madrid"
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "email", "minutes": 240}
            ]
        }
    }

    if email:
        event["attendees"] = [{"email": email}]

    payload = json.dumps(event).encode("utf-8")

    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"[CALENDAR] Evento creado: {result.get('id')} — {name} {day} {time_str}")
            return True
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")
        return False
