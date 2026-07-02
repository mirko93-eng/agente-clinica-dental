import os
import json
import urllib.request
import urllib.parse
from fastapi import FastAPI, Form, Response, Request
from dotenv import load_dotenv
from agent.agent import DentalAgent

load_dotenv()

app = FastAPI(title="Agente Clínica Dental - Camila")
dental_agent = DentalAgent()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = "https://web-production-39cb7.up.railway.app/oauth2callback"


@app.get("/")
def health():
    return {"status": "ok", "agente": "Camila - Recepcionista Clínica Dental"}


@app.get("/oauth2callback")
async def oauth2callback(request: Request):
    """Recibe el código OAuth2 de Google y lo intercambia por tokens."""
    code = request.query_params.get("code")
    if not code:
        return Response(content="Error: no se recibió código", status_code=400)

    # Intercambiar código por tokens
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
            refresh_token = tokens.get("refresh_token", "")
            print(f"[OAUTH] Refresh token obtenido: {refresh_token}")
            return Response(
                content=f"""
                <html><body>
                <h2>✅ Autorización completada</h2>
                <p>Copia este refresh token y añádelo como variable GOOGLE_REFRESH_TOKEN en Railway:</p>
                <code style="font-size:14px;background:#eee;padding:10px;display:block">{refresh_token}</code>
                </body></html>
                """,
                media_type="text/html"
            )
    except Exception as e:
        print(f"[OAUTH ERROR] {e}")
        return Response(content=f"Error: {e}", status_code=500)


@app.post("/webhook")
async def webhook(
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(default=""),
):
    phone = From.strip()
    message = Body.strip()

    print(f"[IN]  {phone}: {message}")

    try:
        reply = dental_agent.process_message(phone, message)
    except Exception as e:
        print(f"[ERROR] {e}")
        reply = "Disculpe, tenemos un problema técnico momentáneo. Por favor llame al 954 000 000 o inténtelo de nuevo."

    print(f"[OUT] {phone}: {reply}")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply}</Message>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
