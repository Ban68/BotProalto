from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from src.services import WhatsAppService

def is_business_hours() -> bool:
    """Check if the current time is within business hours (8am - 5pm, Mon-Fri)."""
    try:
        tz = ZoneInfo(Config.ADMIN_TIMEZONE)
    except Exception as e:
        print(f"Timezone error: {e}")
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
            f"Por favor ingresa al panel de control para atenderlo: https://bot.proalto.co/admin"
        )
        notify_admins(msg)

def notify_admin_llm_request(user_phone: str, tipo: str) -> None:
    """Notify admins that the LLM agent registered a pending request (no escalation)."""
    tipo_labels = {
        "desembolso_pendiente": "Desembolso pendiente",
        "paz_salvo": "Paz y salvo",
        "compra_cartera": "Compra de cartera",
        "error_descuento": "Error en descuentos",
        "prepago": "Prepago/Abono",
        "cambio_cuenta": "Cambio de cuenta",
        "urgente": "Urgente",
        "reclamo": "Reclamo formal",
        "general": "Consulta general",
    }
    label = tipo_labels.get(tipo, tipo)
    msg = (
        f"📋 *Nueva Solicitud Registrada*\n\n"
        f"El agente LLM registró una solicitud de tipo *{label}* para el número {user_phone}.\n"
        f"Revísala en el panel: https://bot.proalto.co/admin"
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


def notify_admin_contact_update(user_phone: str, client_name: str, summary: dict) -> None:
    """Notify admins that a client just confirmed their yearly contact-data update.

    summary keys (all optional): cedula, telefono_principal, telefono_alterno,
    direccion, email, ref_nombre, ref_telefono, ref_parentesco.
    """
    def _v(k):
        return (summary or {}).get(k) or "-"

    msg = (
        f"📝 *Actualización de datos confirmada*\n\n"
        f"Cliente: {client_name or 'Cliente'} ({user_phone})\n"
        f"Cédula: {_v('cedula')}\n"
        f"Teléfono actual: {_v('telefono_principal')}\n"
        f"Teléfono alterno: {_v('telefono_alterno')}\n"
        f"Dirección: {_v('direccion')}\n"
        f"Correo: {_v('email')}\n"
        f"Referencia: {_v('ref_nombre')} - {_v('ref_telefono')} ({_v('ref_parentesco')})\n\n"
        f"Por favor sincroniza estos datos en el core. "
        f"Revísalo en el panel: https://bot.proalto.co/admin"
    )
    notify_admins(msg)


def notify_admin_cedula_mismatch(user_phone: str) -> None:
    """Notify admins that a client failed cedula verification during the
    contact-data update flow and was escalated to a human agent."""
    msg = (
        f"⚠️ *Verificación de identidad fallida*\n\n"
        f"El número {user_phone} intentó actualizar sus datos pero no logró "
        f"verificar su cédula tras varios intentos. Fue derivado a asesor humano.\n"
        f"Revísalo en el panel: https://bot.proalto.co/admin"
    )
    notify_admins(msg)
