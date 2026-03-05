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
from src.flows import user_sessions

admin_bp = Blueprint('admin', __name__, template_folder='../templates')


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
    body = request.get_json()
    phone = body.get("phone", "").strip()
    text = body.get("text", "").strip()

    if not phone or not text:
        return jsonify({"error": "phone and text are required"}), 400

    # Prefix with advisor label so user knows it's a human
    advisor_msg = f"👨‍💼 *Asesor ProAlto:*\n{text}"
    result = WhatsAppService.send_message(phone, advisor_msg)

    if result:
        return jsonify({"status": "sent"})
    else:
        return jsonify({"error": "Failed to send message"}), 500


@admin_bp.route('/admin/api/close-agent/<phone>', methods=['POST'])
@requires_auth
def api_close_agent(phone):
    """Close agent mode and return user to the bot."""
    set_agent_mode(phone, False)

    # Update in-memory session too
    if phone in user_sessions:
        user_sessions[phone]["status"] = "active"
    else:
        user_sessions[phone] = {"status": "active"}

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
    set_agent_mode(phone, True)

    # Update in-memory session too
    if phone in user_sessions:
        user_sessions[phone]["status"] = "agent_mode"
    else:
        user_sessions[phone] = {"status": "agent_mode"}

    WhatsAppService.send_message(
        phone,
        "👨‍💼 Un asesor ha tomado el control de esta conversación. En un momento te escribiremos."
    )

    return jsonify({"status": "forced"})


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
