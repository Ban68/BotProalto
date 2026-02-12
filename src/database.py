import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

# Global Connection Pool
db_pool = None

def init_db_pool():
    global db_pool
    try:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', '5432')
        )
        print("✅ Database Connection Pool Created")
    except Exception as e:
        print(f"❌ Error creating DB Pool: {e}")

@contextmanager
def get_db_cursor():
    """
    Yields a cursor from a pooled connection.
    Ensures connection is returned to pool even if error occurs.
    """
    global db_pool
    if not db_pool:
        init_db_pool()
        
    conn = None
    try:
        conn = db_pool.getconn()
        yield conn.cursor(cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"Database Operation Error: {e}")
        raise e
    finally:
        if conn:
            db_pool.putconn(conn)

def get_solicitud_status(cedula):
    """
    Queries v_solicitudes_whatsapp using connection pool.
    """
    try:
        with get_db_cursor() as cur:
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
