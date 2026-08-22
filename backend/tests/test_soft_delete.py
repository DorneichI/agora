from datetime import datetime

from sqlmodel import Field

from app.soft_delete import SoftDeleteMixin


class _MixinFieldsProbe(SoftDeleteMixin):
    name: str = Field()


def test_mixin_provides_id_timestamps_and_nullable_deleted_at():
    probe = _MixinFieldsProbe(name="widget")

    assert probe.id is None  # unset until inserted
    assert isinstance(probe.created_at, datetime)
    assert isinstance(probe.updated_at, datetime)
    assert probe.deleted_at is None
