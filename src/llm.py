"""
LLM handler for ProAlto WhatsApp Bot.
Uses Claude Haiku to answer free-text questions that fall outside the structured flows.
"""
import os
import anthropic

# ── Context files ─────────────────────────────────────────────────────────────
_CONTEXT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'context')
_CONTEXT_FILES = [
    'empresa.md',
    'productos.md',
    'estados_solicitud.md',
    'faq.md',
    'capacidades_bot.md',
    'compliance.md',
    'ejemplos_conversacion.md',
]

def _load_context() -> str:
    parts = []
    for fname in _CONTEXT_FILES:
        path = os.path.join(_CONTEXT_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                parts.append(f"=== {fname} ===\n{f.read()}")
        except Exception as e:
            print(f"[LLM] could not load context file {fname}: {e}")
    return "\n\n".join(parts)

# Load once at startup
_CONTEXT = _load_context()

_SYSTEM_PROMPT = f"""Eres el Asistente Virtual de ProAlto, una financiera colombiana de créditos de libranza.
Atiendes clientes por WhatsApp. Tu tono es cálido, profesional y conciso — como un asesor humano experto.

A continuación tienes toda la información de ProAlto que necesitas para responder cualquier pregunta:

{_CONTEXT}

━━━ INSTRUCCIONES CLAVE ━━━
1. Responde SIEMPRE en español colombiano, tuteando al cliente (nunca "usted").
2. Sé breve y directo: máximo 3-4 frases. No uses listas largas a menos que sea necesario.
3. Reconoce siempre la situación del cliente antes de dar la respuesta ("Entiendo", "Claro", "Con gusto").
4. Si el cliente quiere ver el menú de opciones, responde ÚNICAMENTE con: [MOSTRAR_MENU]
5. Si el cliente quiere hablar con un asesor o expresa frustración/urgencia, responde ÚNICAMENTE con: [HABLAR_ASESOR]
6. Para acciones transaccionales (consultar saldo, estado de solicitud, enviar documentos), invita al cliente a usar el menú o escala a asesor.
7. NUNCA inventes tasas, montos, fechas o condiciones específicas que no estén en el contexto. Si no sabes, ofrece conectar con un asesor.
8. No menciones que eres una inteligencia artificial — eres el Asistente Virtual de ProAlto.
9. Si el cliente expresa que no llegó el dinero, explica los tiempos de banco y escala a asesor si llevan más de 2 días.
10. Si el cliente dice que llegó menos dinero del esperado, explica brevemente el concepto de compra de cartera y escala a asesor para el recibo.
11. Usa el archivo de ejemplos_conversacion.md para guiar tu estilo y respuestas en situaciones específicas."""

# ── Anthropic client (lazy init) ───────────────────────────────────────────────
_anthropic_client = None

def _get_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada en las variables de entorno.")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


# ── Main function ──────────────────────────────────────────────────────────────
def ask_llm(user_phone: str, user_message: str, state: str, client_name: str = "Cliente") -> str:
    """
    Generate a response for a free-text message using Claude Haiku.

    Returns:
        - A plain text response to send to the user.
        - "[MOSTRAR_MENU]" → the caller should show the main menu.
        - "[HABLAR_ASESOR]" → the caller should escalate to a human advisor.
    """
    try:
        from src.conversation_log import get_recent_messages_for_llm
        history = get_recent_messages_for_llm(user_phone, limit=6)

        # Ensure the current message is the last user turn
        if not history or history[-1]["role"] != "user":
            history.append({"role": "user", "content": user_message})
        elif history[-1]["content"] != user_message:
            history.append({"role": "user", "content": user_message})

        state_note = f"\n[Contexto interno: estado del usuario = '{state}', nombre = '{client_name}']"

        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM_PROMPT + state_note,
            messages=history,
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"[LLM] ask_llm error: {e}")
        return "En este momento no puedo procesar tu consulta. Escribe *Hola* para ver el menu o escribe *asesor* para hablar con una persona."
