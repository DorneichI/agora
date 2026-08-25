import json
import time

import httpx2
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import SQLModel

from app.clerk import CLERK_ISSUER, _jwk_client
from app.db import engine, get_session
from app.main import app
from app.models import User


@pytest_asyncio.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest.fixture(scope="session")
def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def _mock_clerk_jwks(monkeypatch, _rsa_keypair):
    """Skip the real network call to Clerk's JWKS endpoint; return our test key instead."""
    _private_key, public_key = _rsa_keypair
    jwk_dict = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk_dict.update(kid="test-kid", use="sig", alg="RS256")
    signing_key = jwt.PyJWK.from_json(json.dumps(jwk_dict))
    monkeypatch.setattr(_jwk_client, "get_signing_key_from_jwt", lambda token: signing_key)


@pytest.fixture
async def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    transport = httpx2.ASGITransport(app=app)
    try:
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        del app.dependency_overrides[get_session]


@pytest.fixture
def make_clerk_token(_rsa_keypair):
    private_key, _public_key = _rsa_keypair

    def _make(
        clerk_id="user_test123", email="rower@example.com", name="Rower Example", **overrides
    ):
        payload = {
            "sub": clerk_id,
            "iss": CLERK_ISSUER,
            "email": email,
            "name": name,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            **overrides,
        }
        return jwt.encode(payload, private_key, algorithm="RS256")

    return _make


@pytest.fixture
def make_admin(client, make_clerk_token, db_session):
    async def _make_admin(clerk_id, email, name):
        token = make_clerk_token(clerk_id=clerk_id, email=email, name=name)
        me_response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id = me_response.json()["id"]

        user = await db_session.get(User, user_id)
        user.role = "admin"
        user.username = f"user{user_id}"
        db_session.add(user)
        await db_session.commit()

        return token, user_id

    return _make_admin


@pytest.fixture
def make_user(client, make_clerk_token, db_session):
    async def _make_user(clerk_id, email, name):
        token = make_clerk_token(clerk_id=clerk_id, email=email, name=name)
        me_response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id = me_response.json()["id"]

        user = await db_session.get(User, user_id)
        user.username = f"user{user_id}"
        db_session.add(user)
        await db_session.commit()

        return token, user_id

    return _make_user
