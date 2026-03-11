import os
import requests

# ──────────────────────────────────────────────────
#  Cloud Run API Bridge
#  Instead of connecting directly to PostgreSQL
#  (blocked by GCP firewall), we call our secure
#  Cloud Run microservice that queries the DB
#  internally within the same GCP project.
# ──────────────────────────────────────────────────

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "").rstrip("/")
API_TOKEN_SECRET = os.getenv("API_TOKEN_SECRET", "")


def get_solicitud_status(cedula):
    """
    Queries the Cloud Run API bridge to get the latest
    solicitud status for the given cedula.
    Returns a dict with the result or None if not found / error.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"cedula": cedula},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                # Map the Cloud Run response keys to the same dict keys
                # that flows.py already expects (RealDictCursor style)
                return {
                    "nro_solicitud": data.get("nro_solicitud"),
                    "nombre_completo": data.get("nombre_completo", ""),
                    "fecha_de_solicitud": data.get("fecha_de_solicitud", ""),
                    "valor_preestudiado": data.get("valor_preestudiado", 0),
                    "estado_interno": data.get("estado_interno", ""),
                    "plazo": data.get("plazo"),
                }
            else:
                return None
        elif response.status_code == 401:
            print("❌ Cloud Run API: Unauthorized (check API_TOKEN_SECRET)")
            return None
        else:
            print(f"❌ Cloud Run API Error {response.status_code}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error: {e}")
        return None

def get_aprobados_por_el_cliente():
    """
    Queries the Cloud Run API bridge to get all applications 
    in state 'Aprobado por el cliente'.
    Returns a list of dicts (each representing an application) or None.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "aprobados"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("aprobados", [])
            return []
        else:
            print(f"❌ Cloud Run API Error ({response.status_code}): {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out for get_aprobados_por_el_cliente")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for get_aprobados_por_el_cliente: {e}")
        return None


def test_cloud_run_connection():
    """
    Quick health check: sends a dummy cedula to verify the
    Cloud Run function is reachable and responding.
    """
    if not CLOUD_RUN_URL:
        return False, "CLOUD_RUN_URL not configured"

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"cedula": "0"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=5
        )
        if response.status_code == 200:
            return True, "Cloud Run API OK"
        else:
            return False, f"Status {response.status_code}: {response.text}"
    except Exception as e:
        return False, str(e)


def get_saldo(cedula):
    """
    Queries the Cloud Run API bridge to get all active loans
    and their balance for the given cedula.
    Returns a list of dicts (one per loan), empty list if none found, 
    or None if there was a technical error/API failure.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"cedula": cedula, "tipo": "saldo"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("prestamos", [])
            else:
                # Successfully queried, but no loans found for this ID
                return []
        elif response.status_code == 401:
            print(f"❌ Cloud Run API: Unauthorized for cedula {cedula} (check API_TOKEN_SECRET)")
            return None
        else:
            print(f"❌ Cloud Run API Error {response.status_code} for cedula {cedula}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        print(f"❌ Cloud Run API: Request timed out for cedula {cedula}")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for cedula {cedula}: {e}")
        return None
