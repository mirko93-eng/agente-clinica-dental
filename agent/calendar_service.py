import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
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

_WEEKDAY_NAMES_ES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

_DAY_TOKEN_PATTERN = re.compile(
    r'\b(hoy|mañana|manana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b',
    re.IGNORECASE
)

MONTH_MAP = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
}

_DATE_WITH_MONTH_NAME_PATTERN = re.compile(
    r'\b(\d{1,2})\s*(?:de\s+)?(' + '|'.join(MONTH_MAP.keys()) + r')'
    r'(?:\s*(?:de\s+)?(\d{4}))?\b',
    re.IGNORECASE
)

_NUMERIC_DATE_PATTERN = re.compile(r'\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b')

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


def normalize_phone(phone: str) -> str:
    """
    Normaliza el identificador de teléfono a un formato estable. Es la ÚNICA
    función que debe usarse tanto al guardar el teléfono en extendedProperties
    (create_calendar_event) como al buscar por él (find_appointments_by_phone),
    para que espacios o mayúsculas distintas en el prefijo "whatsapp:" no
    impidan encontrar la cita real del paciente.
    """
    return re.sub(r'\s+', '', phone.strip().lower())


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


def _resolve_year(month: int, day_num: int, now: datetime) -> int:
    """Si el mes/día ya pasó este año, usa el año siguiente (próxima ocurrencia)."""
    try:
        candidate = SPAIN_TZ.localize(datetime(now.year, month, day_num))
    except ValueError:
        return now.year
    return now.year + 1 if candidate.date() < now.date() else now.year


def parse_day_to_date(day: str) -> datetime | None:
    """
    Convierte un día en un objeto datetime (hora 0:00, zona España). Es la
    ÚNICA función de parseo de fecha del proyecto — la usan tanto la creación
    y consulta de Google Calendar como la programación/cancelación de
    recordatorios de WhatsApp, para no tener que arreglar el mismo bug de
    formato en dos sitios.

    Reconoce, en este orden de prioridad (una fecha explícita manda sobre un
    nombre de día suelto si ambos aparecen en el texto):
      1) Fecha con nombre de mes: "8 de julio", "martes 7 de julio de 2026"
      2) Fecha numérica: "07/07", "8/7/2026", "07-07"
      3) Nombre de día de la semana o término relativo, en cualquier parte
         del texto (soporta "Martes 7", "hoy", "mañana", etc.)

    Si el año no se especifica, usa el actual o el siguiente si esa fecha
    ya pasó este año.
    """
    now = datetime.now(SPAIN_TZ)

    m = _DATE_WITH_MONTH_NAME_PATTERN.search(day)
    if m:
        day_num = int(m.group(1))
        month = MONTH_MAP[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else _resolve_year(month, day_num, now)
        try:
            return SPAIN_TZ.localize(datetime(year, month, day_num))
        except ValueError:
            return None

    m = _NUMERIC_DATE_PATTERN.search(day)
    if m:
        day_num, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3))
            if year < 100:
                year += 2000
        else:
            year = _resolve_year(month, day_num, now)
        try:
            return SPAIN_TZ.localize(datetime(year, month, day_num))
        except ValueError:
            return None

    match = _DAY_TOKEN_PATTERN.search(day)
    if not match:
        return None
    day_lower = match.group(0).lower()

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
    base = parse_day_to_date(day)
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

    appt_date = parse_day_to_date(day)
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


def create_calendar_event(name: str, day: str, time_str: str, reason: str, phone: str, email: str = None) -> str | None:
    """Crea un evento en Google Calendar. Devuelve el ID del evento creado o None si falla."""
    access_token = _get_access_token()
    if not access_token:
        return None

    start, end = _parse_appointment_datetime(day, time_str)
    if not start:
        print(f"[CALENDAR] No se pudo parsear la fecha: {day} {time_str}")
        return None

    phone_key = normalize_phone(phone)

    event = {
        "summary": f"🦷 Cita — {name}",
        "description": f"Motivo: {reason}\nPaciente: {name}\nTeléfono: {phone}",
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "Europe/Madrid"
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "Europe/Madrid"
        },
        "extendedProperties": {
            "private": {"phone": phone_key}
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
            event_id = result.get('id')
            print(f"[CALENDAR] Evento creado: {event_id} — {name} {day} {time_str}")
            return event_id
    except Exception as e:
        print(f"[CALENDAR ERROR] {e}")
        return None


def find_appointments_by_phone(phone: str) -> list | None:
    """
    Busca en Google Calendar las citas futuras del paciente identificado por su
    teléfono (mismo identificador usado para la memoria por paciente), usando
    extendedProperties.private.phone.

    Devuelve una lista de dicts (event_id, summary, description, start,
    day_display, time_display) ordenada cronológicamente, [] si no hay citas,
    o None si no se pudo consultar el calendario.
    """
    access_token = _get_access_token()
    if not access_token:
        return None

    phone_key = normalize_phone(phone)

    now = datetime.now(SPAIN_TZ)
    params = urllib.parse.urlencode({
        "timeMin": now.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "privateExtendedProperty": f"phone={phone_key}",
    })

    req = urllib.request.Request(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{params}",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            items = data.get("items", [])
    except Exception as e:
        print(f"[CALENDAR ERROR] Búsqueda citas (phone_key={phone_key!r}): {e}")
        return None

    appointments = []
    for item in items:
        start_raw = item.get("start", {}).get("dateTime")
        if not start_raw:
            continue
        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(SPAIN_TZ)
        appointments.append({
            "event_id": item.get("id"),
            "summary": item.get("summary", ""),
            "description": item.get("description", ""),
            "start": start_dt,
            "day_display": f"{_WEEKDAY_NAMES_ES[start_dt.weekday()]} {start_dt.strftime('%d/%m')}",
            "time_display": start_dt.strftime("%H:%M"),
        })

    if not appointments:
        print(
            f"[CALENDAR] Búsqueda citas para phone_key={phone_key!r}: 0 encontradas "
            f"(sin coincidencias en extendedProperties.private.phone — puede ser una "
            f"cita creada antes de guardar el teléfono, o un desajuste de formato)"
        )
    else:
        print(f"[CALENDAR] Búsqueda citas para phone_key={phone_key!r}: {len(appointments)} encontrada(s)")
    return appointments


def get_event(event_id: str) -> dict | None:
    """Obtiene un evento de Google Calendar por su ID (incluye start real en España)."""
    access_token = _get_access_token()
    if not access_token:
        return None

    req = urllib.request.Request(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            item = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(
                f"[CALENDAR] Evento {event_id!r} no existe (404) — probablemente un ID "
                f"inventado por el modelo o una cita ya borrada anteriormente"
            )
        else:
            print(f"[CALENDAR ERROR] Obtener evento {event_id}: HTTP {e.code} {e.reason}")
        return None
    except Exception as e:
        print(f"[CALENDAR ERROR] Obtener evento {event_id}: {e}")
        return None

    start_raw = item.get("start", {}).get("dateTime")
    if not start_raw:
        return None

    start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00")).astimezone(SPAIN_TZ)
    return {
        "event_id": item.get("id"),
        "summary": item.get("summary", ""),
        "description": item.get("description", ""),
        "start": start_dt,
        "phone": item.get("extendedProperties", {}).get("private", {}).get("phone"),
    }


def delete_calendar_event(event_id: str) -> bool:
    """Elimina un evento de Google Calendar por su ID (calendar.events.delete)."""
    access_token = _get_access_token()
    if not access_token:
        return False

    req = urllib.request.Request(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        method="DELETE"
    )

    try:
        urllib.request.urlopen(req)
        print(f"[CALENDAR] Evento eliminado: {event_id}")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404 or e.code == 410:
            print(f"[CALENDAR ERROR] Evento {event_id!r} no existe o ya estaba borrado (HTTP {e.code})")
        else:
            print(f"[CALENDAR ERROR] Eliminar evento {event_id}: HTTP {e.code} {e.reason}")
        return False
    except Exception as e:
        print(f"[CALENDAR ERROR] Eliminar evento {event_id}: {e}")
        return False
