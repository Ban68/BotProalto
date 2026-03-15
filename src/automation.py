import time
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import get_aprobados_por_el_cliente
from src.services import WhatsAppService
from src.conversation_log import get_notified_phones_batch, set_user_state

# --- TEST MODE CONFIG ---
TEST_MODE = False  # SET TO FALSE BEFORE PRODUCTION
TEST_NUMBER = "573106176713"
# -------------------------

def get_pending_approved_notifications():
    """
    Returns a list of applications in 'Aprobado por el cliente' state
    who are eligible to receive a notification today.
    """
    if TEST_MODE:
        # En modo prueba solo mostramos el número de test (si no se le ha enviado hoy)
        # Comentamos el filtro para poder probar varias veces el mismo día en modo test
        return [{"phone": TEST_NUMBER, "name": "PROALTO TEST"}]

    aprobados = get_aprobados_por_el_cliente()
    if not aprobados:
        return []

    raw_users = []
    phones_to_check = []
    
    for user in aprobados:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")
        
        # We need a valid phone number
        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))
        
        if not phone_str:
            continue
            
        # Ensure country code
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"
            
        raw_users.append({"phone": phone_str, "name": nombre})
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return []

    # SINGLE query to Supabase for all phones
    notified_today = get_notified_phones_batch(phones_to_check)
    
    # Filter out those already notified
    eligible_users = [u for u in raw_users if u["phone"] not in notified_today]
        
    return eligible_users

def execute_bulk_approved_notifications(users_list):
    """
    Sends the 'estado_verde' template to a list of users.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}
    
    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")
        
        if not phone_str:
            continue
            
        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text", 
                        "text": nombre,
                        "parameter_name": "nombre"
                    }
                ]
            }
        ]
        
        response = WhatsAppService.send_template(phone_str, "estado_verde", components=components)
        
        # Check if response is truthy AND contains a messages array or message_id indicating success
        if response and response.get('messages'):
            # Only update state if Meta successfully accepted the message
            set_user_state(phone_str, "waiting_for_email")
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")
            
    return results

# --- Scheduler Logic for future automation ---
def scheduled_task():
    print(f"[{datetime.now()}] Checking for pending approved notifications...")
    # This is where we'd put the automated logic if we want it 100% hands-free later
    # For now, it's triggered manually from the admin panel.
    pass

scheduler = BackgroundScheduler()
# scheduler.add_job(func=scheduled_task, trigger="interval", minutes=60)
# scheduler.start()

# atexit.register(lambda: scheduler.shutdown())
