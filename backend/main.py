"""
FastAPI Backend for Sistema Clínico Digital Interoperable Corte 2
HL7 FHIR R4, double API-Key auth, PostgreSQL, MinIO
"""

from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import re
from contextlib import asynccontextmanager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routers and utilities
from config import settings
from db import init_db, get_db_pool, close_db
from routers import fhir, auth, admin, admin_users


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
    if text.endswith("perm"):
        text = text[:-4]
    return text


async def validate_api_keys(
    request: Request,
    x_access_key: str = Header(None),
    x_permission_key: str = Header(None)
):
    """Validate double API-Key against DB on all endpoints except auth/health/docs"""
    path = request.url.path
    exempt = (
        path.startswith("/auth/")
        or path in ("/health", "/", "/docs", "/openapi.json", "/redoc")
        or path.startswith("/docs")
        or path.startswith("/openapi")
    )
    if exempt:
        return {"access_key": x_access_key, "permission_key": x_permission_key}

    x_access_key = _normalize_access_key(x_access_key)
    x_permission_key = _normalize_permission_key(x_permission_key)

    if not x_access_key or not x_permission_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Access-Key or X-Permission-Key headers"
        )

    pool = await get_db_pool()
    user = await pool.fetchrow(
        "SELECT id, role, permission_key, is_active FROM users WHERE access_key=$1 AND deleted_at IS NULL",
        x_access_key
    )

    if not user or not user["is_active"]:
        raise HTTPException(status_code=403, detail="Invalid or inactive API key")

    stored_permission_key = _normalize_permission_key(user["permission_key"])
    if stored_permission_key != x_permission_key:
        raise HTTPException(status_code=403, detail="Permission key mismatch")

    return {
        "access_key": x_access_key,
        "permission_key": x_permission_key,
        "role": user["role"],
        "user_id": str(user["id"])
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 Initializing Sistema Clínico Digital...")
    await init_db()
    logger.info("✅ Database initialized")
    yield
    await close_db()
    logger.info("🛑 Shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Sistema Clínico Digital Interoperable",
    description="HL7 FHIR R4 • ML/DL cuantizado • Corte 2",
    version="2.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers — fhir/admin/admin_users require valid API keys
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(fhir.router, prefix="/fhir", tags=["FHIR"],
                   dependencies=[Depends(validate_api_keys)])
app.include_router(admin.router, prefix="/admin", tags=["Admin"],
                   dependencies=[Depends(validate_api_keys)])
app.include_router(admin_users.router, prefix="/admin/users", tags=["Admin Users"],
                   dependencies=[Depends(validate_api_keys)])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "backend",
        "version": "2.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Sistema Clínico Digital Interoperable - Corte 2",
        "api_docs": "/docs",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=os.getenv("ENV", "production") == "development"
    )

