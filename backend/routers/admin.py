"""Admin router - Administrative functions backed by PostgreSQL"""
import csv
import io
import json

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
import logging
from datetime import datetime
from db import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter()

TABLE_MAP = {
    "patients": "patients",
    "risk_reports": "risk_reports",
    "inference_queue": "inference_queue",
    "users": "users",
}


async def _require_admin(pool, access_key: str):
    user = await pool.fetchrow(
        "SELECT id, role FROM users WHERE access_key=$1 AND is_active=TRUE AND deleted_at IS NULL",
        access_key
    )
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


@router.get("/audit-log")
async def get_audit_log(
    action: str = Query(None),
    user_id: str = Query(None),
    resource_type: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    rows = await pool.fetch(
        """SELECT id, ts, user_id, role, action, resource_type, resource_id, ip_address, result
           FROM audit_log
           WHERE ($1::uuid IS NULL OR user_id = $1::uuid)
             AND ($2 IS NULL OR action = $2)
             AND ($3 IS NULL OR resource_type = $3)
           ORDER BY ts DESC LIMIT $4 OFFSET $5""",
        user_id, action, resource_type, limit, offset
    )
    total = await pool.fetchval(
        """SELECT COUNT(*) FROM audit_log
           WHERE ($1::uuid IS NULL OR user_id=$1::uuid)
             AND ($2 IS NULL OR action=$2)
             AND ($3 IS NULL OR resource_type=$3)""",
        user_id, action, resource_type
    )

    entries = [{
        "id": str(r["id"]),
        "ts": r["ts"].isoformat(),
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "role": r["role"],
        "action": r["action"],
        "resource_type": r["resource_type"],
        "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
        "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
        "result": r["result"],
    } for r in rows]

    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entries": entries}


@router.get("/audit-log/export")
async def export_audit_log(
    format: str = Query("csv", pattern="^(csv|json)$"),
    action: str = Query(None),
    user_id: str = Query(None),
    resource_type: str = Query(None),
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    rows = await pool.fetch(
        """SELECT id, ts, user_id, role, action, resource_type, resource_id, ip_address, result, detail
           FROM audit_log
           WHERE ($1::uuid IS NULL OR user_id = $1::uuid)
             AND ($2 IS NULL OR action = $2)
             AND ($3 IS NULL OR resource_type = $3)
           ORDER BY ts DESC""",
        user_id, action, resource_type
    )

    serializable_rows = [{
        "id": str(r["id"]),
        "ts": r["ts"].isoformat() if r["ts"] else None,
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "role": r["role"],
        "action": r["action"],
        "resource_type": r["resource_type"],
        "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
        "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
        "result": r["result"],
        "detail": r["detail"],
    } for r in rows]

    if format == "json":
        return JSONResponse(
            content={"total": len(serializable_rows), "entries": serializable_rows},
            headers={"Content-Disposition": 'attachment; filename="audit_log.json"'}
        )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "ts", "user_id", "role", "action", "resource_type", "resource_id", "ip_address", "result", "detail"],
    )
    writer.writeheader()
    for row in serializable_rows:
        row = dict(row)
        row["detail"] = json.dumps(row["detail"], ensure_ascii=True) if row["detail"] is not None else ""
        writer.writerow(row)

    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'}
    )


@router.get("/statistics")
async def get_statistics(x_access_key: str = Header(None)):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    total_patients = await pool.fetchval("SELECT COUNT(*) FROM patients WHERE deleted_at IS NULL")
    total_users = await pool.fetchval("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")
    total_inferences = await pool.fetchval("SELECT COUNT(*) FROM inference_queue WHERE deleted_at IS NULL")
    total_reports = await pool.fetchval("SELECT COUNT(*) FROM risk_reports WHERE deleted_at IS NULL")
    signed_reports = await pool.fetchval("SELECT COUNT(*) FROM risk_reports WHERE signed_at IS NOT NULL AND deleted_at IS NULL")
    accepted = await pool.fetchval("SELECT COUNT(*) FROM risk_reports WHERE doctor_action='ACCEPTED' AND deleted_at IS NULL")
    rejected = await pool.fetchval("SELECT COUNT(*) FROM risk_reports WHERE doctor_action='REJECTED' AND deleted_at IS NULL")
    critical_today = await pool.fetchval(
        "SELECT COUNT(*) FROM risk_reports WHERE is_critical=TRUE AND created_at::date=CURRENT_DATE AND deleted_at IS NULL"
    )

    acceptance_rate = round(accepted / total_reports, 2) if total_reports else 0
    rejection_rate = round(rejected / total_reports, 2) if total_reports else 0

    return {
        "total_patients": total_patients,
        "total_users": total_users,
        "total_inferences": total_inferences,
        "total_risk_reports": total_reports,
        "signed_reports": signed_reports,
        "unsigned_reports": total_reports - signed_reports,
        "inference_acceptance_rate": acceptance_rate,
        "inference_rejection_rate": rejection_rate,
        "critical_alerts_today": critical_today,
    }


@router.post("/restore/{resource_type}/{resource_id}")
async def restore_deleted(
    resource_type: str,
    resource_id: str,
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    await _require_admin(pool, x_access_key)

    table = TABLE_MAP.get(resource_type)
    if not table:
        raise HTTPException(status_code=400, detail=f"Unknown resource type: {resource_type}")

    result = await pool.execute(
        f"UPDATE {table} SET deleted_at=NULL WHERE id::text=$1 AND deleted_at IS NOT NULL",
        resource_id
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Resource not found or not deleted")

    return {
        "message": "Resource restored",
        "resource_id": resource_id,
        "resource_type": resource_type,
        "restored_at": datetime.utcnow().isoformat(),
    }


@router.post("/configure-alert-threshold")
async def configure_alert_threshold(
    threshold_config: dict,
    x_access_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _require_admin(pool, x_access_key)
    await pool.execute(
        """INSERT INTO alert_threshold_config (config_key, config_json, updated_at, updated_by)
           VALUES ('default', $1::jsonb, NOW(), $2)
           ON CONFLICT (config_key) DO UPDATE
           SET config_json = EXCLUDED.config_json,
               updated_at = EXCLUDED.updated_at,
               updated_by = EXCLUDED.updated_by""",
        json.dumps(threshold_config),
        user["id"],
    )
    return {"message": "Threshold updated", "config": threshold_config}
