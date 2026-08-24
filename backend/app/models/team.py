from sqlmodel import Field, SQLModel

from app.soft_delete import SoftDeleteMixin


class Team(SoftDeleteMixin, table=True):
    name: str = Field()
    school: str = Field()
    mascot: str = Field()
    image_url: str | None = Field(default=None)
    created_by: int = Field(foreign_key="user.id")
    updated_by: int | None = Field(default=None, foreign_key="user.id")


class TeamRead(SQLModel):
    """Public shape of a Team, used as API response models instead of the table model
    itself -- keeps internal/bookkeeping columns (e.g. any added to SoftDeleteMixin or
    Team later) from being auto-exposed (and auto-codegen'd into the web/mobile clients,
    see docs/architecture.md#api-contract) just by existing on the table. See
    backend/CLAUDE.md's "Response schemas" convention."""

    id: int
    name: str
    school: str
    mascot: str
    image_url: str | None
    created_by: int
    updated_by: int | None
