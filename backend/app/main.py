from fastapi import FastAPI

from app.routers import health, leagues, teams, users

app = FastAPI(title="Agora API")
app.include_router(health.router)
app.include_router(users.router)
app.include_router(leagues.router)
app.include_router(teams.router)
