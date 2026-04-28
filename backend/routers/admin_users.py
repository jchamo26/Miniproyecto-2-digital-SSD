"""Admin Users router - User CRUD backed by PostgreSQL"""
from fastapi import APIRouter, Header, HTTPException, Query
import logging
from datetime import datetime
from uuid import uuid4
from db import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def _require_admin(pool, access_key: str):
    user = await pool.fetchrow(
        "SELECT id, role FROM users WHERE access_key=$1 AND is_active=TRUE AND deleted_at IS NULL",
        access_key
    )
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def _user_row(r):
    return {
        "id": str(r["id"]),
        "username": r["username"],
        "email": r["email"],
        "role": r["role"],
        "access_key": r["access_key"],
        "permission_key": r["permission_key"],
        "is_active": r["is_active"],
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
    }


@router.post("/")
async def create_user(user: dict, x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    username = user.get("username", "").strip()
    role = user.get("role", "").strip()
    email = user.get("email", f"{username}@clinical.local").strip()

    if not username or not role:
        raise HTTPException(status_code=400, detail="Missing username or role")
    if role not in ("admin", "medico", "paciente"):
        raise HTTPException(status_code=400, detail="Invalid role: must be admin, medico, or paciente")

    uid = uuid4()
    access_key = f"key-{uid.hex[:16]}"
    permission_key = role

    try:
        row = await pool.fetchrow(
            """INSERT INTO users (username, email, role, access_key, permission_key, is_active)
               VALUES ($1,$2,$3,$4,$5,TRUE) RETURNING id, username, email, role, access_key, permission_key, is_active, created_at""",
            username, email, role, access_key, permission_key
        )
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail="Username or email already exists")
        raise

    return _user_row(row)


@router.get("/")
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    rows = await pool.fetch(
        "SELECT id, username, email, role, access_key, permission_key, is_active, created_at "
        "FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset
    )
    total = await pool.fetchval("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")

    return {"total": total, "users": [_user_row(r) for r in rows]}


@router.get("/{user_id}")
async def get_user(user_id: str, x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    row = await pool.fetchrow(
        "SELECT id, username, email, role, access_key, permission_key, is_active, created_at "
        "FROM users WHERE id::text=$1 AND deleted_at IS NULL",
        user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_row(row)


@router.patch("/{user_id}")
async def update_user(user_id: str, updates: dict, x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    allowed_fields = {"username", "email", "role", "is_active"}
    fields = {k: v for k, v in updates.items() if k in allowed_fields}
    if not fields:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    if "role" in fields and fields["role"] not in ("admin", "medico", "paciente"):
        raise HTTPException(status_code=400, detail="Invalid role")

    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    result = await pool.execute(
        f"UPDATE users SET {set_clause} WHERE id::text=$1 AND deleted_at IS NULL",
        user_id, *values
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")

    return {"id": user_id, "message": "User updated", "updated_at": datetime.utcnow().isoformat()}


@router.delete("/{user_id}")
async def deactivate_user(user_id: str, x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    result = await pool.execute(
        "UPDATE users SET is_active=FALSE, deleted_at=NOW() WHERE id::text=$1 AND deleted_at IS NULL",
        user_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")

    return {"id": user_id, "message": "User deactivated", "deleted_at": datetime.utcnow().isoformat()}


@router.post("/{user_id}/revoke-key")
async def revoke_api_key(user_id: str, x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    new_key = f"key-{uuid4().hex[:16]}"
    result = await pool.execute(
        "UPDATE users SET access_key=$1 WHERE id::text=$2 AND deleted_at IS NULL",
        new_key, user_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")

    return {"id": user_id, "message": "API key revoked and regenerated",
            "new_access_key": new_key, "revoked_at": datetime.utcnow().isoformat()}


@router.post("/{user_id}/assign-patients")
async def assign_patients_to_doctor(
    user_id: str,
    patients: list,
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    user_row = await pool.fetchrow(
        "SELECT id, role FROM users WHERE id::text=$1 AND deleted_at IS NULL", user_id
    )
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    if user_row["role"] not in ("admin", "medico"):
        raise HTTPException(status_code=400, detail="Can only assign patients to medico or admin")

    assigned = 0
    for patient_ref in patients:
        p = await pool.fetchrow(
            "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
            str(patient_ref)
        )
        if p:
            await pool.execute(
                "INSERT INTO user_patients (user_id, patient_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                user_row["id"], p["id"]
            )
            assigned += 1

    return {
        "doctor_id": user_id,
        "patients_assigned": assigned,
        "assigned_at": datetime.utcnow().isoformat(),
    }
