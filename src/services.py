import requests
import json
import os
import time
from config import Config
from src.conversation_log import log_message
from src import test_mode, error_tracker


def _fake_meta_response() -> dict:
    """Respuesta simulada compatible con la forma que devuelve Meta."""
    return {"messages": [{"id": "test_message"}]}


# Timeout por intento (segundos) y reintentos ante errores transitorios.
# Sin timeout, un cuelgue de red bloquea el hilo de Flask indefinidamente.
_SEND_TIMEOUT = 15
_SEND_ATTEMPTS = 3          # 1 intento + 2 reintentos
_SEND_BACKOFF = (1.5, 3.0)  # espera antes del 2º y 3º intento


def _send_to_meta(to_number, payload, kind, log_text, log_type):
    """POST a la Cloud API con timeout, reintentos y registro de resultado.

    - Reintenta solo errores transitorios (5xx de Meta, fallos de red, rate
      limit); los rechazos definitivos (token, ventana 24h, payload) no.
    - Éxito  → loguea el outbound en Supabase con su wamid y devuelve el JSON.
    - Fracaso → loguea el mensaje como msg_type "failed" (visible en el panel),
      registra el evento clasificado en error_tracker y devuelve None (mismo
      contrato que antes para los callers).
    """
    url = f"https://graph.facebook.com/{Config.API_VERSION}/{Config.BUSINESS_PHONE}/messages"
    headers = {
        "Authorization": f"Bearer {Config.API_TOKEN}",
        "Content-Type": "application/json",
    }

    last_classified = None
    for attempt in range(_SEND_ATTEMPTS):
        try:
            response = requests.post(url, headers=headers, json=payload,
                                     timeout=_SEND_TIMEOUT)
            response.raise_for_status()
            res_json = response.json()

            wamid = None
            if "messages" in res_json and len(res_json["messages"]) > 0:
                wamid = res_json["messages"][0].get("id")
            log_message(to_number, "outbound", log_text, log_type, wamid=wamid)
            return res_json

        except requests.exceptions.RequestException as e:
            last_classified = error_tracker.classify_send_exception(e)
            print(f"Error sending {kind} (intento {attempt + 1}/{_SEND_ATTEMPTS}): "
                  f"{last_classified['detail']}")
            if not last_classified["retryable"] or attempt == _SEND_ATTEMPTS - 1:
                break
            time.sleep(_SEND_BACKOFF[min(attempt, len(_SEND_BACKOFF) - 1)])

    # Todos los intentos fallaron: dejar rastro visible y clasificado.
    error_tracker.record_event(
        last_classified["category"],
        f"Envío {kind} fallido tras {_SEND_ATTEMPTS if last_classified['retryable'] else 1} "
        f"intento(s): {last_classified['detail']}",
        phone=to_number,
        http_status=last_classified["http_status"],
        meta_code=last_classified["meta_code"],
    )
    log_message(to_number, "outbound", log_text, "failed")
    return None


def _staging_blocks_send(to_number, kind: str, summary) -> bool:
    """Guard global de staging (cinturón y tirantes).

    Cuando ENVIRONMENT == "staging", bloquea CUALQUIER envío real saliente a
    Meta/WhatsApp y lo registra en log en lugar de enviarlo. Es adicional e
    independiente del test_mode: aunque un teléfono real (no de prueba) se cuele
    en el entorno de staging, nunca recibirá un mensaje. Se invoca en cada método
    de envío DESPUÉS del check de test_mode (para que el panel /admin/test siga
    funcionando con teléfonos de prueba). Devuelve True si bloqueó el envío.
    """
    if Config.IS_STAGING:
        print(f"[STAGING] Envío real bloqueado → {to_number} | {kind}: {str(summary)[:140]}")
        return True
    return False


class WhatsAppService:
    @staticmethod
    def send_message(to_number, message_body, msg_type="text"):
        """
        Send a text message to a WhatsApp user specifically for Cloud API.
        msg_type: log type — use "llm" for LLM-generated responses (admin-only marker).
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "text",
                "body": message_body,
                "msg_type": msg_type,
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "text", message_body):
            return _fake_meta_response()

        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message_body}
        }
        return _send_to_meta(to_number, data, "text", message_body, msg_type)

    @staticmethod
    def send_image(to_number, image_url, caption=None):
        """
        Send an image via public URL.
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "image",
                "url": image_url,
                "caption": caption or "",
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "image", image_url):
            return _fake_meta_response()

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
        return _send_to_meta(to_number, data, "image", image_url, "image")

    @staticmethod
    def send_document(to_number, doc_url, filename=None, caption=None):
        """
        Send a document via public URL.
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "document",
                "url": doc_url,
                "filename": filename or "",
                "caption": caption or "",
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "document", doc_url):
            return _fake_meta_response()

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
        return _send_to_meta(to_number, data, "document", doc_url, "document")

    @staticmethod
    def send_interactive_button(to_number, body_text, buttons):
        """
        Send an interactive message with buttons.
        buttons: list of dictionaries, e.g., [{"id": "btn1", "title": "Option 1"}]
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "interactive",
                "body": body_text,
                "buttons": [{"id": b.get("id"), "title": b.get("title")} for b in (buttons or [])],
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "interactive", body_text):
            return _fake_meta_response()

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

        button_titles = [b["reply"]["title"] for b in action_buttons]
        log_text = f"{body_text} [Botones: {', '.join(button_titles)}]"
        return _send_to_meta(to_number, data, "interactive", log_text, "interactive")

    @staticmethod
    def send_interactive_list(to_number, body_text, button_text, sections):
        """
        Send an interactive list message (for >3 options).
        sections: list of dicts, e.g. [{ "title": "Section Title", "rows": [{"id": "1", "title": "Row 1"}] }]
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "list",
                "body": body_text,
                "button_text": button_text,
                "sections": sections,
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "list", body_text):
            return _fake_meta_response()

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

        # Las listas (menús) ahora también quedan en el historial del panel;
        # antes eran invisibles incluso cuando salían bien.
        row_titles = [row.get("title", "") for sec in (sections or []) for row in sec.get("rows", [])]
        log_text = f"{body_text} [Lista: {', '.join(row_titles)}]"
        return _send_to_meta(to_number, data, "list", log_text, "interactive")

    @staticmethod
    def send_template(to_number, template_name, language_code="es_CO", components=None):
        """
        Send a WhatsApp template message.
        components: List of component dicts (e.g. for parameters)
        """
        if test_mode.is_test_phone(to_number):
            test_mode.append_outbound(to_number, {
                "type": "template",
                "template_name": template_name,
                "language_code": language_code,
                "components": components or [],
            })
            return _fake_meta_response()

        if _staging_blocks_send(to_number, "template", template_name):
            return _fake_meta_response()

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
        return _send_to_meta(to_number, data, "template",
                             f"[Template: {template_name}]", "template")

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
            response = requests.get(url, headers=headers, timeout=_SEND_TIMEOUT)
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
            
            response = requests.get(media_url, headers=headers, stream=True, timeout=60)
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
        if isinstance(message_id, str) and message_id.startswith("test_"):
            return True, {"status": "test_skipped"}

        if _staging_blocks_send(message_id, "revoke", message_id):
            return True, {"status": "staging_skipped"}

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
            response = requests.post(url, headers=headers, json=data, timeout=_SEND_TIMEOUT)
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
