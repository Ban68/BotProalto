import requests
import json
from config import Config

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
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error sending interactive message: {e}")
            return None
