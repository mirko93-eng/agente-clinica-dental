# Despliegue — Agente Clínica Dental (Camila)

Stack: FastAPI + Claude API + Twilio WhatsApp + Railway

---

## PASO 1 — Copia tus variables de entorno

Duplica `.env.example` como `.env` y rellena:

```
ANTHROPIC_API_KEY=sk-ant-...     ← platform.anthropic.com
TWILIO_ACCOUNT_SID=AC...         ← Twilio Console → Account Info
TWILIO_AUTH_TOKEN=...            ← Twilio Console → Account Info
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

---

## PASO 2 — Prueba en local

```bash
pip install -r requirements.txt
uvicorn agent.main:app --reload --port 8000
```

Abre http://localhost:8000 → debe responder `{"status": "ok"}`

---

## PASO 3 — Sube a GitHub

```bash
git init
git add .
git commit -m "feat: agente clinica dental camila"
git remote add origin https://github.com/TU_USUARIO/agente-clinica-dental.git
git push -u origin main
```

---

## PASO 4 — Despliega en Railway

1. Entra a railway.app → New Project → Deploy from GitHub
2. Selecciona el repositorio
3. En Variables, añade las 4 variables del `.env`
4. Railway despliega automáticamente
5. Copia la URL pública (ej: `https://agente-clinica-dental.up.railway.app`)

---

## PASO 5 — Configura el webhook en Twilio

1. Twilio Console → Messaging → Try it out → Send a WhatsApp message
2. En "When a message comes in" pega:
   `https://agente-clinica-dental.up.railway.app/webhook`
3. Método: HTTP POST
4. Guarda los cambios

Envía un WhatsApp al número de sandbox de Twilio → Camila responde.

---

## Estructura del proyecto

```
agente de clinica dental/
├── agent/
│   ├── __init__.py
│   ├── main.py        ← servidor FastAPI + webhook Twilio
│   ├── agent.py       ← lógica Claude API + memoria
│   └── knowledge.py   ← info clínica + system prompt
├── .env.example
├── .env               ← NO subir a GitHub
├── requirements.txt
├── Procfile
└── railway.json
```

---

## Personalización

Para cambiar precios, servicios o el tono de Camila, edita `agent/knowledge.py`.
