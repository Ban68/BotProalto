import requests
import json
import os
from config import Config
from src.conversation_log import log_message

class WhatsAppService:
    @staticmethod
    def send_message(to_number, message_body, msg_type="text"):
        """
        Send a text message to a WhatsApp user specifically for Cloud API.
        msg_type: log type — use "llm" for LLM-generated responses (admin-only marker).
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
            res_json = response.json()
            
            # Extract WhatsApp Message ID
            wamid = None
            if "messages" in res_json and len(res_json["messages"]) > 0:
                wamid = res_json["messages"][0].get("id")

            # Log outbound message with its ID
            log_message(to_number, "outbound", message_body, msg_type, wamid=wamid)
            return res_json
        except requests.exceptions.RequestException as e:
            print(f"Error sending message: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None

    @staticmethod
    def send_image(to_number, image_url, caption=None):
        """
        Send an image via public URL.
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        if caption:
            data["image"]["caption"] = caption

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            res_json = response.json()
            wamid = res_json["messages"][0].get("id") if "messages" in res_json else None
            log_message(to_number, "outbound", image_url, "image", wamid=wamid)
            return res_json
        except Exception as e:
            print(f"Error sending image: {e}")
            return None

    @staticmethod
    def send_document(to_number, doc_url, filename=None, caption=None):
        """
        Send a document via public URL.
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "document",
            "document": {
                "link": doc_url
            }
        }
        if filename:
            data["document"]["filename"] = filename
        if caption:
            data["document"]["caption"] = caption

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            res_json = response.json()
            wamid = res_json["messages"][0].get("id") if "messages" in res_json else None
            log_message(to_number, "outbound", doc_url, "document", wamid=wamid)
            return res_json
        except Exception as e:
            print(f"Error sending document: {e}")
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
            res_json = response.json()

            # Extract WhatsApp Message ID
            wamid = None
            if "messages" in res_json and len(res_json["messages"]) > 0:
                wamid = res_json["messages"][0].get("id")

            # Log outbound interactive message
            button_titles = [b["reply"]["title"] for b in action_buttons]
            log_text = f"{body_text} [Botones: {', '.join(button_titles)}]"
            log_message(to_number, "outbound", log_text, "interactive", wamid=wamid)
            return res_json
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

    @staticmethod
    def send_template(to_number, template_name, language_code="es_CO", components=None):
        """
        Send a WhatsApp template message.
        components: List of component dicts (e.g. for parameters)
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or []
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            res_json = response.json()
            
            # Extract WhatsApp Message ID
            wamid = None
            if "messages" in res_json and len(res_json["messages"]) > 0:
                wamid = res_json["messages"][0].get("id")

            # Log outbound template message
            log_message(to_number, "outbound", f"[Template: {template_name}]", "template", wamid=wamid)
            return res_json
        except requests.exceptions.RequestException as e:
            print(f"Error sending template: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None

    @staticmethod
    def get_media_url(media_id):
        """
        Fetch the temporary URL for a media file from WhatsApp Cloud API.
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{media_id}"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json().get("url")
        except requests.exceptions.RequestException as e:
            print(f"Error fetching media URL: {e}")
            if e.response:
                print(f"Response content: {e.response.text}")
            return None

    @staticmethod
    def download_media_file(media_url, target_path):
        """
        Download the media file from Meta servers to a local path.
        """
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}"
        }
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            response = requests.get(media_url, headers=headers, stream=True)
            response.raise_for_status()
            
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True
        except Exception as e:
            print(f"Error downloading media file: {e}")
            return False

    @staticmethod
    def upload_to_supabase_storage(local_path, storage_path, content_type):
        """
        Uploads a local file to Supabase Storage ('media' bucket) and returns the public URL.
        """
        from src.conversation_log import supabase_client
        if not supabase_client:
            print("Supabase client not initialized, skipping storage upload.")
            return None
            
        try:
            with open(local_path, "rb") as f:
                file_bytes = f.read()
                
            supabase_client.storage.from_("media").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            
            # Fetch and return the public URL
            url = supabase_client.storage.from_("media").get_public_url(storage_path)
            return url
        except Exception as e:
            print(f"Error uploading media to Supabase Storage: {e}")
            return None

    @staticmethod
    def revoke_message(message_id):
        """
        Delete (revoke) a message previously sent via WhatsApp Cloud API.
        The message must have been sent within the last 2 days.
        Returns (True, result) on success, (False, error_msg) on failure.
        """
        url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
        headers = {
            "Authorization": f"Bearer {Config.API_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "status": "deleted",
            "message_id": message_id.strip() if message_id else message_id
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            res_json = response.json()
            
            if response.status_code >= 200 and response.status_code < 300:
                return True, res_json
            else:
                error_msg = res_json.get("error", {}).get("message", "Error desconocido de WhatsApp")
                print(f"WhatsApp API Error revoking message {message_id}: {error_msg}")
                return False, error_msg
                
        except Exception as e:
            print(f"Exception revoking message {message_id}: {e}")
            return False, str(e)
