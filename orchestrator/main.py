"""Inference Orchestrator - AsyncIO queue with DB persistence and WebSocket updates."""
import asyncio
import json
import logging
import os
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Inference Orchestrator", version="1.0.0")

# Global semaphore for concurrency control
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
sem = asyncio.Semaphore(MAX_WORKERS)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@postgres:5432/clinical_db")

# In-memory cache + PostgreSQL source of truth for persistence
inference_queue = {}
db_pool = None

class InferenceRequest(BaseModel):
    patient_id: str
    model_type: str  # ML, DL, MULTIMODAL
    image_base64: str | None = None

class InferenceResponse(BaseModel):
    task_id: str
    status: str
    message: str


def _to_uuid_or_none(raw: str | None):
    try:
        return UUID(str(raw)) if raw else None
    except Exception:
        return None


async def _get_db_pool():
    global db_pool
    if db_pool is None:
        retries = 0
        while retries < 10:
            try:
                db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
                break
            except Exception as exc:
                retries += 1
                logger.warning("DB connection attempt %s/10 failed: %s", retries, exc)
                await asyncio.sleep(2)
        if db_pool is None:
            raise RuntimeError("Unable to connect to orchestrator database")
    return db_pool


async def _ensure_schema():
    pool = await _get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inference_queue (
                id UUID PRIMARY KEY,
                patient_id TEXT,
                model_type VARCHAR(20),
                status VARCHAR(20) DEFAULT 'PENDING',
                requested_by UUID,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                result_id UUID,
                error_msg TEXT,
                result_json JSONB,
                deleted_at TIMESTAMPTZ
            );
            """
        )


async def _persist_task(task: dict):
    pool = await _get_db_pool()
    created_at = task.get("created_at")
    completed_at = task.get("completed_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if isinstance(completed_at, str):
        completed_at = datetime.fromisoformat(completed_at)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inference_queue (id, patient_id, model_type, status, requested_by, created_at, completed_at, error_msg, result_json)
            VALUES ($1::uuid, $2, $3, $4, $5::uuid, $6::timestamptz, $7::timestamptz, $8, $9::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                requested_by = EXCLUDED.requested_by,
                completed_at = EXCLUDED.completed_at,
                error_msg = EXCLUDED.error_msg,
                result_json = EXCLUDED.result_json
            """,
            task["task_id"],
            task["patient_id"],
            task["model_type"],
            task["status"],
            task.get("requested_by"),
            created_at,
            completed_at,
            task.get("error_msg"),
            json.dumps(task.get("result")) if task.get("result") is not None else None,
        )


async def _fetch_task(task_id: str):
    if task_id in inference_queue:
        return inference_queue[task_id]

    pool = await _get_db_pool()
    row = await pool.fetchrow(
        """
        SELECT id, patient_id, model_type, status, created_at, completed_at, error_msg, result_json
               , requested_by
        FROM inference_queue
        WHERE id::text = $1 AND deleted_at IS NULL
        """,
        task_id,
    )
    if not row:
        return None

    task = {
        "task_id": str(row["id"]),
        "patient_id": row["patient_id"],
        "model_type": row["model_type"],
        "status": row["status"],
        "requested_by": str(row["requested_by"]) if row["requested_by"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "result": row["result_json"],
        "error_msg": row["error_msg"],
    }
    inference_queue[task_id] = task
    return task


@app.on_event("startup")
async def startup_event():
    await _ensure_schema()


@app.on_event("shutdown")
async def shutdown_event():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def _authenticate_medico(x_access_key: str | None, x_permission_key: str | None):
    access_key = str(x_access_key or "").strip()
    permission_key = str(x_permission_key or "").strip().lower()
    if not access_key or permission_key != "medico":
        raise HTTPException(status_code=403, detail="Only medico can execute inferences")

    pool = await _get_db_pool()
    user = await pool.fetchrow(
        "SELECT id, role, permission_key, is_active FROM users WHERE access_key=$1 AND deleted_at IS NULL",
        access_key,
    )
    if not user or not user["is_active"] or user["role"] != "medico" or str(user["permission_key"]).lower() != "medico":
        raise HTTPException(status_code=403, detail="Only medico can execute inferences")
    return user


async def _assert_medico_patient_access(user_id, patient_id: str):
    pool = await _get_db_pool()
    patient = await pool.fetchrow(
        "SELECT id FROM patients WHERE (id::text=$1 OR fhir_id=$1) AND deleted_at IS NULL",
        patient_id,
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    allowed = await pool.fetchval(
        "SELECT 1 FROM user_patients WHERE user_id=$1 AND patient_id=$2",
        user_id,
        patient["id"],
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Patient not assigned to this medico")
    return patient

@app.post("/infer", response_model=InferenceResponse)
async def request_inference(
    req: InferenceRequest,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    """
    Request inference for a patient
    Returns task_id immediately (non-blocking)
    """
    model_type = (req.model_type or "").upper()
    if model_type not in ("ML", "DL", "MULTIMODAL"):
        raise HTTPException(status_code=400, detail="model_type must be ML, DL, or MULTIMODAL")

    user = await _authenticate_medico(x_access_key, x_permission_key)
    await _assert_medico_patient_access(user["id"], req.patient_id)

    if model_type == "MULTIMODAL" and not req.image_base64:
        raise HTTPException(status_code=400, detail="MULTIMODAL inference requires image_base64")

    task_id = str(uuid4())
    
    inference_queue[task_id] = {
        "task_id": task_id,
        "patient_id": req.patient_id,
        "model_type": model_type,
        "requested_by": str(user["id"]),
        "image_base64": req.image_base64,
        "status": "PENDING",
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "result": None,
        "error_msg": None
    }
    await _persist_task(inference_queue[task_id])
    
    logger.info(f"🎯 Inference requested: {task_id} (model={model_type})")
    
    # Start background task
    asyncio.create_task(
        run_inference_with_semaphore(task_id, req.patient_id, model_type, req.image_base64)
    )
    
    return InferenceResponse(
        task_id=task_id,
        status="PENDING",
        message="Inference queued"
    )

async def run_inference_with_semaphore(task_id: str, patient_id: str, model_type: str, image_base64: str | None):
    """Run inference with concurrency limit (Semaphore)"""
    async with sem:
        await run_inference(task_id, patient_id, model_type, image_base64)

async def run_inference(task_id: str, patient_id: str, model_type: str, image_base64: str | None):
    """Execute inference on ML or DL service"""
    try:
        inference_queue[task_id]["status"] = "RUNNING"
        await _persist_task(inference_queue[task_id])
        logger.info(f"Running inference: {task_id}")
        
        # Call appropriate service
        async with httpx.AsyncClient(timeout=120.0) as client:
            result_payload = None

            if model_type == "ML":
                url = "http://ml-service:8001/predict"
                response = await client.post(url, json={"patient_id": patient_id})
                if response.status_code == 200:
                    result_payload = response.json()
            elif model_type == "DL":
                url = "http://dl-service:8003/predict"
                response = await client.post(url, json={"patient_id": patient_id, "image_base64": image_base64})
                if response.status_code == 200:
                    result_payload = response.json()
            elif model_type == "MULTIMODAL":
                # Parallel calls to ML and DL
                async def get_ml():
                    return await client.post("http://ml-service:8001/predict", json={"patient_id": patient_id})
                
                async def get_dl():
                    return await client.post("http://dl-service:8003/predict", json={"patient_id": patient_id, "image_base64": image_base64})
                
                ml_response, dl_response = await asyncio.gather(get_ml(), get_dl())

                if ml_response.status_code != 200:
                    raise Exception(f"ML service returned {ml_response.status_code}")
                if dl_response.status_code != 200:
                    raise Exception(f"DL service returned {dl_response.status_code}")

                ml_result = ml_response.json()
                dl_result = dl_response.json()
                response = ml_response
                result_payload = {
                    "model_type": "MULTIMODAL",
                    "ml_result": ml_result,
                    "dl_result": dl_result,
                    "risk_score": ml_result.get("risk_score"),
                    "risk_category": ml_result.get("risk_category"),
                    "is_critical": bool(ml_result.get("is_critical") or dl_result.get("is_critical")),
                    "shap_values": ml_result.get("shap_values"),
                    "predicted_class": dl_result.get("predicted_class"),
                    "probabilities": dl_result.get("probabilities"),
                }
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            if response.status_code == 200:
                inference_queue[task_id]["result"] = result_payload if result_payload is not None else response.json()
                inference_queue[task_id]["status"] = "DONE"
                inference_queue[task_id]["completed_at"] = datetime.utcnow().isoformat()
                await _persist_task(inference_queue[task_id])
                logger.info(f"Inference completed: {task_id}")
            else:
                raise Exception(f"Service returned {response.status_code}")
                
    except asyncio.TimeoutError:
        inference_queue[task_id]["status"] = "ERROR"
        inference_queue[task_id]["error_msg"] = "Inference timeout (>120s)"
        inference_queue[task_id]["completed_at"] = datetime.utcnow().isoformat()
        await _persist_task(inference_queue[task_id])
        logger.error(f"Timeout: {task_id}")
    except Exception as e:
        inference_queue[task_id]["status"] = "ERROR"
        inference_queue[task_id]["error_msg"] = str(e)
        inference_queue[task_id]["completed_at"] = datetime.utcnow().isoformat()
        await _persist_task(inference_queue[task_id])
        logger.error(f"Error: {task_id} - {e}")

@app.get("/infer/{task_id}")
async def get_inference_result(
    task_id: str,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None),
):
    """Get inference result by task_id (polling)"""
    user = await _authenticate_medico(x_access_key, x_permission_key)
    task = await _fetch_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("requested_by") != str(user["id"]):
        raise HTTPException(status_code=403, detail="Not allowed to access this task")
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "patient_id": task["patient_id"],
        "model_type": task["model_type"],
        "result": task["result"],
        "error_msg": task["error_msg"],
        "created_at": task["created_at"]
    }


@app.websocket("/infer/ws/{task_id}")
async def stream_inference(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        try:
            user = await _authenticate_medico(
                websocket.headers.get("x-access-key"),
                websocket.headers.get("x-permission-key"),
            )
        except HTTPException:
            await websocket.send_json({"task_id": task_id, "status": "FORBIDDEN"})
            await websocket.close(code=1008)
            return

        while True:
            task = await _fetch_task(task_id)
            if task is None:
                await websocket.send_json({"task_id": task_id, "status": "NOT_FOUND"})
                break
            if task.get("requested_by") != str(user["id"]):
                await websocket.send_json({"task_id": task_id, "status": "FORBIDDEN"})
                break

            await websocket.send_json(
                {
                    "task_id": task_id,
                    "status": task["status"],
                    "patient_id": task["patient_id"],
                    "model_type": task["model_type"],
                    "result": task["result"],
                    "error_msg": task["error_msg"],
                    "created_at": task["created_at"],
                }
            )

            if task["status"] in ("DONE", "ERROR"):
                break
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for task=%s", task_id)

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "max_workers": MAX_WORKERS,
        "active_tasks": len([t for t in inference_queue.values() if t["status"] == "RUNNING"]),
        "persistence": "postgresql"
    }
