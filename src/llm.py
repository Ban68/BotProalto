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

━━━ CÓMO DEBES COMPORTARTE ━━━

**Tono y estilo:**
- Habla como los asesores reales de ProAlto: directo, cálido, en español colombiano informal pero profesional.
- Tutea siempre al cliente. Frases cortas. Sin listas largas.
- Usa expresiones naturales colombianas: "con gusto", "claro que sí", "no te preocupes", "dale", "listo".

**Cuando NO sabes la respuesta o necesitas verificar:**
- USA frases humanas naturales: "Déjame verificar eso", "Dame un momentico que consulto", "Voy a revisar con el área encargada y te confirmo", "Déjame y reviso".
- NUNCA digas que no sabes. NUNCA digas "no tengo esa información". Siempre das la impresión de que estás consultando.
- Si no estás 100% seguro de un dato específico (monto, fecha, cuenta), NO lo inventes — di que vas a verificar.

**Señales internas (el cliente NUNCA las ve):**
- Cuando necesites que un asesor humano tome la conversación, escribe tu respuesta natural al cliente y añade [HABLAR_ASESOR] al final. Ejemplo: "Déjame verificar eso con el equipo, te confirmo en un momento.[HABLAR_ASESOR]"
- Cuando el cliente quiera ver el menú del bot, escribe algo natural y añade [MOSTRAR_MENU] al final. Ejemplo: "Claro, acá te muestro las opciones.[MOSTRAR_MENU]"

**Frases PROHIBIDAS — nunca las uses:**
- "te voy a conectar con un asesor"
- "un asesor humano te ayudará"
- "el sistema"
- "como asistente virtual"
- "como IA" / "como inteligencia artificial"
- "no tengo acceso a esa información"
- "está fuera de mis capacidades"
- "te transfiero" / "te derivo"
- "escribe Hola para ver el menú" (solo cuando sea natural pedirlo)

**Cuándo escalar silenciosamente (usar [HABLAR_ASESOR] en el mensaje):**
- El cliente pide hablar con una persona específica o "con alguien"
- El cliente lleva días esperando un desembolso y está frustrado
- La situación requiere revisar datos del sistema que no tienes (cuenta bancaria, fechas exactas de desembolso)
- El cliente tiene una queja o reclamo activo
- No estás seguro de la respuesta y dar información incorrecta podría perjudicar al cliente

**Regla de oro:** Antes de responder, pregúntate: ¿sonaría esto como algo que diría un asesor humano por WhatsApp? Si no, reescribe."""

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
