"""
Registro central de fallos del bot para el panel de Diagnóstico (/admin).

Guarda en memoria los últimos eventos de error (envíos a Meta fallidos,
entregas fallidas, errores de Supabase, Cloud Run, LLM o de código) y los
clasifica por ORIGEN, con una guía de acción para el equipo que gestiona el
bot: cuándo solo hay que esperar (caída de Meta), cuándo hay que usar una
plantilla (ventana de 24h) y cuándo requiere intervención técnica.

Es un buffer en memoria (no Supabase): sobrevive lo suficiente para
diagnosticar un incidente en curso. Un reinicio de Render lo limpia, lo cual
es aceptable porque el panel también detecta el caso "servidor caído" por sí
mismo (si este módulo no responde, el problema es Render).
"""
import threading
from collections import deque
from datetime import datetime, timedelta

import requests

from config import Config


_lock = threading.Lock()
_events: deque = deque(maxlen=300)

# ── Categorías de fallo ──────────────────────────────────────────────
# accion: "esperar"   → no requiere intervención, se resuelve solo
#         "gestionar" → lo resuelve el equipo desde el panel (sin código)
#         "intervenir"→ requiere intervención técnica (Carlos / config)
CATEGORIES = {
    "meta_caida": {
        "origen": "Meta / WhatsApp",
        "titulo": "Caída temporal de Meta",
        "accion": "esperar",
        "que_hacer": "Falla en los servidores de WhatsApp/Meta. El bot reintenta cada envío "
                     "automáticamente. No hay nada que hacer de nuestro lado: esperar a que Meta "
                     "se restablezca (suele ser cuestión de minutos). Si persiste más de 30 "
                     "minutos, verificar metastatus.com y avisar a los asesores que respondan "
                     "manualmente desde el celular del negocio si es urgente.",
    },
    "red": {
        "origen": "Red / Render",
        "titulo": "Problema de red del servidor",
        "accion": "esperar",
        "que_hacer": "El servidor (Render) no logró conectarse con Meta (timeout o conexión "
                     "rechazada). El bot reintenta automáticamente. Si solo son casos aislados, "
                     "esperar. Si TODOS los envíos fallan por más de 15 minutos, revisar el "
                     "estado de Render (status.render.com) o contactar a Carlos.",
    },
    "meta_token": {
        "origen": "Meta / WhatsApp",
        "titulo": "Token o permisos de Meta",
        "accion": "intervenir",
        "que_hacer": "Meta rechazó la autenticación del bot (token vencido, revocado o sin "
                     "permisos). El bot NO va a poder enviar nada hasta corregirlo. Requiere "
                     "intervención: renovar el API_TOKEN en Render. Contactar a Carlos.",
    },
    "meta_limite": {
        "origen": "Meta / WhatsApp",
        "titulo": "Límite de envíos de Meta",
        "accion": "esperar",
        "que_hacer": "Meta está limitando la velocidad o cantidad de envíos de la cuenta. "
                     "Normalmente se resuelve solo en minutos u horas. Pausar campañas masivas "
                     "si hay alguna corriendo. Si pasa todos los días, contactar a Carlos para "
                     "revisar los límites de la cuenta.",
    },
    "meta_ventana": {
        "origen": "Meta / WhatsApp",
        "titulo": "Ventana de 24 horas cerrada",
        "accion": "gestionar",
        "que_hacer": "No es una falla: WhatsApp solo permite mensajes libres dentro de las 24 "
                     "horas siguientes al último mensaje del cliente. Para retomar la "
                     "conversación hay que enviar una PLANTILLA aprobada (desde las campañas del "
                     "panel) o esperar a que el cliente escriba de nuevo.",
    },
    "meta_entrega": {
        "origen": "Meta / WhatsApp",
        "titulo": "Mensaje no entregado al cliente",
        "accion": "gestionar",
        "que_hacer": "Meta aceptó el mensaje pero no pudo entregarlo al teléfono del cliente "
                     "(número inválido, sin WhatsApp, o el cliente bloqueó al negocio). No es "
                     "falla del sistema: verificar el número o contactar al cliente por otro "
                     "medio.",
    },
    "meta_payload": {
        "origen": "Bot (código)",
        "titulo": "Mensaje rechazado por Meta",
        "accion": "intervenir",
        "que_hacer": "Meta rechazó el formato del mensaje que el bot intentó enviar (error en el "
                     "código o plantilla mal configurada). Reintentar no sirve. Requiere "
                     "intervención: contactar a Carlos con la hora del error.",
    },
    "supabase": {
        "origen": "Supabase",
        "titulo": "Error guardando en Supabase",
        "accion": "intervenir",
        "que_hacer": "Falló la escritura/lectura en Supabase (historial y estados de chat). Los "
                     "mensajes pueden estar saliendo bien aunque no se vean en el panel. Revisar "
                     "status.supabase.com; si Supabase está OK y el error persiste, contactar a "
                     "Carlos.",
    },
    "cloud_run": {
        "origen": "Cloud Run (base de datos)",
        "titulo": "Error consultando la base de solicitudes",
        "accion": "esperar",
        "que_hacer": "Falló la consulta a la base de datos de solicitudes (Cloud Run/GCP). El "
                     "bot responde al cliente que intente más tarde. Si son casos aislados, "
                     "esperar. Si persiste más de 15 minutos, contactar a Carlos.",
    },
    "llm": {
        "origen": "Agente LLM (Anthropic)",
        "titulo": "Error del agente LLM",
        "accion": "esperar",
        "que_hacer": "El agente de IA no pudo generar respuesta (límite de uso o caída de "
                     "Anthropic). El bot queda en silencio con ese cliente: un asesor puede "
                     "responder manualmente tomando el control del chat. Si persiste más de 30 "
                     "minutos, contactar a Carlos (puede ser crédito agotado de la API).",
    },
    "codigo": {
        "origen": "Bot (código)",
        "titulo": "Error interno del bot",
        "accion": "intervenir",
        "que_hacer": "Error inesperado en el código del bot. Requiere intervención: contactar a "
                     "Carlos indicando la hora y el teléfono del cliente afectado.",
    },
}


def record_event(category: str, detail: str, phone: str = None,
                 http_status: int = None, meta_code=None):
    """Registra un evento de fallo. Nunca lanza excepción (es instrumentación)."""
    try:
        if category not in CATEGORIES:
            category = "codigo"
        with _lock:
            _events.appendleft({
                "timestamp": datetime.now().isoformat(),
                "category": category,
                "detail": str(detail)[:300],
                "phone": phone,
                "http_status": http_status,
                "meta_code": meta_code,
            })
    except Exception as e:
        print(f"[DIAG] No se pudo registrar evento: {e}")


def get_events(limit: int = 100) -> list:
    """Eventos recientes (más nuevos primero) con su categoría expandida."""
    with _lock:
        events = list(_events)[:limit]
    out = []
    for ev in events:
        cat = CATEGORIES.get(ev["category"], CATEGORIES["codigo"])
        out.append({**ev, **cat})
    return out


def get_summary(minutes: int = 60) -> dict:
    """Conteo de eventos recientes por acción requerida (para el resumen del panel)."""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    counts = {"esperar": 0, "gestionar": 0, "intervenir": 0, "total": 0}
    with _lock:
        for ev in _events:
            try:
                if datetime.fromisoformat(ev["timestamp"]) < cutoff:
                    break  # deque ordenada: lo más nuevo primero
            except ValueError:
                continue
            accion = CATEGORIES.get(ev["category"], CATEGORIES["codigo"])["accion"]
            counts[accion] = counts.get(accion, 0) + 1
            counts["total"] += 1
    return counts


# ── Clasificación de errores de envío a Meta ─────────────────────────

def _meta_error_code(response) -> tuple:
    """Extrae (code, message) del JSON de error de Meta, si existe."""
    try:
        err = response.json().get("error", {})
        return err.get("code"), err.get("message", "")
    except Exception:
        return None, (response.text[:200] if response is not None else "")


def classify_send_exception(exc) -> dict:
    """Clasifica una excepción de requests al enviar a Meta.

    Devuelve {category, detail, http_status, meta_code, retryable}.
    retryable=True → vale la pena reintentar (5xx, red, rate limit).
    """
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return {"category": "red", "detail": f"{type(exc).__name__}: {exc}",
                "http_status": None, "meta_code": None, "retryable": True}

    response = getattr(exc, "response", None)
    if response is None:
        return {"category": "codigo", "detail": str(exc),
                "http_status": None, "meta_code": None, "retryable": False}

    status = response.status_code
    code, msg = _meta_error_code(response)
    detail = f"HTTP {status} — código Meta {code}: {msg}" if code else f"HTTP {status}: {msg}"

    if status >= 500:
        return {"category": "meta_caida", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": True}
    if status == 429 or code in (4, 80007, 130429, 131048, 131056):
        return {"category": "meta_limite", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": True}
    if status == 401 or code in (190, 0, 3, 10, 200):
        return {"category": "meta_token", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": False}
    if code == 131026:
        # "Message Undeliverable": el destinatario no puede recibir (sin WhatsApp,
        # ToS no aceptados, número inválido). NO es la ventana de 24h.
        return {"category": "meta_entrega", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": False}
    if code in (131047, 131021, 131051):
        return {"category": "meta_ventana", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": False}
    if status == 403:
        return {"category": "meta_token", "detail": detail,
                "http_status": status, "meta_code": code, "retryable": False}
    return {"category": "meta_payload", "detail": detail,
            "http_status": status, "meta_code": code, "retryable": False}


def classify_delivery_failure(meta_code) -> str:
    """Categoría para un status 'failed' que llega por webhook (entrega fallida)."""
    if meta_code in (131047, 131051):
        return "meta_ventana"
    if meta_code in (130429, 131048, 131056, 80007, 4):
        return "meta_limite"
    if meta_code in (131009, 100, 131008):
        return "meta_payload"
    return "meta_entrega"


# ── Health checks en vivo (los consume /admin/api/diagnostics) ──────

def check_meta() -> dict:
    """Consulta de solo lectura a la Graph API para verificar token y disponibilidad."""
    url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}"
    try:
        r = requests.get(url, params={"fields": "id"},
                         headers={"Authorization": f"Bearer {Config.API_TOKEN}"},
                         timeout=8)
        if r.status_code == 200:
            return {"estado": "ok", "detalle": "API de WhatsApp respondiendo con normalidad."}
        if r.status_code in (401, 403):
            return {"estado": "caido",
                    "detalle": f"Token rechazado por Meta (HTTP {r.status_code}).",
                    "que_hacer": CATEGORIES["meta_token"]["que_hacer"]}
        if r.status_code >= 500:
            return {"estado": "caido",
                    "detalle": f"Meta devuelve error interno (HTTP {r.status_code}).",
                    "que_hacer": CATEGORIES["meta_caida"]["que_hacer"]}
        return {"estado": "alerta", "detalle": f"Respuesta inesperada de Meta (HTTP {r.status_code})."}
    except requests.exceptions.RequestException as e:
        return {"estado": "caido",
                "detalle": f"No se pudo contactar a Meta: {type(e).__name__}.",
                "que_hacer": CATEGORIES["red"]["que_hacer"]}


def check_supabase() -> dict:
    """Lectura mínima a Supabase (historial y estados de chat)."""
    try:
        from src.conversation_log import supabase_client
        if not supabase_client:
            return {"estado": "caido", "detalle": "Cliente de Supabase no inicializado (revisar SUPABASE_URL/KEY).",
                    "que_hacer": CATEGORIES["supabase"]["que_hacer"]}
        supabase_client.table("bot_conversations").select("phone").limit(1).execute()
        return {"estado": "ok", "detalle": "Supabase respondiendo con normalidad."}
    except Exception as e:
        return {"estado": "caido", "detalle": f"Error consultando Supabase: {str(e)[:150]}",
                "que_hacer": CATEGORIES["supabase"]["que_hacer"]}


def check_cloud_run() -> dict:
    """Consulta liviana al bridge de Cloud Run (base de solicitudes)."""
    import os
    cloud_run_url = os.getenv("CLOUD_RUN_URL", "").rstrip("/")
    token = os.getenv("API_TOKEN_SECRET", "")
    if not cloud_run_url:
        return {"estado": "alerta", "detalle": "CLOUD_RUN_URL no configurada."}
    try:
        r = requests.post(cloud_run_url, json={"cedula": "0"},
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                          timeout=8)
        if r.status_code == 200:
            return {"estado": "ok", "detalle": "Base de solicitudes respondiendo con normalidad."}
        if r.status_code == 401:
            return {"estado": "caido", "detalle": "Cloud Run rechazó la autenticación (API_TOKEN_SECRET).",
                    "que_hacer": CATEGORIES["cloud_run"]["que_hacer"]}
        return {"estado": "alerta", "detalle": f"Cloud Run respondió HTTP {r.status_code}.",
                "que_hacer": CATEGORIES["cloud_run"]["que_hacer"]}
    except requests.exceptions.RequestException as e:
        return {"estado": "caido", "detalle": f"No se pudo contactar Cloud Run: {type(e).__name__}.",
                "que_hacer": CATEGORIES["cloud_run"]["que_hacer"]}


def check_llm() -> dict:
    """Check pasivo del agente LLM: clave configurada + errores recientes registrados.

    No hace una llamada real a Anthropic (cuesta tokens); se apoya en los
    eventos que registra ask_llm cuando falla.
    """
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"estado": "caido", "detalle": "ANTHROPIC_API_KEY no configurada.",
                "que_hacer": CATEGORIES["llm"]["que_hacer"]}
    cutoff = datetime.now() - timedelta(minutes=30)
    with _lock:
        recent_errors = sum(
            1 for ev in _events
            if ev["category"] == "llm"
            and datetime.fromisoformat(ev["timestamp"]) >= cutoff
        )
    if recent_errors >= 3:
        return {"estado": "caido",
                "detalle": f"{recent_errors} fallos del LLM en los últimos 30 minutos.",
                "que_hacer": CATEGORIES["llm"]["que_hacer"]}
    if recent_errors > 0:
        return {"estado": "alerta",
                "detalle": f"{recent_errors} fallo(s) del LLM en los últimos 30 minutos.",
                "que_hacer": CATEGORIES["llm"]["que_hacer"]}
    return {"estado": "ok", "detalle": "Sin fallos recientes del agente LLM."}
