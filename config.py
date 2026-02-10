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
