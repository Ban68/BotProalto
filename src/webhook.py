from flask import Blueprint, request, jsonify, current_app
from config import Config
from src.flows import FlowHandler

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Verification endpoint for Meta Webhook.
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == Config.WEBHOOK_VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            return 'Forbidden', 403
    return 'Bad Request', 400

@webhook_bp.route('/webhook', methods=['POST'])
def receive_message():
    """
    Endpoint to receive messages from WhatsApp Cloud API.
    """
    try:
        data = request.get_json()
        print(f"Received webhook data: {data}") # Debug logging
        
        # Async processing could be added here in the future
        FlowHandler.handle_incoming_message(data)
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error in webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
