"""
Authentication helper for AcmeOps.
Handles both session cookies for browser UI and Bearer tokens for REST API.
"""

import time
import secrets
from typing import Optional, Dict
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from acme_ops.database import authenticate_user

# In-memory session store: session_id -> {user_id, username, role, expires_at}
SESSIONS: Dict[str, Dict] = {}
SESSION_TTL_SECONDS = 3600 * 8  # 8 hours

security_bearer = HTTPBearer(auto_error=False)


def create_session(user: dict) -> str:
    session_id = secrets.token_hex(24)
    SESSIONS[session_id] = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    return session_id


def get_session(session_id: Optional[str]) -> Optional[Dict]:
    if not session_id or session_id not in SESSIONS:
        return None
    session_data = SESSIONS[session_id]
    if time.time() > session_data["expires_at"]:
        del SESSIONS[session_id]
        return None
    return session_data


def delete_session(session_id: str):
    if session_id in SESSIONS:
        del SESSIONS[session_id]


async def get_current_user_optional(request: Request) -> Optional[Dict]:
    """Check session cookie or Bearer header without raising."""
    # 1. Check Bearer token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        session = get_session(token)
        if session:
            return session

    # 2. Check Cookie
    session_id = request.cookies.get("acme_session")
    if session_id:
        session = get_session(session_id)
        if session:
            return session

    return None


async def require_auth_cookie(request: Request) -> Dict:
    """For Web UI: require valid session cookie, otherwise redirect or 401."""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login.",
        )
    return user


async def require_auth_api(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    request: Request = None,
) -> Dict:
    """For REST API: require valid Bearer token or session cookie."""
    if auth:
        session = get_session(auth.credentials)
        if session:
            return session

    # Fallback to cookie if API called from authenticated browser
    if request:
        user = await get_current_user_optional(request)
        if user:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Bearer token. Use POST /api/auth/token to obtain a token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
