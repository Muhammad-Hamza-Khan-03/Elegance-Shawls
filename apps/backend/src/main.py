from fastapi import FastAPI
from dotenv import load_dotenv
import os
# from db import connect_supabase
from supabase import create_client, Client

load_dotenv()

SUPABSE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = FastAPI()
supabase: Client = create_client(SUPABSE_URL, SUPABASE_KEY)

@app.get("/")
def get_root():
    return {"message": "Welcome to the Elegance Shawls Backend!"}

@app.get("/health")
def get_health():
    return {"status": "ok"}

