from src.services import WhatsAppService
from src.database import get_solicitud_status, get_saldo
from src.google_sheets import get_solicitud_reciente_sheet
from src.conversation_log import log_message, set_agent_mode, get_user_state, set_user_state
from src.notifications import notify_admin_agent_request, notify_admin_error
import os
import json
import re

# Pre-load status mapping for optimization throughout the lifecycle
MAPPING_PATH = os.path.join(os.path.dirname(__file__), 'status_mapping.json')
try:
    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        STATUS_MESSAGES = json.load(f)
except Exception as e:
    print(f"Error loading status mapping: {e}")
    STATUS_MESSAGES = {}

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
                    
                    # 2. Send a second, separate, and highlighted instruction message
                    instruction_msg = (
                        "⚠️ *ACCIÓN NECESARIA*\n\n"
                        "Para continuar con tu desembolso, por favor *CONFÍRMANOS TU CORREO ELECTRÓNICO* 📧 escribiéndolo a continuación.\n\n"
                        "_Lo necesitamos para enviarte el contrato para firma electrónica._"
                    )
                    WhatsAppService.send_message(user_phone, instruction_msg)
                    
                    # 3. Set state to wait for email
                    set_user_state(user_phone, "waiting_for_email")
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
            if not result or clean_status not in ["APROBADO POR EL CLIENTE", "LISTO PARA HACERLE DOCUMENTACIÓN"]:
                set_user_state(user_phone, "active")
                WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 2a. Check if waiting for Email
        if state == "waiting_for_email":
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
            email = email_match.group(0) if email_match else None
            if email:
                from src.conversation_log import save_captured_email, get_client_name
                client_name = get_client_name(user_phone)

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

        # 2b. Check if waiting for Cedula (Saldo / Balance)
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
        greetings = ["hola", "menu", "inicio", "start", "buenas", "holis", "holi", "saludos", "hi", "hello", "buen", "buenos"]
        
        first_word = norm_text.split()[0] if norm_text else ""
        for char in [",", ".", "!", "?", "¿", "¡"]:
            first_word = first_word.replace(char, "")
            
        exact_phrases = ["buenos dias", "buenos días", "buenas tardes", "buenas noches", "buen dia", "buen día", "que tal", "q tal"]
        is_greeting = first_word in greetings or norm_text in exact_phrases
        
        if is_greeting:
            set_user_state(user_phone, "active")
            FlowHandler.send_main_menu(user_phone)
        else:
            WhatsAppService.send_message(user_phone, "No entendí tu mensaje. Escribe 'Hola' para ver el menú principal.")

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

            
        elif btn_id in ["menu_support", "Hablar con un asesor"]:
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
            {"id": "menu_cliente", "title": "Soy Cliente"},
            {"id": "menu_solicitud", "title": "Estado Solicitud"},
            {"id": "menu_credito", "title": "Solicitar Crédito"}
        ]
        WhatsAppService.send_interactive_button(user_phone, menu_text, buttons)

    @staticmethod
    def send_client_menu(user_phone):
        menu_text = "¿Qué deseas hacer hoy?"
        buttons = [
            {"id": "menu_saldo", "title": "Consultar Saldo"},
            {"id": "menu_support", "title": "Hablar con Asesor"},
            {"id": "menu_main", "title": "Volver al Inicio"}
        ]
        WhatsAppService.send_interactive_button(user_phone, menu_text, buttons)
