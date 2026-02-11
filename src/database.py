import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', '5432')
        )
        return conn
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        return None

def get_solicitud_status(cedula):
    """
    Queries v_solicitudes_whatsapp for the given cedula.
    Returns the latest application status.
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # We select the latest request based on nro_solicitud
            query = """
                SELECT nro_solicitud, fecha_de_solicitud, valor_preestudiado, 
                       estado_interno, nombre_completo, plazo
                FROM v_solicitudes_whatsapp 
                WHERE cedula_nit = %s 
                ORDER BY nro_solicitud DESC 
                LIMIT 1;
            """
            cur.execute(query, (cedula,))
            result = cur.fetchone()
            return result
    except Exception as e:
        print(f"Error querying solicitud: {e}")
        return None
    finally:
        conn.close()
