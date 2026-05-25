"""
Diagnóstico puntual: consulta el Cloud Run con una cédula y muestra qué
documentos enviaría build_docs_message al cliente. Útil para verificar fixes
en el parser de documentos_faltantes.

Uso: python scripts/debug_docs_faltantes.py 12637392
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.automation import build_docs_message  # noqa: E402

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "").rstrip("/")
API_TOKEN_SECRET = os.getenv("API_TOKEN_SECRET", "")

if len(sys.argv) < 2:
    print("Uso: python scripts/debug_docs_faltantes.py <cedula>")
    sys.exit(1)

cedula = sys.argv[1]

resp = requests.post(
    CLOUD_RUN_URL,
    json={"cedula": cedula},
    headers={
        "Authorization": f"Bearer {API_TOKEN_SECRET}",
        "Content-Type": "application/json",
    },
    timeout=15,
)
resp.raise_for_status()
data = resp.json()

docs = data.get("documentos_faltantes")
tipo_empleador = data.get("tipo_empleador", "EMPRESA")

print(f"\nCédula: {cedula}")
print(f"Solicitud: {data.get('nro_solicitud')}")
print(f"Estado interno: {data.get('estado_interno')}")
print(f"documentos_faltantes (raw): {docs!r}")
print(f"tipo_empleador: {tipo_empleador}\n")

print("=== Mensaje que enviaría build_docs_message ===")
print(build_docs_message(docs, tipo_empleador))
