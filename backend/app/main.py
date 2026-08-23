from fastapi import Depends, FastAPI

from app.deps import get_current_user
from app.models import User

app = FastAPI(title="Agora API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me", response_model=User)
async def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user
