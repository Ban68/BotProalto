from flask import Flask
from config import Config
from src.webhook import webhook_bp
from src.admin import admin_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)
    
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

# Start background automation
try:
    from src.automation import start_scheduler
    start_scheduler()
except ImportError as e:
    print(f"Could not start scheduler: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
