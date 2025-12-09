import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Fetch variables
USER = os.getenv("SUPABASE_USER")
PASSWORD = os.getenv("SUPABASE_PASSWORD")
HOST = os.getenv("HOST")
PORT = os.getenv("SUPABASE_PORT")
DBNAME = os.getenv("SUPABASE_DB")


def connect_supabase():
    try:
        connection = psycopg2.connect(
            user=USER,
            password=PASSWORD,
            host=HOST,
            port=PORT,
            dbname=DBNAME
        )
        print("Connection successful!")

        # Create a cursor to execute SQL queries
        cursor = connection.cursor()

        # Example query
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        print("Current Time:", result)

        # Close the cursor and connection
        cursor.close()
        connection.close()
        print("Connection closed.")

    except Exception as e:
        print(f"Failed to connect: {e}")