from fastapi import FastAPI

from app.routers import health, leagues, users

app = FastAPI(title="Agora API")
app.include_router(health.router)
app.include_router(users.router)
app.include_router(leagues.router)
