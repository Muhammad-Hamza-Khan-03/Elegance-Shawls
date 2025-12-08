from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def get_root():
    return {"message": "Welcome to the Elegance Shawls Backend!"}

@app.get("/health")
def get_health():
    return {"status": "ok"}