from fastapi import FastAPI

from app.routers import health, users

app = FastAPI(title="Agora API")
app.include_router(health.router)
app.include_router(users.router)
