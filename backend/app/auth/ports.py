from dataclasses import dataclass
from typing import Protocol


@dataclass
class AuthenticatedIdentity:
    external_id: str
    email: str | None


class IdentityProvider(Protocol):
    def verify(self, token: str) -> AuthenticatedIdentity: ...
