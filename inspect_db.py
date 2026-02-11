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

def list_tables():
    print(f"Connecting to database '{DB_NAME}' at {DB_HOST}:{DB_PORT}...")
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        cur = conn.cursor()
        
        # Query to list all tables in the public schema
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        tables = cur.fetchall()
        
        print(f"\n✅ Connection Successful! Found {len(tables)} tables:\n")
        
        for table in tables:
            print(f" - {table[0]}")
            
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Connection Failed: {e}")

if __name__ == "__main__":
    list_tables()
