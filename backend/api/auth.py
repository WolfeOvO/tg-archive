"""Authentication API endpoints."""

import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# Simple rate limiting
_login_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


def create_token() -> str:
    """Create a JWT token."""
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "sub": "admin",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def verify_token(token: str) -> bool:
    """Verify a JWT token."""
    try:
        jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return True
    except jwt.InvalidTokenError:
        return False


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Dependency for protected endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not verify_token(credentials.credentials):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return credentials.credentials


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, client_ip: str = "unknown"):
    """Authenticate with password and receive JWT token."""
    # Rate limiting
    now = time.time()
    if client_ip in _login_attempts:
        attempts = [t for t in _login_attempts[client_ip] if now - t < LOCKOUT_SECONDS]
        _login_attempts[client_ip] = attempts
        if len(attempts) >= MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail=f"Too many attempts. Try again in {LOCKOUT_SECONDS}s",
            )
    else:
        _login_attempts[client_ip] = []

    if req.password != settings.admin_password:
        _login_attempts[client_ip].append(now)
        raise HTTPException(status_code=401, detail="Invalid password")

    _login_attempts.pop(client_ip, None)

    token = create_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    return LoginResponse(token=token, expires_at=expires.isoformat())


@router.get("/verify")
async def verify(token: str = Depends(require_auth)):
    """Verify that a token is valid."""
    return {"valid": True}
