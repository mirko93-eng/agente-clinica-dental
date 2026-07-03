import re


def extract_email_from_messages(messages: list) -> str | None:
    """Busca el email en los mensajes del usuario."""
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    for msg in reversed(messages):
        if msg['role'] == 'user':
            match = re.search(email_pattern, msg['content'])
            if match:
                return match.group()
    return None


def parse_appointment_from_response(response: str) -> dict | None:
    """
    Detecta si la respuesta de Camila contiene una confirmación de cita
    y extrae los datos estructurados.
    """
    if 'Confirmo su cita' not in response:
        return None

    appointment = {}

    name_match = re.search(r'\*?Nombre:\*?\s*(.+?)[\n\r]', response)
    if name_match:
        appointment['name'] = name_match.group(1).strip().strip('*')

    day_match = re.search(r'\*?Día:\*?\s*(.+?)[\n\r]', response)
    if day_match:
        appointment['day'] = day_match.group(1).strip().strip('*')

    time_match = re.search(r'\*?Hora:\*?\s*(.+?)[\n\r]', response)
    if time_match:
        appointment['time'] = time_match.group(1).strip().strip('*')

    reason_match = re.search(r'\*?Motivo:\*?\s*(.+?)[\n\r]', response)
    if reason_match:
        appointment['reason'] = reason_match.group(1).strip().strip('*')

    return appointment if len(appointment) >= 2 else None


def parse_cancellation_from_response(response: str) -> dict | None:
    """
    Detecta si la respuesta de Camila contiene una confirmación de cancelación
    y extrae los datos estructurados (incluido el ID real del evento de
    Google Calendar, inyectado previamente vía contexto [CANCELACION-BUSQUEDA]).
    """
    if 'Confirmo cancelación' not in response and 'Confirmo cancelacion' not in response:
        return None

    cancellation = {}

    id_match = re.search(r'\*?ID:\*?\s*(.+?)(?:[\n\r]|$)', response)
    if id_match:
        cancellation['event_id'] = id_match.group(1).strip().strip('*')

    name_match = re.search(r'\*?Nombre:\*?\s*(.+?)(?:[\n\r]|$)', response)
    if name_match:
        cancellation['name'] = name_match.group(1).strip().strip('*')

    day_match = re.search(r'\*?Día:\*?\s*(.+?)(?:[\n\r]|$)', response)
    if day_match:
        cancellation['day'] = day_match.group(1).strip().strip('*')

    time_match = re.search(r'\*?Hora:\*?\s*(.+?)(?:[\n\r]|$)', response)
    if time_match:
        cancellation['time'] = time_match.group(1).strip().strip('*')

    return cancellation if cancellation.get('event_id') else None
