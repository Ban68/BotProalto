# GUÍA DE IMPLEMENTACIÓN: MICROSERVICIO EN GOOGLE CLOUD RUN (CONTENEDORES)

## Introducción
Esta guía detalla cómo crear una API puente utilizando **Google Cloud Run (Servicio de Contenedores)**. Este microservicio actuará como intermediario: recibirá peticiones seguras de nuestro bot en Render y consultará la base de datos PostgreSQL de forma interna y privada. Esta opción aprovecha la potencia de los contenedores Docker y entra dentro del generoso **Nivel Gratuito de Google Cloud ($0/mes)** para los volúmenes de uso que prevemos.

---

## Paso 1: Preparar los Archivos del Contenedor (Código Fuente)

Deberás crear una carpeta en tu entorno local (o en Cloud Shell) y colocar tres archivos dentro.

### 1. `requirements.txt`
Contiene las dependencias de Python necesarias.
```text
functions-framework==3.*
psycopg2-binary==2.9.9
flask==3.0.0
```

### 2. `main.py`
El código principal de la API que ejecuta la consulta y valida la seguridad.

**IMPORTANTE:** El "Entry point" (punto de entrada) en Cloud Run debe ser: `get_solicitud`

```python
import os
import psycopg2
import functions_framework
from flask import jsonify

@functions_framework.http
def get_solicitud(request):
    # 1. Medida de seguridad: Validar el request con el API Token
    auth_header = request.headers.get("Authorization")
    expected_token = f"Bearer {os.environ.get('API_TOKEN_SECRET')}"
    
    if auth_header != expected_token:
        return jsonify({"error": "No Autorizado"}), 401
    
    # 2. Extraer la cédula enviada (Payload JSON)
    request_json = request.get_json(silent=True)
    if not request_json or 'cedula' not in request_json:
        return jsonify({"error": "Cédula no proporcionada"}), 400
        
    cedula = request_json['cedula']
    
    # 3. Conexión rápida a PostgreSQL
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST"),
            database=os.environ.get("DB_NAME"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            port=os.environ.get("DB_PORT", "5432"),
            connect_timeout=3
        )
        cur = conn.cursor()
        cur.execute("SET statement_timeout = 5000")
        
        # Consulta a la vista de solicitudes
        query = """
            SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado, 
                   estado_interno, nombre_completo, plazo
            FROM v_solicitudes_whatsapp 
            WHERE cedula_nit = %s 
            ORDER BY nro_solicitud DESC 
            LIMIT 1
        """
        cur.execute(query, (cedula,))
        record = cur.fetchone()
        
        cur.close()
        conn.close()
        
        # 4. Responder al cliente HTTPS
        if record:
            return jsonify({
                "found": True,
                "nro_solicitud": record[0],
                "fecha_de_solicitud": str(record[1]) if record[1] else "",
                "valor_preestudiado": float(record[2]) if record[2] else 0,
                "estado_interno": record[3] or "",
                "nombre_completo": record[4] or "",
                "plazo": record[5]
            }), 200
        else:
            return jsonify({"found": False}), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### 3. `Dockerfile`
Este archivo contiene las instrucciones para "empaquetar" la aplicación en un contenedor de Docker.
```dockerfile
# Usar imagen ligera de Python oficial
FROM python:3.12-slim

# Directorio de trabajo
WORKDIR /app

# Copiar archivos e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el ejecutable
COPY main.py .

# Variables de entorno por defecto
ENV PORT=8080

# Ejecutar el framework de funciones de Google escuchando en el puerto asignado por Cloud Run
CMD exec functions-framework --target=get_solicitud --port=$PORT
```

---

## Paso 2: Construir y subir el Contenedor

La forma más rápida de subir este contenedor es usar **Google Cloud Shell** (el ícono `>_` en la esquina superior derecha de la consola GCP).

```bash
# 1. Crear carpeta y entrar
mkdir bot-api && cd bot-api

# 2. Crear los 3 archivos (main.py, requirements.txt, Dockerfile)
#    Utilizar el editor de Cloud Shell o los comandos cat > archivo << 'EOF' ... EOF

# 3. Desplegar directamente
gcloud run deploy bot-proalto-db-api \
  --source . \
  --region us-south1 \
  --allow-unauthenticated \
  --port 8080
```

---

## Paso 3: Configurar las Variables de Entorno en Cloud Run

1. Dirígete a **Cloud Run** en la Consola de Google Cloud.
2. Selecciona el servicio `bot-proalto-db-api`.
3. Haz clic en **Editar y aplicar nueva revisión** (Edit & Deploy New Revision).
4. Ve a la pestaña **Variables y secretos** (Variables & Secrets).
5. Agrega las siguientes variables:
   * `DB_HOST`: *(La IP interna o externa de tu Base de Datos en GCP)*.
   * `DB_NAME`: `proalto`
   * `DB_USER`: `monsalve`
   * `DB_PASSWORD`: *(Contraseña del usuario correspondiente)*.
   * `DB_PORT`: `5432`
   * `API_TOKEN_SECRET`: *(Un token secreto compartido con Render)*.
6. Clic en **Implementar** (Deploy).

---

## Paso 4: Configurar las Variables de Entorno en Render (Bot)

En el dashboard de Render, agregar estas dos variables de entorno:

* `CLOUD_RUN_URL`: `https://bot-proalto-db-api-335508189707.us-south1.run.app`
* `API_TOKEN_SECRET`: *(El mismo token secreto que se puso en Cloud Run)*.

---

## Cierre y Verificación
Una vez configuradas ambas partes:
1. Visitar la URL del bot en Render: `/health` para verificar la conexión.
2. Enviar un mensaje de WhatsApp con una cédula conocida para confirmar que el bot devuelve el estado correctamente.
