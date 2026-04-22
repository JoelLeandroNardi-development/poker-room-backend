from fastapi import FastAPI

from .infrastructure.config import SERVICE_NAME
from .api.commands.auth_authentication_command_routes import auth_authentication_command_router
from .api.commands.auth_password_command_routes import auth_password_command_router
from .api.commands.auth_user_command_routes import auth_user_command_router
from .api.queries.auth_user_query_routes import auth_user_query_router

app = FastAPI(title="Auth Service")

app.include_router(auth_authentication_command_router)
app.include_router(auth_password_command_router)
app.include_router(auth_user_command_router)
app.include_router(auth_user_query_router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": SERVICE_NAME}