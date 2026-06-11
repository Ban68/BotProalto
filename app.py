import hashlib
import os

from flask import Flask, url_for
from config import Config
from src.webhook import webhook_bp
from src.admin import admin_bp
from src.analytics_api import analytics_bp

# Cache de hashes de estáticos: {filename: (mtime, hash8)}
_static_hash_cache = {}


def _static_file_hash(static_folder, filename):
    path = os.path.join(static_folder, filename)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _static_hash_cache.get(filename)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, 'rb') as f:
        digest = hashlib.md5(f.read()).hexdigest()[:8]
    _static_hash_cache[filename] = (mtime, digest)
    return digest


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    # Los módulos JS importados via `import` no llevan ?v=, así que forzamos
    # revalidación por ETag (304 si no cambió) para que un deploy refresque
    # CSS/JS sin Ctrl+F5.
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    @app.template_global()
    def static_v(filename):
        """url_for('static') con ?v=<hash> para cache busting en deploys."""
        digest = _static_file_hash(app.static_folder, filename)
        if digest:
            return url_for('static', filename=filename, v=digest)
        return url_for('static', filename=filename)

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
