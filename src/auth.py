"""
Shared HTTP Basic Auth utilities for ProAlto admin blueprints.
"""
import functools
from flask import request, Response
from config import Config


def check_auth(username, password):
    """Verify admin credentials."""
    return username == Config.ADMIN_USER and password == Config.ADMIN_PASS


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
