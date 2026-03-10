import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def list_distinct_states():
    print("Connecting to DB to fetch distinct states...")
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        query = """
            SELECT DISTINCT estado_interno 
            FROM v_solicitudes_whatsapp 
            ORDER BY estado_interno;
        """
        cur.execute(query)
        states = cur.fetchall()
        
        print(f"\n✅ Found {len(states)} distinct states:\n")
        
        for state in states:
            # Handle None value clearly
            val = state[0] if state[0] is not None else "NULL (Vacío)"
            print(f" - {val}")
            
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    list_distinct_states()
