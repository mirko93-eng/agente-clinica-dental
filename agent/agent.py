import os
import anthropic
from collections import defaultdict
from agent.knowledge import SYSTEM_PROMPT


class DentalAgent:
    """
    Agente recepcionista de clínica dental.
    Mantiene memoria de conversación por número de teléfono.
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        # Historial de conversación por paciente (número WhatsApp)
        self.conversations: dict[str, list[dict]] = defaultdict(list)

    def process_message(self, phone: str, message: str) -> str:
        """
        Procesa un mensaje entrante y devuelve la respuesta del agente.
        phone: número del paciente (ej: whatsapp:+34600000000)
        message: texto recibido
        """
        # Añadir mensaje del paciente al historial
        self.conversations[phone].append({
            "role": "user",
            "content": message
        })

        # Mantener últimos 20 turnos para no superar el contexto
        history = self.conversations[phone][-20:]

        # Llamada a Claude
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=history
        )

        reply = response.content[0].text.strip()

        # Guardar respuesta en historial
        self.conversations[phone].append({
            "role": "assistant",
            "content": reply
        })

        return reply
