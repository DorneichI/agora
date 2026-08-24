from fastapi import FastAPI

from app.routers import events, health, leagues, races, teams, users, venues

app = FastAPI(title="Agora API")
app.include_router(health.router)
app.include_router(users.router)
app.include_router(leagues.router)
app.include_router(teams.router)
app.include_router(venues.router)
app.include_router(events.router)
app.include_router(races.router)
