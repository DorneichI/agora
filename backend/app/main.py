from fastapi import FastAPI

from app.gameplay.routers import router as gameplay_router
from app.leagues.routers import router as leagues_router
from app.routers import health, users
from app.standings.router import router as standings_router

app = FastAPI(title="Agora API")
app.include_router(health.router)
app.include_router(users.router)
app.include_router(leagues_router)
app.include_router(gameplay_router)
app.include_router(standings_router)
