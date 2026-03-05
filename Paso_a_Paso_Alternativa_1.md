# GUÍA DE IMPLEMENTACIÓN PARA INFRAESTRUCTURA (Alternativa 1)

## Introducción
La **Alternativa 1 (Microservicio Puente en Google Cloud)** es sin duda la más segura, ya que Google Cloud confía por defecto en sus propios recursos internos. En vez de forzar a la base de datos a aceptar IPs externas de internet, crearemos una sencilla "API" (`Cloud Function`) dentro de la nube de GCP. Esta función tiene permisos automáticos para leer la base de datos de manera interna y le responderá al Bot por internet de forma segura.

---

## Paso 1: Crear una función en Google Cloud (Cloud Functions)
1. Entra a Google Cloud Platform (GCP) y ve a **Cloud Functions** (o Cloud Run Functions).
2. Haz clic en **Crear Función**.
3. Configuración inicial:
   * **Entorno:** 2ª gen (Cloud Run).
   * **Nombre:** `bot-proalto-db-api`
   * **Región:** *(Debe ser la misma región donde esté alojada la base de datos para que no haya cobros excesivos por transferencia de red ni latencia)*.
   * **Gatillo (Trigger):** HTTPS (Permitir invocaciones no autenticadas en IAM; manejaremos la seguridad internamente con un Token).

## Paso 2: Configurar variables de red y conexión (Networking)
En el menú de "Configuración avanzada" > **Variables de entorno (Runtime)**:
1. Agrega las credenciales de la Base de Datos PostgreSQL:
   * `DB_HOST`: *(La IP interna de la Base de Datos en GCP para mayor velocidad y evitar salir a internet, o la externa actual)*.
   * `DB_NAME`: `proalto`
   * `DB_USER`: `monsalve`
   * `DB_PASSWORD`: *(Contraseña del usuario)*.
   * `DB_PORT`: `5432`
   * `API_TOKEN_SECRET`: `cualquier_contraseña_secreta_aqui_fuerte_123!` *(Este token secreto se validará contra nuestro Bot alojado en Render)*.

## Paso 3: Pegar el código (Runtime Python)
En la pantalla de código fuente, elige **Python 3.12** como entorno de ejecución. Hay que crear o editar dos archivos:

### Archivo 1: `requirements.txt`
Asegúrate de incluir estas dos dependencias en el archivo de requerimientos:
```text
functions-framework==3.*
psycopg2-binary==2.9.9
```

### Archivo 2: `main.py`
Borra el código que venga por defecto y pega este código. Modifica el **Punto de Entrada** (Entry point) en la consola de Google al nombre de la función principal, en este caso deberás poner: `get_solicitud`.

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
        cur.execute("SET statement_timeout = 5000") # Timeout de seguridad
        
        # Consulta Original
        query = """
            SELECT nro_solicitud, nro_identificacion_cliente, id_estado_solicitud, estado, observaciones 
            FROM v_solicitudes_whatsapp 
            WHERE nro_identificacion_cliente = %s 
            ORDER BY nro_solicitud DESC LIMIT 1
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
                "cedula": record[1],
                "id_estado_solicitud": record[2],
                "estado_str": record[3],
                "observaciones": record[4]
            }), 200
        else:
            return jsonify({"found": False}), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

## Paso 4: Desplegar y Recopilar URL
Presiona el botón **Desplegar / Implementar** (Deploy). Google Cloud tardará unos minutos construyendo el contenedor y la función.

Una vez finalizado, Google Cloud proporcionará una URL pública (ej. `https://us-central1-tu-proyecto.cloudfunctions.net/bot-proalto-db-api`).

***

## Cierre y Entrega
Por favor, asegúrate de proveer al equipo de desarrollo (programador del bot) con los siguientes **dos datos** para actualizar el Bot en Render y finalizar la producción:

1. **La URL exacta** que generó Google Cloud para la función desplegada.
2. **El token secreto** configurado bajo `API_TOKEN_SECRET`.
