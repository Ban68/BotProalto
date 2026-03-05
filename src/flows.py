from src.services import WhatsAppService
from src.database import get_solicitud_status, get_saldo
from src.conversation_log import log_message, set_agent_mode

# Simple in-memory storage for MVP (Use DB in production)
# Structure: { "phone_number": { "status": "pending_consent" | "active" | "waiting_for_cedula", "last_interaction": timestamp } }
user_sessions = {}

class FlowHandler:
    @staticmethod
    def handle_incoming_message(payload):
        """
        Process incoming webhook payload.
        """
        try:
            # Extract relevant info from the complex WhatsApp payload
            entry = payload.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            
            if "messages" not in value:
                # Use cases like status updates (sent, delivered, read) fall here
                return
            
            message = value["messages"][0]
            user_phone = message["from"]
            msg_type = message["type"]
            
            # Initialize session if new
            if user_phone not in user_sessions:
                from src.conversation_log import get_conversation
                conv = get_conversation(user_phone)
                
                init_status = "pending_consent"
                if conv:
                    db_status = conv.get("status")
                    if db_status == "agent":
                        init_status = "agent_mode"
                    elif len(conv.get("messages", [])) > 0:
                        # User has talked to us before, skip consent
                        init_status = "active"
                
                user_sessions[user_phone] = {"status": init_status}
            
            user_state = user_sessions[user_phone]

            # ── Log inbound message ──────────────────────────────────
            if msg_type == "text":
                log_message(user_phone, "inbound", message["text"]["body"].strip(), "text")
            elif msg_type == "interactive":
                btn_title = message["interactive"].get("button_reply", {}).get("title", "")
                log_message(user_phone, "inbound", btn_title, "button_reply")

            # Handle Text Messages
            if msg_type == "text":
                text_body = message["text"]["body"].strip() # Keep case for Cedula
                FlowHandler.process_text_input(user_phone, text_body, user_state)
                
            # Handle Interactive Button Replies
            elif msg_type == "interactive":
                reply = message["interactive"]["button_reply"]
                reply_id = reply["id"]
                FlowHandler.process_button_click(user_phone, reply_id, user_state)
                
        except Exception as e:
            print(f"Error processing message: {e}")

    @staticmethod
    def process_text_input(user_phone, text, state):
        # 0. Agent Mode — bot stays silent, let human advisor handle
        if state["status"] == "agent_mode":
            if text.lower() in ["salir", "cancelar", "volver"]:
                state["status"] = "active"
                set_agent_mode(user_phone, False)
                WhatsAppService.send_message(user_phone, "Has salido del modo asesor. Escribe 'Hola' para ver el menú principal.")
            # Otherwise do nothing — message was already logged above
            return

        # 1. Check Consent Flow
        if state["status"] == "pending_consent":
            FlowHandler.send_habeas_data_prompt(user_phone)
            return
        
        # 2. Check if waiting for Cedula (Application Status)
        if state["status"] == "waiting_for_cedula":
            # Basic validation: ensure it's a number-like string
            if not text.isdigit():
                 WhatsAppService.send_message(user_phone, "Por favor envía solo números, sin puntos ni espacios. Intenta de nuevo:")
                 return

            # 2. Check connections and Maintenance
            from config import Config
            if Config.MAINTENANCE_MODE:
                WhatsAppService.send_message(user_phone, "⚠️ *Sistema en Mantenimiento*\n\nEstamos realizando mejoras en nuestros servidores. Por favor intenta consultar tu estado más tarde. Agradecemos tu paciencia.")
                return

            # Query Database
            result = get_solicitud_status(text)
            
            if result:
                # Format Response
                estado_interno = result['estado_interno']
                
                # Load Status Mapping
                import json
                import os
                
                mapping_path = os.path.join(os.path.dirname(__file__), 'status_mapping.json')
                status_messages = {}
                try:
                    with open(mapping_path, 'r', encoding='utf-8') as f:
                        status_messages = json.load(f)
                except Exception as e:
                    print(f"Error loading status mapping: {e}")

                # Normalize and Map
                clean_status = estado_interno.strip().upper() if estado_interno else "NULL"
                
                # Get user-friendly message or fallback to the internal status if allowed/generic
                mensaje_cliente = status_messages.get(clean_status, estado_interno or "Pendiente / En Estudio")
                
                monto = result['valor_preestudiado']
                nombre = result['nombre_completo']
                fecha = result['fecha_de_solicitud']
                plazo = result.get('plazo') # Safe get in case DB schema is old

                response_msg = (
                    f"🔍 *Resultado de Solicitud*\n\n"
                    f"👤 *Cliente:* {nombre}\n"
                    f"📅 *Fecha:* {fecha}\n"
                    f"💰 *Monto Pre-aprobado:* ${monto:,.0f}\n"
                )

                # Add Term if status is 'APROBADO POR EL CLIENTE'
                if clean_status == "APROBADO POR EL CLIENTE" and plazo:
                    response_msg += f"⏱️ *Plazo:* {plazo} meses\n"

                response_msg += f"📋 *Estado:* {mensaje_cliente}\n"
                WhatsAppService.send_message(user_phone, response_msg)
            else:
                WhatsAppService.send_message(user_phone, f"❌ No encontramos ninguna solicitud reciente con la cédula *{text}*.")
            
            # Return to main menu state
            state["status"] = "active"
            WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 2b. Check if waiting for Cedula (Saldo / Balance)
        if state["status"] == "waiting_for_cedula_saldo":
            if not text.isdigit():
                WhatsAppService.send_message(user_phone, "Por favor envía solo números, sin puntos ni espacios. Intenta de nuevo:")
                return

            from config import Config
            if Config.MAINTENANCE_MODE:
                WhatsAppService.send_message(user_phone, "⚠️ *Sistema en Mantenimiento*\n\nEstamos realizando mejoras en nuestros servidores. Por favor intenta más tarde.")
                return

            # Query Saldo
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
                        
                        # Handle last payment date representation properly
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

            state["status"] = "active"
            WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 3. Main Menu Logic (Reset triggers)
        norm_text = text.lower().strip()
        
        # Base greeting words
        greetings = ["hola", "menu", "inicio", "start", "buenas", "holis", "holi", "saludos", "hi", "hello", "buen", "buenos"]
        
        # Extract the first word and clean punctuation
        first_word = norm_text.split()[0] if norm_text else ""
        for char in [",", ".", "!", "?", "¿", "¡"]:
            first_word = first_word.replace(char, "")
            
        # Match if the first word is a greeting or the exact phrase is a greeting
        exact_phrases = ["buenos dias", "buenos días", "buenas tardes", "buenas noches", "buen dia", "buen día", "que tal", "q tal"]
        is_greeting = first_word in greetings or norm_text in exact_phrases
        
        if is_greeting:
            state["status"] = "active" # Reset any stuck state
            FlowHandler.send_main_menu(user_phone)
        else:
            # Fallback for unrecognized text
            WhatsAppService.send_message(user_phone, "No entendí tu mensaje. Escribe 'Hola' para ver el menú principal.")

    @staticmethod
    def process_button_click(user_phone, btn_id, state):
        if btn_id == "accept_terms":
            state["status"] = "active"
            WhatsAppService.send_message(user_phone, "¡Gracias por aceptar! Bienvenido a ProAlto.")
            FlowHandler.send_main_menu(user_phone)
        
        elif btn_id == "decline_terms":
            WhatsAppService.send_message(user_phone, "Entendemos. No podremos atenderte por este medio sin tu autorización. Si cambias de opinión, escribe 'Hola'.")
            state["status"] = "pending_consent"

        # 3. Handle Client Menu Options
        elif btn_id == "menu_cliente":
            FlowHandler.send_client_menu(user_phone)

        elif btn_id == "menu_solicitud":
            state["status"] = "waiting_for_cedula"
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu solicitud:")

        elif btn_id == "menu_credito":
            WhatsAppService.send_message(user_phone, "Para solicitar tu crédito, por favor llena el siguiente formulario:\n\n👉 https://forms.gle/zXzrcrzVefuoVsEX6")

        elif btn_id == "menu_saldo":
            state["status"] = "waiting_for_cedula_saldo"
            WhatsAppService.send_message(user_phone, "Por favor escribe el número de *Cédula o NIT* (sin puntos ni espacios) para consultar tu saldo:")
            
        elif btn_id == "menu_support":
            state["status"] = "agent_mode"
            set_agent_mode(user_phone, True)
            WhatsAppService.send_message(
                user_phone,
                "👨‍💼 *Modo Asesor Activado*\n\n"
                "Un asesor se conectará contigo en esta misma conversación. "
                "Por favor espera, te responderemos lo más pronto posible.\n\n"
                "_Si deseas volver al menú del bot, escribe *salir*._"
            )

        elif btn_id == "menu_main":
            FlowHandler.send_main_menu(user_phone)

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
