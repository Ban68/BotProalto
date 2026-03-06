from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from src.services import WhatsAppService

def is_business_hours() -> bool:
    """Check if the current time is within business hours (8am - 5pm, Mon-Fri)."""
    try:
        tz = ZoneInfo(Config.ADMIN_TIMEZONE)
    except Exception as e:
        print(f"Timezone error, defaulting to UTC: {e}")
        tz = None
        
    now = datetime.now(tz)
    
    # Check if Monday-Friday (0=Monday, 4=Friday)
    if now.weekday() > 4:
        return False
        
    # Check if time is between 08:00 and 17:00
    if 8 <= now.hour < 17:
        return True
    
    return False

def notify_admins(message: str) -> None:
    """Send a WhatsApp message to all configured admin numbers."""
    if not Config.ADMIN_NOTIFY_NUMBERS or Config.ADMIN_NOTIFY_NUMBERS == [""]:
        print("No admin numbers configured for notifications.")
        return
        
    for number in Config.ADMIN_NOTIFY_NUMBERS:
        phone = number.strip()
        if phone:
            WhatsAppService.send_message(phone, message)

def notify_admin_agent_request(user_phone: str) -> None:
    """Notify admins that a user has requested an agent during business hours."""
    if is_business_hours():
        msg = (
            f"🚨 *Aviso de Soporte*\n\n"
            f"El usuario con número {user_phone} ha solicitado hablar con un asesor.\n"
            f"Por favor ingresa al panel de control para atenderlo: https://botproalto.onrender.com/admin"
        )
        notify_admins(msg)

def notify_admin_error(user_phone: str, error_msg: str) -> None:
    """Notify admins that a system error occurred while interacting with a user."""
    msg = (
        f"⚠️ *Alerta de Sistema*\n\n"
        f"La conversación con {user_phone} generó un error.\n"
        f"Detalle: {error_msg}"
    )
    notify_admins(msg)
