from src.services import WhatsAppService

# Simple in-memory storage for MVP (Use DB in production)
# Structure: { "phone_number": { "status": "pending_consent" | "active", "last_interaction": timestamp } }
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
                text_body = message["text"]["body"].lower().strip()
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

        # 2. Main Menu Logic
        if text in ["hola", "menu", "inicio", "start"]:
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

        elif btn_id == "menu_saldo":
            WhatsAppService.send_message(user_phone, "Actualmente esta función está en desarrollo. Pronto podrás consultar tu saldo aquí.")
        
        elif btn_id == "menu_cert":
            WhatsAppService.send_message(user_phone, "Para solicitar tu certificado, por favor envíanos tu número de cédula (Función en desarrollo).")
            
        elif btn_id == "menu_support":
             WhatsAppService.send_message(user_phone, "Un asesor humano te atenderá pronto. Por favor espera...")

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
            {"id": "menu_saldo", "title": "Consultar Saldo"},
            {"id": "menu_cert", "title": "Certificados"},
            {"id": "menu_support", "title": "Hablar con Asesor"}
        ]
        WhatsAppService.send_interactive_button(user_phone, menu_text, buttons)
