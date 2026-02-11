from src.services import WhatsAppService
from src.database import get_solicitud_status

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
                user_sessions[user_phone] = {"status": "pending_consent"}
            
            user_state = user_sessions[user_phone]
            
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

            # Query Database
            result = get_solicitud_status(text)
            
            if result:
                # Format Response
                estado = result['estado_interno']
                if not estado: # Handle None or empty string
                    estado = "Pendiente / En Estudio"
                elif estado.strip().upper() == "LISTO EN DOCUSIGN":
                    estado = "En legalización de contratos para proceder a desembolso"
                
                monto = result['valor_preestudiado']
                nombre = result['nombre_completo']
                fecha = result['fecha_de_solicitud']
                
                response_msg = (
                    f"🔍 *Resultado de Solicitud*\n\n"
                    f"👤 *Cliente:* {nombre}\n"
                    f"📅 *Fecha:* {fecha}\n"
                    f"💰 *Monto Pre-aprobado:* ${monto:,.0f}\n"
                    f"📋 *Estado Actual:* {estado}\n"
                )
                WhatsAppService.send_message(user_phone, response_msg)
            else:
                WhatsAppService.send_message(user_phone, f"❌ No encontramos ninguna solicitud reciente con la cédula *{text}*.")
            
            # Return to main menu state
            state["status"] = "active"
            WhatsAppService.send_message(user_phone, "¿Necesitas algo más? Escribe 'Hola' para ver el menú.")
            return

        # 3. Main Menu Logic (Reset triggers)
        norm_text = text.lower()
        if norm_text in ["hola", "menu", "inicio", "start"]:
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
            WhatsAppService.send_message(user_phone, "Esta función de Saldo está en desarrollo. Intenta 'Estado Solicitud'.")
            
        elif btn_id == "menu_support":
             WhatsAppService.send_message(user_phone, "Un asesor humano te atenderá pronto. Por favor espera...")

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
