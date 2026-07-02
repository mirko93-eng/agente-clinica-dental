import os
import re
from datetime import datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client

SPAIN_TZ = pytz.timezone('Europe/Madrid')

DAY_MAP = {
    'lunes': 0, 'martes': 1,
    'miércoles': 2, 'miercoles': 2,
    'jueves': 3, 'viernes': 4,
    'sábado': 5, 'sabado': 5,
    'domingo': 6,
}

scheduler = BackgroundScheduler(timezone=SPAIN_TZ)
scheduler.start()


def _next_weekday(day_name: str) -> datetime | None:
    """Devuelve el próximo datetime para el nombre de día dado."""
    target = DAY_MAP.get(day_name.lower().strip())
    if target is None:
        return None
    now = datetime.now(SPAIN_TZ)
    days_ahead = target - now.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


def schedule_whatsapp_reminder(phone: str, name: str, day: str, time_str: str, reason: str):
    """Programa un recordatorio de WhatsApp 4 horas antes de la cita."""
    try:
        appt_date = _next_weekday(day)
        if not appt_date:
            print(f"[REMINDER] No se pudo parsear el día: {day}")
            return

        m = re.match(r'(\d{1,2}):(\d{2})', time_str)
        if not m:
            print(f"[REMINDER] No se pudo parsear la hora: {time_str}")
            return

        hour, minute = int(m.group(1)), int(m.group(2))
        appt_dt = appt_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        reminder_dt = appt_dt - timedelta(hours=4)

        if reminder_dt <= datetime.now(SPAIN_TZ):
            print(f"[REMINDER] La hora del recordatorio ya pasó: {reminder_dt}")
            return

        job_id = f"reminder_{phone}_{appt_dt.isoformat()}"

        # Evitar duplicados
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        scheduler.add_job(
            _send_whatsapp_reminder,
            trigger='date',
            run_date=reminder_dt,
            args=[phone, name, day, time_str, reason],
            id=job_id,
        )
        print(f"[REMINDER] Programado para {reminder_dt} → {phone}")

    except Exception as e:
        print(f"[REMINDER ERROR] {e}")


def _send_whatsapp_reminder(phone: str, name: str, day: str, time_str: str, reason: str):
    """Envía el recordatorio por WhatsApp via Twilio."""
    try:
        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN'),
        )
        from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+34603523811')

        body = (
            f"⏰ *Recordatorio de cita — Clínica Dental Sevilla*\n\n"
            f"Estimado/a {name}, le recordamos su cita en *4 horas*:\n\n"
            f"📅 Día: {day}\n"
            f"⏰ Hora: {time_str}\n"
            f"🦷 Motivo: {reason}\n\n"
            f"Si necesita cancelar o modificar, responda a este mensaje.\n"
            f"¡Le esperamos!"
        )

        client.messages.create(from_=from_number, to=phone, body=body)
        print(f"[REMINDER SENT] → {phone}")

    except Exception as e:
        print(f"[REMINDER SEND ERROR] {e}")
