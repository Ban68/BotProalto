from src.services import WhatsAppService
from src.database import get_solicitud_status, get_saldo
from src.google_sheets import get_solicitud_reciente_sheet, get_anticipo_by_cedula
from src.conversation_log import log_message, set_agent_mode, get_user_state, set_user_state, get_client_name, set_client_name, log_received_document, count_received_documents, get_last_campaign_template
from src.notifications import notify_admin_agent_request, notify_admin_error, notify_admin_contact_update, notify_admin_cedula_mismatch
from src import referrals_ab
import os
import json
import re
import threading

# ── LLM thread deduplication ─────────────────────────────────────────────────
# Prevents multiple simultaneous LLM responses when the client sends rapid
# messages (e.g., 3 messages in 2 seconds → 3 threads → 3 bot replies).
# Only one LLM thread per phone can run at a time; subsequent messages are
# queued and only the latest is processed after the current one finishes.
_llm_active: dict[str, bool] = {}
_llm_pending: dict[str, str] = {}  # stores latest pending message per phone
_llm_lock = threading.Lock()

# ── Document confirmation debounce ───────────────────────────────────────────
# Waits DOC_CONFIRM_DELAY seconds after the last document before sending the
# final confirmation, so the client has time to attach all their files.
DOC_CONFIRM_DELAY = 60  # seconds
_doc_timers: dict[str, threading.Timer] = {}
_doc_timers_lock = threading.Lock()


def _send_doc_confirmation(user_phone: str):
    """Fires after debounce delay to send the final confirmation message."""
    with _doc_timers_lock:
        _doc_timers.pop(user_phone, None)
    WhatsAppService.send_message(
        user_phone,
        "✅ Perfecto, gracias. Nuestro equipo revisará los documentos que enviaste y te contactaremos pronto."
    )


def _schedule_doc_confirmation(user_phone: str):
    """Cancels any pending timer and schedules a fresh one (debounce)."""
    with _doc_timers_lock:
        existing = _doc_timers.pop(user_phone, None)
        if existing:
            existing.cancel()
        t = threading.Timer(DOC_CONFIRM_DELAY, _send_doc_confirmation, args=[user_phone])
        t.daemon = True
        t.start()
        _doc_timers[user_phone] = t

# Pre-load status mapping for optimization throughout the lifecycle
MAPPING_PATH = os.path.join(os.path.dirname(__file__), 'status_mapping.json')
try:
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        STATUS_MESSAGES = json.load(f)
except Exception as e:
    print(f"Error loading status mapping: {e}")
    STATUS_MESSAGES = {}

# Pre-load denegado-reason mapping (estado_interno = DENEGADO + columna opc_negadas).
# Keys are normalized (upper-case, single-spaced) versions of the option the asesor
# selects in el software. Si opc_negadas viene vacío o con un valor desconocido,
# el flujo cae al mensaje genérico de DENEGADO en STATUS_MESSAGES.
NEGADAS_PATH = os.path.join(os.path.dirname(__file__), 'negadas_mapping.json')
try:
    with open(NEGADAS_PATH, 'r', encoding='utf-8') as f:
        NEGADAS_MESSAGES = json.load(f)
except Exception as e:
    print(f"Error loading negadas mapping: {e}")
    NEGADAS_MESSAGES = {}


def _normalize_opc_negadas(value):
    """Normaliza el valor de opc_negadas para hacer match con NEGADAS_MESSAGES:
    mayúsculas, sin espacios extra. Devuelve '' si no hay valor."""
    if not value:
        return ""
    return " ".join(str(value).upper().split())


def _denegado_reason_message(opc_negadas):
    """Devuelve el mensaje específico de negación según opc_negadas, o None si
    no hay un motivo reconocido (el caller cae al mensaje genérico de DENEGADO)."""
    return NEGADAS_MESSAGES.get(_normalize_opc_negadas(opc_negadas))


def _send_denegado_reason(user_phone):
    """Envía al cliente el motivo concreto por el que se negó su crédito, usando
    la MISMA lógica que el estado interno DENEGADO (opc_negadas → NEGADAS_MESSAGES).
    Se dispara desde el botón "Consultar motivo" del template estado_negados.
    Como ese template no traía la cédula, resolvemos opc_negadas por teléfono
    (última solicitud). Si no hay motivo reconocido, cae al mensaje genérico."""
    from src.database import get_client_context_by_phone
    ctx = get_client_context_by_phone(user_phone) or {}
    msg = _denegado_reason_message(ctx.get("opc_negadas"))
    if not msg:
        msg = STATUS_MESSAGES.get(
            "DENEGADO",
            "Lamentamos informarte que tu crédito no fue aprobado porque no se "
            "cumplen los requisitos mínimos de nuestras políticas de pago. Por "
            "ahora no podemos otorgarte este préstamo.",
        )
    nombre = ctx.get("nombre_completo") or get_client_name(user_phone)
    if nombre:
        set_client_name(user_phone, nombre)
    WhatsAppService.send_message(user_phone, msg)
    set_user_state(user_phone, "active")
    WhatsAppService.send_message(user_phone, "Necesitas algo más? Escribe 'Hola' para ver el menú.")


def _send_referrals_ab_info(user_phone: str):
    WhatsAppService.send_interactive_button(
        user_phone,
        referrals_ab.info_text_for_phone(user_phone),
        [
            {"id": "referidos_quiero_beneficio", "title": "Quiero el beneficio"},
            {"id": "referidos_quizas_despues", "title": "Quizás después"},
        ],
    )
    referrals_ab.record_event(user_phone, "info_sent", "referidos_info")


def _handle_referrals_ab_button(user_phone: str, btn_id: str, state: str) -> bool:
    explicit_referral_id = str(btn_id or "").startswith("referidos_")
    if not referrals_ab.is_referral_prompt_state(state) and not explicit_referral_id:
        return False

    kind = referrals_ab.button_kind(btn_id)
    if not kind:
        return False

    referrals_ab.record_button_click(user_phone, btn_id, kind)

    if kind == "info":
        set_user_state(user_phone, referrals_ab.STATE_INFO_SENT)
        _send_referrals_ab_info(user_phone)
        return True

    if kind == "benefit":
        set_user_state(user_phone, referrals_ab.STATE_WAITING_NAME)
        referrals_ab.record_event(user_phone, "capture_started", "referidos_capture")
        WhatsAppService.send_message(user_phone, referrals_ab.ASK_NAME_TEXT)
        return True

    if kind == "later":
        set_user_state(user_phone, "active")
        referrals_ab.record_event(user_phone, "declined", "quizas_despues")
        WhatsAppService.send_message(user_phone, referrals_ab.LATER_TEXT)
        return True

    return False


def _is_greeting(text: str) -> bool:
    """Check if text looks like a greeting (used in multiple states to allow menu escape)."""
    norm = text.lower().strip()
    first_word = norm.split()[0] if norm else ""
    for ch in ",.:!?¿¡":
        first_word = first_word.replace(ch, "")
    greetings = {"hola", "menu", "menú", "inicio", "start", "buenas", "holis", "holi",
                 "saludos", "hi", "hello", "buen", "buenos", "ola", "hol", "hla",
                 "hl", "holaa", "holaaaa", "holaaa", "alo", "hey"}
    phrases = {"buenos dias", "buenos días", "buenas tardes", "buenas noches",
               "buen dia", "buen día", "que tal", "q tal"}
    return first_word in greetings or norm in phrases


def _is_advisor_request(text: str) -> bool:
    """Check if user is explicitly asking to talk to a human advisor."""
    norm = text.lower().strip()
    # Remove punctuation for better matching
    for char in ".,!?¿¡;:":
        norm = norm.replace(char, "")

    patterns = [
        "hablar con un asesor", "hablar con asesor", "hablar asesor",
        "contactar asesor", "contactar con asesor", "contactarme con un asesor",
        "contactarme con asesor", "necesito un asesor", "necesito asesor",
        "quiero hablar con alguien", "quiero un asesor", "quiero asesor",
        "pasame con un asesor", "pásame con un asesor",
        "comunicarme con un asesor", "comunicarme con asesor",
        "conectarme con un asesor", "conectarme con asesor",
        "hablar con una persona", "persona real", "agente humano", "asesor humano",
        "hablar con alguien", "contactar un asesor", "conectar asesor",
        "quiero hablar con asesor", "necesito hablar con asesor",
    ]
    return any(p in norm for p in patterns)


# msg_type value used to tag LLM-generated outbound messages in the DB
# The admin panel reads this to show the 🤖 indicator — clients never see it
_LLM_MSG_TYPE = "llm"


_DEAD_END_PHRASES = [
    "déjame verificar", "dejame verificar", "déjame revisar", "dejame revisar",
    "déjame consultar", "dejame consultar", "dame un momento", "dame un momentico",
    "voy a revisar", "voy a consultar", "voy a verificar",
    "un momentico", "un momento que", "espérame un momento", "esperame un momento",
    "deja y reviso", "deja y consulto",
]


def _process_llm_signals(llm_response: str) -> tuple:
    """
    Strip ALL signal tags from the LLM response and return (clean_text, signals).
    Signals is a dict with keys: hablar_asesor, mostrar_menu, registrar_solicitud.
    This prevents tags from leaking to WhatsApp when the LLM uses multiple tags.
    Also patches dead-end responses (no tag + vague promise) with a safety net.
    """
    signals = {}

    if "[HABLAR_ASESOR]" in llm_response:
        signals["hablar_asesor"] = True
        llm_response = llm_response.replace("[HABLAR_ASESOR]", "")

    if "[MOSTRAR_MENU]" in llm_response:
        signals["mostrar_menu"] = True
        llm_response = llm_response.replace("[MOSTRAR_MENU]", "")

    match = re.search(r'\[REGISTRAR_SOLICITUD:([^\]]+)\]', llm_response)
    if match:
        signals["registrar_solicitud"] = match.group(1).strip()
        llm_response = re.sub(r'\[REGISTRAR_SOLICITUD:[^\]]+\]', '', llm_response)

    # Strip ANY remaining bracket tags the LLM may have hallucinated
    # (e.g. [CONSULTAR_CEDULA:xxx], [CÉDULA_CONSULTADA:xxx], [DATOS POR CÉDULA], etc.)
    # This prevents internal tags and PII from leaking to client messages.
    llm_response = re.sub(r'\[[A-ZÁÉÍÓÚÑ_ ]+(?::[^\]]*)?\]', '', llm_response)

    # Clean up artifacts: leftover pipes, double spaces, leading/trailing whitespace
    clean = re.sub(r'\s*\|\s*', ' ', llm_response).strip()
    clean = re.sub(r'  +', ' ', clean)

    # Safety net: if no signals and response is a dead-end promise, force registration
    if not signals:
        lower = clean.lower()
        if any(phrase in lower for phrase in _DEAD_END_PHRASES):
            signals["registrar_solicitud"] = "general"
            clean = clean.rstrip(".") + ", tomé nota y lo revisamos."
            print(f"[LLM] Dead-end safety net triggered: '{llm_response[:60]}...'")

    return clean, signals


# Tipos de REGISTRAR_SOLICITUD que son solicitudes de documentos: van al panel
# de documentos (document_requests), separado de las solicitudes LLM para que
# no se pierdan. Hoy solo paz y salvo; agregar aquí futuros tipos de documento.
DOC_REQUEST_TIPOS = {"paz_salvo"}


def registrar_solicitud_llm(user_phone: str, client_name: str, tipo: str, detalle: str):
    """Enruta una señal REGISTRAR_SOLICITUD del agente LLM: los tipos de
    documento van a document_requests, el resto a llm_requests."""
    if tipo in DOC_REQUEST_TIPOS:
        from src.conversation_log import save_document_request
        from src.notifications import notify_admin_document_request
        save_document_request(user_phone, client_name, tipo, source="llm", detalle=detalle)
        notify_admin_document_request(user_phone, tipo, source="llm")
    else:
        from src.conversation_log import save_llm_request
        from src.notifications import notify_admin_llm_request
        save_llm_request(user_phone, client_name, tipo, detalle)
        notify_admin_llm_request(user_phone, tipo)


def _launch_llm_agent(user_phone: str, text: str):
    """
    Safe launcher for LLM agent. Deduplicates rapid messages from the same
    phone so only one LLM call runs at a time. If a call is already in
    progress, the new message replaces the pending queue (only latest matters).
    """
    with _llm_lock:
        if _llm_active.get(user_phone):
            # Thread already running — queue the latest message, skip thread launch
            _llm_pending[user_phone] = text
            print(f"[LLM-BG] DEDUP: {user_phone} already active, queued: '{text[:40]}...'")
            return
        _llm_active[user_phone] = True

    t = threading.Thread(target=_handle_llm_agent, args=[user_phone, text], daemon=True)
    t.start()


def _handle_llm_agent(user_phone: str, text: str):
    """
    Background worker for LLM agent mode.
    Runs Cloud Run API lookups + LLM call outside the webhook request
    so WhatsApp doesn't timeout waiting for a response.
    """
    import time as _time
    t0 = _time.time()
    print(f"[LLM-BG] START for {user_phone}: '{text[:40]}...'")
    try:
        from src.llm import ask_llm
        from concurrent.futures import ThreadPoolExecutor
        client_name = get_client_name(user_phone)

        # If message looks like a cedula, look it up and pass result to LLM
        cedula_context = None
        saldo_context = None
        if text.strip().isdigit() and 6 <= len(text.strip()) <= 12:
            cedula_num = text.strip()
            # Run both Cloud Run API calls in parallel to save time
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_solicitud = pool.submit(get_solicitud_status, cedula_num)
                fut_saldo = pool.submit(get_saldo, cedula_num)
                result = fut_solicitud.result(timeout=50)
                saldo_result = fut_saldo.result(timeout=50)
            t1 = _time.time()
            print(f"[LLM-BG] Cloud Run calls done in {t1-t0:.1f}s")

            if result is None:
                cedula_context = {"_error": True}
                print(f"[LLM-BG] Cedula {cedula_num}: solicitud API ERROR")
            elif result:
                cedula_context = result
                print(f"[LLM-BG] Cedula {cedula_num}: solicitud FOUND")
            else:
                cedula_context = {}
                print(f"[LLM-BG] Cedula {cedula_num}: solicitud NOT FOUND")

            if saldo_result is None:
                saldo_context = "error"
                print(f"[LLM-BG] Cedula {cedula_num}: saldo API ERROR")
            elif saldo_result:
                saldo_context = saldo_result
                print(f"[LLM-BG] Cedula {cedula_num}: saldo FOUND ({len(saldo_result)} loans)")
            else:
                saldo_context = []
                print(f"[LLM-BG] Cedula {cedula_num}: saldo NOT FOUND")

        t_llm_start = _time.time()
        print(f"[LLM-BG] Calling LLM for {user_phone}...")
        llm_response = ask_llm(user_phone, text, "agent_llm", client_name,
                               cedula_context=cedula_context,
                               saldo_context=saldo_context)
        t_llm_end = _time.time()
        print(f"[LLM-BG] LLM responded in {t_llm_end-t_llm_start:.1f}s")

        if not llm_response:
            print(f"[LLM-BG] No response for {user_phone}, staying silent")
            return

        human_msg, signals = _process_llm_signals(llm_response)

        if signals:
            if human_msg:
                WhatsAppService.send_message(user_phone, human_msg, msg_type=_LLM_MSG_TYPE)

            if "registrar_solicitud" in signals:
                registrar_solicitud_llm(user_phone, client_name, signals["registrar_solicitud"], text)

            if signals.get("hablar_asesor"):
                set_agent_mode(user_phone, "agent")
                notify_admin_agent_request(user_phone)
            elif signals.get("mostrar_menu"):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
        else:
            WhatsAppService.send_message(user_phone, llm_response, msg_type=_LLM_MSG_TYPE)

        print(f"[LLM-BG] DONE for {user_phone} in {_time.time()-t0:.1f}s total")

    except Exception as e:
        print(f"[LLM-BG] ERROR for {user_phone} after {_time.time()-t0:.1f}s: {e}")
    finally:
        # Release lock and check for pending messages
        with _llm_lock:
            pending_text = _llm_pending.pop(user_phone, None)
            if pending_text:
                # Process the queued message (only the latest one)
                print(f"[LLM-BG] Processing pending message for {user_phone}: '{pending_text[:40]}...'")
                # Keep _llm_active[user_phone] = True, recurse
            else:
                _llm_active.pop(user_phone, None)

        if pending_text:
            _handle_llm_agent(user_phone, pending_text)


# ── Status messages map (used by both waiting_for_cedula and choice handlers) ─
def _render_credito_result(user_phone, result):
    """Builds and sends the response for a crédito ordinario lookup, and sets the
    appropriate next state. Extracted so it can be called both from the cédula
    flow and from the disambiguation choice flow."""
    estado_interno = result['estado_interno']
    clean_status = estado_interno.strip().upper() if estado_interno else "NULL"
    mensaje_cliente = STATUS_MESSAGES.get(clean_status, estado_interno or "Pendiente / En Estudio")

    monto = result['valor_preestudiado']
    nombre = result['nombre_completo']
    fecha = result['fecha_de_solicitud']
    plazo = result.get('plazo')
    cuota = result.get('cuota')
    frecuencia = result.get('frecuencia', '')

    response_msg = (
        f"🔍 *Resultado de Solicitud*\n\n"
        f"👤 *Cliente:* {nombre}\n"
        f"📅 *Fecha:* {fecha}\n"
    )

    statuses_no_monto = [
        "REVISAR NUEVAMENTE",
        "FALTA ALGÚN DOCUMENTO",
        "EMPRESA PAUSADA",
        "DENEGADO",
        "CANCELADO POR LA EMPRESA",
        "DESISTIÓ DEL CRÉDITO",
        "NO RESPONDIÓ",
    ]

    if clean_status not in statuses_no_monto:
        monto_label = "Monto Solicitado" if clean_status in ("ENVIADO A VB EMPRESA", "PENDIENTE POR ENVIAR A VB") else "Monto Aprobado"
        response_msg += f"💰 *{monto_label}:* ${monto:,.0f}\n"

    if clean_status in ["APROBADO POR EL CLIENTE", "LISTO PARA HACERLE DOCUMENTACIÓN"]:
        if plazo:
            plazo_label = f"{plazo} cuotas {frecuencia}".strip() if frecuencia else f"{plazo} cuotas"
            response_msg += f"⏱️ *Plazo:* {plazo_label}\n"
        if cuota:
            cuota_fmt = f"${cuota:,.0f}".replace(",", ".") if isinstance(cuota, (int, float)) else str(cuota)
            response_msg += f"💳 *Cuota:* {cuota_fmt}\n"
        response_msg += f"📋 *Estado:* {mensaje_cliente}\n"

        WhatsAppService.send_message(user_phone, response_msg)
        set_client_name(user_phone, nombre)
        _ask_aprobado_choice(user_phone)
        return

    if clean_status == "FALTA ALGÚN DOCUMENTO":
        from src.automation import build_docs_message
        from src.conversation_log import set_solicitud_context
        docs_faltantes = result.get("documentos_faltantes", "")
        tipo_empleador = result.get("tipo_empleador", "EMPRESA")
        set_client_name(user_phone, nombre)
        set_solicitud_context(user_phone, result.get("empresa", ""), docs_faltantes, tipo_empleador)
        set_user_state(user_phone, "waiting_for_docs_rojo")
        docs_part = build_docs_message(docs_faltantes, tipo_empleador)
        combined = (
            response_msg
            + "📋 *Estado:* Tu proceso está detenido porque te faltan los siguientes documentos:\n\n"
            + docs_part.split("\n\n", 1)[1]
        )
        WhatsAppService.send_message(user_phone, combined)
        log_message(user_phone, "outbound", "[Menu: estado_rojo]", "text")
        return

    # Denegado con motivo específico: la columna opc_negadas indica por qué no se
    # aprobó. Mostramos el mensaje concreto en lugar del genérico. Si no hay motivo
    # reconocido, caemos al mensaje neutro de abajo (STATUS_MESSAGES["DENEGADO"]).
    if clean_status == "DENEGADO":
        neg_msg = _denegado_reason_message(result.get("opc_negadas"))
        if neg_msg:
            set_client_name(user_phone, nombre)
            WhatsAppService.send_message(user_phone, neg_msg)
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, "Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

    # Estado neutro: mostrar y volver a "active"
    response_msg += f"📋 *Estado:* {mensaje_cliente}\n"
    WhatsAppService.send_message(user_phone, response_msg)
    set_user_state(user_phone, "active")
    WhatsAppService.send_message(user_phone, "Necesitas algo más? Escribe 'Hola' para ver el menú.")


def _render_anticipo_result(user_phone, anticipo):
    """Responde sobre el estado del anticipo de salario combinando dos columnas
    del Sheet:
      - 'Estado'         → decisión: Aprobado / Denegado / (vacío = en estudio)
      - 'Estado Interno' → etapa operativa: Listo para llamar, Listo en panda,
                           Listo para documentación, Desprendible, Desembolsado.
    Prioridad: Estado Interno (más específico) sobre Estado (más general)."""
    nombre = (anticipo.get("nombre_completo") or "").strip()
    fecha = (anticipo.get("fecha_de_solicitud") or "").strip()
    estado_apr = (anticipo.get("estado") or "").strip().upper()
    estado_int = (anticipo.get("estado_interno") or "").strip().upper()

    saludo = f"Hola {nombre.split()[0]}, " if nombre else ""
    fecha_txt = f" el {fecha}" if fecha else ""
    header = "🔍 *Resultado de Solicitud*"
    cierre_default = "Necesitas algo más? Escribe 'Hola' para ver el menú."

    # 1. Estado Interno tiene la información operativa más útil
    if "DESEMBOLSADO" in estado_int:
        body = (
            f"{saludo}tu anticipo de salario ya fue *desembolsado*. "
            f"Si no has visto el dinero en tu cuenta, escríbenos para revisarlo."
        )
        next_msg = cierre_default
    elif "DESPRENDIBLE" in estado_int:
        body = (
            f"{saludo}tu solicitud de anticipo está pendiente porque nos falta tu *último desprendible de pago*. "
            f"Puedes enviárnoslo por este chat para continuar."
        )
        next_msg = "Cuando lo envíes, lo revisamos. Si necesitas algo más, escribe 'Hola' para ver el menú."
    elif "PANDA" in estado_int or "DOCUMENTACI" in estado_int:
        body = (
            f"{saludo}tu anticipo de salario fue *aprobado* y estamos preparando el contrato para firma. "
            f"Te avisaremos cuando esté listo para firmar."
        )
        next_msg = cierre_default
    elif "LLAMAR" in estado_int:
        body = (
            f"{saludo}tu anticipo de salario fue *aprobado*. Un asesor te contactará pronto para terminar el proceso."
        )
        next_msg = cierre_default
    # 2. Si Estado Interno está vacío, caemos a Estado (Aprobado / Denegado)
    elif "DENEGADO" in estado_apr:
        body = (
            f"{saludo}tu solicitud de anticipo fue revisada y no fue viable en esta ocasión. "
            f"Si quieres más detalle, un asesor te puede atender."
        )
        next_msg = cierre_default
    elif "APROBADO" in estado_apr:
        body = (
            f"{saludo}tu anticipo de salario fue *aprobado*. "
            f"Estamos coordinando los siguientes pasos, te avisamos por este medio apenas tengamos novedad."
        )
        next_msg = cierre_default
    # 3. Ninguno de los dos campos tiene valor → recién radicada
    else:
        body = (
            f"{saludo}hemos recibido tu solicitud de anticipo de salario{fecha_txt}. "
            f"Actualmente se encuentra *En Estudio*.\n\n"
            f"Te avisaremos por este medio apenas tengamos novedad."
        )
        next_msg = cierre_default

    WhatsAppService.send_message(user_phone, f"{header}\n\n{body}")
    set_user_state(user_phone, "active")
    WhatsAppService.send_message(user_phone, next_msg)


def _ask_aprobado_choice(user_phone):
    """Tras mostrar el estado APROBADO POR EL CLIENTE, ofrece dos opciones:
    enviar el correo para el contrato, o expresar dudas sobre el valor aprobado.
    Los botones los maneja process_button_click, así que el estado vuelve a 'active'."""
    WhatsAppService.send_interactive_button(
        user_phone,
        "Para enviarte el contrato para firma necesitamos tu correo. ¿Cómo quieres seguir?",
        [
            {"id": "aprobado_enviar_correo", "title": "Enviar correo"},
            {"id": "aprobado_dudas_valor", "title": "Tengo dudas"},
        ]
    )
    set_user_state(user_phone, "active")


def _proceed_to_aprobado_email(user_phone):
    """Continúa el proceso de envío de contrato: si ya hay correo guardado lo
    confirma, si no lo pide. El nombre del cliente ya se guardó al mostrar el estado."""
    from src.conversation_log import get_email_for_phone
    existing_email = get_email_for_phone(user_phone)

    if existing_email:
        WhatsAppService.send_message(
            user_phone,
            f"📧 En breve te llegará el contrato para firma electrónica al correo *{existing_email}*.\n\n"
            "Estamos trabajando en tu proceso. ¡Pronto tendrás noticias!"
        )
        set_user_state(user_phone, "active")
    else:
        instruction_msg = (
            "⚠️ *ACCIÓN NECESARIA*\n\n"
            "Para continuar con tu desembolso, por favor *CONFÍRMANOS TU CORREO ELECTRÓNICO* 📧 escribiéndolo a continuación.\n\n"
            "_Lo necesitamos para enviarte el contrato para firma electrónica._"
        )
        WhatsAppService.send_message(user_phone, instruction_msg)
        set_user_state(user_phone, "waiting_for_email")


def _ask_solicitud_choice(user_phone, cedula):
    """Sends the two-button disambiguation prompt and parks the state with the cédula."""
    WhatsAppService.send_interactive_button(
        user_phone,
        "Vemos que tienes dos solicitudes activas: una de crédito ordinario y una de anticipo de salario.\n\n¿Sobre cuál quieres consultar?",
        [
            {"id": "choice_credito", "title": "Crédito ordinario"},
            {"id": "choice_anticipo", "title": "Anticipo de salario"},
        ]
    )
    set_user_state(user_phone, f"waiting_for_solicitud_choice|{cedula}")


# ── Yearly contact-data update flow ──────────────────────────────────────────
# Block of text that mirrors the approved Meta template content, used when
# the flow is triggered from the menu (or as a follow-up) — that is, within
# the 24h session window where templates are not needed.
CONTACT_UPDATE_INTRO_TEXT = (
    "¡Hola! 👋\n\n"
    "En FINANCIERA PROALTO SAS queremos seguir brindándote el mejor servicio.\n\n"
    "Le recordamos que, de acuerdo con la Cláusula Tercera de su contrato y lo "
    "ratificado en la Cláusula Vigésima Quinta, es su obligación contractual "
    "realizar la actualización de sus datos personales anualmente. Esto nos "
    "permite cumplir con la Ley 1581 de 2012 y asegurar que tus notificaciones "
    "lleguen correctamente.\n\n"
    "Por favor, confírmanos los siguientes datos:\n"
    "Cédula o NIT:\n"
    "Teléfono celular actual:\n"
    "Dirección:\n"
    "Contacto de referencia (Nombre y teléfono):\n\n"
    "⚖️ Nota Legal: Al suministrar estos datos, autorizas el tratamiento de tu "
    "información según nuestra Política de Privacidad y la normativa de Habeas "
    "Data vigente."
)

# Ordered list of (state, field_in_db, prompt_template). The prompt may include
# {nombre_ref} which is replaced with the previously-captured reference name.
_CONTACT_UPDATE_STEPS = [
    ("actualizar_datos_telefono_principal", "telefono_principal",
     "Confírmanos tu número de celular actual. Si es el mismo desde el que escribes, contesta SI."),
    ("actualizar_datos_telefono_alterno", "telefono_alterno",
     "Por si no logramos ubicarte, déjanos un segundo número de contacto (familiar o cercano). Si no tienes, contesta NINGUNO."),
    ("actualizar_datos_direccion", "direccion",
     "Cuál es tu dirección de residencia actual? Incluye barrio y ciudad."),
    ("actualizar_datos_email", "email",
     "Cuál es tu correo electrónico vigente?"),
    ("actualizar_datos_ref_nombre", "ref_nombre",
     "Para terminar, danos un contacto de referencia. Escribe el nombre completo de esa persona."),
    ("actualizar_datos_ref_telefono", "ref_telefono",
     "Cuál es el teléfono de {nombre_ref}?"),
    ("actualizar_datos_ref_parentesco", "ref_parentesco",
     "Qué parentesco tiene {nombre_ref} contigo? (mamá, hermano, cónyuge, etc.)"),
]


def _send_contact_update_summary(user_phone: str):
    """Build and send the confirmation summary with [Confirmar] [Corregir] buttons."""
    from src.conversation_log import get_in_progress_contact_update
    row = get_in_progress_contact_update(user_phone) or {}

    def _v(k):
        return row.get(k) or "-"

    summary = (
        "Estos son los datos que registramos:\n\n"
        f"Cédula: {_v('cedula')}\n"
        f"Teléfono actual: {_v('telefono_principal')}\n"
        f"Teléfono alterno: {_v('telefono_alterno')}\n"
        f"Dirección: {_v('direccion')}\n"
        f"Correo: {_v('email')}\n"
        f"Referencia: {_v('ref_nombre')} - {_v('ref_telefono')} ({_v('ref_parentesco')})\n\n"
        "Están correctos?"
    )
    WhatsAppService.send_interactive_button(
        user_phone,
        summary,
        [
            {"id": "update_data_confirm", "title": "Confirmar"},
            {"id": "update_data_correct", "title": "Corregir"},
        ],
    )


def _start_contact_update_flow(user_phone: str, trigger_source: str, send_intro: bool = True):
    """Kick off the contact-data update flow. Inserts the in_progress row,
    optionally sends the legal intro text, then asks for the cedula."""
    from src.conversation_log import start_contact_update
    start_contact_update(user_phone, trigger_source)
    if send_intro:
        WhatsAppService.send_message(user_phone, CONTACT_UPDATE_INTRO_TEXT)
    set_user_state(user_phone, "actualizar_datos_inicio|0")
    WhatsAppService.send_message(
        user_phone,
        "Vamos por partes. Primero, escribe tu número de cédula o NIT (sin puntos ni espacios).",
    )


def _send_contact_update_next_prompt(user_phone: str, next_state: str):
    """Send the prompt that corresponds to a given step state."""
    from src.conversation_log import get_in_progress_contact_update
    for state_key, _field, prompt in _CONTACT_UPDATE_STEPS:
        if state_key == next_state:
            if "{nombre_ref}" in prompt:
                row = get_in_progress_contact_update(user_phone) or {}
                ref_name = row.get("ref_nombre") or "esa persona"
                prompt = prompt.replace("{nombre_ref}", ref_name)
            WhatsAppService.send_message(user_phone, prompt)
            return


def _advance_contact_update(user_phone: str, current_state: str):
    """Move to the next step in the contact-update flow, or finish with summary."""
    keys = [s[0] for s in _CONTACT_UPDATE_STEPS]
    try:
        idx = keys.index(current_state)
    except ValueError:
        # Came from `actualizar_datos_inicio` → first step
        next_state = _CONTACT_UPDATE_STEPS[0][0]
        set_user_state(user_phone, next_state)
        _send_contact_update_next_prompt(user_phone, next_state)
        return

    if idx + 1 < len(_CONTACT_UPDATE_STEPS):
        next_state = _CONTACT_UPDATE_STEPS[idx + 1][0]
        set_user_state(user_phone, next_state)
        _send_contact_update_next_prompt(user_phone, next_state)
    else:
        set_user_state(user_phone, "actualizar_datos_confirmacion")
        _send_contact_update_summary(user_phone)


def _handle_contact_update_text(user_phone: str, text: str, state: str) -> bool:
    """Handle a user text message when in any of the contact-update states.
    Returns True if the state was handled, False otherwise."""
    from src.conversation_log import update_contact_field
    from src.database import verify_cedula_matches_phone

    if _is_greeting(text):
        # User wants to escape the flow → drop them back to main menu
        from src.conversation_log import abandon_contact_update
        abandon_contact_update(user_phone, "abandoned")
        set_user_state(user_phone, "active")
        FlowHandler.send_main_menu(user_phone)
        return True

    # Step 0: cedula verification with up to 2 retries (state encodes attempt count)
    if state.startswith("actualizar_datos_inicio"):
        attempts = 0
        if "|" in state:
            try:
                attempts = int(state.split("|", 1)[1])
            except ValueError:
                attempts = 0

        typed = "".join(filter(str.isdigit, text))
        if not typed:
            WhatsAppService.send_message(
                user_phone,
                "Por favor envía solo el número de tu cédula (sin puntos ni espacios)."
            )
            return True

        if verify_cedula_matches_phone(user_phone, typed):
            update_contact_field(user_phone, "cedula", typed)
            _advance_contact_update(user_phone, "actualizar_datos_inicio")
            return True

        # Mismatch
        if attempts >= 1:
            # Already used 1 retry → escalate
            from src.conversation_log import abandon_contact_update
            abandon_contact_update(user_phone, "cedula_mismatch")
            set_agent_mode(user_phone, "agent")
            WhatsAppService.send_message(
                user_phone,
                "No logramos verificar tu identidad por este medio. "
                "En un momento un asesor te contacta para ayudarte."
            )
            try:
                notify_admin_cedula_mismatch(user_phone)
            except Exception as e:
                print(f"Error notifying admin (cedula_mismatch): {e}")
            return True

        set_user_state(user_phone, f"actualizar_datos_inicio|{attempts + 1}")
        WhatsAppService.send_message(
            user_phone,
            "Esa cédula no coincide con la que tenemos registrada para este número. "
            "Por favor intenta de nuevo (sin puntos ni espacios)."
        )
        return True

    # Telefono principal: SI or 10-digit number
    if state == "actualizar_datos_telefono_principal":
        norm = text.strip().lower()
        if norm in ("si", "sí", "s"):
            # Use the WhatsApp number itself, strip the 57 country code if present
            phone_clean = user_phone[2:] if user_phone.startswith("57") and len(user_phone) > 10 else user_phone
            update_contact_field(user_phone, "telefono_principal", phone_clean)
            _advance_contact_update(user_phone, state)
            return True
        digits = "".join(filter(str.isdigit, text))
        if len(digits) == 10:
            update_contact_field(user_phone, "telefono_principal", digits)
            _advance_contact_update(user_phone, state)
            return True
        WhatsAppService.send_message(
            user_phone,
            "Por favor escribe SI si es el mismo número desde el que chateas, o envíanos tu celular actual de 10 dígitos."
        )
        return True

    # Telefono alterno: 10 digits or 'ninguno'
    if state == "actualizar_datos_telefono_alterno":
        norm = text.strip().lower()
        if norm in ("ninguno", "no", "no tengo", "n/a", "na"):
            update_contact_field(user_phone, "telefono_alterno", "")
            _advance_contact_update(user_phone, state)
            return True
        digits = "".join(filter(str.isdigit, text))
        if len(digits) == 10:
            update_contact_field(user_phone, "telefono_alterno", digits)
            _advance_contact_update(user_phone, state)
            return True
        WhatsAppService.send_message(
            user_phone,
            "Por favor envíanos un celular alterno de 10 dígitos, o escribe NINGUNO si no tienes."
        )
        return True

    # Direccion: at least 10 characters
    if state == "actualizar_datos_direccion":
        direccion = text.strip()
        if len(direccion) < 10:
            WhatsAppService.send_message(
                user_phone,
                "Por favor escribe tu dirección completa, incluyendo barrio y ciudad."
            )
            return True
        update_contact_field(user_phone, "direccion", direccion)
        _advance_contact_update(user_phone, state)
        return True

    # Email
    if state == "actualizar_datos_email":
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        email = email_match.group(0) if email_match else None
        if not email:
            WhatsAppService.send_message(
                user_phone,
                "Por favor envíanos un correo electrónico válido (ejemplo: correo@email.com)."
            )
            return True
        update_contact_field(user_phone, "email", email)
        _advance_contact_update(user_phone, state)
        return True

    # Reference name
    if state == "actualizar_datos_ref_nombre":
        nombre = text.strip()
        if len(nombre) < 5:
            WhatsAppService.send_message(
                user_phone,
                "Por favor escribe el nombre completo de la persona de referencia."
            )
            return True
        update_contact_field(user_phone, "ref_nombre", nombre)
        _advance_contact_update(user_phone, state)
        return True

    # Reference phone
    if state == "actualizar_datos_ref_telefono":
        digits = "".join(filter(str.isdigit, text))
        if len(digits) != 10:
            WhatsAppService.send_message(
                user_phone,
                "Por favor envíanos un celular de 10 dígitos."
            )
            return True
        update_contact_field(user_phone, "ref_telefono", digits)
        _advance_contact_update(user_phone, state)
        return True

    # Reference parentesco
    if state == "actualizar_datos_ref_parentesco":
        parentesco = text.strip()
        if len(parentesco) < 3:
            WhatsAppService.send_message(
                user_phone,
                "Por favor escribe el parentesco (mamá, hermano, cónyuge, amigo, etc.)."
            )
            return True
        update_contact_field(user_phone, "ref_parentesco", parentesco)
        _advance_contact_update(user_phone, state)
        return True

    # Confirmation state — user wrote text instead of tapping a button: resend buttons
    if state == "actualizar_datos_confirmacion":
        _send_contact_update_summary(user_phone)
        return True

    return False


class FlowHandler:
    @staticmethod
    def handle_incoming_message(payload):
        """Process incoming webhook payload."""
        try:
            entry = payload.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            
            if "messages" not in value:
                return
            
            message = value["messages"][0]
            user_phone = message["from"]
            msg_type = message["type"]
            
            # Fetch current real state from Database
            current_state = get_user_state(user_phone)

            # ── Log inbound message ──────────────────────────────────
            msg_id = message.get("id")
            if msg_type == "text":
                log_message(user_phone, "inbound", message["text"]["body"].strip(), "text", wamid=msg_id)
            elif msg_type == "interactive":
                interactive = message["interactive"]
                if interactive.get("type") == "list_reply":
                    btn_title = interactive.get("list_reply", {}).get("title", "")
                else:
                    btn_title = interactive.get("button_reply", {}).get("title", "")
                log_message(user_phone, "inbound", btn_title, "button_reply", wamid=msg_id)
            elif msg_type == "button":
                btn_text = message["button"].get("text", "")
                log_message(user_phone, "inbound", btn_text, "button", wamid=msg_id)
            elif msg_type in ["image", "document"]:
                media_info = message[msg_type]
                media_id = media_info["id"]
                filename = media_info.get("filename", f"{msg_type}_{media_id}")
                if msg_type == "image":
                    ext = media_info.get("mime_type", "").split("/")[-1] or "jpg"
                    filename = f"{media_id}.{ext}" if "." not in filename else filename
                
                # Fetch and download
                media_url = WhatsAppService.get_media_url(media_id)
                if media_url:
                    target_dir = os.path.join("static", "uploads", user_phone)
                    target_path = os.path.join(target_dir, filename)
                    if WhatsAppService.download_media_file(media_url, target_path):
                        # Determine MIME type for Supabase
                        mime_type = media_info.get("mime_type", "application/octet-stream")
                        if msg_type == "image" and not getattr(media_info, 'mime_type', None):
                             mime_type = "image/jpeg"
                             
                        # Try to upload to Supabase Storage
                        supabase_path = f"{user_phone}/{filename}"
                        public_url = WhatsAppService.upload_to_supabase_storage(target_path, supabase_path, mime_type)
                        
                        # Use public URL if successful, otherwise fallback to local relative path
                        final_path = public_url if public_url else f"/static/uploads/{user_phone}/{filename}"
                        
                        log_message(user_phone, "inbound", final_path, msg_type, wamid=msg_id)

                        # Track documents received in any state (not just docs-expected states)
                        if public_url:
                            client_name = get_client_name(user_phone)
                            log_received_document(user_phone, client_name, filename, mime_type, final_path)

                        # Cédula del tercero — capture and advance flow
                        if current_state.startswith("waiting_for_cedula_tercero"):
                            nombre_tercero = current_state.split("|", 1)[1] if "|" in current_state else ""
                            client_name = get_client_name(user_phone)
                            from src.conversation_log import save_partial_tercero_cuenta
                            save_partial_tercero_cuenta(user_phone, client_name, nombre_tercero, final_path)
                            set_user_state(user_phone, "waiting_for_numero_cuenta_tercero")
                            WhatsAppService.send_message(
                                user_phone,
                                "Cédula recibida ✅\n\nAhora escríbenos el número de cuenta del titular (solo dígitos, sin espacios ni guiones)."
                            )

                        # Send confirmation in document-expected states; remind email if waiting for it
                        elif current_state in ("waiting_for_docs_rojo", "waiting_for_cuenta_amarillo"):
                            _schedule_doc_confirmation(user_phone)
                        elif current_state == "waiting_for_email":
                            WhatsAppService.send_message(
                                user_phone,
                                "Recibimos tu documento, gracias. Pero aún necesitamos tu correo electrónico para enviarte el contrato. Por favor escríbelo aquí:"
                            )

                        # Optionally cleanup local file to save disk space if uploaded successfully
                        if public_url:
                            try:
                                os.remove(target_path)
                            except Exception as e:
                                print(f"Could not remove temporary file {target_path}: {e}")
                    else:
                        WhatsAppService.send_message(user_phone, "Lo siento, hubo un error al procesar tu archivo.")
                else:
                    WhatsAppService.send_message(user_phone, "Lo siento, no pudimos obtener el archivo de WhatsApp.")

            # Handle Text Messages
            if msg_type == "text":
                text_body = message["text"]["body"].strip()
                FlowHandler.process_text_input(user_phone, text_body, current_state)
                
            # Handle Interactive Button Replies (both button and list replies)
            elif msg_type == "interactive":
                interactive = message["interactive"]
                interactive_type = interactive.get("type")
                if interactive_type == "list_reply":
                    reply = interactive.get("list_reply", {})
                else:
                    reply = interactive.get("button_reply", {})
                reply_id = reply.get("id", "")
                FlowHandler.process_button_click(user_phone, reply_id, current_state)
            
            # Handle Template Button Replies (Quick Replies)
            elif msg_type == "button":
                reply = message["button"]
                # For templates, the payload is often exactly what we want, 
                # but if not present, we use the text as fallback ID.
                reply_id = reply.get("payload", reply.get("text"))
                FlowHandler.process_button_click(user_phone, reply_id, current_state)
                
        except Exception as e:
            print(f"Error processing message: {e}")
            try:
                # Notify admin on failure
                notify_admin_error(locals().get('user_phone', 'Desconocido'), str(e))
            except Exception as notify_err:
                print(f"Error sending admin notification: {notify_err}")

    @staticmethod
    def process_text_input(user_phone, text, state):
        # 0. Agent Mode — bot stays silent, let human advisor handle
        if state in ["agent", "agent_silent"]:
            if text.lower() in ["salir", "cancelar", "volver"]:
                set_user_state(user_phone, "active")
                WhatsAppService.send_message(user_phone, "Has salido del modo asesor. Escribe 'Hola' para ver el menú principal.")
            return

        # 0b. LLM Agent Mode — handle with LLM agent (manual activation only via admin panel)
        if state == "agent_llm":
            _launch_llm_agent(user_phone, text)
            return

        # 0c. Referral A/B capture flow
        if referrals_ab.is_waiting_name_state(state):
            if _is_greeting(text):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
                return
            if not referrals_ab.is_valid_referred_name(text):
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor escríbenos el nombre completo del compañero referido."
                )
                return

            referred_name = referrals_ab.clean_referred_name(text)
            referrer_name = get_client_name(user_phone)
            referrals_ab.save_referral_name(user_phone, referrer_name, referred_name)
            set_user_state(user_phone, f"{referrals_ab.STATE_WAITING_PHONE_PREFIX}{referred_name}")
            WhatsAppService.send_message(user_phone, referrals_ab.ASK_PHONE_TEXT)
            return

        if referrals_ab.is_waiting_phone_state(state):
            referred_name = state.split("|", 1)[1] if "|" in state else ""
            if not referrals_ab.is_valid_referred_phone(text):
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor envíanos un número válido, solo dígitos. Ejemplo: 3201234567."
                )
                return

            referred_phone = referrals_ab.normalize_referred_phone(text)
            referrer_name = get_client_name(user_phone)
            referrals_ab.complete_referral(user_phone, referrer_name, referred_name, referred_phone)
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, referrals_ab.thanks_text_for_phone(user_phone))
            return

        if referrals_ab.is_referral_prompt_state(state):
            if _is_greeting(text):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
                return
            intent = referrals_ab.text_intent(text)
            if intent:
                button_text = {
                    "info": "¿Cómo funciona?",
                    "benefit": "Quiero el beneficio",
                    "later": "Quizás después",
                }[intent]
                _handle_referrals_ab_button(user_phone, button_text, state)
                return

            referrals_ab.record_event(user_phone, "free_text", text[:300])
            set_user_state(user_phone, referrals_ab.STATE_INFO_SENT)
            _send_referrals_ab_info(user_phone)
            return

        # 1. Check Consent Flow
        if state == "pending_consent":
            FlowHandler.send_habeas_data_prompt(user_phone)
            return
        
        # 2. Check if waiting for Cedula (Application Status)
        if state == "waiting_for_cedula":
            if not text.isdigit():
                 WhatsAppService.send_message(user_phone, "Por favor envía solo números, sin puntos ni espacios. Intenta de nuevo:")
                 return

            result = get_solicitud_status(text)
            anticipo = get_anticipo_by_cedula(text)

            # Branch 1: cliente con ambas solicitudes activas → preguntar cuál
            if result and anticipo:
                _ask_solicitud_choice(user_phone, text)
                return

            # Branch 2: solo crédito ordinario → comportamiento original
            if result:
                _render_credito_result(user_phone, result)
                return

            # Branch 3: solo anticipo de salario → confirmar recepción
            if anticipo:
                _render_anticipo_result(user_phone, anticipo)
                return

            # Branch 4: ninguno → fallback al Sheet de crédito recién radicado
            sheet_result = get_solicitud_reciente_sheet(text)
            if sheet_result:
                WhatsAppService.send_message(
                    user_phone,
                    f"🔍 *Resultado de Solicitud*\n\n"
                    f"¡Hola! Hemos recibido tu solicitud radicada recientemente. Actualmente se encuentra *En Estudio*.\n\n"
                    f"Te estaremos avisando por este medio apenas tengamos una respuesta o novedad."
                )
            else:
                WhatsAppService.send_message(user_phone, f"❌ No encontramos ninguna solicitud reciente con la cédula *{text}*.")
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, "Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 2.b Disambiguación entre crédito ordinario y anticipo (cliente con ambas)
        if state.startswith("waiting_for_solicitud_choice"):
            cedula = state.split("|", 1)[1] if "|" in state else ""
            norm = text.lower().strip()
            if re.search(r"\b(cr[eé]d|ordinari|libranza)", norm):
                result = get_solicitud_status(cedula) if cedula else None
                if result:
                    _render_credito_result(user_phone, result)
                else:
                    set_user_state(user_phone, "active")
                    WhatsAppService.send_message(user_phone, "No pude recuperar tu solicitud de crédito en este momento. Intenta consultarla de nuevo desde el menú.")
                return
            if re.search(r"\b(antic|salari|n[oó]min)", norm):
                anticipo = get_anticipo_by_cedula(cedula) if cedula else None
                if anticipo:
                    _render_anticipo_result(user_phone, anticipo)
                else:
                    set_user_state(user_phone, "active")
                    WhatsAppService.send_message(user_phone, "No pude recuperar tu solicitud de anticipo en este momento. Intenta consultarla de nuevo desde el menú.")
                return
            # Texto no reconocido → reenviar botones
            if cedula:
                _ask_solicitud_choice(user_phone, cedula)
            else:
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
            return

        # 2a-bis. Yearly contact-data update flow — handle all of its states
        if state.startswith("actualizar_datos_") or state == "esperando_respuesta_actualizacion":
            if state == "esperando_respuesta_actualizacion":
                # Client typed text instead of tapping the template buttons.
                # Treat any non-greeting text as a desire to start the flow.
                if _is_greeting(text):
                    set_user_state(user_phone, "active")
                    FlowHandler.send_main_menu(user_phone)
                    return
                _start_contact_update_flow(user_phone, "campaign_annual", send_intro=False)
                return
            if _handle_contact_update_text(user_phone, text, state):
                return

        # 2a. Check if waiting for Email
        if state == "waiting_for_email":
            if _is_greeting(text):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
                return
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            email = email_match.group(0) if email_match else None
            if email:
                from src.conversation_log import save_captured_email
                client_name = get_client_name(user_phone)

                # Fallback: if name is still unknown, look it up by phone in Cloud Run
                if not client_name or client_name == "Cliente":
                    from src.database import get_name_by_phone
                    resolved = get_name_by_phone(user_phone)
                    if resolved:
                        client_name = resolved
                        set_client_name(user_phone, client_name)

                # Save to database
                save_captured_email(user_phone, email, client_name)

                WhatsAppService.send_message(user_phone, "¡Gracias! Hemos registrado tu correo electrónico. En breve te estaremos enviando el contrato de crédito.")
                
                # Optional: Send a notification to Admin about the email
                try:
                    notify_admin_agent_request(user_phone)
                except Exception as e:
                    print(f"Error notifying admin: {e}")
                
                set_user_state(user_phone, "active")
            else:
                WhatsAppService.send_message(user_phone, "Por favor ingresa un correo electrónico válido (ejemplo: correo@email.com):")
            return

        # 2b. Check if waiting for docs after estado_rojo
        if state == "waiting_for_docs_rojo":
            if _is_greeting(text):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
                return
            if text.lower().strip() in ["asesor", "asesor humano", "ayuda", "help"]:
                set_agent_mode(user_phone, "agent")
                WhatsAppService.send_message(user_phone, "Dame un momento mientras reviso tu información y ya mismo te escribo.\n\n_Si deseas volver al menú del bot, escribe *salir*._")
                notify_admin_agent_request(user_phone)
            else:
                from src.conversation_log import get_solicitud_context
                from src.automation import build_docs_message
                ctx = get_solicitud_context(user_phone)
                docs_reminder = build_docs_message(
                    ctx.get("docs_faltantes", ""),
                    ctx.get("tipo_empleador", "EMPRESA"),
                )
                WhatsAppService.send_interactive_button(
                    user_phone,
                    docs_reminder,
                    [
                        {"id": "cargar_documentos", "title": "Cargar documentos"},
                        {"id": "ya_envie_docs", "title": "Ya los envié"},
                        {"id": "hablar_asesor_docs", "title": "Hablar con un asesor"},
                    ]
                )
            return

        # 2c. Tercero flow — step 1: waiting for titular's name
        if state == "waiting_for_nombre_tercero":
            nombre = text.strip()
            if len(nombre) >= 3:
                set_user_state(user_phone, f"waiting_for_cedula_tercero|{nombre}")
                WhatsAppService.send_message(
                    user_phone,
                    "Anotado. Ahora envíanos una foto de la cédula del titular."
                )
            else:
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor escribe el nombre completo del titular de la cuenta."
                )
            return

        # 2c. Tercero flow — step 3: waiting for account number after cedula received
        if state == "waiting_for_numero_cuenta_tercero":
            digits = "".join(filter(str.isdigit, text))
            if len(digits) >= 5:
                from src.conversation_log import update_tercero_cuenta_numero
                update_tercero_cuenta_numero(user_phone, digits)
                set_user_state(user_phone, "waiting_for_banco")
                WhatsAppService.send_message(
                    user_phone,
                    "Número registrado ✅\n\nEn qué banco está la cuenta? (Ej: Bancolombia, Davivienda, Nequi...)"
                )
            else:
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor envíanos solo el número de cuenta (mínimo 5 dígitos, sin letras ni espacios)."
                )
            return

        # 2c. Cuenta propia — waiting for account number (digits only)
        if state in ("waiting_for_numero_cuenta", "waiting_for_cuenta_amarillo"):
            digits = "".join(filter(str.isdigit, text))
            if len(digits) >= 5:
                from src.conversation_log import save_captured_cuenta
                client_name = get_client_name(user_phone)
                save_captured_cuenta(user_phone, digits, client_name)
                set_user_state(user_phone, "waiting_for_banco")
                WhatsAppService.send_message(
                    user_phone,
                    "Número registrado ✅\n\nEn qué banco está la cuenta? (Ej: Bancolombia, Davivienda, Nequi...)"
                )
            else:
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor envíanos solo el número de cuenta (mínimo 5 dígitos, sin letras ni espacios)."
                )
            return

        # 2d. Step 2: waiting for bank name
        if state == "waiting_for_banco":
            banco = text.strip()
            if len(banco) >= 2:
                from src.conversation_log import update_captured_cuenta_banco
                update_captured_cuenta_banco(user_phone, banco)
                set_user_state(user_phone, "active")
                WhatsAppService.send_message(
                    user_phone,
                    "✅ ¡Gracias! Hemos registrado tu número de cuenta y banco. "
                    "Nuestro equipo lo revisará y te contactaremos pronto para finalizar el desembolso."
                )
            else:
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor escribe el nombre de tu *banco* (ej: Bancolombia, Davivienda, Nequi...)."
                )
            return

        # 2e. denegado_notified — template sent; acknowledgments are absorbed silently,
        #     any other message shows the main menu
        if state == "denegado_notified":
            norm = text.lower().strip()
            # El cliente escribió en vez de tocar el botón "Consultar motivo".
            if "consultar motivo" in norm or norm == "motivo":
                _send_denegado_reason(user_phone)
                return
            set_user_state(user_phone, "active")
            ack_words = ["ok", "okay", "entendido", "gracias", "de acuerdo", "listo",
                         "bien", "claro", "comprendo", "entiendo", "perfecto", "👍"]
            is_ack = any(norm == w or norm.startswith(w + " ") or norm.startswith(w + ",") for w in ack_words)
            if not is_ack:
                FlowHandler.send_main_menu(user_phone)
            return

        # 2g. anticipos_notified — template sent; absorb acks, route advisor requests, else show menu
        if state == "anticipos_notified":
            set_user_state(user_phone, "active")
            ack_words = ["ok", "okay", "entendido", "gracias", "de acuerdo", "listo",
                         "bien", "claro", "comprendo", "entiendo", "perfecto", "👍"]
            norm = text.lower().strip()
            is_ack = any(norm == w or norm.startswith(w + " ") or norm.startswith(w + ",") for w in ack_words)
            if is_ack:
                return
            if _is_greeting(norm):
                FlowHandler.send_main_menu(user_phone)
                return
            if _is_advisor_request(norm):
                set_agent_mode(user_phone, "agent")
                WhatsAppService.send_message(
                    user_phone,
                    "Con gusto! En un momento un asesor te contactara para darte informacion sobre el anticipo de nomina."
                )
                notify_admin_agent_request(user_phone)
                return
            FlowHandler.send_main_menu(user_phone)
            return

        # 2f. renovado_notified — template sent; absorb acks, route advisor requests, else show menu
        if state == "renovado_notified":
            set_user_state(user_phone, "active")
            ack_words = ["ok", "okay", "entendido", "gracias", "de acuerdo", "listo",
                         "bien", "claro", "comprendo", "entiendo", "perfecto", "👍"]
            norm = text.lower().strip()
            is_ack = any(norm == w or norm.startswith(w + " ") or norm.startswith(w + ",") for w in ack_words)
            if is_ack:
                return
            if _is_greeting(norm):
                FlowHandler.send_main_menu(user_phone)
                return
            if _is_advisor_request(norm):
                set_agent_mode(user_phone, "agent")
                WhatsAppService.send_message(
                    user_phone,
                    "Con gusto! En un momento un asesor te contactará para darte información sobre tu renovación."
                )
                notify_admin_agent_request(user_phone)
                return
            FlowHandler.send_main_menu(user_phone)
            return

        # 2d. Check if waiting for Cedula (Saldo / Balance)
        if state == "waiting_for_cedula_saldo":
            if not text.isdigit():
                WhatsAppService.send_message(user_phone, "Por favor envía solo números, sin puntos ni espacios. Intenta de nuevo:")
                return

            prestamos = get_saldo(text)

            if prestamos is not None:
                if prestamos:
                    nombre = prestamos[0].get("nombre_completo", "")
                    response_msg = f"💰 *Consulta de Saldo*\n\n👤 *Cliente:* {nombre}\n"

                    for p in prestamos:
                        saldo = p.get("saldo_actual", 0)
                        estado = p.get("estado_del_prestamo", "")
                        id_prestamo = p.get("id_prestamo", "")
                        cuotas = p.get("cuotas_restantes", 0)
                        
                        ultima_fecha = p.get("ultima_fecha_pago")
                        if not ultima_fecha:
                            ultima_fecha_str = "No registra"
                        elif hasattr(ultima_fecha, 'strftime'):
                            ultima_fecha_str = ultima_fecha.strftime('%Y-%m-%d')
                        else:
                            ultima_fecha_str = str(ultima_fecha)

                        response_msg += (
                            f"\n🔢 *ID:* {id_prestamo}\n"
                            f"💵 *Saldo:* ${saldo:,.0f}\n"
                            f"📌 *Estado:* {estado}\n"
                            f"📊 *Cuotas restantes:* {cuotas}\n"
                            f"📅 *Última fecha de pago:* {ultima_fecha_str}\n"
                        )
                    WhatsAppService.send_message(user_phone, response_msg)
                else:
                    WhatsAppService.send_message(user_phone, f"❌ No encontramos préstamos activos con la cédula *{text}*.")
            else:
                WhatsAppService.send_message(user_phone, "⚠️ *Error del Sistema*\n\nNo pudimos conectar con el servidor de base de datos. Por favor intenta de nuevo en unos minutos.")

            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, "Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 3. Main Menu Logic
        norm_text = text.lower().strip()

        if _is_greeting(norm_text):
            set_user_state(user_phone, "active")
            FlowHandler.send_main_menu(user_phone)
            return

        # Detect post-action confirmations ("ya llené el formulario", etc.)
        post_action_keywords = ["ya llene", "ya llené", "ya envie", "ya envié", "ya lo hice",
                                "ya lo envie", "ya lo envié", "ya lo llene", "ya lo llené",
                                "listo formulario", "ya diligencié", "ya diligiencie",
                                "formulario listo", "ya lo rellene", "ya lo rellené"]
        if any(kw in norm_text for kw in post_action_keywords):
            WhatsAppService.send_message(
                user_phone,
                "Perfecto, gracias por avisarnos. Nuestro equipo lo revisará y te contactaremos pronto con novedades."
            )
            set_user_state(user_phone, "active")
            return

        # Only activate human agent for explicit advisor requests; everything else shows the menu
        if not _is_advisor_request(norm_text):
            set_user_state(user_phone, "active")
            FlowHandler.send_main_menu(user_phone)
            return

        set_agent_mode(user_phone, "agent")
        WhatsAppService.send_message(user_phone, "Claro, en un momento un asesor te atiende.")
        notify_admin_agent_request(user_phone)

    @staticmethod
    def process_button_click(user_phone, btn_id, state):
        if _handle_referrals_ab_button(user_phone, btn_id, state):
            return

        if btn_id == "accept_terms":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, "¡Gracias por aceptar! Bienvenido a ProAlto.")
            FlowHandler.send_main_menu(user_phone)
        
        elif btn_id == "decline_terms":
            WhatsAppService.send_message(user_phone, "Entendemos. No podremos atenderte por este medio sin tu autorización. Si cambias de opinión, escribe 'Hola'.")
            set_user_state(user_phone, "pending_consent")

        elif btn_id == "menu_cliente":
            FlowHandler.send_client_menu(user_phone)

        # ── Nuevo menú interactivo — Nivel 1 → submenús ──
        elif btn_id == "menu_info":
            # Nivel 2A — Información General: mensaje + lista de opciones.
            FlowHandler.send_info_general_menu(user_phone)

        elif btn_id == "menu_mi_credito":
            # Nivel 2C — Mi Crédito ProAlto: mensaje + lista de gestión.
            FlowHandler.send_mi_credito_menu(user_phone)

        elif btn_id == "menu_solicitar":
            # Nivel 2B — Solicitar Crédito: sin submenú, link directo al formulario.
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Realiza tu crédito rápido con ProAlto por DESCUENTO DE NÓMINA. "
                "Ahora es más fácil y práctico 👇🏼 https://forms.gle/zXzrcrzVefuoVsEX6\n"
                "Ten en cuenta estas 3 claves:\n"
                "✅ Tu límite ágil: puedes solicitar hasta el doble de tu salario sin necesidad de codeudor.\n"
                "🤝 Monto mayor: para más del doble de tu salario, requerimos un codeudor y sus documentos.\n"
                "📈 Aumento de crédito: si ya tuviste un crédito con nosotros, revisamos tu capacidad para aumentarlo un 40% sobre el valor anterior.\n"
                "🛡️ ¿Prefieres no abrir enlaces externos? Lo entendemos. Tu seguridad es nuestra prioridad. Si te sientes más tranquilo, puedes hacer tu solicitud directamente desde nuestro sitio web oficial: www.proalto.co"
            )

        # ── Nivel 2A — respuestas de la lista "Información General" ──
        elif btn_id == "info_requisitos":
            WhatsAppService.send_message(
                user_phone,
                "Para iniciar tu solicitud, solo necesitas tener a la mano estos documentos:\n"
                "✅ 2 últimos desprendibles de pago de nómina.\n"
                "✅ Certificado laboral.\n"
                "✅ Foto de tu cédula.\n"
                "✅ Recibo público (agua, luz, gas o telefonía).\n"
                "🎯 ¡Dato importante! Tu historial crediticio no es un impedimento. Si estás reportado en Datacrédito u otras centrales, ¡en ProAlto sí te prestamos!"
            )

        elif btn_id == "info_tasas":
            WhatsAppService.send_message(
                user_phone,
                "En ProAlto nos esforzamos continuamente por ofrecer tasas por debajo del mercado para que cumplas tus metas.\n"
                "💡 Actualmente manejamos tasas desde el 1,8% mensual. (El porcentaje final puede variar según el mercado, tu antigüedad y tu capacidad de pago).\n"
                "¡Dato importante! Todas nuestras cuotas son fijas: siempre sabrás exactamente cuánto vas a pagar desde el primer hasta el último día, sin sorpresas."
            )

        elif btn_id == "info_montos":
            WhatsAppService.send_message(
                user_phone,
                "Ajustamos nuestros préstamos a tu capacidad de pago. Con nosotros cuentas con:\n"
                "💰 Préstamos desde $500.000 hasta el doble de tu salario sin necesidad de codeudor. 🗓️ Plazos flexibles desde 3 meses en adelante.\n"
                "🤝 ¿Buscas un monto superior al doble de tu salario?\n"
                "¡Claro que sí! En este caso solicitaremos el respaldo de un codeudor con los siguientes documentos:\n"
                "Foto de la cédula.\n"
                "Certificación laboral (o de ingresos para independientes).\n"
                "Desprendibles de pago o extractos bancarios.\n"
                "Certificación bancaria.\n"
                "Dirección y teléfono de contacto."
            )

        # ── Nivel 2C — "Paz y Salvo": registro manual mientras no exista
        # generación automática. La solicitud queda en document_requests y los
        # asesores la gestionan desde el panel de admin (pestaña Paz y Salvos).
        # TODO: cuando exista la generación automática del paz y salvo,
        # reemplazar este registro por el envío directo del documento.
        elif btn_id == "cred_paz":
            set_user_state(user_phone, "active")
            from src.conversation_log import save_document_request
            from src.notifications import notify_admin_document_request
            client_name = get_client_name(user_phone)
            save_document_request(user_phone, client_name, "paz_salvo", source="menu",
                                  detalle="Solicitado desde el menú (botón Paz y Salvo)")
            notify_admin_document_request(user_phone, "paz_salvo", source="menu")
            WhatsAppService.send_message(
                user_phone,
                "Estamos generando tu paz y salvo, un asesor te lo enviará en breve."
            )

        # ── Template estado_negados — botón "Consultar motivo" ──
        elif btn_id in ["Consultar motivo", "consultar_motivo"]:
            # El cliente quiere saber por qué se negó su crédito. Reusamos la
            # misma lógica que el estado interno DENEGADO (opc_negadas →
            # NEGADAS_MESSAGES), resolviendo el motivo por teléfono. Meta manda
            # el texto del botón como payload en los quick-replies de template.
            _send_denegado_reason(user_phone)

        # ── Estado APROBADO POR EL CLIENTE — elección post-aprobación ──
        elif btn_id in ["aprobado_enviar_correo", "Enviar correo"]:
            # Confluyen aquí: el botón "Enviar correo" en sesión, el "Sí, enviar
            # correo" del set de dudas, y el quick-reply "Enviar correo" del
            # template estado_verde (Meta manda el texto del botón como payload).
            _proceed_to_aprobado_email(user_phone)

        elif btn_id in ["aprobado_dudas_valor", "Tengo dudas"]:
            WhatsAppService.send_interactive_button(
                user_phone,
                "Te aprobamos esta cantidad porque es el valor más seguro para ti en este momento. "
                "Revisamos tus gastos y queremos estar seguros de que la cuota que vas a pagar no te "
                "deje sin plata para tus cosas de todos los días. Así puedes estar al día sin pasar apuros.",
                [
                    {"id": "aprobado_enviar_correo", "title": "📩 Sí, enviar correo"},
                    {"id": "aprobado_no_seguir", "title": "❌ No seguir"},
                ]
            )
            set_user_state(user_phone, "active")

        elif btn_id == "aprobado_no_seguir":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Entendido, respetamos tu decisión. Si más adelante quieres retomar tu crédito, "
                "escríbenos y con gusto te ayudamos."
            )
            from src.notifications import notify_admin_aprobado_abandono
            notify_admin_aprobado_abandono(user_phone, get_client_name(user_phone))

        elif btn_id in ["menu_solicitud", "cred_estado"]:
            # "Estado Solicitud" (menú viejo) y "Estado de mi solicitud" (nuevo
            # menú → cred_estado) comparten el MISMO flujo de consulta por cédula.
            set_user_state(user_phone, "waiting_for_cedula")
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu solicitud:")

        elif btn_id in ["menu_credito", "Solicitar crédito"]:
            set_user_state(user_phone, "active")

            if state == "renovado_notified":
                WhatsAppService.send_message(
                    user_phone,
                    "Que buena noticia! Para renovar tu crédito, diligencia el siguiente formulario:\n\n"
                    "👉 https://forms.gle/zXzrcrzVefuoVsEX6\n\n"
                    "Si tienes alguna duda durante el proceso, estamos aquí para ayudarte."
                )
            elif btn_id == "Solicitar crédito":
                # Opción "Solicitar crédito" de la plantilla de leads (contacto_leads).
                WhatsAppService.send_message(
                    user_phone,
                    "Realiza tu crédito rápido con ProAlto por DESCUENTO DE NÓMINA. "
                    "Ahora es más fácil y práctico 👇🏼 https://forms.gle/zXzrcrzVefuoVsEX6\n"
                    "Ten en cuenta estas 3 claves:\n"
                    "✅ Tu límite ágil: puedes solicitar hasta el doble de tu salario sin necesidad de codeudor.\n"
                    "🤝 Monto mayor: para más del doble de tu salario, requerimos un codeudor y sus documentos.\n"
                    "📈 Aumento de crédito: si ya tuviste un crédito con nosotros, revisamos tu capacidad para aumentarlo un 40% sobre el valor anterior.\n"
                    "🛡️ ¿Prefieres no abrir enlaces externos? Lo entendemos. Tu seguridad es nuestra prioridad. Si te sientes más tranquilo, puedes hacer tu solicitud directamente desde nuestro sitio web oficial: www.proalto.co"
                )
            else:
                WhatsAppService.send_message(user_phone, "Para solicitar tu crédito, por favor llena el siguiente formulario:\n\n👉 https://forms.gle/zXzrcrzVefuoVsEX6")

        elif btn_id in ["choice_credito", "choice_anticipo"]:
            # Respuesta a la disambiguación cuando el cliente tenía solicitud
            # de crédito Y de anticipo activas al mismo tiempo.
            cedula = state.split("|", 1)[1] if state.startswith("waiting_for_solicitud_choice") and "|" in state else ""
            if not cedula:
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
            elif btn_id == "choice_credito":
                result = get_solicitud_status(cedula)
                if result:
                    _render_credito_result(user_phone, result)
                else:
                    set_user_state(user_phone, "active")
                    WhatsAppService.send_message(user_phone, "No pude recuperar tu solicitud de crédito en este momento. Intenta consultarla de nuevo desde el menú.")
            else:  # choice_anticipo
                anticipo = get_anticipo_by_cedula(cedula)
                if anticipo:
                    _render_anticipo_result(user_phone, anticipo)
                else:
                    set_user_state(user_phone, "active")
                    WhatsAppService.send_message(user_phone, "No pude recuperar tu solicitud de anticipo en este momento. Intenta consultarla de nuevo desde el menú.")

        elif btn_id in ["menu_saldo", "cred_saldo"]:
            # "Consultar Saldo" (menú viejo) y "Consulta de saldo" (nuevo menú →
            # cred_saldo) comparten el MISMO flujo de consulta de saldo por cédula.
            set_user_state(user_phone, "waiting_for_cedula_saldo")
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu saldo:")

            
        elif btn_id in ["enviar_numero_cuenta", "Enviar número de cuenta", "Enviar Cuenta propia"]:
            set_user_state(user_phone, "waiting_for_numero_cuenta")
            WhatsAppService.send_message(
                user_phone,
                "Por favor escríbenos tu número de cuenta (solo dígitos, sin espacios ni guiones)."
            )

        elif btn_id in ["Enviar Cuenta de tercero", "Enviar| Cuenta de tercero"]:
            set_user_state(user_phone, "waiting_for_nombre_tercero")
            WhatsAppService.send_message(
                user_phone,
                "Entendido. Para registrar la cuenta del tercero necesitamos:\n\n"
                "1. Nombre completo del titular\n"
                "2. Foto de su cédula\n"
                "3. Número de cuenta\n"
                "4. Banco\n\n"
                "Empecemos: escribe el nombre completo del titular de la cuenta."
            )

        elif "consultar" in btn_id.lower():
            from src.conversation_log import get_solicitud_context
            from src.automation import build_docs_message
            ctx = get_solicitud_context(user_phone)
            docs_msg = build_docs_message(
                ctx.get("docs_faltantes", ""),
                ctx.get("tipo_empleador", "EMPRESA"),
            )
            WhatsAppService.send_interactive_button(
                user_phone,
                docs_msg,
                [
                    {"id": "cargar_documentos", "title": "Cargar documentos"},
                    {"id": "ya_envie_docs", "title": "Ya los envié"},
                    {"id": "hablar_asesor_docs", "title": "Hablar con un asesor"},
                ]
            )

        elif btn_id in ["cargar_documentos", "Cargar documentos"]:
            WhatsAppService.send_message(
                user_phone,
                "Para enviarnos tus documentos, simplemente adjunta el archivo o foto directamente en este chat, como si fuera una imagen normal. 📎\n\n"
                "Puedes enviar varios archivos por separado, uno a la vez."
            )

        elif btn_id in ["ya_envie_docs", "Ya los envié"]:
            WhatsAppService.send_message(
                user_phone,
                "✅ Perfecto, gracias. Nuestro equipo revisará los documentos que enviaste y te contactaremos pronto."
            )
            set_user_state(user_phone, "active")

        elif btn_id in ["hablar_asesor_docs", "menu_support", "Hablar con un asesor", "info_asesor", "cred_asesor"]:
            # Handler único de "Hablar con un asesor". Tanto el menú viejo
            # (menu_support) como el nuevo (info_asesor en Información General y
            # cred_asesor en Mi Crédito ProAlto) reutilizan esta misma lógica.
            is_lead = (state in ("lead_notified", "renovado_notified", "anticipos_notified"))
            set_agent_mode(user_phone, "agent")

            try:
                notify_admin_agent_request(user_phone)
            except Exception as e:
                print(f"Error notifying admin: {e}")

            if is_lead:
                msg = (
                    "¡Claro que sí! 🚀 Me alegra tu interés en ProAlto. \n\n"
                    "En un momento un asesor comercial te atenderá para brindarte información personalizada y ayudarte con tu solicitud."
                )
            else:
                msg = (
                    "Claro, en un momento un asesor te atiende."
                )

            WhatsAppService.send_message(user_phone, msg)

        elif btn_id == "¿Cómo funciona?":
            # Tercer botón de la plantilla de anticipo. Explica el producto y
            # ofrece dos sub-opciones (requisitos / solicitar) en el mismo mensaje.
            set_user_state(user_phone, "active")
            from src.conversation_log import log_anticipo_response
            log_anticipo_response(user_phone, "como_funciona")
            WhatsAppService.send_interactive_button(
                user_phone,
                "¡Es súper fácil! Un adelanto en ProAlto te permite acceder a una parte de tu salario "
                "antes del día de pago. Es ideal para resolver cualquier urgencia o cubrir un imprevisto "
                "sin complicaciones. 💸\n\n"
                "Todo el trámite es digital y, una vez aprobado, recibes la plata directamente en tu "
                "cuenta en máximo 24 horas hábiles.",
                [
                    {"id": "anticipo_requisitos", "title": "Ver requisitos 📋"},
                    {"id": "anticipo_solicitar", "title": "Solicitarlo 🚀"},
                ]
            )

        elif btn_id == "anticipo_requisitos":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Lo único que necesitas tener a la mano es el desprendible de tu última nómina y listo."
            )

        elif btn_id in ("Solicitar Anticipo", "anticipo_solicitar"):
            set_user_state(user_phone, "active")
            from src.conversation_log import log_anticipo_response
            log_anticipo_response(user_phone, "solicitar")
            WhatsAppService.send_message(
                user_phone,
                "Para solicitar tu anticipo de nomina, diligencia el siguiente formulario:\n\n"
                "https://forms.gle/EVvXfpndrRGdtjMz5\n\n"
                "Si tienes alguna duda durante el proceso, estamos aqui para ayudarte."
            )

        elif btn_id == "renovar_info_asesor":
            # Cliente de renovación pide asesor tras ver los requisitos. NO se trata
            # como lead: handler propio con copy de renovación, sin pasar por is_lead.
            set_agent_mode(user_phone, "agent")
            WhatsAppService.send_message(
                user_phone,
                "Con gusto! En un momento un asesor te contactará para darte toda la información sobre tu renovación."
            )
            try:
                notify_admin_agent_request(user_phone)
            except Exception as e:
                print(f"Error notifying admin: {e}")

        elif btn_id in ("Ahora no, gracias", "renovar_ahora_no"):
            set_user_state(user_phone, "active")
            if state == "anticipos_notified":
                from src.conversation_log import log_anticipo_response
                log_anticipo_response(user_phone, "no_gracias")
            WhatsAppService.send_message(
                user_phone,
                "Entendido, agradecemos tu tiempo. Estaremos aquí cuando nos necesites."
            )

        elif btn_id == "No lo quiero":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Entendido, lo tenemos en cuenta. Si en algún momento deseas renovar tu crédito, escríbenos y con gusto te ayudamos."
            )

        elif btn_id == "Necesito más información":
            # Botón compartido (mismo payload) por la plantilla de leads
            # (contacto_leads) y la de renovación (estado_renovar). Para elegir el
            # copy correcto NO usamos el status de la conversación: cualquier
            # transición posterior o una segunda campaña lo sobrescribe, y un lead
            # real podía quedar con status renovado_notified y recibir el copy de
            # renovación. Enrutamos por la ÚLTIMA plantilla de campaña realmente
            # enviada (rastro inmutable en bot_messages); el status solo se usa como
            # último recurso si no hay rastro de plantilla.
            last_tpl = get_last_campaign_template(user_phone)
            if last_tpl is not None:
                is_renovado = (last_tpl == "estado_renovar")
            else:
                is_renovado = (state == "renovado_notified")

            if not is_renovado:
                # Plantilla de leads (contacto_leads): "Necesito más información"
                # entra al MISMO flujo de "Información General" (intro + lista:
                # Requisitos / Tasas / Montos y plazos / Hablar con un asesor).
                set_user_state(user_phone, "active")
                FlowHandler.send_info_general_menu(user_phone)
            else:
                # Plantilla de renovación: explica qué es el retranqueo, lista los
                # requisitos y ofrece dos sub-opciones (asesor / posponer) en el mismo
                # mensaje. Estos contactos son clientes que renuevan, NO leads: el
                # botón de asesor tiene su propio handler (renovar_info_asesor) para
                # no caer en el copy de lead del handler genérico.
                WhatsAppService.send_interactive_button(
                    user_phone,
                    "Un retranqueo o renovación significa que puedes solicitar un nuevo crédito "
                    "con nosotros de forma inmediata. Te enviamos este mensaje porque vimos que "
                    "tu crédito actual ya está a punto de finalizar. 🎉\n\n"
                    "📋 Requisitos\n"
                    "Para iniciar tu solicitud, solo necesitas tener a la mano estos documentos:\n"
                    "✅ 2 últimos desprendibles de pago de nómina.\n"
                    "✅ Certificado laboral.\n"
                    "✅ Foto de tu cédula.\n"
                    "✅ Recibo público (agua, luz, gas o telefonía).",
                    [
                        {"id": "renovar_info_asesor", "title": "💬 Hablar con asesor"},
                        {"id": "renovar_ahora_no", "title": "⏳ Ahora no, gracias"},
                    ]
                )

        elif btn_id == "menu_main":
            FlowHandler.send_main_menu(user_phone)

        # ── Yearly contact-data update — template buttons & menu entry ──
        elif btn_id in ("update_data_yes", "Actualizar ahora"):
            # Client tapped "Actualizar ahora" on the campaign template.
            # The legal intro is already in the template body itself, so we
            # don't resend it — go straight into the cedula step.
            _start_contact_update_flow(user_phone, "campaign_annual", send_intro=False)

        elif btn_id in ("update_data_no", "Más tarde", "Mas tarde"):
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Listo, lo dejamos para más adelante. Te recordaremos por este "
                "mismo medio cuando sea momento de actualizar tus datos."
            )

        elif btn_id == "update_data_confirm":
            from src.conversation_log import get_in_progress_contact_update, confirm_contact_update
            row = get_in_progress_contact_update(user_phone) or {}
            confirm_contact_update(user_phone)
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Gracias! Hemos registrado tu actualización. Cualquier cambio adicional, "
                "escríbenos y con gusto te ayudamos."
            )
            try:
                client_name = get_client_name(user_phone)
                notify_admin_contact_update(user_phone, client_name, row)
            except Exception as e:
                print(f"Error notifying admin (contact_update): {e}")

        elif btn_id == "update_data_correct":
            # Reinicia el flujo desde el inicio. La fila in_progress queda,
            # los campos se sobreescriben con la siguiente captura.
            set_user_state(user_phone, "actualizar_datos_inicio|0")
            WhatsAppService.send_message(
                user_phone,
                "Sin problema. Empecemos otra vez para corregir. "
                "Escribe tu número de cédula o NIT (sin puntos ni espacios)."
            )

        elif btn_id in ["acepto_condiciones", "Acepto las condiciones"]:
            set_user_state(user_phone, "waiting_for_email")
            WhatsAppService.send_message(user_phone, "¡Excelente! Por favor envíanos tu *correo electrónico* para poder enviarte el contrato de crédito.")

    @staticmethod
    def send_habeas_data_prompt(user_phone):
        legal_text = (
            "Bienvenido a ProAlto. Para continuar, necesitamos tu autorización para tratar tus datos personales "
            "según nuestra política de privacidad y la Ley 1581 de 2012."
        )
        buttons = [
            {"id": "accept_terms", "title": "Acepto"},
            {"id": "decline_terms", "title": "No Acepto"}
        ]
        WhatsAppService.send_interactive_button(user_phone, legal_text, buttons)

    @staticmethod
    def send_main_menu(user_phone):
        # Nivel 1 — Menú principal. Es también el menú que dispara la señal
        # [MOSTRAR_MENU] del agente LLM. Texto verbatim de plantilla: los emojis
        # y los signos de apertura (¡ ¿) son intencionales SOLO para estas
        # plantillas de menú (excepción al estilo general del bot).
        menu_text = (
            "¡Hola! 👋 Gracias por comunicarte con Financiera ProAlto. "
            "¿Qué trámite o consulta deseas realizar hoy?"
        )
        # Menú principal en formato LISTA para poder mostrar un subtítulo
        # (description) por opción. Los ids llegan como list_reply, pero el
        # enrutador (handle_incoming_message) extrae el id igual que para los
        # botones y dispara los MISMOS handlers en process_button_click.
        sections = [{
            "title": "Opciones",
            "rows": [
                {"id": "menu_info", "title": "Información General",
                 "description": "Conoce a ProAlto y nuestros servicios."},
                {"id": "menu_solicitar", "title": "💸 Solicitar Crédito",
                 "description": "Inicia tu trámite ahora y conoce los pasos a seguir."},
                {"id": "menu_mi_credito", "title": "Mi Crédito ProAlto",
                 "description": "Consulta tu saldo, estado de solicitud y certificados."},
            ],
        }]
        WhatsAppService.send_interactive_list(user_phone, menu_text, "Ver opciones", sections)

    @staticmethod
    def send_info_general_menu(user_phone):
        # Nivel 2A — "Información General": primero el mensaje y LUEGO la lista.
        intro = (
            "¡Hola! 👋 Somos Financiera ProAlto. Nos especializamos en brindar "
            "créditos por descuento de nómina de manera ágil y segura.\n"
            "¿Estás reportado en centrales de riesgo? ¡No te preocupes! Con "
            "nosotros tienes la oportunidad de acceder a tu crédito y tener una "
            "segunda oportunidad.\n"
            "Te apoyamos para que cumplas tus metas con nuestras dos líneas "
            "principales:\n"
            "✅ Créditos para lo que necesites: Libre inversión, viajes, estudio, "
            "remodelación o ese proyecto que tienes en mente.\n"
            "✅ Compra de Cartera: Si tienes deudas con otras entidades, podemos "
            "unificarlas para mejorar tus finanzas (sujeto a tu capacidad de pago).\n"
            "🌐 ¿Quieres simular tu crédito o conocer más de nosotros? Revisa toda "
            "nuestra información ingresando a www.proalto.co"
        )
        WhatsAppService.send_message(user_phone, intro)
        sections = [{
            "title": "Información General",
            "rows": [
                {"id": "info_requisitos", "title": "Requisitos",
                 "description": "Documentos que necesitas para tu crédito."},
                {"id": "info_tasas", "title": "Tasas",
                 "description": "Nuestras tasas y cuotas fijas mensuales."},
                {"id": "info_montos", "title": "Montos y plazos",
                 "description": "Cuánto puedes solicitar y en qué condiciones."},
                {"id": "info_asesor", "title": "Hablar con un asesor",
                 "description": "Te atiende una persona del equipo."},
            ],
        }]
        WhatsAppService.send_interactive_list(
            user_phone,
            "Selecciona una opción para conocer más.",
            "Ver opciones",
            sections,
        )

    @staticmethod
    def send_mi_credito_menu(user_phone):
        # Nivel 2C — "Mi Crédito ProAlto": primero el mensaje y LUEGO la lista.
        intro = (
            "¡Qué bueno tenerte por aquí de nuevo! 🤝 En esta sección puedes "
            "gestionar todo lo relacionado con tu crédito actual."
        )
        WhatsAppService.send_message(user_phone, intro)
        sections = [{
            "title": "Mi Crédito ProAlto",
            "rows": [
                {"id": "cred_estado", "title": "Estado de mi solicitud",
                 "description": "Revisa en qué etapa va tu crédito."},
                {"id": "cred_saldo", "title": "Consulta de saldo",
                 "description": "Conoce un saldo aproximado de tu deuda."},
                {"id": "cred_paz", "title": "Paz y Salvo",
                 "description": "Solicita tu certificado de crédito al día."},
                {"id": "cred_asesor", "title": "Hablar con un asesor",
                 "description": "Recibe ayuda personalizada para tu caso."},
            ],
        }]
        WhatsAppService.send_interactive_list(
            user_phone,
            "Selecciona qué quieres gestionar.",
            "Gestionar",
            sections,
        )

    @staticmethod
    def send_client_menu(user_phone):
        menu_text = "Qué deseas hacer hoy?"
        buttons = [
            {"id": "menu_saldo", "title": "Consultar Saldo"},
            {"id": "menu_support", "title": "Hablar con Asesor"},
            {"id": "menu_main", "title": "Volver al Inicio"}
        ]
        WhatsAppService.send_interactive_button(user_phone, menu_text, buttons)
