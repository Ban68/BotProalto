import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Meta (Facebok) Config
    WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "proalto_secure_token")
    API_TOKEN = os.getenv("API_TOKEN")
    BUSINESS_PHONE = os.getenv("BUSINESS_PHONE")
    API_VERSION = "v21.0"
    
    # App Config
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True") == "True"
    
    # Notifications Config
    ADMIN_NOTIFY_NUMBERS = os.getenv("ADMIN_NOTIFY_NUMBERS", "").split(",")
    ADMIN_TIMEZONE = os.getenv("ADMIN_TIMEZONE", "America/Bogota")
    
    # Admin Panel Config
    ADMIN_USER = os.getenv("ADMIN_USER", "admin")
    ADMIN_PASS = os.getenv("ADMIN_PASS", "proalto2024")
    
    # Supabase (Chat History) Config
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Emergency Maintenance Mode: Set to True to disable DB calls
    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "False") == "True"
