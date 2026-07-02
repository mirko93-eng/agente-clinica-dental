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


def _parse_appointment_datetime(day: str, time_str: str):
    """Convierte día y hora en datetime de España."""
    import re
    now = datetime.now(SPAIN_TZ)
    day_lower = day.lower().strip()

    if day_lower in ('hoy', 'today'):
        base = now
    elif day_lower in ('mañana', 'manana', 'tomorrow'):
        base = now + timedelta(days=1)
    else:
        target = DAY_MAP.get(day_lower)
        if target is None:
            return None, None
        days_ahead = target - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        base = now + timedelta(days=days_ahead)

    m = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if not m:
        return None, None

    hour, minute = int(m.group(1)), int(m.group(2))
    start = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start, end


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
