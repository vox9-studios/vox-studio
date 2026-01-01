from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import test_connection

app = FastAPI(title="Vox Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Vox Platform API", "status": "healthy"}

@app.get("/health")
async def health():
    db_connected = test_connection()
    return {
        "status": "ok",
        "database": "connected" if db_connected else "disconnected"
    }
