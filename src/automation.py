import time
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import get_aprobados_por_el_cliente
from src.services import WhatsAppService
from src.conversation_log import get_notified_phones_batch, set_user_state

# --- TEST MODE CONFIG ---
TEST_MODE = True  # SET TO FALSE BEFORE PRODUCTION
TEST_NUMBER = "573106176713"
# -------------------------

def get_pending_approved_notifications():
    """
    Returns a list of applications in 'Aprobado por el cliente' state
    who are eligible to receive a notification today.
    """
    if TEST_MODE:
        # En modo prueba solo mostramos el número de test (si no se le ha enviado hoy)
        notified = get_notified_phones_batch([TEST_NUMBER])
        if TEST_NUMBER in notified:
            return []
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
    Executes the sending of notifications for a provided list of users.
    Validates Meta response before updating state to prevent ghost conversations.
    """
    results = {"success": 0, "failed": 0, "errors": []}
    
    for user in users_list:
        phone_str = user.get("phone")
        nombre = user.get("name")
        
        if not phone_str:
            continue
            
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": nombre}
                ]
            }
        ]
        
        response = WhatsAppService.send_template(phone_str, "estado_verde", components=components)
        
        # Check if response is truthy AND contains a messages array or message_id indicating success
        if response and response.get('messages'):
            # Only update state if Meta successfully accepted the message
            # But do NOT set the status to active to avoid flooding the admin panel view.
            # set_user_state typically updates status to 'active'. 
            # We will use an internal state bypass or standard set_user_state depending on current logic.
            # Currently set_user_state sets the bot state and the DB state.
            set_user_state(phone_str, "waiting_for_email")
            results["success"] += 1
            from src.conversation_log import log_message
            # Log with 'outbound' so it's detected by the 'already notified' check
            log_message(phone_str, "outbound", f"✅ Notificación Masiva Aprobado enviada a {nombre}.", "bot_notification")
        else:
            error_details = "No response from Meta"
            if response and 'error' in response:
                error_details = response['error'].get('message', str(response))
            elif response:
                error_details = str(response)
                
            print(f"[{datetime.now()}] ERROR sending bulk to {phone_str}: {error_details}")
            results["failed"] += 1
            results["errors"].append({"phone": phone_str, "error": error_details})
            
        time.sleep(1) # Sleep slightly to avoid rate-limiting
        
    return results

def send_approved_notifications():
    """ 
    Legacy wrapper, used for testing or raw script execution.
    """
    pending = get_pending_approved_notifications()
    execute_bulk_approved_notifications(pending)

def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    
    # DESACTIVADO TEMPORALMENTE PARA REVISIÓN
    # scheduler.add_job(send_approved_notifications, 'cron', hour=9, minute=0)
    # scheduler.add_job(send_approved_notifications, 'cron', hour=15, minute=0)
    
    # Start the scheduler
    scheduler.start()
    print("Background scheduler started (TAREAS AUTOMÁTICAS DESACTIVADAS).")
    
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown(wait=False))
