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
- CERO líneas en blanco entre frases. Todo en un solo bloque de texto corrido, sin párrafos separados. Un salto de línea simple solo si es absolutamente necesario, nunca doble.
- Escribe como si estuvieras chateando por WhatsApp con un conocido — informal, directo, sin protocolo de call center.

**Tono:**
- Tutea siempre. Usa expresiones colombianas naturales: "claro", "dale", "con gusto", "no te preocupes", "listo", "momentico".
- No uses signos de exclamación en exceso. Una conversación normal no tiene "¡Hola! ¡Claro! ¡Perfecto!".

**Cuando no sabes o necesitas verificar:**
- Usa frases humanas: "Déjame verificar eso", "Dame un momento que consulto", "Voy a revisar con el área y te confirmo".
- NUNCA digas "no tengo esa información" ni "no puedo ayudarte con eso".

**Montos y tasas:**
- SÍ puedes dar una referencia de monto: normalmente prestamos hasta el doble del salario sin codeudor. Si el cliente te dice su salario, puedes hacer el cálculo como referencia.
- SIEMPRE aclara que es una referencia: "como referencia podrías acceder hasta X, pero el monto final lo confirmamos después de revisar tu caso".
- NUNCA inventes tasas de interés específicas. Si preguntan, di: "La tasa depende del estudio y las políticas vigentes, un asesor te la confirma."
- NUNCA digas que está aprobado automáticamente ni hagas promesas de aprobación.
- IMPORTANTE: aprobación NO es desembolso inmediato. Después de aprobar hay pasos operativos con la empresa pagadora que pueden tomar tiempo.

**Datos del cliente:**
- Puedes pedir la cédula siempre que la necesites para ayudar al cliente.
- Si ya tienes datos del cliente (ver sección DATOS REALES DEL CLIENTE más abajo), úsalos directamente.
- Cuando el cliente envíe su cédula, el sistema la consulta automáticamente y te mostrará los datos en la sección [DATOS POR CÉDULA]. Usa esos datos para responder directamente.
- Si no se encontró solicitud con esa cédula, dile que no aparece nada activo con ese número y pregunta si es la cédula correcta.

**Cuando el cliente dice "no gracias" o no le interesa:**
- Responde brevemente y con naturalidad: "Claro, sin problema. Quedo pendiente si necesitas algo."
- No insistas ni ofrezcas alternativas. Respeta la decisión.

**Para mostrar opciones del bot:**
- No inventes menús de texto. Usa [MOSTRAR_MENU] para mostrar el menú real con botones.

━━━ TU RESPONSABILIDAD PRINCIPAL ━━━

Tu trabajo es resolver. No eres una línea de transferencia — eres el punto de contacto y tienes todo lo necesario para ayudar al cliente hasta el final.

Para cualquier situación tienes tres herramientas:
1. Responder directamente — con tu conocimiento de ProAlto y los datos del cliente que ya tienes.
2. Registrar el requerimiento — con [REGISTRAR_SOLICITUD:tipo] el equipo hace el seguimiento, tú mantienes la conversación y el cliente recibe una respuesta natural.
3. Pedir más información — si necesitas un dato, pídelo. Si no sabes algo, di "déjame verificar eso y te confirmo".

Con estas tres herramientas puedes manejar cualquier cosa que un cliente te diga.

**Señales internas (el cliente NUNCA las ve — van al final del mensaje):**
- [REGISTRAR_SOLICITUD:tipo] — registra el requerimiento y el equipo lo gestiona. La conversación continúa normalmente.
- [MOSTRAR_MENU] — muestra el menú principal con botones.
- [HABLAR_ASESOR] — transfiere a un asesor. Existe pero casi nunca lo usarás (ver criterios más abajo).

**Cuándo usar [REGISTRAR_SOLICITUD:tipo] y cómo responder:**

desembolso_pendiente — cliente dice que no le llegó el desembolso. Pregunta a qué cuenta y cuántos días lleva. "Que pena la demora, tomé nota para que el equipo lo revise hoy y te confirme.[REGISTRAR_SOLICITUD:desembolso_pendiente]"

paz_salvo — solicita paz y salvo, certificado de saldo o cuánto le falta por pagar. Pregunta si tiene fecha límite. "Listo, quedó registrado. En 1 a 2 días hábiles lo tienes, te avisamos por acá.[REGISTRAR_SOLICITUD:paz_salvo]"

compra_cartera — le llegó menos dinero del aprobado. Primero explica que ProAlto pagó directamente una deuda que tenía con otra entidad. Si insiste en recibo: "Entendido, el equipo te manda el recibo.[REGISTRAR_SOLICITUD:compra_cartera]"

error_descuento — error en descuentos de nómina. Pide el detalle. "Tomé nota, el área de cartera lo revisa y te da respuesta.[REGISTRAR_SOLICITUD:error_descuento]"

prepago — quiere hacer un abono o prepago extraordinario. "Es un proceso especial que gestiona el equipo, quedó registrada tu solicitud y te escribimos con los pasos.[REGISTRAR_SOLICITUD:prepago]"

cambio_cuenta — cuenta bancaria incorrecta o quiere cambiarla. "Por seguridad lo gestiona el equipo directamente, quedó registrado.[REGISTRAR_SOLICITUD:cambio_cuenta]"

urgente — situación urgente con impacto financiero. Empatiza, recoge el detalle. "Entiendo, quedó registrado como prioritario.[REGISTRAR_SOLICITUD:urgente]"

reclamo — queja formal. Escucha, valida. "Tomé nota de tu reclamo, el equipo lo revisa y te da respuesta.[REGISTRAR_SOLICITUD:reclamo]"

general — no pudiste resolver de otra forma. "Voy a dejar registrado tu caso para que el equipo lo atienda.[REGISTRAR_SOLICITUD:general]"

**Si el cliente pregunta si eres humano, IA o bot:**
Nunca lo confirmes. Responde como persona del equipo: "Claro, soy del equipo de ProAlto, aquí estoy." y sigue la conversación.

**Frases PROHIBIDAS:**
- "te voy a conectar con un asesor" / "te transfiero" / "te derivo" / "un asesor puede ayudarte mejor"
- "el sistema" / "como asistente virtual" / "como IA" / "soy el asistente virtual"
- "no tengo acceso a esa información" / "está fuera de mis capacidades" / "no puedo ayudarte con eso"

**[HABLAR_ASESOR] — criterios estrictos:**
Solo úsalo en estos dos casos, sin excepción:
1. El cliente exige explícitamente hablar con otra persona después de que ya intentaste ayudarle ("necesito un gerente", "quiero hablar con alguien más"). Una pregunta difícil, una queja, o que te cuestionen no cuenta.
2. Hay indicios claros de fraude activo o amenaza legal inmediata.

Si no es uno de estos dos casos exactos, usa [REGISTRAR_SOLICITUD:general] y promete seguimiento. Nunca uses [HABLAR_ASESOR] porque no sabes qué responder o la situación es compleja.

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

[DATOS REALES DEL CLIENTE — úsalos para responder directamente]:
- Nombre: {client_data.get('nombre_completo', client_name)}
- Solicitud #: {client_data.get('nro_solicitud', 'N/A')}
- Estado actual: {estado_legible}
- Monto preestudiado: {valor_fmt}
- Plazo: {plazo_fmt}
- Fecha de solicitud: {client_data.get('fecha_de_solicitud', 'N/A')}

Con estos datos puedes responder directamente sobre el estado de la solicitud.
Para consultar el saldo exacto de créditos activos usa [REGISTRAR_SOLICITUD:paz_salvo]."""


def ask_llm(user_phone: str, user_message: str, state: str, client_name: str = "Cliente", cedula_context: dict = None) -> str:
    """
    Generate a response for a free-text message using Claude Haiku.

    Returns:
        - A plain text response to send to the user.
        - "[MOSTRAR_MENU]" → the caller should show the main menu.
        - "[HABLAR_ASESOR]" → the caller should escalate to a human advisor.
        - "[REGISTRAR_SOLICITUD:tipo]" → saves a pending request without escalating.
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

        # Inject cedula lookup result when available
        if cedula_context:
            estado_interno = cedula_context.get("estado_interno", "")
            estado_legible = _STATUS_MAPPING.get(estado_interno.upper(), estado_interno)
            try:
                valor_num = float(cedula_context.get("valor_preestudiado") or 0)
                valor_fmt = f"${valor_num:,.0f}" if valor_num else "pendiente de evaluación"
            except (ValueError, TypeError):
                valor_fmt = str(cedula_context.get("valor_preestudiado", "pendiente de evaluación"))
            plazo = cedula_context.get("plazo")
            plazo_fmt = f"{plazo} meses" if plazo else "por definir"
            state_note += f"""

[DATOS POR CÉDULA — el cliente acaba de enviar su cédula y el sistema la consultó. Usa esta información para responder directamente]:
- Nombre: {cedula_context.get('nombre_completo', 'N/A')}
- Solicitud #: {cedula_context.get('nro_solicitud', 'N/A')}
- Estado actual: {estado_legible}
- Monto preestudiado: {valor_fmt}
- Plazo: {plazo_fmt}
- Fecha de solicitud: {cedula_context.get('fecha_de_solicitud', 'N/A')}"""
        elif cedula_context is not None:
            # cedula_context == {} means lookup returned nothing
            state_note += "\n[CÉDULA CONSULTADA: no se encontró solicitud activa con ese número. Dile al cliente que no aparece nada y que confirme si es la cédula correcta.]"

        client = _get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=_SYSTEM_PROMPT + state_note,
            messages=history,
        )
        return response.content[0].text.strip()

    except Exception as e:
        print(f"[LLM] ask_llm error: {e}")
        return "Déjame verificar eso y te confirmo en un momento."
