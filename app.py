from flask import Flask
from config import Config
from src.webhook import webhook_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(webhook_bp)

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
        from src.database import get_db_cursor
        try:
            with get_db_cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return "✅ Database Connection OK", 200
        except Exception as e:
            return f"❌ Database Connection Error: {str(e)}", 500

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=Config.DEBUG)
