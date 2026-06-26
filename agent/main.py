import os
from fastapi import FastAPI, Form, Response
from dotenv import load_dotenv
from agent.agent import DentalAgent

load_dotenv()

app = FastAPI(title="Agente Clínica Dental - Camila")
dental_agent = DentalAgent()


@app.get("/")
def health():
    return {"status": "ok", "agente": "Camila - Recepcionista Clínica Dental"}


@app.post("/webhook")
async def webhook(
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(default=""),
):
    """
    Webhook de Twilio. Recibe mensajes de WhatsApp y responde con TwiML.
    Configurar en Twilio Console → Messaging → Sandbox → When a message comes in.
    URL: https://TU-DOMINIO.railway.app/webhook
    """
    phone = From.strip()       # e.g. whatsapp:+34600000000
    message = Body.strip()

    print(f"[IN]  {phone}: {message}")

    try:
        reply = dental_agent.process_message(phone, message)
    except Exception as e:
        print(f"[ERROR] {e}")
        reply = "Disculpe, tenemos un problema técnico momentáneo. Por favor llame al 954 000 000 o inténtelo de nuevo."

    print(f"[OUT] {phone}: {reply}")

    # Respuesta TwiML para Twilio
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
