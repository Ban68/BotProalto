import time
import hmac
import hashlib
import threading
from flask import Blueprint, request, jsonify, current_app
from config import Config
from src.flows import FlowHandler
from src import error_tracker
from src.conversation_log import log_message

webhook_bp = Blueprint('webhook', __name__)


def _process_failed_statuses(value: dict):
    """Registra entregas fallidas que Meta reporta via webhook de 'statuses'.

    Meta puede ACEPTAR un mensaje (devuelve wamid) y aun asi fallar la
    entrega despues (ventana de 24h cerrada, numero invalido, etc.). Ese
    fallo llega aqui. Los statuses sent/delivered/read se ignoran como antes.
    """
    for status in value.get("statuses", []):
        if status.get("status") != "failed":
            continue
        recipient = status.get("recipient_id", "")
        errors = status.get("errors", []) or [{}]
        err = errors[0]
        code = err.get("code")
        title = err.get("title", "")
        details = (err.get("error_data") or {}).get("details", "") or err.get("message", "")

        category = error_tracker.classify_delivery_failure(code)
        error_tracker.record_event(
            category,
            f"Entrega fallida reportada por Meta - codigo {code} ({title}): {details}",
            phone=recipient,
            meta_code=code,
        )
        log_message(
            recipient,
            "outbound",
            f"[Entrega fallida — código {code}] {title}: {details}",
            "failed",
            wamid=status.get("id"),
        )


# Deduplication cache. A message is marked as processed only after the flow
# completes, so Meta can retry if processing fails before completion.
_in_progress_messages: dict[str, float] = {}
_processed_messages: dict[str, float] = {}
_DEDUP_TTL_SECONDS = 300  # keep IDs for 5 minutes, then forget them
_dedup_lock = threading.Lock()
_signature_warning_logged = False


def _purge_dedup(now: float):
    expired_processed = [mid for mid, ts in _processed_messages.items()
                         if now - ts > _DEDUP_TTL_SECONDS]
    for mid in expired_processed:
        del _processed_messages[mid]
    expired_in_progress = [mid for mid, ts in _in_progress_messages.items()
                           if now - ts > _DEDUP_TTL_SECONDS]
    for mid in expired_in_progress:
        del _in_progress_messages[mid]


def _begin_processing(message_id: str) -> str:
    """Return accepted, duplicate_processed, or duplicate_in_progress."""
    if not message_id:
        return "accepted"
    now = time.time()
    with _dedup_lock:
        _purge_dedup(now)
        if message_id in _processed_messages:
            return "duplicate_processed"
        if message_id in _in_progress_messages:
            return "duplicate_in_progress"
        _in_progress_messages[message_id] = now
    return "accepted"


def _mark_processed(message_id: str):
    if not message_id:
        return
    now = time.time()
    with _dedup_lock:
        _purge_dedup(now)
        _in_progress_messages.pop(message_id, None)
        _processed_messages[message_id] = now


def _mark_failed(message_id: str):
    if not message_id:
        return
    with _dedup_lock:
        _in_progress_messages.pop(message_id, None)


def _mask_phone(phone: str) -> str:
    digits = "".join(filter(str.isdigit, str(phone or "")))
    if len(digits) <= 7:
        return "***"
    return f"{digits[:3]}***{digits[-4:]}"


def _short_id(value: str) -> str:
    text = str(value or "")
    return text if len(text) <= 24 else f"{text[:12]}...{text[-8:]}"


def _extract_value(data: dict) -> dict:
    entry = data.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    return changes.get("value", {}) or {}


def _log_webhook_summary(value: dict):
    messages = value.get("messages", []) or []
    statuses = value.get("statuses", []) or []
    if messages:
        msg = messages[0]
        print(
            "[WEBHOOK] message received "
            f"id={_short_id(msg.get('id'))} "
            f"type={msg.get('type', '')} "
            f"phone={_mask_phone(msg.get('from'))} "
            f"statuses={len(statuses)}"
        )
    elif statuses:
        status = statuses[0]
        print(
            "[WEBHOOK] status received "
            f"id={_short_id(status.get('id'))} "
            f"status={status.get('status', '')} "
            f"phone={_mask_phone(status.get('recipient_id'))} "
            f"count={len(statuses)}"
        )
    else:
        print("[WEBHOOK] event received messages=0 statuses=0")

@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Verification endpoint for Meta Webhook.
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == Config.WEBHOOK_VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            return 'Forbidden', 403
    return 'Bad Request', 400

def _verify_signature(request) -> bool:
    """Verify X-Hub-Signature-256 only when strict enforcement is enabled."""
    global _signature_warning_logged
    app_secret = Config.APP_SECRET
    if not Config.ENFORCE_WEBHOOK_SIGNATURE:
        if not app_secret and not _signature_warning_logged:
            print("[CONFIG] APP_SECRET no configurado: firma webhook no validada (modo permisivo).")
            _signature_warning_logged = True
        return True

    if not app_secret:
        print("[WEBHOOK] rejected: ENFORCE_WEBHOOK_SIGNATURE=true pero APP_SECRET no está configurado.")
        return False

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        return False

    received = signature_header[len("sha256="):]
    expected = hmac.new(
        app_secret.encode("utf-8"),
        request.get_data(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, received)


@webhook_bp.route('/webhook', methods=['POST'])
def receive_message():
    """
    Endpoint to receive messages from WhatsApp Cloud API.
    """
    if not _verify_signature(request):
        print("[WEBHOOK] rejected: invalid X-Hub-Signature-256")
        return jsonify({"status": "unauthorized"}), 401

    try:
        data = request.get_json(silent=True) or {}
        msg_id = ""

        # Extract message_id for deduplication and log only non-PII metadata.
        try:
            value = _extract_value(data)
            _log_webhook_summary(value)

            # Entregas fallidas (statuses): solo registro, no interrumpe el flujo
            try:
                _process_failed_statuses(value)
            except Exception as status_err:
                print(f"Error procesando statuses: {status_err}")

            messages = value.get("messages", [])
            if messages:
                msg_id = messages[0].get("id", "")
                dedup_status = _begin_processing(msg_id)
                if dedup_status == "duplicate_processed":
                    print(f"[WEBHOOK] duplicate processed ignored: {_short_id(msg_id)}")
                    return jsonify({"status": "duplicate_ignored"}), 200
                if dedup_status == "duplicate_in_progress":
                    print(f"[WEBHOOK] duplicate in-progress ignored: {_short_id(msg_id)}")
                    return jsonify({"status": "duplicate_in_progress"}), 200
        except (IndexError, KeyError):
            pass  # If extraction fails, continue processing normally

        try:
            FlowHandler.handle_incoming_message(data)
            _mark_processed(msg_id)
        except Exception:
            _mark_failed(msg_id)
            raise

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error in webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
