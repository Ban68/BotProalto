from src.services import WhatsAppService
from src.database import get_solicitud_status, get_saldo
from src.google_sheets import get_solicitud_reciente_sheet
from src.conversation_log import log_message, set_agent_mode, get_user_state, set_user_state, get_client_name, set_client_name, log_received_document, count_received_documents
from src.notifications import notify_admin_agent_request, notify_admin_error
import os
import json
import re
import threading

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
    patterns = [
        "hablar con un asesor", "hablar con asesor", "contactar asesor",
        "necesito un asesor", "quiero hablar con alguien", "contactarme con un asesor",
        "quiero un asesor", "pasame con un asesor", "pásame con un asesor",
        "comunicarme con un asesor", "hablar con una persona", "persona real",
        "agente humano", "asesor humano", "hablar con alguien", "necesito asesor",
        "quiero asesor", "contactar un asesor", "conectarme con un asesor",
    ]
    return any(p in norm for p in patterns)


# Prefix for LLM-generated messages (visible in chat for admin monitoring)
_LLM_PREFIX = "🤖 "


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
                btn_title = message["interactive"].get("button_reply", {}).get("title", "")
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

                        # Send confirmation in document-expected states; remind email if waiting for it
                        if current_state in ("waiting_for_docs_rojo", "waiting_for_cuenta_amarillo"):
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
                
            # Handle Interactive Button Replies
            elif msg_type == "interactive":
                reply = message["interactive"]["button_reply"]
                reply_id = reply["id"]
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

        # 0b. LLM Agent Mode — all messages routed through Claude
        if state == "agent_llm":
            # Pre-route: greetings exit to menu without calling LLM
            if _is_greeting(text):
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
                return

            from src.llm import ask_llm
            client_name = get_client_name(user_phone)

            # If message looks like a cedula, look it up and pass result to LLM
            cedula_context = None
            if text.strip().isdigit() and 6 <= len(text.strip()) <= 12:
                result = get_solicitud_status(text.strip())
                cedula_context = result if result else {}

            llm_response = ask_llm(user_phone, text, state, client_name, cedula_context=cedula_context)

            if "[HABLAR_ASESOR]" in llm_response:
                human_msg = llm_response.replace("[HABLAR_ASESOR]", "").strip()
                if human_msg:
                    WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
                set_agent_mode(user_phone, "agent")
                notify_admin_agent_request(user_phone)
            elif "[MOSTRAR_MENU]" in llm_response:
                human_msg = llm_response.replace("[MOSTRAR_MENU]", "").strip()
                if human_msg:
                    WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
                set_user_state(user_phone, "active")
                FlowHandler.send_main_menu(user_phone)
            elif "[REGISTRAR_SOLICITUD:" in llm_response:
                match = re.search(r'\[REGISTRAR_SOLICITUD:([^\]]+)\]', llm_response)
                tipo = match.group(1).strip() if match else "general"
                human_msg = re.sub(r'\[REGISTRAR_SOLICITUD:[^\]]+\]', '', llm_response).strip()
                if human_msg:
                    WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
                from src.conversation_log import save_llm_request
                from src.notifications import notify_admin_llm_request
                save_llm_request(user_phone, client_name, tipo, text)
                notify_admin_llm_request(user_phone, tipo)
            else:
                WhatsAppService.send_message(user_phone, _LLM_PREFIX + llm_response)
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
            
            if result:
                estado_interno = result['estado_interno']
                clean_status = estado_interno.strip().upper() if estado_interno else "NULL"
                mensaje_cliente = STATUS_MESSAGES.get(clean_status, estado_interno or "Pendiente / En Estudio")
                
                monto = result['valor_preestudiado']
                nombre = result['nombre_completo']
                fecha = result['fecha_de_solicitud']
                plazo = result.get('plazo')

                response_msg = (
                    f"🔍 *Resultado de Solicitud*\n\n"
                    f"👤 *Cliente:* {nombre}\n"
                    f"📅 *Fecha:* {fecha}\n"
                )

                # Definir estados en los que NO se debe mostrar el monto
                statuses_no_monto = [
                    "REVISAR NUEVAMENTE", 
                    "FALTA ALGÚN DOCUMENTO", 
                    "EMPRESA PAUSADA", 
                    "DENEGADO", 
                    "CANCELADO POR LA EMPRESA",
                    "DESISTIÓ DEL CRÉDITO", 
                    "NO RESPONDIÓ"
                ]

                if clean_status not in statuses_no_monto:
                    response_msg += f"💰 *Monto Pre-aprobado:* ${monto:,.0f}\n"

                if clean_status in ["APROBADO POR EL CLIENTE", "LISTO PARA HACERLE DOCUMENTACIÓN"]:
                    if plazo:
                        response_msg += f"⏱️ *Plazo:* {plazo} meses\n"
                    response_msg += f"📋 *Estado:* {mensaje_cliente}\n"

                    # 1. Send the result box
                    WhatsAppService.send_message(user_phone, response_msg)

                    # 2. Check if email already captured
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
                        set_client_name(user_phone, nombre)
                        set_user_state(user_phone, "waiting_for_email")
                elif clean_status == "FALTA ALGÚN DOCUMENTO":
                    from src.automation import build_docs_message
                    from src.conversation_log import set_solicitud_context
                    docs_faltantes = result.get("documentos_faltantes", "")
                    tipo_empleador = result.get("tipo_empleador", "EMPRESA")
                    set_client_name(user_phone, nombre)
                    set_solicitud_context(user_phone, result.get("empresa", ""), docs_faltantes, tipo_empleador)
                    set_user_state(user_phone, "waiting_for_docs_rojo")
                    # build_docs_message returns "Para agilizar...\n\n{lista}\n\nPuedes enviárnoslos..."
                    # We skip its intro and use our own to produce a single combined message
                    docs_part = build_docs_message(docs_faltantes, tipo_empleador)
                    combined = (
                        response_msg
                        + "📋 *Estado:* Tu proceso está detenido porque te faltan los siguientes documentos:\n\n"
                        + docs_part.split("\n\n", 1)[1]
                    )
                    WhatsAppService.send_message(user_phone, combined)
                    log_message(user_phone, "outbound", "[Menu: estado_rojo]", "text")
                else:
                    response_msg += f"📋 *Estado:* {mensaje_cliente}\n"
                    WhatsAppService.send_message(user_phone, response_msg)
            else:
                # 2.3 Si no está en BD, verificar en Google Sheets de los últimos 3 días
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
            
            # Reset state and ask if they need anything else, UNLESS they are in "Aprobado" and we're waiting for them to type email
            if not result or clean_status not in ["APROBADO POR EL CLIENTE", "LISTO PARA HACERLE DOCUMENTACIÓN", "FALTA ALGÚN DOCUMENTO"]:
                set_user_state(user_phone, "active")
                WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
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
                    from src.notifications import notify_admin_agent_request
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

        # 2c. Step 1: waiting for account number (digits only)
        if state in ("waiting_for_numero_cuenta", "waiting_for_cuenta_amarillo"):
            digits = "".join(filter(str.isdigit, text))
            if len(digits) >= 5:
                from src.conversation_log import save_captured_cuenta
                client_name = get_client_name(user_phone)
                save_captured_cuenta(user_phone, digits, client_name)
                set_user_state(user_phone, "waiting_for_banco")
                WhatsAppService.send_message(
                    user_phone,
                    "Número registrado ✅\n\n¿En qué *banco* está la cuenta? (Ej: Bancolombia, Davivienda, Nequi...)"
                )
            else:
                WhatsAppService.send_message(
                    user_phone,
                    "Por favor envíanos solo el *número de cuenta* (mínimo 5 dígitos, sin letras ni espacios)."
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
            set_user_state(user_phone, "active")
            ack_words = ["ok", "okay", "entendido", "gracias", "de acuerdo", "listo",
                         "bien", "claro", "comprendo", "entiendo", "perfecto", "👍"]
            norm = text.lower().strip()
            is_ack = any(norm == w or norm.startswith(w + " ") or norm.startswith(w + ",") for w in ack_words)
            if not is_ack:
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
            WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
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

        # Route everything else to LLM (including "hablar con asesor" — the LLM IS the advisor)
        from src.llm import ask_llm
        client_name = get_client_name(user_phone)
        set_user_state(user_phone, "agent_llm")

        cedula_context = None
        if norm_text.isdigit() and 6 <= len(norm_text) <= 12:
            result = get_solicitud_status(norm_text)
            cedula_context = result if result else {}

        llm_response = ask_llm(user_phone, text, "agent_llm", client_name, cedula_context=cedula_context)

        if "[HABLAR_ASESOR]" in llm_response:
            human_msg = llm_response.replace("[HABLAR_ASESOR]", "").strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
            set_agent_mode(user_phone, "agent")
            notify_admin_agent_request(user_phone)
        elif "[MOSTRAR_MENU]" in llm_response:
            human_msg = llm_response.replace("[MOSTRAR_MENU]", "").strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
            set_user_state(user_phone, "active")
            FlowHandler.send_main_menu(user_phone)
        elif "[REGISTRAR_SOLICITUD:" in llm_response:
            match = re.search(r'\[REGISTRAR_SOLICITUD:([^\]]+)\]', llm_response)
            tipo = match.group(1).strip() if match else "general"
            human_msg = re.sub(r'\[REGISTRAR_SOLICITUD:[^\]]+\]', '', llm_response).strip()
            if human_msg:
                WhatsAppService.send_message(user_phone, _LLM_PREFIX + human_msg)
            from src.conversation_log import save_llm_request
            from src.notifications import notify_admin_llm_request
            save_llm_request(user_phone, client_name, tipo, text)
            notify_admin_llm_request(user_phone, tipo)
        else:
            WhatsAppService.send_message(user_phone, _LLM_PREFIX + llm_response)

    @staticmethod
    def process_button_click(user_phone, btn_id, state):
        if btn_id == "accept_terms":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(user_phone, "¡Gracias por aceptar! Bienvenido a ProAlto.")
            FlowHandler.send_main_menu(user_phone)
        
        elif btn_id == "decline_terms":
            WhatsAppService.send_message(user_phone, "Entendemos. No podremos atenderte por este medio sin tu autorización. Si cambias de opinión, escribe 'Hola'.")
            set_user_state(user_phone, "pending_consent")

        elif btn_id == "menu_cliente":
            FlowHandler.send_client_menu(user_phone)

        elif btn_id == "menu_solicitud":
            set_user_state(user_phone, "waiting_for_cedula")
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu solicitud:")

        elif btn_id in ["menu_credito", "Solicitar crédito"]:
            set_user_state(user_phone, "active")
            
            # Optional: A slightly different prefix if it was a quick reply from the template
            prefix = "¡Excelente elección! " if btn_id == "Solicitar crédito" else ""
            WhatsAppService.send_message(user_phone, f"{prefix}Para solicitar tu crédito, por favor llena el siguiente formulario:\n\n👉 https://forms.gle/zXzrcrzVefuoVsEX6")

        elif btn_id == "menu_saldo":
            set_user_state(user_phone, "waiting_for_cedula_saldo")
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu saldo:")

            
        elif btn_id in ["enviar_numero_cuenta", "Enviar número de cuenta"]:
            set_user_state(user_phone, "waiting_for_numero_cuenta")
            WhatsAppService.send_message(
                user_phone,
                "Por favor escríbenos tu *número de cuenta* (solo dígitos, sin espacios ni guiones). 🏦"
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

        elif btn_id in ["hablar_asesor_docs", "menu_support", "Hablar con un asesor"]:
            is_lead = (state == "lead_notified")
            set_user_state(user_phone, "agent")
            
            try:
                # Notify admin of support request
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
                    "Dame un momento mientras reviso tu información y ya mismo te escribo.\n\n"
                    "_Si deseas volver al menú del bot, escribe *salir*._"
                )
                
            WhatsAppService.send_message(user_phone, msg)

        elif btn_id == "Ahora no, gracias":
            set_user_state(user_phone, "active")
            WhatsAppService.send_message(
                user_phone,
                "Entendido, agradecemos tu tiempo. Estaremos aquí cuando nos necesites."
            )

        elif btn_id == "menu_main":
            FlowHandler.send_main_menu(user_phone)

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
        menu_text = "Hola, ¿en qué podemos ayudarte hoy?"
        buttons = [
            {"id": "menu_solicitud", "title": "Estado Solicitud"},
            {"id": "menu_saldo", "title": "Consultar Saldo"},
            {"id": "menu_credito", "title": "Solicitar Crédito"}
        ]
        WhatsAppService.send_interactive_button(user_phone, menu_text, buttons)

    @staticmethod
    def send_client_menu(user_phone):
        """Backward compat: redirects to merged main menu."""
        FlowHandler.send_main_menu(user_phone)
