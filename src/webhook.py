import time
import hmac
import hashlib
from flask import Blueprint, request, jsonify, current_app
from config import Config
from src.flows import FlowHandler

webhook_bp = Blueprint('webhook', __name__)

# ── Deduplication cache ──────────────────────────────────────────────
# Stores { message_id: timestamp } to avoid processing the same
# webhook delivery twice (Meta sometimes retries or sends duplicates).
_processed_messages: dict[str, float] = {}
_DEDUP_TTL_SECONDS = 300  # keep IDs for 5 minutes, then forget them


def _is_duplicate(message_id: str) -> bool:
    """Return True if we already processed this message_id recently."""
    now = time.time()

    # Purge expired entries (simple housekeeping)
    expired = [mid for mid, ts in _processed_messages.items()
               if now - ts > _DEDUP_TTL_SECONDS]
    for mid in expired:
        del _processed_messages[mid]

    if message_id in _processed_messages:
        return True

    _processed_messages[message_id] = now
    return False


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
    """Verify X-Hub-Signature-256 from Meta. Returns True if valid or APP_SECRET not configured."""
    app_secret = Config.APP_SECRET
    if not app_secret:
        return True  # Si no está configurado, no bloquea (modo permisivo)

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
        print("⚠️  Webhook rejected: invalid X-Hub-Signature-256")
        return jsonify({"status": "unauthorized"}), 401

    try:
        data = request.get_json()
        print(f"Received webhook data: {data}") # Debug logging

        # ── Extract message_id for deduplication ──────────────────
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            if messages:
                msg_id = messages[0].get("id", "")
                if msg_id and _is_duplicate(msg_id):
                    print(f"⏭️  Duplicate message ignored: {msg_id}")
                    return jsonify({"status": "duplicate_ignored"}), 200
        except (IndexError, KeyError):
            pass  # If extraction fails, continue processing normally

        FlowHandler.handle_incoming_message(data)
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error in webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
