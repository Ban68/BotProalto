import os
import json
import base64
from app import app
from src.conversation_log import get_conversations, get_conversation

def run_tests():
    # Setup test client
    print("--- Starting Local Verification ---")
    client = app.test_client()
    
    # 1. Simulate inbound message to the webhook
    payload = {
        "entry": [{
            "id": "12345",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "12345", "phone_number_id": "12345"},
                    "messages": [{
                        "from": "573001234567",
                        "id": "wamid.test.123",
                        "timestamp": "1610990486",
                        "type": "text",
                        "text": {"body": "Hola, necesito información"}
                    }]
                }
            }]
        }]
    }
    
    print("\n[1] Simulating inbound WhatsApp message...")
    res = client.post('/webhook', json=payload)
    print(f"Webhook Status: {res.status_code}")
    
    # 2. Check if it was logged
    print("\n[2] Checking conversation log...")
    convs = get_conversations()
    print(f"Total conversations: {len(convs)}")
    if convs:
        print(f"Latest conversation phone: {convs[0]['phone']}, Status: {convs[0]['status']}")
        
    full_conv = get_conversation("573001234567")
    if full_conv:
        messages = full_conv["messages"]
        print(f"Messages in conversation: {len(messages)}")
        for m in messages:
            print(f"  [{m['direction'].upper()}] {m['text']} (Type: {m['type']})")
            
    # 3. Test Admin Dashboard with Auth
    print("\n[3] Testing Admin Dashboard Page...")
    auth_string = "admin:proalto2024"
    auth_bytes = auth_string.encode('utf-8')
    auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
    headers = {"Authorization": f"Basic {auth_base64}"}
    
    res = client.get('/admin/', headers=headers)
    print(f"/admin/ UI Status: {res.status_code}")
    
    res = client.get('/admin/api/conversations', headers=headers)
    print(f"/admin/api/conversations Status: {res.status_code}")
    print(f"API Data: {json.dumps(res.json, indent=2)}")
    
if __name__ == "__main__":
    run_tests()
