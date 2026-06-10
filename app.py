from flask import Flask
from config import Config
from src.webhook import webhook_bp
from src.admin import admin_bp
from src.analytics_api import analytics_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)
    
    @app.route('/')
    def index():
        return "ProAlto Bot is running 🚀", 200

    @app.route('/privacy')
    def privacy():
        return """
        <html>
            <head><title>Privacy Policy</title></head>
            <body>
                <h1>Privacy Policy for ProAlto Bot</h1>
                <p>We process data only for the purpose of communicating with customers via WhatsApp.</p>
                <p>No user data is shared with third parties.</p>
            </body>
        </html>
        """, 200

    @app.route('/health')
    def health():
        return "OK", 200

    @app.route('/whoami')
    def whoami():
        try:
            import requests
            ip = requests.get('https://api.ipify.org', timeout=5).text
            return f"Render Outbound IP: {ip}", 200
        except Exception as e:
            return str(e), 500

    return app

app = create_app()

print(f"[BOOT] ProAlto Bot — ENVIRONMENT={Config.ENVIRONMENT}")

# Start background automation.
# En STAGING NO arrancamos el scheduler: las tareas programadas mutan estado en
# Supabase y disparan campañas. Como staging comparte recursos con producción,
# dejarlo correr "tocaría" producción (marcaría registros como notificados,
# escribiría logs) aunque los envíos a Meta ya estén bloqueados por el guard.
# Ver docs/STAGING.md.
if Config.IS_STAGING:
    print("[STAGING] Scheduler de automatización DESACTIVADO (no se tocan datos de producción).")
else:
    try:
        from src.automation import start_scheduler
        start_scheduler()
    except ImportError as e:
        print(f"Could not start scheduler: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
