"""Authentication router - Login and token management"""
from fastapi import APIRouter, HTTPException, Header, Request
from datetime import datetime, timedelta
import jwt
import json
import logging
import re
from config import settings
from db import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_access_key(raw: str | None) -> str:
    text = str(raw or "")
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text).strip()
    text = text.strip('`"\'“”‘’')
    return re.sub(r"[^A-Za-z0-9_-]", "", text)


def _normalize_permission_key(raw: str | None) -> str:
    text = str(raw or "")
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text).strip()
    text = text.strip('`"\'“”‘’').lower()
    text = re.sub(r"[^a-z]", "", text)
    # Backward compatibility: historic keys looked like "medico_perm_456".
    if text.endswith("perm"):
        text = text[:-4]
    return text


@router.post("/login")
async def login(credentials: dict, request: Request):
    """
    Login with double API-Key validated against DB.
    Returns JWT token. Registers audit log entry.
    """
    access_key = _normalize_access_key(credentials.get("access_key"))
    permission_key = _normalize_permission_key(credentials.get("permission_key"))
    ip = request.client.host if request.client else "unknown"

    if not access_key or not permission_key:
        raise HTTPException(status_code=400, detail="Missing credentials")

    pool = await get_db_pool()
    user = await pool.fetchrow(
        "SELECT id, role, permission_key, is_active FROM users WHERE access_key=$1 AND deleted_at IS NULL",
        access_key
    )

    if not user or not user["is_active"]:
        await pool.execute(
            "INSERT INTO audit_log (action, ip_address, result, detail) VALUES ('LOGIN', $1::inet, 'FAILED', $2::jsonb)",
            ip, json.dumps({"reason": "invalid_key"})
        )
        raise HTTPException(status_code=403, detail="Invalid credentials")

    stored_permission_key = _normalize_permission_key(user["permission_key"])
    if stored_permission_key != permission_key:
        await pool.execute(
            "INSERT INTO audit_log (user_id, action, ip_address, result, detail) VALUES ($1, 'LOGIN', $2::inet, 'FAILED', $3::jsonb)",
            user["id"], ip, json.dumps({"reason": "permission_key_mismatch"})
        )
        raise HTTPException(status_code=403, detail="Permission key mismatch")

    payload = {
        "sub": access_key,
        "role": user["role"],
        "user_id": str(user["id"]),
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    await pool.execute(
        "INSERT INTO audit_log (user_id, role, action, ip_address, result) VALUES ($1, $2, 'LOGIN', $3::inet, 'SUCCESS')",
        user["id"], user["role"], ip
    )

    logger.info(f"✅ Login successful for role: {user['role']}")

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": str(user["id"]),
        "expires_in": settings.JWT_EXPIRATION_HOURS * 3600
    }


@router.post("/logout")
async def logout(request: Request, x_access_key: str = Header(None)):
    """Logout endpoint — logs audit event"""
    ip = request.client.host if request.client else "unknown"
    x_access_key = _normalize_access_key(x_access_key)
    if x_access_key:
        pool = await get_db_pool()
        user = await pool.fetchrow(
            "SELECT id, role FROM users WHERE access_key=$1 AND deleted_at IS NULL", x_access_key
        )
        if user:
            await pool.execute(
                "INSERT INTO audit_log (user_id, role, action, ip_address, result) VALUES ($1, $2, 'LOGOUT', $3::inet, 'SUCCESS')",
                user["id"], user["role"], ip
            )
    logger.info("📤 User logged out")
    return {"message": "Logged out successfully"}


@router.get("/verify")
async def verify_token(
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None)
):
    """Verify if API keys are valid against DB"""
    x_access_key = _normalize_access_key(x_access_key)
    x_permission_key = _normalize_permission_key(x_permission_key)
    if not x_access_key or not x_permission_key:
        raise HTTPException(status_code=401, detail="Missing authentication")

    pool = await get_db_pool()
    user = await pool.fetchrow(
        "SELECT id, role, permission_key, is_active FROM users WHERE access_key=$1 AND deleted_at IS NULL",
        x_access_key
    )

    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="Invalid credentials")

    stored_permission_key = _normalize_permission_key(user["permission_key"])
    if stored_permission_key != x_permission_key:
        raise HTTPException(status_code=403, detail="Invalid credentials")

    return {
        "valid": True,
        "role": user["role"],
        "user_id": str(user["id"]),
        "timestamp": datetime.utcnow().isoformat()
    }

