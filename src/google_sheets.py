import requests
from config import Config

def get_solicitud_reciente_sheet(cedula):
    """
    Llama a la API de Google Apps Script para verificar si la cédula
    fue ingresada en el Google Form recientemente (últimos 3-4 días).
    """
    url = Config.GOOGLE_APPS_SCRIPT_URL
    if not url:
        return None

    try:
        # Hacemos la peticion GET mandando la cédula
        response = requests.get(url, params={"cedula": cedula}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found") and data.get("isRecent"):
                # Si se encuentra y es reciente, devolvemos un diccionario
                return {"en_estudio": True}
            return None
        else:
            print(f"❌ Error en Google Apps Script: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Timeout al conectar con Google Sheets")
        return None
    except Exception as e:
        print(f"❌ Error interno al conectar con Google Sheets: {e}")
        return None


def get_anticipo_by_cedula(cedula):
    """
    Consulta el Apps Script del Sheet de anticipos por cédula.
    Returns: dict con {'found': True, 'nombre_completo', 'fecha_de_solicitud'} si existe,
             None si no existe o si hay error/URL no configurada.
    """
    url = Config.GOOGLE_APPS_SCRIPT_ANTICIPO_URL
    if not url:
        return None
    try:
        response = requests.get(url, params={"cedula": cedula}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data if data.get("found") else None
        print(f"❌ Error en Apps Script de anticipos: {response.status_code} - {response.text}")
        return None
    except requests.exceptions.Timeout:
        print("❌ Timeout consultando Sheet de anticipos")
        return None
    except Exception as e:
        print(f"❌ Error consultando Sheet de anticipos: {e}")
        return None
