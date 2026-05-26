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
    get_conversations, get_conversation, get_lead_conversations,
    get_renovado_conversations, get_anticipos_conversations,
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


@admin_bp.route('/admin/api/lead-conversations')
@requires_auth
def api_lead_conversations():
    """Get list of lead conversations (from contacto_leads template)."""
    return jsonify(get_lead_conversations())


@admin_bp.route('/admin/api/renovado-conversations')
@requires_auth
def api_renovado_conversations():
    """Get list of renovado conversations (from estado_renovar template)."""
    return jsonify(get_renovado_conversations())


@admin_bp.route('/admin/api/anticipos-conversations')
@requires_auth
def api_anticipos_conversations():
    """Get list of anticipo conversations (from anticipo_nomina template)."""
    return jsonify(get_anticipos_conversations())


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


@admin_bp.route('/admin/api/llm-retrigger/<phone>', methods=['POST'])
@requires_auth
def api_llm_retrigger(phone):
    """Re-process the last client message through the LLM and send the response."""
    try:
        from src.conversation_log import get_recent_messages_for_llm, get_client_name
        from src.llm import ask_llm
        from src.flows import _LLM_MSG_TYPE, FlowHandler
        import re

        # Find the last inbound (user) message
        history = get_recent_messages_for_llm(phone, limit=10)
        last_user_msg = None
        for msg in reversed(history):
            if msg.get("role") == "user":
                last_user_msg = msg["content"]
                break

        if not last_user_msg:
            return jsonify({"error": "No hay mensajes del cliente para reprocesar"}), 404

        set_agent_mode(phone, "agent_llm")
        client_name = get_client_name(phone)

        # Detect cedula in last message and fetch context (same as flows.py)
        cedula_context = None
        saldo_context = None
        text = last_user_msg.strip()
        if text.isdigit() and 6 <= len(text) <= 12:
            from src.database import get_solicitud_status, get_saldo
            result = get_solicitud_status(text)
            if result is None:
                cedula_context = {"_error": True}
            else:
                cedula_context = result if result else {}
            saldo_result = get_saldo(text)
            if saldo_result is None:
                saldo_context = "error"
            else:
                saldo_context = saldo_result

        llm_response = ask_llm(phone, last_user_msg, "agent_llm", client_name,
                               cedula_context=cedula_context,
                               saldo_context=saldo_context)

        if not llm_response:
            return jsonify({"error": "El LLM no pudo generar una respuesta"}), 500

        # Handle tags the same way as flows.py
        from src.conversation_log import set_user_state, save_llm_request
        from src.notifications import notify_admin_agent_request, notify_admin_llm_request
        from src.flows import set_agent_mode as flows_set_agent_mode

        # Strip ALL signal tags and process each action
        from src.flows import _process_llm_signals
        human_msg, signals = _process_llm_signals(llm_response)

        if signals:
            if human_msg:
                WhatsAppService.send_message(phone, human_msg, msg_type=_LLM_MSG_TYPE)

            if "registrar_solicitud" in signals:
                save_llm_request(phone, client_name, signals["registrar_solicitud"], last_user_msg)
                notify_admin_llm_request(phone, signals["registrar_solicitud"])

            if signals.get("hablar_asesor"):
                set_agent_mode(phone, "agent")
                notify_admin_agent_request(phone)
            elif signals.get("mostrar_menu"):
                set_agent_mode(phone, "active")
                FlowHandler.send_main_menu(phone)
        else:
            WhatsAppService.send_message(phone, llm_response, msg_type=_LLM_MSG_TYPE)

        return jsonify({"status": "sent"})

    except Exception as e:
        print(f"[admin] llm_retrigger error: {e}")
        return jsonify({"error": str(e)}), 500


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
@admin_bp.route('/admin/api/trigger-bulk-renovados', methods=['POST'])
@requires_auth
def api_trigger_bulk_renovados():
    """Execute bulk send of contacto_renovados template for renewal candidates."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_renovados_notifications
    try:
        results = execute_bulk_renovados_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/admin/api/lead-metrics')
@requires_auth
def api_lead_metrics():
    """Get metrics for the contacto_leads campaign (retrospective from bot_messages)."""
    from src.conversation_log import get_lead_metrics
    try:
        return jsonify({"status": "ok", "metrics": get_lead_metrics()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/renovado-metrics')
@requires_auth
def api_renovado_metrics():
    """Get metrics for the estado_renovar campaign (retrospective from bot_messages)."""
    from src.conversation_log import get_renovado_metrics
    try:
        return jsonify({"status": "ok", "metrics": get_renovado_metrics()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/anticipo-metrics')
@requires_auth
def api_anticipo_metrics():
    """Get metrics for the anticipo_salario campaign."""
    from src.conversation_log import get_anticipo_metrics
    try:
        metrics = get_anticipo_metrics()
        return jsonify({"status": "ok", "metrics": metrics})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/anticipo-toggle-form/<phone>', methods=['POST'])
@requires_auth
def api_anticipo_toggle_form(phone):
    """Toggle form_submitted status for a phone in anticipo_responses."""
    from src.conversation_log import toggle_anticipo_form_submitted
    result = toggle_anticipo_form_submitted(phone)
    if result["success"]:
        return jsonify({"status": "ok", "form_submitted": result["form_submitted"]})
    return jsonify({"status": "error", "message": "No se encontró el registro"}), 404


@admin_bp.route('/admin/api/trigger-bulk-anticipos', methods=['POST'])
@requires_auth
def api_trigger_bulk_anticipos():
    """Execute bulk send of anticipo_nomina template for payroll advance leads."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_anticipos_notifications
    try:
        results = execute_bulk_anticipos_notifications(users_list)
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


@admin_bp.route('/admin/api/captured-emails/<phone>/toggle-processed', methods=['POST'])
@requires_auth
def api_toggle_email_processed(phone):
    """Toggle the processed (sent) status of a captured email (by phone, most recent record)."""
    from src.conversation_log import toggle_email_processed
    result = toggle_email_processed(phone)
    if result["success"]:
        return jsonify({"status": "ok", "processed": result["processed"]})
    return jsonify({"status": "error", "message": "No se encontró el registro"}), 404


@admin_bp.route('/admin/api/captured-emails/by-id/<record_id>/toggle-processed', methods=['POST'])
@requires_auth
def api_toggle_email_processed_by_id(record_id):
    """Toggle the processed (sent) status of a specific captured email record by its ID."""
    from src.conversation_log import toggle_email_processed_by_id
    result = toggle_email_processed_by_id(record_id)
    if result["success"]:
        return jsonify({"status": "ok", "processed": result["processed"]})
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


@admin_bp.route('/admin/api/mark-all-docs-reviewed', methods=['POST'])
@requires_auth
def api_mark_all_docs_reviewed():
    """Mark all received documents for a phone as reviewed."""
    body = request.get_json() or {}
    phone = body.get("phone")

    if not phone:
        return jsonify({"status": "error", "message": "No phone provided."}), 400

    from src.conversation_log import mark_all_docs_reviewed
    try:
        mark_all_docs_reviewed(phone)
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


@admin_bp.route('/admin/api/pending-denegado')
@requires_auth
def api_pending_denegado():
    """Get list of users eligible for 'estado_negados' bulk send (never notified before), plus excluded with reasons."""
    from src.automation import get_pending_denegado_notifications
    try:
        result = get_pending_denegado_notifications()
        return jsonify({"status": "ok", "pending": result["eligible"], "excluded": result["excluded"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/trigger-bulk-denegado', methods=['POST'])
@requires_auth
def api_trigger_bulk_denegado():
    """Execute bulk send of estado_negados template for denied/cancelled users."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_denegado_notifications
    try:
        results = execute_bulk_denegado_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/pending-actualizacion-datos')
@requires_auth
def api_pending_actualizacion_datos():
    """Get list of clients eligible for the yearly contact-data update campaign,
    plus excluded clients with reasons."""
    from src.automation import get_pending_contact_update_notifications
    try:
        result = get_pending_contact_update_notifications()
        return jsonify({"status": "ok", "pending": result["eligible"], "excluded": result["excluded"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/trigger-bulk-actualizacion-datos', methods=['POST'])
@requires_auth
def api_trigger_bulk_actualizacion_datos():
    """Execute bulk send of the actualizacion_datos template to active clients
    who haven't updated their contact info in the last 12 months."""
    body = request.get_json() or {}
    users_list = body.get("users", [])

    if not users_list:
        return jsonify({"status": "error", "message": "No users provided for bulk send."}), 400

    from src.automation import execute_bulk_contact_update_notifications
    try:
        results = execute_bulk_contact_update_notifications(users_list)
        return jsonify({"status": "ok", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@admin_bp.route('/admin/api/captured-cuentas')
@requires_auth
def api_captured_cuentas():
    """Get list of all captured account numbers from Supabase."""
    from src.conversation_log import get_captured_cuentas
    try:
        cuentas = get_captured_cuentas()
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


# ─────────────────────────────────────────────────────────────────────
# MODO TEST — panel para probar el bot sin contaminar datos reales
# ─────────────────────────────────────────────────────────────────────

import time as _time
from src import test_mode
from src import test_runner
from src.test_personas import list_personas, get_persona


def _current_admin_user() -> str:
    """Best-effort: extrae el usuario de basic auth para 'started_by' / 'author'."""
    auth = request.authorization
    return (auth.username if auth and auth.username else "admin")


@admin_bp.route('/admin/test')
@requires_auth
def test_dashboard():
    """Panel de pruebas. Conversa con el bot sin tocar Supabase ni Meta."""
    return render_template('admin_test.html')


@admin_bp.route('/admin/test/review')
@requires_auth
def test_review_dashboard():
    """Panel de revisión de sesiones de prueba guardadas."""
    return render_template('admin_test_review.html')


@admin_bp.route('/admin/api/test/start', methods=['POST'])
@requires_auth
def api_test_start():
    """Crea una sesión de prueba y devuelve su test_phone.

    Body opcional:
      - client_name: str
      - save_for_review: bool — si true, persiste la sesión en Supabase
    """
    body = request.get_json(silent=True) or {}
    client_name = (body.get("client_name") or "").strip()
    save_for_review = bool(body.get("save_for_review"))

    test_phone = test_mode.register_session()
    if client_name:
        test_mode.set_client_name(test_phone, client_name)

    session_id = None
    if save_for_review:
        session_id = test_runner.create_session(
            mode="manual",
            client_name=client_name or None,
            started_by=_current_admin_user(),
            test_phone=test_phone,
        )

    return jsonify({
        "status": "ok",
        "test_phone": test_phone,
        "session_id": session_id,
        "snapshot": test_mode.snapshot(test_phone),
    })


def _wait_for_llm(test_phone: str, timeout_s: float = 6.0) -> bool:
    """Espera a que termine el thread del LLM agent para este phone test.
    Devuelve True si terminó, False si timeout."""
    deadline = _time.time() + timeout_s
    while _time.time() < deadline:
        if not test_mode.is_llm_pending(test_phone):
            return True
        _time.sleep(0.15)
    return not test_mode.is_llm_pending(test_phone)


@admin_bp.route('/admin/api/test/send', methods=['POST'])
@requires_auth
def api_test_send():
    """Envía un mensaje al bot dentro de la sesión de prueba.

    Body: { test_phone, text, [kind: 'text' | 'button_reply'], [button_id] }
    """
    body = request.get_json(silent=True) or {}
    test_phone = (body.get("test_phone") or "").strip()
    text = (body.get("text") or "").strip()
    kind = (body.get("kind") or "text").strip()
    button_id = (body.get("button_id") or "").strip()

    if not test_mode.session_exists(test_phone):
        return jsonify({"status": "error", "message": "Sesión de prueba inválida o expirada"}), 400
    if not text and not button_id:
        return jsonify({"status": "error", "message": "Texto o button_id requerido"}), 400

    # Limpiar buffer outbound previo para que esta llamada solo vea las
    # respuestas generadas por este mensaje.
    test_mode.drain_outbound(test_phone)

    # Si la sesión tiene persistencia activa, registrar el inbound antes
    # de procesar (para preservar el orden con seq).
    session_id = test_runner.session_id_for(test_phone)
    if session_id:
        inbound_text = text if kind != "button_reply" else f"▶ {text or button_id}"
        test_runner.persist_inbound(
            session_id,
            inbound_text,
            role="user",
            msg_type=("button" if kind == "button_reply" else "text"),
        )

    msg_id = f"test_msg_{int(_time.time() * 1000)}"
    if kind == "button_reply":
        message = {
            "from": test_phone,
            "id": msg_id,
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": button_id or "btn", "title": text or button_id or "Botón"},
            },
        }
    else:
        message = {
            "from": test_phone,
            "id": msg_id,
            "type": "text",
            "text": {"body": text},
        }

    payload = {"entry": [{"changes": [{"value": {"messages": [message]}}]}]}

    t_start = _time.time()
    from src.flows import FlowHandler
    try:
        FlowHandler.handle_incoming_message(payload)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error procesando mensaje: {e}"}), 500

    # Esperar al LLM si arrancó en background.
    llm_done = _wait_for_llm(test_phone, timeout_s=6.0)
    outbound = test_mode.drain_outbound(test_phone)

    if session_id:
        latency_ms = int((_time.time() - t_start) * 1000)
        test_runner.persist_outbound(session_id, outbound, total_latency_ms=latency_ms)
        test_runner.increment_turns(session_id)

    return jsonify({
        "status": "ok",
        "outbound": outbound,
        "llm_pending": not llm_done,
        "snapshot": test_mode.snapshot(test_phone),
        "session_id": session_id,
    })


@admin_bp.route('/admin/api/test/poll', methods=['GET'])
@requires_auth
def api_test_poll():
    """Devuelve los mensajes outbound acumulados desde la última llamada.
    Usado por el frontend mientras el LLM thread sigue corriendo."""
    test_phone = (request.args.get("test_phone") or "").strip()
    if not test_mode.session_exists(test_phone):
        return jsonify({"status": "error", "message": "Sesión de prueba inválida o expirada"}), 400

    outbound = test_mode.drain_outbound(test_phone)

    # Si la sesión está siendo persistida, registrar los outbound que llegaron
    # asincrónicamente (típicamente respuestas del LLM en background).
    session_id = test_runner.session_id_for(test_phone)
    if session_id and outbound:
        test_runner.persist_outbound(session_id, outbound)

    return jsonify({
        "status": "ok",
        "outbound": outbound,
        "llm_pending": test_mode.is_llm_pending(test_phone),
        "snapshot": test_mode.snapshot(test_phone),
        "session_id": session_id,
    })


@admin_bp.route('/admin/api/test/reset', methods=['POST'])
@requires_auth
def api_test_reset():
    """Resetea el estado de la sesión sin desregistrarla."""
    body = request.get_json(silent=True) or {}
    test_phone = (body.get("test_phone") or "").strip()
    if not test_mode.reset_session(test_phone):
        return jsonify({"status": "error", "message": "Sesión no encontrada"}), 404
    return jsonify({"status": "ok", "snapshot": test_mode.snapshot(test_phone)})


@admin_bp.route('/admin/api/test/end', methods=['POST'])
@requires_auth
def api_test_end():
    """Cierra la sesión y libera memoria. Si tenía persistencia, marca ended_at."""
    body = request.get_json(silent=True) or {}
    test_phone = (body.get("test_phone") or "").strip()
    session_id = test_runner.session_id_for(test_phone)
    if session_id:
        test_runner.end_session(session_id)
    test_runner.unbind(test_phone)
    test_mode.unregister_session(test_phone)
    return jsonify({"status": "ok"})


_VALID_CATEGORIAS = ("aprobados", "falta_documento", "listo_en_docusign", "denegado", "activos")


@admin_bp.route('/admin/api/test/random-cedula', methods=['GET'])
@requires_auth
def api_test_random_cedula():
    """Devuelve una cédula aleatoria de la base de datos por categoría.

    Query param: categoria ∈ aprobados | falta_documento | listo_en_docusign | denegado | activos.
    """
    categoria = (request.args.get("categoria") or "").strip()
    if categoria not in _VALID_CATEGORIAS:
        return jsonify({"status": "error", "message": f"Categoría inválida. Usa una de: {', '.join(_VALID_CATEGORIAS)}"}), 400

    from src.database import get_random_cedula_by_categoria
    try:
        pick = get_random_cedula_by_categoria(categoria)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error consultando Cloud Run: {e}"}), 500

    if not pick:
        return jsonify({"status": "empty", "message": f"No hay clientes en la categoría '{categoria}'"}), 404

    return jsonify({"status": "ok", "pick": pick})


# ─────────────────────────────────────────────────────────────────────
# MODO TEST — AUTOMÁTICO (LLM-vs-LLM con personas curadas)
# ─────────────────────────────────────────────────────────────────────


@admin_bp.route('/admin/api/test/personas', methods=['GET'])
@requires_auth
def api_test_personas():
    """Lista de personas curadas disponibles para el modo automático."""
    return jsonify({"status": "ok", "personas": list_personas()})


@admin_bp.route('/admin/api/test/auto/start', methods=['POST'])
@requires_auth
def api_test_auto_start():
    """Crea una sesión de prueba en modo automático.

    Body: { persona_slug, objetivo, categoria_cedula?, client_name? }
    """
    body = request.get_json(silent=True) or {}
    persona_slug = (body.get("persona_slug") or "").strip()
    objetivo = (body.get("objetivo") or "").strip()
    categoria_cedula = (body.get("categoria_cedula") or "").strip() or None
    client_name = (body.get("client_name") or "").strip() or None

    persona = get_persona(persona_slug) if persona_slug else None
    if not persona:
        return jsonify({"status": "error", "message": "Persona inválida o no encontrada"}), 400
    if not objetivo:
        return jsonify({"status": "error", "message": "El objetivo es obligatorio"}), 400
    if categoria_cedula and categoria_cedula not in _VALID_CATEGORIAS:
        return jsonify({"status": "error", "message": f"Categoría inválida. Usa una de: {', '.join(_VALID_CATEGORIAS)}"}), 400

    # Pick cédula real si aplica
    cedula_used = None
    if categoria_cedula:
        from src.database import get_random_cedula_by_categoria
        try:
            pick = get_random_cedula_by_categoria(categoria_cedula)
            if pick and pick.get("cedula"):
                cedula_used = str(pick["cedula"])
                if not client_name and pick.get("nombre"):
                    client_name = pick["nombre"].split()[0].title()
        except Exception as e:
            print(f"[test_auto_start] cédula lookup error: {e}")

    test_phone = test_mode.register_session()
    if client_name:
        test_mode.set_client_name(test_phone, client_name)
    # En modo auto saltamos el consentimiento: el flujo de habeas data
    # solo acepta button_reply en producción (correcto por compliance) y
    # no es lo que queremos probar aquí. La sesión arranca en 'active',
    # equivalente a un cliente que YA acepto el consent.
    test_mode.set_state(test_phone, "active")

    session_id = test_runner.create_session(
        mode="auto",
        persona_slug=persona_slug,
        objetivo=objetivo,
        categoria_cedula=categoria_cedula,
        cedula_used=cedula_used,
        client_name=client_name,
        started_by=_current_admin_user(),
        test_phone=test_phone,
    )
    if not session_id:
        test_mode.unregister_session(test_phone)
        return jsonify({"status": "error", "message": "No se pudo crear la sesión (Supabase). Verifica configuración."}), 500

    return jsonify({
        "status": "ok",
        "session_id": session_id,
        "test_phone": test_phone,
        "persona": {"slug": persona["slug"], "nombre": persona["nombre"]},
        "objetivo": objetivo,
        "cedula_used": cedula_used,
        "snapshot": test_mode.snapshot(test_phone),
    })


@admin_bp.route('/admin/api/test/auto/next', methods=['POST'])
@requires_auth
def api_test_auto_next():
    """Ejecuta un turno completo en modo automático.

    Body: { session_id, test_phone }
    """
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    test_phone = (body.get("test_phone") or "").strip()
    if not session_id or not test_phone:
        return jsonify({"status": "error", "message": "session_id y test_phone requeridos"}), 400
    if not test_mode.session_exists(test_phone):
        return jsonify({"status": "error", "message": "Sesión de prueba expirada"}), 400

    result = test_runner.run_auto_turn(session_id, test_phone)
    return jsonify({
        "status": "ok",
        "client_text": result.get("client_text"),
        "bot_messages": result.get("bot_messages") or [],
        "signals": result.get("signals") or [],
        "finished": bool(result.get("finished")),
        "reason": result.get("reason"),
        "latency_ms": result.get("latency_ms"),
        "snapshot": test_mode.snapshot(test_phone),
    })


@admin_bp.route('/admin/api/test/auto/stop', methods=['POST'])
@requires_auth
def api_test_auto_stop():
    """Detiene una sesión automática y libera memoria."""
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    test_phone = (body.get("test_phone") or "").strip()
    if session_id:
        test_runner.end_session(session_id)
    if test_phone:
        test_runner.unbind(test_phone)
        test_mode.unregister_session(test_phone)
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────────────────────────────
# MODO TEST — PANEL DE REVISIÓN (lectura, anotación, comparación)
# ─────────────────────────────────────────────────────────────────────


@admin_bp.route('/admin/api/test/sessions', methods=['GET'])
@requires_auth
def api_test_list_sessions():
    """Lista paginada de sesiones de prueba persistidas."""
    mode = (request.args.get("mode") or "").strip() or None
    persona = (request.args.get("persona") or "").strip() or None
    tag = (request.args.get("tag") or "").strip() or None
    try:
        limit = max(1, min(int(request.args.get("limit") or 50), 200))
        offset = max(0, int(request.args.get("offset") or 0))
    except ValueError:
        return jsonify({"status": "error", "message": "limit/offset inválidos"}), 400

    sessions = test_runner.list_sessions(
        mode=mode, persona=persona, tag=tag, limit=limit, offset=offset,
    )
    return jsonify({"status": "ok", "sessions": sessions})


@admin_bp.route('/admin/api/test/sessions/<session_id>', methods=['GET'])
@requires_auth
def api_test_session_detail(session_id):
    detail = test_runner.get_session_detail(session_id)
    if not detail or not detail.get("session"):
        return jsonify({"status": "error", "message": "Sesión no encontrada"}), 404
    return jsonify({"status": "ok", **detail})


@admin_bp.route('/admin/api/test/sessions/<session_id>/tag', methods=['POST'])
@requires_auth
def api_test_session_tag(session_id):
    body = request.get_json(silent=True) or {}
    tag = body.get("tag")
    if tag is not None and tag not in ("ok", "fail", "review"):
        return jsonify({"status": "error", "message": "tag inválido (ok|fail|review|null)"}), 400
    ok = test_runner.update_session_tag(session_id, tag)
    if not ok:
        return jsonify({"status": "error", "message": "No se pudo actualizar"}), 500
    return jsonify({"status": "ok"})


@admin_bp.route('/admin/api/test/sessions/<session_id>/note', methods=['POST'])
@requires_auth
def api_test_session_note(session_id):
    body = request.get_json(silent=True) or {}
    note = body.get("note")
    ok = test_runner.update_session_notes(session_id, note)
    if not ok:
        return jsonify({"status": "error", "message": "No se pudo actualizar"}), 500
    return jsonify({"status": "ok"})


@admin_bp.route('/admin/api/test/sessions/<session_id>/annotate', methods=['POST'])
@requires_auth
def api_test_session_annotate(session_id):
    """Crea una anotación a nivel sesión o a nivel mensaje (si message_id viene)."""
    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip()
    severity = body.get("severity") or "info"
    message_id = body.get("message_id") or None
    if not note:
        return jsonify({"status": "error", "message": "note requerido"}), 400
    ann = test_runner.add_annotation(
        session_id=session_id,
        note=note,
        severity=severity,
        message_id=message_id,
        author=_current_admin_user(),
    )
    if not ann:
        return jsonify({"status": "error", "message": "No se pudo crear la anotación"}), 500
    return jsonify({"status": "ok", "annotation": ann})


@admin_bp.route('/admin/api/test/compare', methods=['GET'])
@requires_auth
def api_test_compare():
    """Devuelve hasta 3 sesiones con sus mensajes para comparación lado a lado."""
    raw = (request.args.get("ids") or "").strip()
    if not raw:
        return jsonify({"status": "error", "message": "ids requerido"}), 400
    ids = [x.strip() for x in raw.split(",") if x.strip()][:3]
    sessions = []
    for sid in ids:
        detail = test_runner.get_session_detail(sid)
        if detail and detail.get("session"):
            sessions.append(detail)
    return jsonify({"status": "ok", "sessions": sessions})
