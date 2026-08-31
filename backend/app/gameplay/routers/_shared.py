from fastapi import HTTPException, status


def _reject_null_updates(updates: dict, required_fields: set[str]) -> None:
    """`exclude_unset=True` keeps a key the client sent as explicit JSON `null` (Pydantic
    accepts null for every PATCH field since `X | None` is how "field omitted" is
    represented). For a column that's NOT NULL in the DB, forwarding that null via
    `setattr` reaches the database as an unvalidated write and surfaces as a raw
    IntegrityError/500 instead of a 422 -- reject it here before it gets that far."""
    nulled = sorted(f for f in required_fields if f in updates and updates[f] is None)
    if nulled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{', '.join(nulled)} must not be null",
        )
