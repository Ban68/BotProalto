import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Get DB config
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_PORT = os.getenv('DB_PORT', '5432')

# Tables to inspect
TARGET_TABLES = ['clientes', 'saldos', 'v_saldos_liquidar', 'v_solicitudes_whatsapp']

def list_columns():
    print(f"Connecting to database '{DB_NAME}'...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        cur = conn.cursor()
        
        for table_name in TARGET_TABLES:
            print(f"\n--- Checking Table: {table_name} ---")
            
            # Query column names
            query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}';
            """
            cur.execute(query)
            columns = cur.fetchall()
            
            if not columns:
                print(f"  (Table '{table_name}' not found or has no columns)")
            else:
                for col_name, data_type in columns:
                    print(f"  - {col_name} ({data_type})")
                    
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Inspection Failed: {e}")

if __name__ == "__main__":
    list_columns()
