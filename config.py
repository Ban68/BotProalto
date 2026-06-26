import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class Config:
    # Meta (Facebok) Config
    WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "")
    APP_SECRET = os.getenv("APP_SECRET", "")
    API_TOKEN = os.getenv("API_TOKEN")
    BUSINESS_PHONE = os.getenv("BUSINESS_PHONE")
    API_VERSION = "v21.0"
    ENFORCE_WEBHOOK_SIGNATURE = _env_bool("ENFORCE_WEBHOOK_SIGNATURE", False)
    
    # App Config
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True") == "True"

    # Deployment environment: "production" | "staging".
    # En "staging" se bloquea TODO envío real saliente a WhatsApp/Meta y las
    # notificaciones a admins (ver guard en src/services.py). Es independiente y
    # adicional al test_mode (cinturón y tirantes): garantiza que ningún teléfono
    # real reciba mensajes desde el entorno de pruebas. Default seguro: production.
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production").strip().lower()
    IS_STAGING = ENVIRONMENT == "staging"
    ENABLE_DIAGNOSTICO_ACTIVOS = _env_bool("ENABLE_DIAGNOSTICO_ACTIVOS", False)
    
    # Notifications Config
    ADMIN_NOTIFY_NUMBERS = os.getenv("ADMIN_NOTIFY_NUMBERS", "").split(",")
    ADMIN_TIMEZONE = os.getenv("ADMIN_TIMEZONE", "America/Bogota")
    
    # Admin Panel Config
    ADMIN_USER = os.getenv("ADMIN_USER", "")
    ADMIN_PASS = os.getenv("ADMIN_PASS", "")
    
    # Supabase (Chat History) Config
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Emergency Maintenance Mode: Set to True to disable DB calls
    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "False") == "True"
    
    # Google Apps Script Web App (Fallback form check)
    GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycbwPHixL8u1fNY43ifidJXYLWMMQnXQWdWGS0lkKDs1EUDrLLu0NZl_FVPxE7hLhi-Jy/exec")

    # Google Apps Script Web App (Sheet de Anticipo de Salario — consulta por cédula)
    # .strip() defensivo: si en Render se pega la URL con un espacio o newline
    # al final, la petición HTTP a Google falla silenciosamente.
    GOOGLE_APPS_SCRIPT_ANTICIPO_URL = os.getenv("GOOGLE_APPS_SCRIPT_ANTICIPO_URL", "").strip()

    @classmethod
    def configuration_warnings(cls) -> list[dict]:
        """Return non-fatal configuration warnings for diagnostics.

        The app must keep booting even when a variable is missing; risky
        actions decide locally whether to continue or block.
        """
        warnings = []

        def add(name, severity, detail, impact):
            warnings.append({
                "name": name,
                "severity": severity,
                "detail": detail,
                "impact": impact,
            })

        if not cls.APP_SECRET:
            add(
                "APP_SECRET",
                "critical" if cls.ENFORCE_WEBHOOK_SIGNATURE else "warning",
                "No configurado.",
                "La firma del webhook no puede validarse; con ENFORCE_WEBHOOK_SIGNATURE=true se rechazarán webhooks.",
            )
        elif not cls.ENFORCE_WEBHOOK_SIGNATURE:
            add(
                "ENFORCE_WEBHOOK_SIGNATURE",
                "warning",
                "Desactivado.",
                "Los webhooks no se rechazan por firma mientras se valida el rollout.",
            )

        if not os.getenv("API_TOKEN_SECRET", "").strip():
            add(
                "API_TOKEN_SECRET",
                "critical",
                "No configurado.",
                "Cloud Run debe rechazar consultas protegidas hasta configurar el token.",
            )

        if not cls.ADMIN_USER or not cls.ADMIN_PASS:
            add(
                "ADMIN_USER/ADMIN_PASS",
                "critical",
                "Credenciales incompletas.",
                "El panel admin queda bloqueado, pero el webhook puede seguir atendiendo conversaciones.",
            )

        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            add(
                "SUPABASE_URL/SUPABASE_KEY",
                "critical",
                "Credenciales incompletas.",
                "Historial, panel y campañas pueden quedar limitados; la app no aborta el arranque.",
            )

        return warnings

