import requests
import json
from config import Config
from src.conversation_log import log_message

class WhatsAppService:
    @staticmethod
    def send_message(to_number, message_body):
        """
        Send a text message to a WhatsApp user specifically for Cloud API.
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message_body}
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            # Log outbound message
            log_message(to_number, "outbound", message_body, "text")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error sending message: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None

    @staticmethod
    def send_interactive_button(to_number, body_text, buttons):
        """
        Send an interactive message with buttons.
        buttons: list of dictionaries, e.g., [{"id": "btn1", "title": "Option 1"}]
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        action_buttons = []
        for btn in buttons:
            action_buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"]
                }
            })

        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": action_buttons}
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            # Log outbound interactive message
            button_titles = [b["reply"]["title"] for b in action_buttons]
            log_text = f"{body_text} [Botones: {', '.join(button_titles)}]"
            log_message(to_number, "outbound", log_text, "interactive")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error sending interactive message: {e}")
            return None

    @staticmethod
    def send_interactive_list(to_number, body_text, button_text, sections):
        """
        Send an interactive list message (for >3 options).
        sections: list of dicts, e.g. [{ "title": "Section Title", "rows": [{"id": "1", "title": "Row 1"}] }]
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error sending list message: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None
