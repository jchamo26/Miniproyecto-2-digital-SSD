"""FHIR router - HL7 FHIR R4 resources backed by PostgreSQL"""
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
import logging
import json
import os
import io
from datetime import datetime
from uuid import uuid4, UUID
from db import get_db_pool, log_audit
try:
    from minio import Minio
except ImportError:
    Minio = None

logger = logging.getLogger(__name__)
router = APIRouter()

# MinIO client for image serving
_minio_client = None

def _get_minio_client():
    global _minio_client
    if _minio_client is None and Minio:
        _minio_client = Minio(
            os.getenv("MINIO_ENDPOINT", "minio:9000"),
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=False,
        )
    return _minio_client


async def _get_user(pool, access_key: str):
    """Fetch user row by access_key"""
    return await pool.fetchrow(
        "SELECT id, role, permission_key FROM users WHERE access_key=$1 AND is_active=TRUE AND deleted_at IS NULL",
        access_key
    )


async def _assert_patient_access(pool, user, patient_db_id):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if user["role"] == "admin":
        return

    allowed = await pool.fetchval(
        "SELECT 1 FROM user_patients WHERE user_id=$1 AND patient_id=$2",
        user["id"], patient_db_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access denied to this patient")


def _safe_ip(request: Request):
    return request.client.host if request.client else "unknown"


def _patient_resource_from_row(row, role: str):
    """Build patient response and enforce masking for admin role."""
    if role == "admin":
        return {
            "resourceType": "Patient",
            "id": row["fhir_id"] or str(row["id"]),
            "db_id": str(row["id"]),
            "name": [{"given": ["CIFRADO"], "family": "PACIENTE"}],
            "birthDate": None,
            "gender": "unknown",
            "active": row["is_active"],
            "meta": {"tag": [{"system": "privacy", "code": "masked-for-admin"}]},
        }

    parts = row["name"].split()
    return {
        "resourceType": "Patient",
        "id": row["fhir_id"] or str(row["id"]),
        "db_id": str(row["id"]),
        "name": [{"given": [parts[0]], "family": parts[-1] if len(parts) > 1 else ""}],
        "birthDate": row["birth_date"].isoformat() if row["birth_date"] else None,
        "gender": row["gender"],
        "active": row["is_active"],
    }


# ─────────────────────────── PATIENTS ───────────────────────────────

@router.get("/Patient")
async def list_patients(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    role = user["role"] if user else "paciente"

    if role == "admin":
        rows = await pool.fetch(
            "SELECT id, fhir_id, name, birth_date, gender, is_active FROM patients "
            "WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        total = await pool.fetchval("SELECT COUNT(*) FROM patients WHERE deleted_at IS NULL")
    else:
        # medico sees assigned patients; paciente sees only their own linked patient
        rows = await pool.fetch(
            """SELECT p.id, p.fhir_id, p.name, p.birth_date, p.gender, p.is_active
               FROM patients p
               JOIN user_patients up ON up.patient_id = p.id
               WHERE up.user_id = $1 AND p.deleted_at IS NULL
               ORDER BY p.created_at DESC LIMIT $2 OFFSET $3""",
            user["id"], limit, offset
        )
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM patients p JOIN user_patients up ON up.patient_id=p.id "
            "WHERE up.user_id=$1 AND p.deleted_at IS NULL",
            user["id"]
        )

    patients = [_patient_resource_from_row(r, role) for r in rows]

    await log_audit(pool, str(user["id"]) if user else None, role,
                    "LIST_PATIENTS", "Patient", None, _safe_ip(request), "SUCCESS")

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": total,
        "entry": [{"resource": p} for p in patients],
        "link": [
            {"relation": "self", "url": f"/fhir/Patient?limit={limit}&offset={offset}"},
            {"relation": "next", "url": f"/fhir/Patient?limit={limit}&offset={offset + limit}"},
        ],
    }


@router.post("/Patient")
async def create_patient(
    request: Request,
    patient: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if user and user["role"] == "paciente":
        raise HTTPException(status_code=403, detail="Patients cannot create patient records")

    name_data = patient.get("name", [{}])[0]
    given = (name_data.get("given") or ["Unknown"])[0]
    family = name_data.get("family", "")
    full_name = f"{given} {family}".strip()
    birth_date = patient.get("birthDate")
    if isinstance(birth_date, str):
        try:
            birth_date = datetime.fromisoformat(birth_date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="birthDate must be YYYY-MM-DD")
    gender = patient.get("gender", "unknown")
    fhir_id = str(uuid4())

    async with (await get_db_pool()).acquire() as conn:
        patient_id = await conn.fetchval(
            "INSERT INTO patients (fhir_id, name, birth_date, gender, is_active) "
            "VALUES ($1, $2, $3, $4, TRUE) RETURNING id",
            fhir_id, full_name, birth_date, gender,
        )
        if user and user["role"] == "medico":
            await conn.execute(
                "INSERT INTO user_patients (user_id, patient_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                user["id"], patient_id,
            )

    await log_audit(pool, str(user["id"]) if user else None,
                    user["role"] if user else "unknown",
                    "CREATE_PATIENT", "Patient", patient_id, _safe_ip(request), "SUCCESS")

    return {"id": fhir_id, "db_id": str(patient_id), "status": "created",
            "resource": {**patient, "id": fhir_id}}


@router.get("/Patient/{patient_id}")
async def get_patient(
    request: Request,
    patient_id: str,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    row = await pool.fetchrow(
        "SELECT id, fhir_id, name, birth_date, gender, is_active FROM patients "
        "WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")

    await _assert_patient_access(pool, user, row["id"])

    await log_audit(pool, str(user["id"]) if user else None,
                    user["role"] if user else "unknown",
                    "VIEW_PATIENT", "Patient", row["id"], _safe_ip(request), "SUCCESS")

    role = user["role"] if user else "paciente"
    return _patient_resource_from_row(row, role)


@router.post("/Patient/{patient_id}/close")
async def close_patient(
    request: Request,
    patient_id: str,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    """Soft-close a patient. Returns 409 if any RiskReport is unsigned."""
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not user or user["role"] not in ("admin", "medico"):
        raise HTTPException(status_code=403, detail="Only admin or médico can close patients")

    row = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")

    unsigned = await pool.fetchval(
        "SELECT COUNT(*) FROM risk_reports "
        "WHERE patient_id=$1 AND signed_at IS NULL AND deleted_at IS NULL",
        row["id"]
    )
    if unsigned > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot close patient: {unsigned} RiskReport(s) pending signature. "
                   "All reports must be signed before closing."
        )

    await pool.execute(
        "UPDATE patients SET is_active=FALSE, deleted_at=NOW() WHERE id=$1",
        row["id"]
    )
    await log_audit(pool, str(user["id"]), user["role"],
                    "CLOSE_PATIENT", "Patient", row["id"], _safe_ip(request), "SUCCESS")

    return {"message": "Patient closed successfully", "patient_id": patient_id}


# ─────────────────────────── OBSERVATIONS ───────────────────────────

@router.post("/Observation")
async def create_observation(
    request: Request,
    observation: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can create observations")

    obs_id = str(uuid4())

    subject_ref = observation.get("subject", {}).get("reference", "")
    patient_ref = subject_ref.replace("Patient/", "") if subject_ref else None

    patient_db_id = None
    if patient_ref:
        p = await pool.fetchrow(
            "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
            patient_ref
        )
        if p:
            patient_db_id = p["id"]

    code_data = (observation.get("code", {}).get("coding") or [{}])[0]
    loinc_code = code_data.get("code")
    display_name = code_data.get("display")
    value = observation.get("valueQuantity", {}).get("value")
    unit = observation.get("valueQuantity", {}).get("unit")

    if patient_db_id:
        await _assert_patient_access(pool, user, patient_db_id)
        await pool.execute(
            "INSERT INTO observations (patient_id, fhir_id, loinc_code, display_name, value_quantity, unit) "
            "VALUES ($1,$2,$3,$4,$5,$6)",
            patient_db_id, obs_id, loinc_code, display_name,
            float(value) if value is not None else None, unit,
        )

    return {"id": obs_id, "status": "created"}


@router.get("/Observation")
async def list_observations(
    request: Request,
    subject: str = Query(None),
    code: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not subject:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}

    patient_ref = subject.replace("Patient/", "")
    p = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_ref
    )
    if not p:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}

    await _assert_patient_access(pool, user, p["id"])

    rows = await pool.fetch(
        "SELECT id, fhir_id, loinc_code, display_name, value_quantity, unit, effective_date "
        "FROM observations WHERE patient_id=$1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
        p["id"], limit, offset
    )
    total = await pool.fetchval("SELECT COUNT(*) FROM observations WHERE patient_id=$1", p["id"])

    entries = []
    for r in rows:
        entries.append({"resource": {
            "resourceType": "Observation",
            "id": str(r["fhir_id"] or r["id"]),
            "status": "final",
            "subject": {"reference": f"Patient/{patient_ref}"},
            "code": {"coding": [{"system": "http://loinc.org",
                                  "code": r["loinc_code"], "display": r["display_name"]}]},
            "valueQuantity": {"value": float(r["value_quantity"]) if r["value_quantity"] else 0,
                              "unit": r["unit"]},
            "effectiveDateTime": r["effective_date"].isoformat() if r["effective_date"] else None,
        }})

    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": entries}


# ─────────────────────────── RISK ASSESSMENT ────────────────────────

@router.get("/RiskAssessment")
async def list_risk_assessments(
    request: Request,
    patient_id: str = Query(None),
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not patient_id:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}

    p = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1)", patient_id
    )
    if not p:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}

    await _assert_patient_access(pool, user, p["id"])

    rows = await pool.fetch(
        "SELECT id, patient_id, model_type, risk_score, risk_category, is_critical, "
        "shap_json, doctor_action, signed_at, created_at "
        "FROM risk_reports WHERE patient_id=$1 AND deleted_at IS NULL "
        "AND ($2::text <> 'paciente' OR signed_at IS NOT NULL) ORDER BY created_at DESC",
        p["id"], user["role"] if user else "paciente"
    )

    entries = [{"resource": {
        "resourceType": "RiskAssessment",
        "id": str(r["id"]),
        "patient_id": str(r["patient_id"]),
        "model_type": r["model_type"],
        "risk_score": float(r["risk_score"]) if r["risk_score"] else 0,
        "risk_category": r["risk_category"],
        "is_critical": r["is_critical"],
        "shap_json": r["shap_json"],
        "doctor_action": r["doctor_action"],
        "signed_at": r["signed_at"].isoformat() if r["signed_at"] else None,
        "created_at": r["created_at"].isoformat(),
    }} for r in rows]

    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}


@router.post("/RiskAssessment")
async def create_risk_assessment(
    request: Request,
    risk: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can create RiskAssessment")

    patient_ref = (risk.get("patient_id")
                   or risk.get("subject", {}).get("reference", "").replace("Patient/", ""))
    p = None
    if patient_ref:
        p = await pool.fetchrow(
            "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
            patient_ref
        )
        if p:
            await _assert_patient_access(pool, user, p["id"])

    shap_data = risk.get("shap_values") or risk.get("shap_json")

    risk_id = await pool.fetchval(
        """INSERT INTO risk_reports (patient_id, model_type, risk_score, risk_category, is_critical, shap_json)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb) RETURNING id""",
        p["id"] if p else None,
        risk.get("model_type", "ML"),
        risk.get("risk_score"),
        risk.get("risk_category"),
        risk.get("is_critical", False),
        json.dumps(shap_data) if shap_data else None,
    )

    await log_audit(pool, str(user["id"]) if user else None,
                    user["role"] if user else "unknown",
                    "CREATE_RISK_ASSESSMENT", "RiskAssessment", risk_id,
                    _safe_ip(request), "SUCCESS")

    return {"id": str(risk_id), "status": "created"}


@router.patch("/RiskAssessment/{risk_id}/sign")
async def sign_risk_report(
    request: Request,
    risk_id: str,
    signature: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can sign reports")

    notes = signature.get("doctor_notes", "")
    if len(notes) < 30:
        raise HTTPException(status_code=400, detail="Doctor notes must be at least 30 characters")

    action = signature.get("doctor_action")
    if action not in ("ACCEPTED", "REJECTED"):
        raise HTTPException(status_code=400, detail="doctor_action must be ACCEPTED or REJECTED")

    if action == "REJECTED" and len(signature.get("rejection_reason", "")) < 20:
        raise HTTPException(status_code=400, detail="Rejection reason must be at least 20 characters")

    row = await pool.fetchrow(
        "SELECT id FROM risk_reports WHERE id::text=$1 AND signed_at IS NULL AND deleted_at IS NULL",
        risk_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Risk report not found or already signed")

    signed_at = datetime.utcnow()
    await pool.execute(
        """UPDATE risk_reports
           SET doctor_action=$1, doctor_notes=$2, rejection_reason=$3,
               signed_by=$4, signed_at=$5
           WHERE id::text=$6""",
        action, notes, signature.get("rejection_reason"),
        user["id"], signed_at, risk_id
    )

    await log_audit(pool, str(user["id"]), user["role"],
                    "SIGN_RISK_REPORT", "RiskAssessment", row["id"],
                    _safe_ip(request), "SUCCESS", {"action": action})

    return {
        "id": risk_id,
        "status": "signed",
        "signed_at": signed_at.isoformat(),
        "doctor_action": action,
        "message": "RiskAssessment signed successfully"
    }


@router.get("/RiskAssessment/{patient_id}/can-close")
async def can_close_patient(
    request: Request,
    patient_id: str,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can close patients")

    p = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id
    )
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    await _assert_patient_access(pool, user, p["id"])

    unsigned = await pool.fetchval(
        "SELECT COUNT(*) FROM risk_reports "
        "WHERE patient_id=$1 AND signed_at IS NULL AND deleted_at IS NULL",
        p["id"]
    )
    can_close = unsigned == 0
    return {
        "can_close": can_close,
        "pending_signatures": int(unsigned),
        "message": ("Patient can be closed"
                    if can_close else f"{unsigned} RiskReport(s) pending signature"),
    }


# ─────────────────────────── MEDIA ──────────────────────────────────

@router.post("/Media")
async def create_media(
    request: Request,
    media: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can create media")

    media_id = str(uuid4())

    patient_ref = media.get("subject", {}).get("reference", "").replace("Patient/", "")
    p = None
    if patient_ref:
        p = await pool.fetchrow(
            "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1)",
            patient_ref
        )
        if p:
            await _assert_patient_access(pool, user, p["id"])

    if p:
        minio_key = media.get("content", {}).get("url", f"clinical-images/{patient_ref}/{media_id}.png")
        await pool.execute(
            "INSERT INTO images (patient_id, minio_key, modality, fhir_media_id) VALUES ($1,$2,$3,$4)",
            p["id"], minio_key.encode(), media.get("modality", "FUNDUS"), media_id
        )

    media["id"] = media_id
    media["resourceType"] = "Media"
    return {"id": media_id, "status": "created"}


# ─────────────────────────── DIAGNOSTIC REPORT ─────────────────────

@router.post("/DiagnosticReport")
async def create_diagnostic_report(
    request: Request,
    report: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not user or user["role"] != "medico":
        raise HTTPException(status_code=403, detail="Only medico can create DiagnosticReport")

    patient_ref = report.get("subject", {}).get("reference", "").replace("Patient/", "")
    p = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_ref
    ) if patient_ref else None
    if p:
        await _assert_patient_access(pool, user, p["id"])

    report_id = str(uuid4())
    coding = (report.get("code", {}).get("coding") or [{}])[0]
    code = coding.get("code") or report.get("code", {}).get("text")

    row_id = await pool.fetchval(
        """
        INSERT INTO diagnostic_reports (patient_id, fhir_id, status, code, conclusion, presented_form, created_by)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
        RETURNING id
        """,
        p["id"] if p else None,
        report_id,
        report.get("status", "final"),
        code,
        report.get("conclusion"),
        json.dumps(report.get("presentedForm", [])),
        user["id"],
    )

    await log_audit(
        pool,
        str(user["id"]),
        user["role"],
        "CREATE_DIAGNOSTIC_REPORT",
        "DiagnosticReport",
        row_id,
        _safe_ip(request),
        "SUCCESS",
    )

    return {"id": report_id, "status": "created", "resourceType": "DiagnosticReport"}


@router.get("/DiagnosticReport")
async def list_diagnostic_reports(
    request: Request,
    patient_id: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not patient_id:
        return {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}

    pid = None
    p = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id
    )
    if p:
        pid = p["id"]
        await _assert_patient_access(pool, user, pid)

    rows = await pool.fetch(
        """
        SELECT id, patient_id, fhir_id, status, code, conclusion, presented_form, created_at
        FROM diagnostic_reports
        WHERE ($1::uuid IS NULL OR patient_id = $1::uuid) AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        pid,
        limit,
        offset,
    )

    total = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM diagnostic_reports
        WHERE ($1::uuid IS NULL OR patient_id = $1::uuid) AND deleted_at IS NULL
        """,
        pid,
    )

    entries = []
    for r in rows:
        presented_form = r["presented_form"]
        if isinstance(presented_form, str):
            try:
                presented_form = json.loads(presented_form)
            except Exception:
                presented_form = []
        entries.append({
            "resource": {
                "resourceType": "DiagnosticReport",
                "id": r["fhir_id"] or str(r["id"]),
                "status": r["status"],
                "subject": {"reference": f"Patient/{patient_id}"} if patient_id else None,
                "code": {"text": r["code"]},
                "conclusion": r["conclusion"],
                "presentedForm": presented_form or [],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
        })

    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": entries}


@router.post("/Patient/{patient_id}/data-correction-request")
async def request_data_correction(
    request: Request,
    patient_id: str,
    payload: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)

    if not user or user["role"] != "paciente":
        raise HTTPException(status_code=403, detail="Only paciente can request data correction")

    patient = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    await _assert_patient_access(pool, user, patient["id"])

    field_name = str(payload.get("field_name", "")).strip()
    requested_value = str(payload.get("requested_value", "")).strip()
    reason = str(payload.get("reason", "")).strip()
    current_value = payload.get("current_value")

    if not field_name or not requested_value or len(reason) < 10:
        raise HTTPException(status_code=400, detail="field_name, requested_value and reason>=10 are required")

    req_id = await pool.fetchval(
        """INSERT INTO data_correction_requests (patient_id, requested_by, field_name, current_value, requested_value, reason)
           VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
        patient["id"], user["id"], field_name, str(current_value) if current_value is not None else None, requested_value, reason
    )

    await log_audit(pool, str(user["id"]), user["role"],
                    "REQUEST_DATA_CORRECTION", "Patient", patient["id"], _safe_ip(request), "SUCCESS",
                    {"field_name": field_name, "request_id": str(req_id)})

    return {"id": str(req_id), "status": "PENDING", "message": "Data correction request created"}


# ─────────────────────────── AUDIT EVENT ────────────────────────────

@router.post("/AuditEvent")
async def create_audit_event(
    request: Request,
    event: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    event_id = uuid4()
    await pool.execute(
        """INSERT INTO audit_log (user_id, role, action, resource_type, ip_address, result, detail)
           VALUES ($1,$2,$3,$4,$5::inet,$6,$7::jsonb)""",
        user["id"] if user else None,
        user["role"] if user else None,
        event.get("action", "UNKNOWN"),
        event.get("resource_type"),
        _safe_ip(request),
        event.get("result", "SUCCESS"),
        json.dumps(event)
    )
    return {"id": str(event_id), "status": "created"}


@router.get("/AuditEvent")
async def list_audit_events(
    request: Request,
    user_id: str = Query(None),
    action: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    caller = await _get_user(pool, x_access_key)
    if not caller or caller["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    rows = await pool.fetch(
        """SELECT id, ts, user_id, role, action, resource_type, resource_id, ip_address, result
           FROM audit_log
           WHERE ($1::uuid IS NULL OR user_id=$1::uuid)
             AND ($2 IS NULL OR action=$2)
           ORDER BY ts DESC LIMIT $3 OFFSET $4""",
        user_id, action, limit, offset
    )
    total = await pool.fetchval(
        "SELECT COUNT(*) FROM audit_log "
        "WHERE ($1::uuid IS NULL OR user_id=$1::uuid) AND ($2 IS NULL OR action=$2)",
        user_id, action
    )

    entries = [{"resource": {
        "resourceType": "AuditEvent",
        "id": str(r["id"]),
        "ts": r["ts"].isoformat(),
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "role": r["role"],
        "action": r["action"],
        "resource_type": r["resource_type"],
        "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
        "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
        "result": r["result"],
    }} for r in rows]

    return {"resourceType": "Bundle", "type": "searchset", "total": total, "entry": entries}


# ─────────────────────────── CONSENT ────────────────────────────────

@router.post("/Consent")
async def create_consent(
    request: Request,
    consent: dict,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    consent_id = uuid4()
    if user:
        await pool.execute(
            "INSERT INTO consent (id, user_id, ip_address) VALUES ($1,$2,$3::inet) ON CONFLICT DO NOTHING",
            consent_id, user["id"], _safe_ip(request)
        )
    return {"id": str(consent_id), "status": "active"}


# ─────────────────────────── IMAGE SERVING ─────────────────────────

@router.get("/image/{task_id}")
async def serve_image(
    task_id: str,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    """Serve Grad-CAM or other images from MinIO"""
    pool = await get_db_pool()
    user = await _get_user(pool, x_access_key)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    client = _get_minio_client()
    if not client:
        raise HTTPException(status_code=503, detail="MinIO not available")
    
    bucket = os.getenv("MINIO_BUCKET", "clinical-images")
    object_name = f"gradcam/{task_id}.png"
    
    try:
        response = client.get_object(bucket, object_name)
        
        def iterfile():
            for chunk in response.stream(32768):
                yield chunk
            response.close()
        
        return StreamingResponse(iterfile(), media_type="image/png")
    except Exception as e:
        logger.warning(f"Image not found: {object_name} ({e})")
        raise HTTPException(status_code=404, detail="Image not found")
