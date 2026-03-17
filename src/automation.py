import time
import atexit
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import get_aprobados_por_el_cliente, get_falta_documento
from src.services import WhatsAppService
from src.conversation_log import (
    get_notified_phones_batch, set_user_state, get_template_stats_batch,
    get_notified_phones_rojo_batch, get_template_stats_batch_rojo
)

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
        # Comentamos el filtro para poder probar varias veces el mismo día en modo test
        return [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "monto": 1000000, "plazo": 12}]

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
            
        raw_users.append({
            "phone": phone_str, 
            "name": nombre,
            "monto": user.get("valor_preestudiado", 0),
            "plazo": user.get("plazo", 0)
        })
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return []

    # SINGLE query to Supabase for all phones
    notified_today = get_notified_phones_batch(phones_to_check)
    
    # Filter out those already notified
    eligible_users = [u for u in raw_users if u["phone"] not in notified_today]

    # Enrich with total send count and last send timestamp
    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    eligible_users.sort(key=lambda u: u["send_count"])
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
            
        # Format monto and plazo for better presentation
        monto_val = user.get("monto", 0)
        # Colombia style: dot as thousand separator
        if isinstance(monto_val, (int, float)):
            monto_format = f"${monto_val:,.0f}".replace(",", ".")
        else:
            monto_format = str(monto_val)
        
        plazo_val = user.get("plazo", 0)
        plazo_format = f"{plazo_val} cuotas"
        
        components = [
            {
                "type": "body",
                "parameters": [
                    {
                        "type": "text", 
                        "text": nombre,
                        "parameter_name": "nombre"
                    },
                    {
                        "type": "text", 
                        "text": monto_format,
                        "parameter_name": "monto"
                    },
                    {
                        "type": "text", 
                        "text": plazo_format,
                        "parameter_name": "plazo"
                    }
                ]
            }
        ]
        
        response = WhatsAppService.send_template(phone_str, "estado_verde", components=components)
        
        # Check if response is truthy AND contains a messages array or message_id indicating success
        if response and response.get('messages'):
            # Only update state if Meta successfully accepted the message
            set_user_state(phone_str, "waiting_for_email")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
            
            results["success"] += 1
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")
            
    return results

def execute_bulk_leads_notifications(users_list):
    """
    Sends the 'contacto_leads' template to a list of leads.
    Returns summary of results.
    """
    results = {"total": len(users_list), "success": 0, "fail": 0, "errors": []}
    
    for user in users_list:
        phone_str = str(user.get("phone", "")).strip()
        # Clean phone number
        phone_str = "".join(filter(str.isdigit, phone_str))
        if not phone_str:
            continue
            
        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        nombre = user.get("name", "Cliente").strip()
        
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
        
        response = WhatsAppService.send_template(phone_str, "contacto_leads", components=components)
        
        if response and response.get('messages'):
            results["success"] += 1
            set_user_state(phone_str, "lead_notified")
            
            # Log a greeting for name scraping
            from src.conversation_log import log_message
            log_message(phone_str, "outbound", f"¡Hola {nombre}!", "text")
        else:
            results["fail"] += 1
            error_msg = "No response from Meta"
            if response and response.get('error'):
                error_msg = response['error'].get('message', error_msg)
            results["errors"].append(f"{phone_str}: {error_msg}")
            
    return results

REQUIRED_DOCUMENTS = [
    "2 últimos desprendibles de pago de nómina",
    "Certificado laboral vigente",
    "Foto de cédula (ambos lados)",
    "Recibo de servicio público reciente (agua, luz, gas o telefonía)"
]

def get_pending_falta_documento_notifications():
    """
    Returns a list of applications in 'Falta algún documento' state
    who are eligible to receive a notification today.
    """
    if TEST_MODE:
        return [{"phone": TEST_NUMBER, "name": "PROALTO TEST", "send_count": 0, "last_sent": None}]

    clientes = get_falta_documento()
    if not clientes:
        return []

    raw_users = []
    phones_to_check = []

    for user in clientes:
        telefono = user.get("telefono")
        nombre = user.get("nombre_completo", "Cliente")

        phone_str = str(telefono).split(".")[0]
        phone_str = "".join(filter(str.isdigit, phone_str))

        if not phone_str:
            continue

        if not phone_str.startswith("57"):
            phone_str = f"57{phone_str}"

        raw_users.append({"phone": phone_str, "name": nombre})
        phones_to_check.append(phone_str)

    if not phones_to_check:
        return []

    notified_today = get_notified_phones_rojo_batch(phones_to_check)
    eligible_users = [u for u in raw_users if u["phone"] not in notified_today]

    eligible_phones = [u["phone"] for u in eligible_users]
    stats = get_template_stats_batch_rojo(eligible_phones)
    for user in eligible_users:
        s = stats.get(user["phone"], {})
        user["send_count"] = s.get("count", 0)
        user["last_sent"] = s.get("last_sent", None)

    return eligible_users


def execute_bulk_falta_documento_notifications(users_list):
    """
    Sends the 'estado_rojo' template to a list of users with missing documents.
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

        response = WhatsAppService.send_template(phone_str, "estado_rojo", components=components)

        if response and response.get('messages'):
            set_user_state(phone_str, "waiting_for_docs_rojo")
            from src.conversation_log import set_client_name
            set_client_name(phone_str, nombre)
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
