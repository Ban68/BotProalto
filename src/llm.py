"""
LLM handler for ProAlto WhatsApp Bot.
Uses Claude Haiku to answer free-text questions that fall outside the structured flows.
"""
import os
import json
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

# Load status mapping for human-readable state labels
_STATUS_MAPPING_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src', 'status_mapping.json')
try:
    with open(_STATUS_MAPPING_PATH, 'r', encoding='utf-8') as f:
        _STATUS_MAPPING = json.load(f)
except Exception:
    _STATUS_MAPPING = {}

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
- SÍ puedes dar una referencia de monto: normalmente prestamos hasta el doble del salario sin necesidad de codeudor. Si el cliente te dice su salario, puedes hacer el cálculo como referencia.
- SIEMPRE aclara que es una referencia, no una aprobación: "como referencia podrías acceder hasta X, pero el monto final lo confirmamos después de revisar tu caso".
- NUNCA digas que está aprobado, que se aprueba automáticamente, ni hagas promesas de aprobación.
- NUNCA inventes tasas ni plazos específicos — para eso redirige al formulario o a un asesor.

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
- Hay una queja, reclamo o situación urgente que requiere gestión humana
- El cliente pregunta por el saldo exacto de lo que le falta por pagar (eso requiere verificación adicional)
- El cliente lleva días esperando y está frustrado
- Necesitas información que no tienes: cuenta bancaria, historial de pagos, datos de contacto de RRHH

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
def _build_client_context_note(user_phone: str, state: str, client_name: str) -> str:
    """Fetches real client data from the DB and builds the context note for the LLM."""
    try:
        from src.database import get_client_context_by_phone
        client_data = get_client_context_by_phone(user_phone)
    except Exception as e:
        print(f"[LLM] could not fetch client context: {e}")
        client_data = None

    base = f"[Contexto interno: estado = '{state}', nombre = '{client_name}']"

    if not client_data:
        return base + "\n[No se encontró solicitud activa para este número. Si el cliente pregunta por su caso específico, dile que no tienes su información registrada y pídele que revise si el número de WhatsApp que usa es el mismo que registró con ProAlto.]"

    estado_interno = client_data.get("estado_interno", "")
    estado_legible = _STATUS_MAPPING.get(estado_interno.upper(), estado_interno)
    valor = client_data.get("valor_preestudiado", 0)
    valor_fmt = f"${valor:,.0f}" if valor else "pendiente de evaluación"
    plazo = client_data.get("plazo")
    plazo_fmt = f"{plazo} meses" if plazo else "por definir"

    return f"""{base}

[DATOS REALES DEL CLIENTE — úsalos para responder directamente, sin pedir la cédula]:
- Nombre: {client_data.get('nombre_completo', client_name)}
- Solicitud #: {client_data.get('nro_solicitud', 'N/A')}
- Estado actual: {estado_legible}
- Monto preestudiado: {valor_fmt}
- Plazo: {plazo_fmt}
- Fecha de solicitud: {client_data.get('fecha_de_solicitud', 'N/A')}

Con estos datos puedes responder directamente sobre el estado de la solicitud.
Para el saldo de créditos activos (cuánto le falta por pagar) necesitas verificación adicional — escala con [HABLAR_ASESOR]."""


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

        state_note = "\n" + _build_client_context_note(user_phone, state, client_name)

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
        return "[HABLAR_ASESOR]"
