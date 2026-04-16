from fastapi import FastAPI

from .infrastructure.config import SERVICE_NAME
from .api.routes import router

app = FastAPI(title="Auth Service")

app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}