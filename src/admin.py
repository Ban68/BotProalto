"""
Admin Dashboard Blueprint for ProAlto WhatsApp Bot.
Provides conversation monitoring and live agent intervention.
"""
import functools
from flask import (
    Blueprint, request, jsonify, render_template,
    Response, current_app
)
from config import Config
from src.conversation_log import (
    get_conversations, get_conversation,
    set_agent_mode, log_message, delete_conversation,
    get_archived_conversations, restore_conversation
)
from src.services import WhatsAppService
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__, template_folder='../templates')

# Track active advisors { "advisor_name": last_seen_datetime }
active_advisors = {}


# ── HTTP Basic Auth ──────────────────────────────────────────────────
def check_auth(username, password):
    """Verify admin credentials."""
    return username == Config.ADMIN_USER and password == Config.ADMIN_PASS


def authenticate():
    """Send a 401 response to prompt for credentials."""
    return Response(
        'Acceso no autorizado. Por favor ingresa tus credenciales.',
        401,
        {'WWW-Authenticate': 'Basic realm="ProAlto Admin"'}
    )


def requires_auth(f):
    """Decorator that requires HTTP Basic Auth."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ── Page Routes ──────────────────────────────────────────────────────

@admin_bp.route('/admin/')
@requires_auth
def dashboard():
    """Main admin dashboard page."""
    return render_template('admin.html')


# ── API Routes ───────────────────────────────────────────────────────

@admin_bp.route('/admin/api/presence', methods=['POST'])
@requires_auth
def api_presence():
    """Receive heartbeat from client and return active advisors with their current chat."""
    body = request.get_json() or {}
    advisor_name = body.get("advisor_name", "").strip()
    current_chat = body.get("current_chat") # Can be null
    
    now = datetime.utcnow()
    
    if advisor_name:
        active_advisors[advisor_name] = {
            "last_seen": now,
            "current_chat": current_chat
        }
        
    # Clean up stale advisors (inactive for > 30 seconds)
    stale_threshold = now - timedelta(seconds=30)
    to_remove = [name for name, info in active_advisors.items() if info["last_seen"] < stale_threshold]
    for name in to_remove:
        del active_advisors[name]
    
    # Format response: list of {name, current_chat}
    response_data = [
        {"name": name, "current_chat": info["current_chat"]}
        for name, info in active_advisors.items()
    ]
        
    return jsonify({"active_advisors": response_data})


@admin_bp.route('/admin/api/conversations')
@requires_auth
def api_conversations():
    """Get list of all conversations."""
    return jsonify(get_conversations())


@admin_bp.route('/admin/api/conversations/<phone>')
@requires_auth
def api_conversation_detail(phone):
    """Get full conversation history for a phone number."""
    data = get_conversation(phone)
    if data is None:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify(data)


@admin_bp.route('/admin/api/send', methods=['POST'])
@requires_auth
def api_send_message():
    """Send a message as the advisor to a user."""
    body = request.get_json() or {}
    phone = body.get("phone", "").strip()
    text = body.get("text", "").strip()
    advisor_name = body.get("advisor_name", "Asesor ProAlto").strip()

    silent = body.get("silent", False)

    if not phone or not text:
        return jsonify({"error": "phone and text are required"}), 400

    # Ensure no other advisor is currently "holding" this chat
    for other_name, info in active_advisors.items():
        if other_name != advisor_name and info.get("current_chat") == phone:
            return jsonify({
                "error": f"Este chat está siendo atendido por {other_name} en este momento.",
                "owner": other_name
            }), 409

    # Prefix with advisor label unless silent mode is on
    if silent:
        advisor_msg = text
    else:
        advisor_msg = f"👨‍💼 *{advisor_name}:*\n{text}"
    
    result = WhatsAppService.send_message(phone, advisor_msg)

    if result:
        return jsonify({"status": "sent"})
    else:
        return jsonify({"error": "Failed to send message"}), 500


@admin_bp.route('/admin/api/close-agent/<phone>', methods=['POST'])
@requires_auth
def api_close_agent(phone):
    """Close agent mode and return user to the bot."""
    conv = get_conversation(phone)
    is_silent = False
    if conv and conv.get("status") == "agent_silent":
        is_silent = True

    set_agent_mode(phone, "active")

    if not is_silent:
        WhatsAppService.send_message(
            phone,
            "✅ Tu asesor ha finalizado la conversación.\n\n"
            "Escribe *Hola* para volver al menú principal."
        )

    return jsonify({"status": "closed"})


@admin_bp.route('/admin/api/force-agent/<phone>', methods=['POST'])
@requires_auth
def api_force_agent(phone):
    """Force agent mode from the dashboard to take over a conversation."""
    body = request.get_json() or {}
    advisor_name = body.get("advisor_name", "Un asesor").strip()
    silent = body.get("silent", False)
    
    # Ensure no other advisor is currently "holding" this chat
    for other_name, info in active_advisors.items():
        if other_name != advisor_name and info.get("current_chat") == phone:
            return jsonify({
                "error": f"Este chat está siendo atendido por {other_name} en este momento.",
                "owner": other_name
            }), 409
            
    set_agent_mode(phone, "agent_silent" if silent else "agent")

    if not silent:
        WhatsAppService.send_message(
            phone,
            "Dame un momento mientras reviso tu información y ya mismo te escribo."
        )

    return jsonify({"status": "forced", "silent": silent})


@admin_bp.route('/admin/api/create-chat', methods=['POST'])
@requires_auth
def api_create_chat():
    """Create a new empty conversation manually in agent mode."""
    body = request.get_json() or {}
    phone = body.get("phone", "").strip()
    
    # Strip any +, spaces or dashes from phone to ensure clean format
    import re
    phone = re.sub(r'\D', '', phone)

    if not phone:
        return jsonify({"error": "Valid phone number required"}), 400

    # Force agent mode natively
    set_agent_mode(phone, "agent")

    return jsonify({"status": "created", "phone": phone})


@admin_bp.route('/admin/api/delete-chat/<phone>', methods=['POST'])
@requires_auth
def api_delete_chat(phone):
    """Delete or hide conversation."""
    body = request.get_json() or {}
    permanent = body.get("permanent", False)
    delete_conversation(phone, permanent)
    return jsonify({"status": "deleted"})


@admin_bp.route('/admin/api/archived-conversations')
@requires_auth
def api_archived_conversations():
    """Get list of archived (hidden) conversations."""
    return jsonify(get_archived_conversations())


@admin_bp.route('/admin/api/restore-chat/<phone>', methods=['POST'])
@requires_auth
def api_restore_chat(phone):
    """Restore an archived conversation back to the active panel."""
    restore_conversation(phone)
    return jsonify({"status": "restored"})


@admin_bp.route('/admin/api/trigger-aprobados')
@requires_auth
def api_trigger_aprobados():
    """Manual trigger to test the send_approved_notifications automation."""
    from src.automation import send_approved_notifications
    try:
        send_approved_notifications()
        return jsonify({"status": "ok", "message": "Automatización ejecutada exitosamente en segundo plano."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
