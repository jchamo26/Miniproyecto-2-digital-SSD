"""Database module for async PostgreSQL connection"""
import asyncpg
import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd
from config import settings
import logging

logger = logging.getLogger(__name__)

db_pool = None


async def _seed_heart_patients_if_needed(conn):
    """Seed all patients from heart-disease.csv when patients table is empty."""
    if not settings.AUTO_SEED_HEART_DATASET:
        logger.info("AUTO_SEED_HEART_DATASET disabled; skipping dataset bootstrap")
        return

    existing = await conn.fetchval("SELECT COUNT(*) FROM patients WHERE deleted_at IS NULL")
    if existing and existing > 0:
        logger.info("Patients already present (%s); skipping dataset bootstrap", existing)
        return

    dataset_path = Path(settings.DATASET_PATH)
    if not dataset_path.exists():
        logger.warning("Dataset not found at %s; skipping patient bootstrap", dataset_path)
        return

    df = pd.read_csv(dataset_path)
    if df.empty:
        logger.warning("Dataset %s is empty; skipping patient bootstrap", dataset_path)
        return

    lower_cols = {c.lower(): c for c in df.columns}
    if "age" not in lower_cols:
        logger.warning("Dataset %s has no age column; skipping patient bootstrap", dataset_path)
        return

    age_col = lower_cols["age"]
    sex_col = lower_cols.get("sex")
    target_col = lower_cols.get("target")
    oldpeak_col = lower_cols.get("oldpeak")

    inserted = 0
    current_year = datetime.utcnow().year

    for idx, row in df.iterrows():
        try:
            age_raw = row.get(age_col)
            age = int(float(age_raw)) if pd.notna(age_raw) else 50
            age = max(18, min(age, 95))

            sex_raw = row.get(sex_col) if sex_col else 1
            sex_val = float(sex_raw) if pd.notna(sex_raw) else 1.0
            gender = "female" if sex_val <= 0 else "male"

            birth_year = max(1930, min(current_year - age, current_year - 18))
            birth_date = date(birth_year, (idx % 12) + 1, (idx % 28) + 1)

            fhir_id = str(uuid4())
            patient_name = f"Paciente {idx + 1:03d}"

            patient_id = await conn.fetchval(
                "INSERT INTO patients (fhir_id, name, birth_date, gender, is_active) "
                "VALUES ($1, $2, $3, $4, TRUE) RETURNING id",
                fhir_id,
                patient_name,
                birth_date,
                gender,
            )

            target_raw = row.get(target_col) if target_col else 0
            target = int(float(target_raw)) if pd.notna(target_raw) else 0
            oldpeak_raw = row.get(oldpeak_col) if oldpeak_col else 0
            oldpeak = float(oldpeak_raw) if pd.notna(oldpeak_raw) else 0.0

            risk_score = min(0.99, max(0.01, 0.30 + (0.45 * target) + (min(max(oldpeak, 0.0), 6.0) / 24.0)))
            if risk_score > 0.8:
                risk_category = "CRITICAL"
            elif risk_score > 0.6:
                risk_category = "HIGH"
            elif risk_score > 0.4:
                risk_category = "MEDIUM"
            else:
                risk_category = "LOW"

            await conn.execute(
                "INSERT INTO risk_reports (patient_id, model_type, risk_score, risk_category, is_critical, shap_json) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
                patient_id,
                "SEED",
                risk_score,
                risk_category,
                risk_category == "CRITICAL",
                json.dumps({"source": "heart-disease.csv", "row_index": int(idx)}),
            )

            inserted += 1
        except Exception as exc:
            logger.warning("Skipping dataset row %s due to error: %s", idx, exc)

    logger.info("Seeded %s patients from %s", inserted, dataset_path)

async def get_db_pool():
    """Get or create database connection pool"""
    global db_pool
    if db_pool is None:
        retries = 0
        while retries < 10:
            try:
                db_pool = await asyncpg.create_pool(
                    settings.DATABASE_URL,
                    min_size=1,
                    max_size=10,
                )
                logger.info("📊 Connection pool created")
                break
            except Exception as exc:
                retries += 1
                logger.warning(
                    f"Database connection attempt {retries}/10 failed: {exc}"
                )
                await asyncio.sleep(3)
        if db_pool is None:
            raise RuntimeError("Unable to connect to the PostgreSQL database")
    return db_pool

async def get_db():
    """Get a database connection from the pool"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        yield conn

async def init_db():
    """Initialize database schema on startup"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Ensure uuid generation extension is available
        await conn.execute("""
            CREATE EXTENSION IF NOT EXISTS pgcrypto;
        """)
        # Create schema if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255),
                hashed_password VARCHAR(255),
                role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'medico', 'paciente')),
                access_key VARCHAR(255) UNIQUE NOT NULL,
                permission_key VARCHAR(20) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS patients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                fhir_id TEXT UNIQUE,
                name VARCHAR(255) NOT NULL,
                birth_date DATE,
                identification_doc BYTEA,
                gender VARCHAR(10),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS user_patients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, patient_id)
            );

            CREATE TABLE IF NOT EXISTS observations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID REFERENCES patients(id),
                fhir_id TEXT,
                loinc_code VARCHAR(20),
                display_name VARCHAR(100),
                value_quantity NUMERIC,
                unit VARCHAR(20),
                effective_date TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS images (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID REFERENCES patients(id),
                minio_key BYTEA NOT NULL,
                modality VARCHAR(50),
                fhir_media_id TEXT,
                uploaded_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS risk_reports (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID REFERENCES patients(id),
                model_type VARCHAR(20),
                risk_score NUMERIC(5,4),
                risk_category VARCHAR(20),
                is_critical BOOLEAN,
                prediction_enc BYTEA,
                shap_json JSONB,
                fhir_risk_id TEXT,
                doctor_action VARCHAR(20),
                doctor_notes TEXT,
                rejection_reason TEXT,
                signed_by UUID REFERENCES users(id),
                signed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS inference_queue (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID,
                model_type VARCHAR(20),
                status VARCHAR(20) DEFAULT 'PENDING',
                requested_by UUID,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                result_id UUID,
                error_msg TEXT,
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS diagnostic_reports (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID REFERENCES patients(id),
                fhir_id TEXT UNIQUE,
                status VARCHAR(20) DEFAULT 'final',
                code VARCHAR(50),
                conclusion TEXT,
                presented_form JSONB,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                ts TIMESTAMPTZ DEFAULT NOW(),
                user_id UUID,
                role VARCHAR(20),
                action VARCHAR(80),
                resource_type VARCHAR(40),
                resource_id UUID,
                ip_address INET,
                result VARCHAR(20),
                detail JSONB
            );

            CREATE TABLE IF NOT EXISTS consent (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id),
                policy_version VARCHAR(20) DEFAULT '1.0',
                accepted_at TIMESTAMPTZ DEFAULT NOW(),
                ip_address INET
            );

            CREATE TABLE IF NOT EXISTS model_feedback (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                risk_report_id UUID REFERENCES risk_reports(id),
                feedback VARCHAR(20) CHECK (feedback IN ('ACCEPTED', 'REJECTED')),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS alert_threshold_config (
                config_key TEXT PRIMARY KEY,
                config_json JSONB NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                updated_by UUID REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS data_correction_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                patient_id UUID REFERENCES patients(id),
                requested_by UUID REFERENCES users(id),
                field_name VARCHAR(100) NOT NULL,
                current_value TEXT,
                requested_value TEXT NOT NULL,
                reason TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                resolved_at TIMESTAMPTZ,
                deleted_at TIMESTAMPTZ
            );
        """)
        # Auth uses API keys - make hashed_password optional if it exists as NOT NULL
        await conn.execute("""
            ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
        """)
        await conn.execute("""
            ALTER TABLE users ALTER COLUMN email DROP NOT NULL;
        """)
        await conn.execute("""
            ALTER TABLE inference_queue
            ALTER COLUMN patient_id TYPE TEXT USING patient_id::text;
        """)
        await conn.execute("""
            ALTER TABLE inference_queue
            ADD COLUMN IF NOT EXISTS result_json JSONB;
        """)
        await conn.execute("""
            ALTER TABLE inference_queue
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
        """)
        await conn.execute("""
            ALTER TABLE risk_reports
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
        """)

        # Seed default users (idempotent via ON CONFLICT)
        await conn.execute(
            """INSERT INTO users (username, email, role, access_key, permission_key, is_active)
               VALUES ($1, $2, 'admin', $3, 'admin', TRUE)
               ON CONFLICT (username) DO UPDATE
               SET email = EXCLUDED.email,
                   access_key = EXCLUDED.access_key,
                   permission_key = EXCLUDED.permission_key,
                   is_active = TRUE,
                   deleted_at = NULL;""",
            "admin", "admin@clinical.local", settings.DEFAULT_ACCESS_KEY
        )
        await conn.execute(
            """INSERT INTO users (username, email, role, access_key, permission_key, is_active)
               VALUES ($1, $2, 'medico', $3, 'medico', TRUE)
               ON CONFLICT (username) DO UPDATE
               SET email = EXCLUDED.email,
                   access_key = EXCLUDED.access_key,
                   permission_key = EXCLUDED.permission_key,
                   is_active = TRUE,
                   deleted_at = NULL;""",
            "dr_garcia", "dr.garcia@clinical.local", settings.DEFAULT_MEDICO_ACCESS_KEY_1
        )
        await conn.execute(
            """INSERT INTO users (username, email, role, access_key, permission_key, is_active)
               VALUES ($1, $2, 'medico', $3, 'medico', TRUE)
               ON CONFLICT (username) DO UPDATE
               SET email = EXCLUDED.email,
                   access_key = EXCLUDED.access_key,
                   permission_key = EXCLUDED.permission_key,
                   is_active = TRUE,
                   deleted_at = NULL;""",
            "dr_lopez", "dr.lopez@clinical.local", settings.DEFAULT_MEDICO_ACCESS_KEY_2
        )
        await conn.execute(
            """INSERT INTO users (username, email, role, access_key, permission_key, is_active)
               VALUES ($1, $2, 'paciente', $3, 'paciente', TRUE)
               ON CONFLICT (username) DO UPDATE
               SET email = EXCLUDED.email,
                   access_key = EXCLUDED.access_key,
                   permission_key = EXCLUDED.permission_key,
                   is_active = TRUE,
                   deleted_at = NULL;""",
            "paciente_001", "paciente001@clinical.local", settings.DEFAULT_PACIENTE_ACCESS_KEY_1
        )

        # Load full patient population from heart-disease dataset if DB is empty.
        await _seed_heart_patients_if_needed(conn)

        # Demo-friendly RBAC mapping:
        # - médicos can see all current patients
        # - paciente_001 is linked to one patient
        await conn.execute("""
            INSERT INTO user_patients (user_id, patient_id)
            SELECT u.id, p.id
            FROM users u
            CROSS JOIN patients p
            WHERE u.role = 'medico'
              AND u.deleted_at IS NULL
              AND p.deleted_at IS NULL
            ON CONFLICT (user_id, patient_id) DO NOTHING;
        """)

        await conn.execute("""
            INSERT INTO user_patients (user_id, patient_id)
            SELECT u.id, p.id
            FROM users u
            JOIN LATERAL (
                SELECT id
                FROM patients
                WHERE deleted_at IS NULL
                ORDER BY created_at ASC
                LIMIT 1
            ) p ON TRUE
            WHERE u.username = 'paciente_001'
              AND u.deleted_at IS NULL
            ON CONFLICT (user_id, patient_id) DO NOTHING;
        """)

        await conn.execute(
            """INSERT INTO alert_threshold_config (config_key, config_json)
               VALUES ('default', '{"critical": 0.8, "high": 0.6, "medium": 0.4}'::jsonb)
               ON CONFLICT (config_key) DO NOTHING;"""
        )
        logger.info("✅ Database schema initialized")

async def log_audit(pool, user_id, role, action, resource_type, resource_id, ip_address, result, detail=None):
    """INSERT-ONLY audit log entry (never updated or deleted)"""
    try:
        rid = None
        if resource_id:
            try:
                rid = UUID(str(resource_id))
            except Exception:
                rid = None
        await pool.execute(
            """INSERT INTO audit_log (user_id, role, action, resource_type, resource_id, ip_address, result, detail)
               VALUES ($1, $2, $3, $4, $5, $6::inet, $7, $8::jsonb)""",
            UUID(str(user_id)) if user_id else None, role, action, resource_type,
            rid, ip_address, result,
            json.dumps(detail) if detail else None
        )
    except Exception as exc:
        logger.warning(f"audit_log write failed: {exc}")


async def close_db():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("🔌 Connection pool closed")
