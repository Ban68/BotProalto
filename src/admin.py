"""
Admin Dashboard Blueprint for ProAlto WhatsApp Bot.
Provides conversation monitoring and live agent intervention.
"""
from flask import (
    Blueprint, request, jsonify, render_template,
    Response, current_app
)
from config import Config
import os
import uuid
from werkzeug.utils import secure_filename
from src.conversation_log import (
    get_conversations, get_conversation,
    set_agent_mode, log_message, delete_conversation,
    get_archived_conversations, restore_conversation,
    mark_message_deleted
)
from src.services import WhatsAppService
from src.auth import requires_auth
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__, template_folder='../templates')

# Track active advisors { "advisor_name": last_seen_datetime }
active_advisors = {}


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


@admin_bp.route('/admin/api/delete-message', methods=['POST'])
@requires_auth
def api_delete_message():
    """Revoke a message on WhatsApp and mark it as deleted in DB."""
    body = request.get_json() or {}
    msg_id_db = body.get("id")
    wamid = body.get("wamid")

    if not wamid:
        return jsonify({"error": "WhatsApp message ID (wamid) is required"}), 400

    # 1. Attempt reveal on WhatsApp
    success, result = WhatsAppService.revoke_message(wamid)
    
    if success:
        if msg_id_db:
            mark_message_deleted(msg_id_db)
        return jsonify({"status": "deleted", "whatsapp_response": result})
    else:
        # result contains the error message here
        return jsonify({"error": f"WhatsApp API: {result}"}), 500


@admin_bp.route('/admin/api/set-llm-agent/<phone>', methods=['POST'])
@requires_auth
def api_set_llm_agent(phone):
    """Activate LLM agent mode for a specific conversation."""
    set_agent_mode(phone, "agent_llm")
    return jsonify({"status": "llm_agent_activated"})


@admin_bp.route('/admin/api/close-agent/<phone>', methods=['POST'])
@requires_auth
def api_close_agent(phone):
    """Close agent mode and return user to the bot."""
    conv = get_conversation(phone)
    is_silent = False
    if conv and conv.get("status") in ("agent_silent", "agent_llm"):
        is_silent = True

    set_agent_mode(phone, "active")

    if not is_silent:
        WhatsAppService.send_message(
            phone,
            "✅ Tu asesor ha finalizado la conversación.\n\n"
            "Escribe *Hola* para volver al menú principal."
        )

    return jsonify({"status": "closed"})


@admin_bp.route('/admin/api/human-takeover/<phone>', methods=['POST'])
@requires_auth
def api_human_takeover(phone):
    """Switch from agent_llm to agent mode silently — no notification to client."""
    set_agent_mode(phone, "agent")
    return jsonify({"status": "human_takeover"})


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


@admin_bp.route('/admin/api/upload-media', methods=['POST'])
@requires_auth
def api_upload_media():
    """Upload a file to temporary storage and then to Supabase."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    phone = request.form.get("phone", "admin_upload")
    
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4()}_{filename}"
    temp_path = os.path.join("static", "uploads", "temp", unique_name)
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    
    file.save(temp_path)
    
    # Determine type
    content_type = file.content_type
    storage_path = f"admin_uploads/{phone}/{unique_name}"
    
    public_url = WhatsAppService.upload_to_supabase_storage(temp_path, storage_path, content_type)
    
    # Cleanup temp file
    try:
        os.remove(temp_path)
    except:
        pass
        
    if public_url:
        return jsonify({
            "status": "uploaded",
            "url": public_url,
            "filename": filename,
            "content_type": content_type
        })
    else:
        return jsonify({"error": "Failed to upload to Supabase"}), 500


@admin_bp.route('/admin/api/send-media', methods=['POST'])
@requires_auth
def api_send_media():
    """Send media (image or document) to a user."""
    body = request.get_json() or {}
    phone = body.get("phone")
    media_url = body.get("url")
    media_type = body.get("type") # 'image' or 'document'
    filename = body.get("filename")
    caption = body.get("caption")

    if not phone or not media_url or not media_type:
        return jsonify({"error": "phone, url, and type are required"}), 400

    if media_type == 'image':
        result = WhatsAppService.send_image(phone, media_url, caption)
    elif media_type == 'document':
        result = WhatsAppService.send_document(phone, media_url, filename, caption)
    else:
        return jsonify({"error": "Invalid media type"}), 400

    if result:
        return jsonify({"status": "sent"})
    else:
        return jsonify({"error": "Failed to send media"}), 500


@admin_bp.route('/admin/api/pending-notifications')
@requires_auth
def api_pending_notifications():
    """Get list of users eligible for 'Aprobado' automation today, plus excluded users with reasons."""
    from src.automation import get_pending_approved_notifications
    try:
        result = get_pending_approved_notifications()
        return jsonify({"status": "ok", "pending": result["eligible"], "excluded": result["excluded"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/api/trigger-bulk-send', methods=['POST'])
@requires_auth
def api_trigger_bulk_send():
    """Execute bulk send for a configured list of users."""
    body = request.get_json() or {}
    users_list = body.get("users", [])
    
    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400
        
    from src.automation import execute_bulk_approved_notifications
    try:
        results = execute_bulk_approved_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/api/trigger-bulk-leads', methods=['POST'])
@requires_auth
def api_trigger_bulk_leads():
    """Execute bulk send for a configured list of leads."""
    body = request.get_json() or {}
    users_list = body.get("users", [])
    
    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400
        
    from src.automation import execute_bulk_leads_notifications
    try:
        results = execute_bulk_leads_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@admin_bp.route('/admin/api/captured-emails')
@requires_auth
def api_captured_emails():
    """Get list of all captured emails."""
    from src.conversation_log import get_captured_emails
    try:
        emails = get_captured_emails()
        return jsonify({"status": "ok", "emails": emails})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/captured-emails/<phone>', methods=['PUT'])
@requires_auth
def api_update_captured_email(phone):
    """Update the most recent captured email for a phone."""
    from src.conversation_log import update_captured_email
    body = request.get_json() or {}
    new_email = body.get("email", "").strip()
    if not new_email:
        return jsonify({"status": "error", "message": "Email requerido"}), 400
    success = update_captured_email(phone, new_email)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "No se encontró el registro"}), 404


@admin_bp.route('/admin/api/pending-falta-documento')
@requires_auth
def api_pending_falta_documento():
    """Get list of users eligible for 'Falta algún documento' bulk send today, plus excluded users with reasons."""
    from src.automation import get_pending_falta_documento_notifications
    try:
        result = get_pending_falta_documento_notifications()
        return jsonify({"status": "ok", "pending": result["eligible"], "excluded": result["excluded"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/trigger-bulk-rojo', methods=['POST'])
@requires_auth
def api_trigger_bulk_rojo():
    """Execute bulk send of estado_rojo template for users with missing documents."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_falta_documento_notifications
    try:
        results = execute_bulk_falta_documento_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/received-documents')
@requires_auth
def api_received_documents():
    """Get list of all documents received from clients after estado_rojo send."""
    from src.conversation_log import get_received_documents
    try:
        docs = get_received_documents()
        return jsonify({"status": "ok", "documents": docs})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/mark-document-reviewed', methods=['POST'])
@requires_auth
def api_mark_document_reviewed():
    """Mark a received document as reviewed."""
    body = request.get_json() or {}
    doc_id = body.get("id")

    if not doc_id:
        return jsonify({"status": "error", "message": "No document id provided."}), 400

    from src.conversation_log import mark_document_reviewed
    try:
        mark_document_reviewed(doc_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/download-doc')
@requires_auth
def api_download_doc():
    """Proxy download for client-uploaded documents — forces attachment download and handles CORS for images."""
    import requests as req_lib
    from flask import stream_with_context

    url = request.args.get('url')
    filename = request.args.get('filename', 'archivo')

    if not url:
        return jsonify({"status": "error", "message": "No URL provided."}), 400

    try:
        r = req_lib.get(url, stream=True, timeout=30)
        r.raise_for_status()
        content_type = r.headers.get('Content-Type', 'application/octet-stream')
        safe_filename = filename.replace('"', '_')
        return Response(
            stream_with_context(r.iter_content(chunk_size=8192)),
            content_type=content_type,
            headers={'Content-Disposition': f'attachment; filename="{safe_filename}"'}
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/pending-listo-docusign')
@requires_auth
def api_pending_listo_docusign():
    """Get list of users eligible for 'Listo en DocuSign' bulk send today, plus excluded users with reasons."""
    from src.automation import get_pending_listo_docusign_notifications
    try:
        result = get_pending_listo_docusign_notifications()
        return jsonify({"status": "ok", "pending": result["eligible"], "excluded": result["excluded"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/trigger-bulk-amarillo', methods=['POST'])
@requires_auth
def api_trigger_bulk_amarillo():
    """Execute bulk send of estado_amarillo template for users in DocuSign ready state."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_listo_docusign_notifications
    try:
        results = execute_bulk_listo_docusign_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/captured-cuentas')
@requires_auth
def api_captured_cuentas():
    """Get list of all captured account numbers, enriched with empresa from CRM."""
    from src.conversation_log import get_captured_cuentas
    from src.database import get_client_context_by_phone
    try:
        cuentas = get_captured_cuentas()
        for cuenta in cuentas:
            ctx = get_client_context_by_phone(cuenta.get("phone", ""))
            cuenta["empresa"] = ctx.get("empresa", "") if ctx else ""
        return jsonify({"status": "ok", "cuentas": cuentas})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/llm-requests')
@requires_auth
def api_llm_requests():
    """Get list of LLM-captured special requests."""
    only_pending = request.args.get('pending', 'false').lower() == 'true'
    from src.conversation_log import get_llm_requests
    try:
        items = get_llm_requests(only_pending=only_pending)
        return jsonify({"status": "ok", "requests": items})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/llm-requests/<request_id>/resolve', methods=['POST'])
@requires_auth
def api_resolve_llm_request(request_id):
    """Mark an LLM request as resolved."""
    from src.conversation_log import resolve_llm_request
    try:
        resolve_llm_request(request_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/mark-docs-completos', methods=['POST'])
@requires_auth
def api_mark_docs_completos():
    """Mark or unmark a client's documents as complete."""
    body = request.get_json() or {}
    phone = body.get("phone")
    value = body.get("value", True)

    if not phone:
        return jsonify({"status": "error", "message": "No phone provided."}), 400

    from src.conversation_log import mark_docs_completos
    try:
        mark_docs_completos(phone, value)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
