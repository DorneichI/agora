from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User, UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user
