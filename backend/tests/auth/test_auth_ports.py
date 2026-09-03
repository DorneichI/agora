from app.auth.ports import AuthenticatedIdentity


def test_authenticated_identity_holds_external_id_and_email():
    identity = AuthenticatedIdentity(external_id="user_1", email="a@example.com")

    assert identity.external_id == "user_1"
    assert identity.email == "a@example.com"


def test_authenticated_identity_email_can_be_none():
    identity = AuthenticatedIdentity(external_id="user_2", email=None)

    assert identity.email is None
