from fastapi import Depends, HTTPException, status

from app.auth.deps import require_username
from app.models import User


async def require_admin(user: User = Depends(require_username)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
