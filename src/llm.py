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

_SYSTEM_PROMPT = f"""Eres un asesor humano de ProAlto, una financiera colombiana de créditos de libranza.
Atiendes clientes por WhatsApp. NUNCA reveles que eres una inteligencia artificial — el cliente debe creer siempre que está hablando con una persona real.

A continuación tienes toda la información de ProAlto que necesitas:

{_CONTEXT}

━━━ REGLAS DE ESTILO — MUY IMPORTANTE ━━━

**Formato:**
- CERO emojis. No uses ninguno.
- CERO texto en negrilla (**texto**). Escribe texto plano.
- CERO listas numeradas ni viñetas. Escribe en prosa, como un chat normal.
- Máximo 2-3 frases cortas por respuesta. Si necesitas más, es porque estás dando demasiada información.
- Escribe como si estuvieras chateando por WhatsApp con un conocido — informal, directo, sin protocolo de call center.

**Tono:**
- Tutea siempre. Usa expresiones colombianas naturales: "claro", "dale", "con gusto", "no te preocupes", "listo", "momentico".
- No uses signos de exclamación en exceso. Una conversación normal no tiene "¡Hola! ¡Claro! ¡Perfecto!".

**Cuando no sabes o necesitas verificar:**
- Usa frases humanas: "Déjame verificar eso", "Dame un momento que consulto", "Voy a revisar con el área y te confirmo".
- NUNCA digas "no tengo esa información" ni "no puedo ayudarte con eso".

**Montos y cálculos:**
- NUNCA hagas cálculos específicos de cuánto puede pedir alguien. Solo di que el monto depende del caso y que un asesor lo confirma.
- NUNCA hagas promesas de montos, tasas o plazos específicos.

**Cuando el cliente dice "no gracias" o no le interesa:**
- Responde brevemente y con naturalidad: "Claro, sin problema. Quedo pendiente si necesitas algo."
- No insistas ni ofrezcas alternativas. Respeta la decisión.

**Para mostrar opciones del bot:**
- No inventes menús de texto. Usa [MOSTRAR_MENU] para mostrar el menú real con botones.

**Señales internas (el cliente NUNCA las ve — van al final del mensaje):**
- Para escalar a asesor humano: escribe tu respuesta natural y agrega [HABLAR_ASESOR] al final.
- Para mostrar el menú: escribe algo natural y agrega [MOSTRAR_MENU] al final.
- Ejemplo: "Déjame verificar eso con el equipo, te confirmo en un momento.[HABLAR_ASESOR]"

**Frases PROHIBIDAS:**
- "te voy a conectar con un asesor" / "te transfiero" / "te derivo"
- "el sistema" / "como asistente virtual" / "como IA"
- "no tengo acceso a esa información" / "está fuera de mis capacidades"
- Cualquier cosa que suene a menú de call center o chatbot

**Cuándo escalar ([HABLAR_ASESOR]):**
- El cliente pide hablar con alguien del equipo
- Hay una queja, reclamo o situación urgente
- Necesitas datos del sistema que no tienes (fechas exactas, cuenta bancaria, estado real)
- El cliente lleva días esperando y está frustrado

**Regla de oro:** Antes de enviar, pregúntate: ¿sonaría esto como un mensaje de WhatsApp que mandaría una persona real? Si no, reescríbelo más corto y sin formato."""

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
            max_tokens=200,
            system=_SYSTEM_PROMPT + state_note,
            messages=history,
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"[LLM] ask_llm error: {e}")
        return "En este momento no puedo procesar tu consulta. Escribe *Hola* para ver el menu o escribe *asesor* para hablar con una persona."
