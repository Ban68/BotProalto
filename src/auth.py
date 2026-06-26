"""
Shared HTTP Basic Auth utilities for ProAlto admin blueprints.
"""
import functools
import secrets
from flask import request, Response
from config import Config

_missing_admin_credentials_warned = False


def check_auth(username, password):
    """Verify admin credentials."""
    global _missing_admin_credentials_warned
    if not Config.ADMIN_USER or not Config.ADMIN_PASS:
        if not _missing_admin_credentials_warned:
            print("[CONFIG] ADMIN_USER/ADMIN_PASS incompletos: panel admin bloqueado, app sigue activa.")
            _missing_admin_credentials_warned = True
        return False
    return (
        secrets.compare_digest(username or "", Config.ADMIN_USER)
        and secrets.compare_digest(password or "", Config.ADMIN_PASS)
    )


def authenticate():
    """Send a 401 response to prompt for credentials."""
    return Response(
        'Acceso no autorizado. Por favor ingresa tus credenciales.',
        401,
        {'WWW-Authenticate': 'Basic realm="ProAlto Admin"'}
    )


def requires_auth(f):
    """Decorator that requires HTTP Basic Auth."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
