import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def debug_query(cedula):
    print(f"Querying for Cedula: {cedula}...")
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', '5432')
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT *
                FROM v_solicitudes_whatsapp 
                WHERE cedula_nit = %s 
                ORDER BY nro_solicitud DESC 
                LIMIT 1;
            """
            cur.execute(query, (cedula,))
            result = cur.fetchone()
            
            if result:
                print("\n✅ Row Found:")
                for key, value in result.items():
                    print(f"  - {key}: {value} (Type: {type(value)})")
            else:
                print("\n❌ No row found.")
                
        conn.close()
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    # Using the cedula from the user's screenshot
    debug_query('78030221')
