import os
import resend
from resend.exceptions import ResendError


def _log_resend_failure(context: str, to_email: str, e: Exception):
    """Log detallado del fallo de envío, distinguiendo errores de la API de
    Resend (código/tipo/mensaje reales) de fallos inesperados (red, etc.)."""
    if isinstance(e, ResendError):
        print(
            f"[EMAIL ERROR] Resend rechazó el envío de {context} a {to_email} — "
            f"status={e.code} tipo={e.error_type} mensaje={e.message}"
        )
    else:
        print(
            f"[EMAIL ERROR] Fallo inesperado enviando {context} a {to_email}: "
            f"{type(e).__name__}: {e}"
        )


def send_confirmation_email(to_email: str, name: str, day: str, time: str, reason: str) -> bool:
    """Envía email de confirmación de cita via Resend SDK."""
    api_key = os.getenv('RESEND_API_KEY')

    if not api_key:
        print("[EMAIL] RESEND_API_KEY no configurado — email no enviado")
        return False

    resend.api_key = api_key

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 500px; margin: 0 auto;">
        <div style="background: #1a73e8; padding: 20px; text-align: center;">
            <h2 style="color: white; margin: 0;">🦷 Clínica Dental Sevilla</h2>
        </div>
        <div style="padding: 30px; background: #f9f9f9;">
            <p>Estimado/a <strong>{name}</strong>,</p>
            <p>Su cita ha sido confirmada correctamente:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #e8f0fe;">
                    <td style="padding: 10px; font-weight: bold;">📅 Día</td>
                    <td style="padding: 10px;">{day}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: bold;">⏰ Hora</td>
                    <td style="padding: 10px;">{time}</td>
                </tr>
                <tr style="background: #e8f0fe;">
                    <td style="padding: 10px; font-weight: bold;">🦷 Motivo</td>
                    <td style="padding: 10px;">{reason}</td>
                </tr>
            </table>
            <p>Recibirá un recordatorio por WhatsApp <strong>4 horas antes</strong> de su cita.</p>
            <p>Si necesita cancelar o modificar, contáctenos respondiendo al WhatsApp.</p>
        </div>
        <div style="padding: 15px; text-align: center; font-size: 12px; color: #666;">
            <p>Clínica Dental Sevilla — Lunes a viernes 9:00-20:00 | Sábados 9:00-14:00</p>
        </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": "Clínica Dental Sevilla <citas@nivelup.es>",
            "to": [to_email],
            "subject": "✅ Confirmación de cita — Clínica Dental Sevilla",
            "html": html,
        }
        response = resend.Emails.send(params)
        print(f"[EMAIL] Confirmación enviada a {to_email} — id: {response.get('id', '?')}")
        return True
    except Exception as e:
        _log_resend_failure("confirmación de cita", to_email, e)
        return False


def send_cancellation_email(to_email: str, name: str, day: str, time: str) -> bool:
    """Envía email de cancelación de cita via Resend SDK."""
    api_key = os.getenv('RESEND_API_KEY')

    if not api_key:
        print("[EMAIL] RESEND_API_KEY no configurado — email de cancelación no enviado")
        return False

    resend.api_key = api_key

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; max-width: 500px; margin: 0 auto;">
        <div style="background: #c62828; padding: 20px; text-align: center;">
            <h2 style="color: white; margin: 0;">🦷 Clínica Dental Sevilla</h2>
        </div>
        <div style="padding: 30px; background: #f9f9f9;">
            <p>Estimado/a <strong>{name}</strong>,</p>
            <p>Le confirmamos que su cita ha sido <strong>cancelada</strong>:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #fdeaea;">
                    <td style="padding: 10px; font-weight: bold;">📅 Día</td>
                    <td style="padding: 10px;">{day}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: bold;">⏰ Hora</td>
                    <td style="padding: 10px;">{time}</td>
                </tr>
            </table>
            <p>Si desea agendar una nueva cita, respóndanos por WhatsApp cuando quiera.</p>
        </div>
        <div style="padding: 15px; text-align: center; font-size: 12px; color: #666;">
            <p>Clínica Dental Sevilla — Lunes a viernes 9:00-20:00 | Sábados 9:00-14:00</p>
        </div>
    </body>
    </html>
    """

    try:
        params = {
            "from": "Clínica Dental Sevilla <citas@nivelup.es>",
            "to": [to_email],
            "subject": "❌ Cancelación de cita — Clínica Dental Sevilla",
            "html": html,
        }
        response = resend.Emails.send(params)
        print(f"[EMAIL] Cancelación enviada a {to_email} — id: {response.get('id', '?')}")
        return True
    except Exception as e:
        _log_resend_failure("cancelación de cita", to_email, e)
        return False
