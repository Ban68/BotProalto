import os
import time
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


def _post_with_retry(url, json_payload, headers, timeout=10, retries=2):
    """POST with automatic retry on timeout (handles Cloud Run cold starts)."""
    for attempt in range(retries + 1):
        try:
            return requests.post(url, json=json_payload, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(1)
                timeout = min(timeout + 5, 20)
            else:
                raise


def get_solicitud_status(cedula):
    """
    Queries the Cloud Run API bridge to get the latest
    solicitud status for the given cedula.
    Returns: dict with data (found), {} (not found), None (API error).
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = _post_with_retry(
            CLOUD_RUN_URL,
            json_payload={"cedula": cedula},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
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
                    "cuota": data.get("cuota"),
                    "frecuencia": data.get("frecuencia", ""),
                    "empresa": data.get("empresa", ""),
                    "documentos_faltantes": data.get("documentos_faltantes", ""),
                    "tipo_empleador": data.get("tipo_empleador", "EMPRESA"),
                }
            else:
                return {}  # Successfully queried, but no solicitud found
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


def get_falta_documento():
    """
    Queries the Cloud Run API bridge to get all applications
    in state 'Falta algún documento'.
    Returns a list of dicts (each representing an application) or None.
    NOTE: The Cloud Run API must support {"tipo": "falta_documento"}.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "falta_documento"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("clientes", [])
            return []
        else:
            print(f"❌ Cloud Run API Error ({response.status_code}): {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out for get_falta_documento")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for get_falta_documento: {e}")
        return None


def get_denegado():
    """
    Queries the Cloud Run API bridge to get all applications
    in state 'DENEGADO' or 'CANCELADO POR LA EMPRESA'.
    Returns a list of dicts (each representing an application) or None.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "denegado"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("clientes", [])
            return []
        else:
            print(f"❌ Cloud Run API Error ({response.status_code}): {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out for get_denegado")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for get_denegado: {e}")
        return None


def get_listo_en_docusign():
    """
    Queries the Cloud Run API bridge to get all applications
    in state 'Listo en DocuSign'.
    Returns a list of dicts (each representing an application) or None.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "listo_en_docusign"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("clientes", [])
            return []
        else:
            print(f"❌ Cloud Run API Error ({response.status_code}): {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out for get_listo_en_docusign")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for get_listo_en_docusign: {e}")
        return None


def get_clientes_activos():
    """
    Queries the Cloud Run API bridge to get all clients with an active loan.
    Used by the yearly contact-data update campaign.

    NOTE: The Cloud Run API must support {"tipo": "activos"} returning a
    `clientes` array with at least: telefono, nombre_completo, cedula.
    """
    if not CLOUD_RUN_URL:
        print("❌ CLOUD_RUN_URL not configured")
        return None

    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "activos"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=20
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("clientes", [])
            return []
        else:
            print(f"❌ Cloud Run API Error ({response.status_code}): {response.text}")
            return None
    except requests.exceptions.Timeout:
        print("❌ Cloud Run API: Request timed out for get_clientes_activos")
        return None
    except Exception as e:
        print(f"❌ Cloud Run API Error for get_clientes_activos: {e}")
        return None


def get_name_by_phone(phone: str) -> str | None:
    """
    Queries the Cloud Run API to get the client's name by phone number.
    Returns nombre_completo or None if not found / error.
    """
    if not CLOUD_RUN_URL:
        return None
    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "por_telefono", "telefono": phone},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return data.get("nombre_completo")
    except Exception as e:
        print(f"❌ Cloud Run get_name_by_phone error for {phone}: {e}")
    return None


def get_client_context_by_phone(phone: str) -> dict | None:
    """
    Fetches full solicitud context for a phone number to inject into the LLM prompt.
    Returns a dict with solicitud fields, or None if not found / error.
    """
    if not CLOUD_RUN_URL:
        return None
    try:
        response = requests.post(
            CLOUD_RUN_URL,
            json={"tipo": "por_telefono_completo", "telefono": phone},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("found"):
                return {
                    "nro_solicitud": data.get("nro_solicitud"),
                    "nombre_completo": data.get("nombre_completo", ""),
                    "cedula": data.get("cedula", ""),
                    "fecha_de_solicitud": data.get("fecha_de_solicitud", ""),
                    "valor_preestudiado": data.get("valor_preestudiado", 0),
                    "estado_interno": data.get("estado_interno", ""),
                    "plazo": data.get("plazo"),
                    "cuota": data.get("cuota"),
                    "empresa": data.get("empresa", ""),
                    "documentos_faltantes": data.get("documentos_faltantes", ""),
                    "tipo_empleador": data.get("tipo_empleador", "EMPRESA"),
                }
    except Exception as e:
        print(f"[DB] get_client_context_by_phone error for {phone}: {e}")
    return None


def verify_cedula_matches_phone(phone: str, cedula_digitada: str) -> bool:
    """Return True if the cedula the client just typed matches the one
    registered in the core for this WhatsApp phone number.

    Uses get_client_context_by_phone, which depends on the Cloud Run endpoint
    `por_telefono_completo` returning a `cedula` field.
    """
    ctx = get_client_context_by_phone(phone)
    if not ctx:
        return False
    expected = "".join(filter(str.isdigit, str(ctx.get("cedula", ""))))
    typed = "".join(filter(str.isdigit, cedula_digitada or ""))
    return bool(expected) and expected == typed


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


def get_random_cedula_by_categoria(categoria: str) -> dict | None:
    """Return a random cédula from a given category, for the admin test panel.

    categoria ∈ {aprobados, falta_documento, listo_en_docusign, denegado, activos}.

    Returns {"cedula", "nombre", "empresa", "estado_interno", "telefono"} or
    None if the category has no matches / error.
    """
    import random

    fetchers = {
        "aprobados": get_aprobados_por_el_cliente,
        "falta_documento": get_falta_documento,
        "listo_en_docusign": get_listo_en_docusign,
        "denegado": get_denegado,
        "activos": get_clientes_activos,
    }
    fetcher = fetchers.get(categoria)
    if not fetcher:
        return None

    items = fetcher()
    if not items:
        return None

    pick = random.choice(items)
    cedula = (pick.get("cedula") or "").strip() if isinstance(pick.get("cedula"), str) else str(pick.get("cedula") or "")

    # Para categorías que no devuelven cédula, derivarla del teléfono.
    if not cedula:
        telefono = pick.get("telefono") or ""
        if telefono:
            ctx = get_client_context_by_phone(telefono)
            if ctx:
                cedula = str(ctx.get("cedula") or "")
                if not pick.get("estado_interno"):
                    pick["estado_interno"] = ctx.get("estado_interno", "")

    if not cedula:
        return None

    return {
        "cedula": cedula,
        "nombre": pick.get("nombre_completo", ""),
        "empresa": pick.get("empresa", ""),
        "estado_interno": pick.get("estado_interno", ""),
        "telefono": pick.get("telefono", ""),
    }


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
        response = _post_with_retry(
            CLOUD_RUN_URL,
            json_payload={"cedula": cedula, "tipo": "saldo"},
            headers={
                "Authorization": f"Bearer {API_TOKEN_SECRET}",
                "Content-Type": "application/json"
            },
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
