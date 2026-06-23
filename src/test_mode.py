"""
Modo Test del bot de WhatsApp ProAlto.

Permite ejecutar el pipeline completo (flows.py, LLM, Cloud Run) sin escribir
en Supabase, sin enviar nada a Meta y sin notificar admins. Se activa cuando
el `phone` empieza con TEST_PHONE_PREFIX.

Funciona como sustituto en memoria de:
  - bot_conversations  (state, client_name, solicitud_context, docs_completos,
                        ultima_actualizacion_datos)
  - bot_messages       (historial de inbound/outbound)
  - llm_requests, captured_emails, captured_cuentas, received_documents,
    contact_data_updates  (solo contadores; el contenido se descarta)
  - WhatsApp send       (los outbound se acumulan en un buffer por sesión)
  - notify_admin_*      (no se envían; quedan marcadas en el buffer)
"""
import threading
import uuid
from datetime import datetime, timedelta


TEST_PHONE_PREFIX = "__test_"

# Sesiones inactivas más antiguas que esto se purgan al registrar una nueva.
_SESSION_TTL = timedelta(hours=2)

_lock = threading.RLock()
_sessions: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now().isoformat()


def is_test_phone(phone) -> bool:
    return isinstance(phone, str) and phone.startswith(TEST_PHONE_PREFIX)


def _new_session() -> dict:
    return {
        "state": "pending_consent",
        "client_name": "",
        "agent_mode": None,
        "docs_completos": False,
        "ultima_actualizacion_datos": None,
        "solicitud_context": {},
        "contact_update": None,   # dict in progress
        "captured_email": None,
        "captured_cuenta_count": 0,
        "received_documents_count": 0,
        "llm_requests_count": 0,
        "document_requests_count": 0,
        "history": [],            # list of {direction, text, msg_type, created_at}
        "outbound": [],           # list pending to drain by the panel
        "last_template": None,    # última plantilla de campaña inyectada
        "created_at": _now_iso(),
        "last_activity": _now_iso(),
    }


def _gc_locked():
    cutoff = datetime.now() - _SESSION_TTL
    stale = []
    for phone, s in _sessions.items():
        try:
            last = datetime.fromisoformat(s.get("last_activity") or s["created_at"])
        except Exception:
            last = datetime.now()
        if last < cutoff:
            stale.append(phone)
    for phone in stale:
        _sessions.pop(phone, None)


def register_session() -> str:
    """Crea un nuevo phone de prueba y devuelve su identificador."""
    test_phone = f"{TEST_PHONE_PREFIX}{uuid.uuid4().hex[:10]}"
    with _lock:
        _gc_locked()
        _sessions[test_phone] = _new_session()
    return test_phone


def unregister_session(phone: str) -> None:
    if not is_test_phone(phone):
        return
    with _lock:
        _sessions.pop(phone, None)


def reset_session(phone: str) -> bool:
    """Resetea el estado pero mantiene el phone registrado."""
    if not is_test_phone(phone):
        return False
    with _lock:
        if phone not in _sessions:
            return False
        _sessions[phone] = _new_session()
    return True


def _touch_locked(phone: str) -> dict | None:
    s = _sessions.get(phone)
    if s is None:
        return None
    s["last_activity"] = _now_iso()
    return s


def _ensure_locked(phone: str) -> dict:
    """Devuelve la sesión; si no existe (el caller llamó con un test_phone
    válido pero no registrado), la crea sobre la marcha para no perder estado."""
    s = _sessions.get(phone)
    if s is None:
        s = _new_session()
        _sessions[phone] = s
    s["last_activity"] = _now_iso()
    return s


def session_exists(phone: str) -> bool:
    if not is_test_phone(phone):
        return False
    with _lock:
        return phone in _sessions


# ── Estado por phone ─────────────────────────────────────────────────

def get_state(phone: str) -> str:
    with _lock:
        s = _ensure_locked(phone)
        return s["state"]


def set_state(phone: str, state: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["state"] = state


def get_last_template(phone: str):
    """Última plantilla de campaña inyectada en esta sesión (o None)."""
    with _lock:
        s = _ensure_locked(phone)
        return s.get("last_template")


def get_client_name(phone: str) -> str:
    with _lock:
        s = _ensure_locked(phone)
        return s["client_name"] or "Cliente"


def set_client_name(phone: str, name: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["client_name"] = name or ""


def get_solicitud_context(phone: str) -> dict:
    with _lock:
        s = _ensure_locked(phone)
        return dict(s["solicitud_context"])


def set_solicitud_context(phone: str, empresa: str, docs_faltantes: str, tipo_empleador: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["solicitud_context"] = {
            "empresa": empresa or "",
            "docs_faltantes": docs_faltantes or "",
            "tipo_empleador": tipo_empleador or "EMPRESA",
        }


def mark_docs_completos(phone: str, value: bool = True) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["docs_completos"] = bool(value)


def get_last_contact_update_date(phone: str):
    with _lock:
        s = _ensure_locked(phone)
        return s.get("ultima_actualizacion_datos")


# ── Captures sin contenido ──────────────────────────────────────────

def record_captured_email(phone: str, email: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["captured_email"] = email


def get_captured_email(phone: str):
    with _lock:
        s = _ensure_locked(phone)
        return s.get("captured_email")


def record_captured_cuenta(phone: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["captured_cuenta_count"] += 1


def record_received_document(phone: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["received_documents_count"] += 1


def count_received_documents(phone: str) -> int:
    with _lock:
        s = _ensure_locked(phone)
        return s["received_documents_count"]


def record_llm_request(phone: str, tipo: str, detalle: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["llm_requests_count"] += 1
        s["outbound"].append({
            "type": "llm_request_recorded",
            "tipo": tipo,
            "detalle": (detalle or "")[:200],
            "created_at": _now_iso(),
        })


def record_document_request(phone: str, doc_type: str, source: str, detalle: str) -> None:
    with _lock:
        s = _ensure_locked(phone)
        s["document_requests_count"] += 1
        s["outbound"].append({
            "type": "document_request_recorded",
            "doc_type": doc_type,
            "source": source,
            "detalle": (detalle or "")[:200],
            "created_at": _now_iso(),
        })


# ── Contact update (yearly) ─────────────────────────────────────────

def start_contact_update(phone: str, trigger_source: str) -> bool:
    with _lock:
        s = _ensure_locked(phone)
        s["contact_update"] = {
            "status": "in_progress",
            "trigger_source": trigger_source,
            "started_at": _now_iso(),
        }
        return True


def update_contact_field(phone: str, field_name: str, value: str) -> bool:
    with _lock:
        s = _ensure_locked(phone)
        if not s.get("contact_update"):
            return False
        s["contact_update"][field_name] = value
        return True


def get_in_progress_contact_update(phone: str):
    with _lock:
        s = _ensure_locked(phone)
        cu = s.get("contact_update")
        if cu and cu.get("status") == "in_progress":
            return dict(cu)
        return None


def confirm_contact_update(phone: str) -> bool:
    with _lock:
        s = _ensure_locked(phone)
        cu = s.get("contact_update")
        if not cu:
            return False
        cu["status"] = "confirmed"
        cu["confirmed_at"] = _now_iso()
        s["ultima_actualizacion_datos"] = cu["confirmed_at"]
        return True


def abandon_contact_update(phone: str, reason: str = "abandoned") -> bool:
    with _lock:
        s = _ensure_locked(phone)
        cu = s.get("contact_update")
        if not cu:
            return False
        cu["status"] = reason
        return True


# ── Historial + outbound ────────────────────────────────────────────

def log_message(phone: str, direction: str, text: str, msg_type: str = "text") -> None:
    entry = {
        "direction": direction,
        "text": text,
        "msg_type": msg_type,
        "created_at": _now_iso(),
    }
    with _lock:
        s = _ensure_locked(phone)
        s["history"].append(entry)
        # Outbound real (lo que el bot envía) lo agregamos al buffer por
        # separado en append_outbound para no duplicar.


def append_outbound(phone: str, msg: dict) -> None:
    """Registra que el bot intentó enviar algo a este phone (texto, imagen,
    documento, botones, template o notificación a admin suprimida)."""
    entry = dict(msg)
    entry.setdefault("created_at", _now_iso())
    with _lock:
        s = _ensure_locked(phone)
        s["outbound"].append(entry)
        # también lo añadimos al historial para que el panel reconstruya bien
        s["history"].append({
            "direction": "outbound",
            "text": entry.get("body") or entry.get("text") or entry.get("type") or "",
            "msg_type": entry.get("type", "text"),
            "created_at": entry["created_at"],
        })


def drain_outbound(phone: str) -> list:
    """Vacía el buffer outbound y lo devuelve. El historial NO se vacía."""
    with _lock:
        s = _ensure_locked(phone)
        items = s["outbound"]
        s["outbound"] = []
        return items


def get_recent_messages_for_llm(phone: str, limit: int = 6) -> list:
    """Reemplazo en memoria del helper de conversation_log para LLM context."""
    with _lock:
        s = _ensure_locked(phone)
        history = list(s["history"])
    messages = []
    for m in history[-limit:]:
        role = "user" if m["direction"] == "inbound" else "assistant"
        text = m["text"] or ""
        if m.get("msg_type") in ("image", "document"):
            text = "[Archivo enviado]"
        elif len(text) > 300:
            text = text[:300] + "..."
        messages.append({"role": role, "content": text})
    # Colapsar consecutivos del mismo rol (Anthropic requiere alternar)
    merged = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append({"role": msg["role"], "content": msg["content"]})
    return merged


# ── Templates de Meta (simulación de flujo) ─────────────────────────
#
# El texto real de cada template vive en el administrador de Meta; aquí solo
# guardamos un cuerpo representativo (con parámetros de ejemplo), el estado que
# el envío real deja en la conversación (ver src/automation.py) y los botones
# de respuesta rápida que disparan el flujo. El `id` de cada botón es la clave
# exacta que `FlowHandler.process_button_click` enruta (a veces el título del
# botón, a veces un id interno); el `title` es solo la etiqueta visible.

# Cuerpos transcritos verbatim del WhatsApp Manager de Meta (capturas jun/2026).
# El `*texto*` es el marcador de negrilla del template (Meta lo renderiza en
# bold; el panel lo muestra literal). Las variables van como {nombre}/{monto}/…
# y se sustituyen con los valores de `sample` al renderizar.
TEMPLATES = {
    "estado_verde": {
        "label": "Aprobado por el cliente (estado_verde)",
        "state": "waiting_for_email",
        "body": ("¡Hola {nombre} ! \U0001f389 Tu solicitud de crédito ha sido *Aprobada*.\n"
                 "Monto \U0001f4b0 {monto}\n"
                 "Plazo ⏱️ {plazo}\n"
                 "Cuota \U0001f4b5 {cuota}\n"
                 "Para continuar, por favor confírmanos tu *correo electrónico* \U0001f4e9. "
                 "A esa dirección te enviaremos el contrato para firma electrónica y así "
                 "proceder con el desembolso."),
        "sample": {"nombre": "Carlos", "monto": "$10.000.000", "plazo": "36 meses", "cuota": "$380.000"},
        "buttons": [
            {"id": "Acepto las condiciones", "title": "Acepto las condiciones"},
        ],
    },
    "contacto_leads": {
        "label": "Campaña Leads (contacto_leads)",
        "state": "lead_notified",
        "header": "Oportunidad de Crédito",
        "body": ("¡Hola {nombre}! \U0001f31f En ProAlto queremos ayudarte a cumplir tus metas. "
                 "Tenemos opciones de crédito disponibles para ti con aprobación rápida y sin "
                 "tantos trámites.\n\n"
                 "¿Te gustaría iniciar tu proceso ahora mismo?"),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "Solicitar crédito", "title": "Solicitar crédito"},
            {"id": "Ahora no, gracias", "title": "Ahora no, gracias"},
            {"id": "Necesito más información", "title": "Necesito más información"},
        ],
    },
    "anticipo_salario": {
        "label": "Campaña Anticipos (anticipo_salario)",
        "state": "anticipos_notified",
        "body": ("¡Hola {nombre}! En ProAlto te adelantamos tu nómina. \U0001f680 "
                 "Recibe tu dinero en máximo 24 horas hábiles para lo que necesites."),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "Solicitar Anticipo", "title": "Solicitar Anticipo"},
            {"id": "Ahora no, gracias", "title": "Ahora no, gracias"},
            {"id": "¿Cómo funciona?", "title": "¿Cómo funciona?"},
        ],
    },
    "estado_renovar": {
        "label": "Campaña Renovados (estado_renovar)",
        "state": "renovado_notified",
        "body": ("¡Hola! {nombre}\U0001f44b\U0001f3fb\n\n"
                 "En ProAlto premiamos tu fidelidad\U0001f60a, se acerca el final de tu crédito "
                 "actual y tienes la oportunidad de renovarlo y acceder a tasas competitivas, "
                 "plazos flexibles y un servicio ajustado a tus necesidades."),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "Solicitar crédito", "title": "Solicitar crédito"},
            {"id": "No lo quiero", "title": "No lo quiero"},
            {"id": "Necesito más información", "title": "Necesito más información"},
        ],
    },
    "estado_rojo": {
        "label": "Falta documento (estado_rojo)",
        "state": "waiting_for_docs_rojo",
        "body": ("Hola {nombre}, tu proceso de crédito está detenido porque nos faltan "
                 "algunos documentos para continuar.\n\n"
                 "Envíanos los documentos directamente por este chat y nuestro equipo los "
                 "revisará."),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "Consultar documentos", "title": "Consultar documentos"},
        ],
    },
    "estado_amarillo": {
        "label": "Listo en PandaDoc (estado_amarillo)",
        "state": "waiting_for_cuenta_amarillo",
        "body": ("Hola {nombre} Tu solicitud ha avanzado con éxito a la fase final del "
                 "proceso. \U0001f4dd\n\n"
                 "Para ir adelantando la gestión del desembolso y agilizar los tiempos, por "
                 "favor envíanos tu *número de cuenta* y el *banco*\n\n"
                 "*Importante*: Si la cuenta no te pertenece, para poder validarla necesitamos "
                 "que nos adjuntes:\n\n"
                 "Nombre completo del titular.\n"
                 "Foto de la cédula del titular.\n"
                 "Número y tipo de cuenta.\n\n"
                 "Estamos trabajando para completar tu proceso lo antes posible."),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "Enviar Cuenta propia", "title": "Enviar Cuenta propia"},
            {"id": "Enviar Cuenta de tercero", "title": "Enviar Cuenta de tercero"},
        ],
    },
    "estado_negados": {
        "label": "Créditos negados (estado_negados)",
        "state": "denegado_notified",
        "body": ("Hola {nombre}, te escribimos de ProAlto.\n\n"
                 "Luego de evaluar tu solicitud de crédito, lamentamos informarte que en "
                 "este momento no nos es posible aprobarla, ya que no cumple con los requisitos "
                 "mínimos de nuestras políticas de crédito.\n\n"
                 "Agradecemos el interés y la confianza que depositaste en nosotros. "
                 "Esperamos poder ayudarte en el futuro. \U0001f64f"),
        "sample": {"nombre": "Carlos"},
        "buttons": [],
    },
    "actualizacion_datos": {
        "label": "Actualización de datos (actualizacion_datos)",
        "state": "esperando_respuesta_actualizacion",
        "body": ("Hola {nombre}, es momento de actualizar tus datos de contacto "
                 "para mantener tu información al día."),
        "sample": {"nombre": "Carlos"},
        "buttons": [
            {"id": "update_data_yes", "title": "Actualizar ahora"},
            {"id": "update_data_no", "title": "Más tarde"},
        ],
    },
}


def list_templates() -> list:
    """Lista de {name, label} para poblar el selector del panel."""
    return [{"name": name, "label": tpl["label"]} for name, tpl in TEMPLATES.items()]


def _render_template_body(tpl: dict) -> str:
    body = tpl["body"]
    for k, v in tpl.get("sample", {}).items():
        body = body.replace("{" + k + "}", v)
    header = tpl.get("header")
    if header:
        body = f"{header}\n\n{body}"
    return body


def inject_template(phone: str, name: str) -> dict | None:
    """Simula la recepción de un template de Meta: deja la conversación en el
    estado que dejaría el envío real y encola el cuerpo + botones como outbound,
    de modo que al pulsar un botón se dispare el flujo correspondiente.

    Devuelve la definición renderizada o None si el template no existe."""
    if not is_test_phone(phone):
        return None
    tpl = TEMPLATES.get(name)
    if not tpl:
        return None
    rendered = _render_template_body(tpl)
    with _lock:
        s = _ensure_locked(phone)
        s["state"] = tpl["state"]
        s["last_template"] = name
    append_outbound(phone, {
        "type": "interactive",
        "body": rendered,
        "buttons": list(tpl["buttons"]),
        "template_name": name,
    })
    return {
        "name": name,
        "label": tpl["label"],
        "body": rendered,
        "buttons": list(tpl["buttons"]),
        "state": tpl["state"],
    }


# ── Snapshot para debug en el panel ─────────────────────────────────

def snapshot(phone: str) -> dict:
    with _lock:
        s = _ensure_locked(phone)
        return {
            "test_phone": phone,
            "state": s["state"],
            "client_name": s["client_name"],
            "docs_completos": s["docs_completos"],
            "ultima_actualizacion_datos": s["ultima_actualizacion_datos"],
            "solicitud_context": dict(s["solicitud_context"]),
            "contact_update": dict(s["contact_update"]) if s.get("contact_update") else None,
            "captured_email": s.get("captured_email"),
            "captured_cuenta_count": s["captured_cuenta_count"],
            "received_documents_count": s["received_documents_count"],
            "llm_requests_count": s["llm_requests_count"],
            "document_requests_count": s.get("document_requests_count", 0),
            "history_length": len(s["history"]),
        }


def is_llm_pending(phone: str) -> bool:
    """Consulta el dict de flows para saber si el thread del LLM sigue
    corriendo para este phone."""
    if not is_test_phone(phone):
        return False
    try:
        from src import flows  # import perezoso para evitar ciclo
        return bool(flows._llm_active.get(phone))
    except Exception:
        return False
