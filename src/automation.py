import time
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import get_aprobados_por_el_cliente
from src.services import WhatsAppService
from src.conversation_log import has_sent_aprobado_msg_today, set_user_state

def send_approved_notifications():
    """
    Fetches all applications in 'Aprobado por el cliente' state,
    and sends them a WhatsApp message with a CTA button if they haven't
    already received one today.
    """
    print(f"[{datetime.now()}] Running scheduled task: send_approved_notifications")
    
    aprobados = get_aprobados_por_el_cliente()
    if not aprobados:
        print("No accounts pending notification or error fetching.")
        return

    for user in aprobados:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")
        
        # We need a valid phone number
        # Convert to string and handle possible floats (e.g. 3123456789.0)
        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))
        
        if not phone_str:
            print(f"Skipping user {nombre} due to invalid or missing phone: {telefono}")
            continue
            
        # Ensure country code (putting 57 unconditionally if it's missing)
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"
            
        if has_sent_aprobado_msg_today(phone_str):
            print(f"Already sent automated message to {phone_str} today. Skipping.")
            continue
            
        # Define component for the template variable
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": nombre}
                ]
            }
        ]
        
        WhatsAppService.send_template(phone_str, "estado_verde", components=components)
        
        # Set state to wait for their email reply
        set_user_state(phone_str, "waiting_for_email")
        
        time.sleep(1) # Sleep slightly to avoid rate-limiting

def start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    
    # Run twice a day (e.g., at 09:00 AM and 03:00 PM)
    scheduler.add_job(send_approved_notifications, 'cron', hour=9, minute=0)
    scheduler.add_job(send_approved_notifications, 'cron', hour=15, minute=0)
    
    # Start the scheduler
    scheduler.start()
    print("Background scheduler started (Cron: 09:00 and 15:00).")
    
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown(wait=False))
