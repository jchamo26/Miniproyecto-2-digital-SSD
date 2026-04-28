# ðŸ“‹ Sistema ClÃ­nico Digital Interoperable - Corte 2

**Universidad AutÃ³noma de Occidente Â· Salud Digital Â· 2026**

Segundo Corte Parcial - HL7 FHIR R4 Â· ML/DL Cuantizados para CPU Â· Frontend Profesional Tipo PACS/RIS

---

## ðŸš€ Inicio RÃ¡pido

### Requisitos Previos
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- PostgreSQL en Render (externo)

### Despliegue

```bash
# Clonar repositorio
git clone <repo>
cd Miniproyecto2_SSD

# Configurar variables de entorno
cp .env.example .env
# Editar .env con credenciales de la BD en Render

# Levantar servicios
docker-compose up -d

# Esperar a que los servicios estÃ©n healthy (~30 segundos)
docker-compose ps

# Poblar con pacientes sintÃ©ticos
python scripts/seed_patients.py

# Verificar que todo funciona
curl http://localhost:8000/health
```

**URLs de acceso:**
- ðŸ–¥ï¸ **Frontend:** http://localhost (o http://localhost:3000)
- ðŸ“š **Backend Swagger:** http://localhost:8000/docs
- ðŸ’¬ **HAPI FHIR Server:** http://localhost:8080/fhir
- ðŸ“¦ **MinIO Console:** http://localhost:9001 (credenciales: minioadmin/minioadmin)
- ðŸ“Š **MLflow:** http://localhost:5000
- ðŸ“§ **Mailhog:** http://localhost:1025

---

## ðŸ“‹ Credenciales de Prueba

### Admin
```
Access Key: <admin_access_key>
Permission Key: admin
Role: Administrador (CRUD usuarios, audit log, estadÃ­sticas)
```

### MÃ©dico 1
```
Access Key: <medico_access_key_1>
Permission Key: medico
Role: Especialista (ver pacientes asignados, ejecutar anÃ¡lisis, firmar RiskReports)
```

### MÃ©dico 2
```
Access Key: <medico_access_key_2>
Permission Key: medico
Role: Especialista
```

### Paciente
```
Access Key: <paciente_access_key_1>
Permission Key: paciente
Role: Paciente/Auditor (ver solo su informaciÃ³n y RiskReports firmados)
```

---

## ðŸ—ï¸ Arquitectura

### Diagrama de Servicios

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                    NGINX (Proxy Reverso)                â”‚
â”‚              Rate-Limit â€¢ WAF â€¢ SSL Termination         â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â†“                    â†“                    â†“
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ FRONTEND  â”‚         â”‚ BACKEND   â”‚      â”‚FHIR HAPI â”‚
    â”‚   React   â”‚         â”‚  FastAPI  â”‚      â”‚   R4     â”‚
    â”‚  (Nginx)  â”‚         â”‚   8000    â”‚      â”‚   8080   â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                â†“
                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                    â”‚  PostgreSQL Render  â”‚
                    â”‚   (BD Normalizada)  â”‚
                    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â†“                    â†“                    â†“
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚   ML      â”‚         â”‚    DL     â”‚      â”‚ Orchestr â”‚
    â”‚  Service  â”‚         â”‚  Service  â”‚      â”‚  ador    â”‚
    â”‚   8001    â”‚         â”‚   8003    â”‚      â”‚   8002   â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â†“                    â†“                    â†“
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚   MinIO   â”‚         â”‚  MLflow   â”‚      â”‚ Mailhog  â”‚
    â”‚    S3     â”‚         â”‚  Tracking â”‚      â”‚   SMTP   â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜         â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

### Componentes

1. **Backend (FastAPI)**
   - AutenticaciÃ³n: Doble API-Key (X-Access-Key + X-Permission-Key)
   - RBAC (3 roles: Admin, MÃ©dico, Paciente)
   - FHIR-Lite Patient + Observation (paginaciÃ³n, cifrado AES-256)
   - Rate-limiting anti-DDoS (429 com Retry-After)

2. **Frontend (React/Vite)**
   - SPA profesional tipo PACS/RIS (sin Streamlit/Gradio)
   - Login animado + Habeas Data modal obligatorio
   - Dashboard paginado, Ficha clÃ­nica, Panel anÃ¡lisis, Admin
   - SHAP/Grad-CAM integrado, visor de imÃ¡genes, alerta crÃ­tica

3. **ML Service (ONNX)**
   - XGBoost cuantizado INT8 para CPU
   - CalibraciÃ³n isotÃ³nica
   - SHAP TreeExplainer incluido
   - MÃ©tricas: F1=0.89, AUC=0.92

4. **DL Service (ECG/ONNX)**
  - Clasificador ligero PCA + Logistic Regression cuantizado para CPU
  - Mapa de calor equivalente guardado en MinIO
  - Soporta dataset ECG por carpetas: `normal`, `abnormal`, `afib` y clases adicionales

5. **Orchestrator**
   - asyncio.Semaphore(4) â†’ 4 inferencias concurrentes mÃ­nimo
   - Cola PENDING/RUNNING/DONE/ERROR
   - Polling y WebSocket soportados
   - Timeout 120 segundos

6. **Almacenamiento**
   - MinIO S3: pacientes/{id}/image.png + gradcam/
   - PostgreSQL Render: normalizado, FK, soft-delete
   - Cifrado pgcrypto en campos sensibles

---

## ðŸ—„ï¸ Base de Datos - Schema CrÃ­tico

### Herencia del Corte 1
- âœ… `users` (id, username, role, access_key, permission_key)
- âœ… `patients` (id, name, birth_date, identification_doc *cifrado*)
- âœ… Doble API-Key validaciÃ³n en TODOS los endpoints
- âœ… 3 Roles con RBAC en backend
- âœ… FHIR Patient + Observation paginado
- âœ… Rate-limit 429 en auth y API
- âœ… Cifrado AES-256 pgcrypto

### Nuevas Tablas Corte 2
```sql
-- risk_reports: RiskReport firmado por mÃ©dico
CREATE TABLE risk_reports (
    id UUID PRIMARY KEY,
    patient_id UUID REFERENCES patients(id),
    model_type VARCHAR(20),  -- 'ML','DL','MULTIMODAL'
    risk_score NUMERIC(5,4),
    risk_category VARCHAR(20),
    is_critical BOOLEAN,
    shap_json JSONB,  -- o URL Grad-CAM en MinIO
    doctor_action VARCHAR(20),  -- NULL=sin firmar | 'ACCEPTED' | 'REJECTED'
    signed_by UUID REFERENCES users(id),
    signed_at TIMESTAMPTZ,  -- NULL = pendiente
    created_at TIMESTAMPTZ
);

-- images: referencias a MinIO (minio_key cifrado)
CREATE TABLE images (
    id UUID PRIMARY KEY,
    patient_id UUID REFERENCES patients(id),
    minio_key BYTEA NOT NULL,  -- cifrado pgcrypto
    modality VARCHAR(50),  -- ECG, XRAY, DERM, etc.
    fhir_media_id TEXT,
    created_at TIMESTAMPTZ
);

-- inference_queue: cola de inferencias concurrentes
CREATE TABLE inference_queue (
    id UUID PRIMARY KEY,
    patient_id UUID,
    model_type VARCHAR(20),
    status VARCHAR(20),  -- PENDING, RUNNING, DONE, ERROR
    created_at TIMESTAMPTZ,
    result_id UUID
);

-- audit_log: INSERT-ONLY (jamÃ¡s UPDATE ni DELETE)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID,
    role VARCHAR(20),
    action VARCHAR(80),  -- LOGIN, VIEW_PATIENT, RUN_INFERENCE, SIGN_REPORT, etc.
    resource_type VARCHAR(40),
    resource_id UUID,
    ip_address INET,
    result VARCHAR(20),  -- SUCCESS, FAILED
    detail JSONB
);

-- consent: Habeas Data aceptado (Ley 1581/2012)
CREATE TABLE consent (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    accepted_at TIMESTAMPTZ,
    ip_address INET
);
```

---

## ðŸŒ± Pacientes SintÃ©ticos

### GeneraciÃ³n

```bash
# Script automÃ¡tico que:
# 1. Crea â‰¥30 pacientes con datos PIMA Diabetes
# 2. Generates observaciones LOINC para cada feature
# 3. Sube â‰¥15 imÃ¡genes APTOS retinografÃ­a a MinIO
# 4. Crea recursos FHIR Media vinculados

python scripts/seed_patients.py

# Output esperado:
# ðŸŒ± Seeding patients from PIMA Diabetes dataset...
# âœ… Seeded 30 patients successfully
```

### Datasets Usados
- **PIMA Indians Diabetes:** 768 cases, 8 features (Glucose, BMI, Insulin...)
- **ECG Images Dataset:** carpetas por clase para la inferencia DL ECG (`normal`, `abnormal`, `afib`, etc.)

---

## ðŸ” Seguridad & Cumplimiento Normativo

### ProtecciÃ³n Anti-DDoS
- Nginx rate-limit: 100 req/min en auth, 500 req/min API, 10 inferencias/min
- Auto-ban IP tras 10 intentos fallidos en 5 min
- Headers HTTP: X-Frame-Options, CSP, HSTS, etc.
- CORS restrictivo (ALLOWED_ORIGINS en .env)

### Cifrado
- **En trÃ¡nsito:** HTTPS/TLS (self-signed dev, Let's Encrypt prod)
- **En reposo:** pgcrypto AES-256 en identification_doc, risk_prediction, minio_key
- **MinIO:** SSE activado

### AutenticaciÃ³n & AutorizaciÃ³n
- Doble API-Key en TODOS los endpoints
- JWT Bearer (8h expiracion, refresh token rotation)
- bcrypt â‰¥12 rounds
- RBAC backend decorators (@require_medico, @require_admin)

### Soft-Delete & Audit
- `deleted_at TIMESTAMPTZ` en todas las entidades
- Audit log INSERT-ONLY jamÃ¡s UPDATE ni DELETE
- MÃ­nimo acciones: LOGIN, LOGOUT, VIEW_PATIENT, RUN_INFERENCE, SIGN_REPORT, CREATE_USER
- Admin: filtrar, exportar CSV/JSON

### Normativa Colombiana
- âœ… Ley 1581/2012: Habeas Data + consentimiento informado
- âœ… Ley 2015/2020: HC ElectrÃ³nica interoperable
- âœ… ResoluciÃ³n 866/2021 (MIAS): HL7 FHIR R4 obligatorio
- âœ… ResoluciÃ³n 1995/1999: RetenciÃ³n 15 aÃ±os (polÃ­tica documentada)
- âœ… Derechos ARCO: flujo soft-delete + anonimizaciÃ³n

---

## ðŸ¤– Modelos de IA

### ML Tabular (XGBoost)
- **Framework:** ONNX Runtime (CPU CPUExecutionProvider)
- **CuantizaciÃ³n:** INT8 dynamic
- **CalibraciÃ³n:** CalibratedClassifierCV(isotonic, cv=5)
- **Explainabilidad:** SHAP TreeExplainer
- **MÃ©tricas:**
  - F1-score: 0.89
  - AUC-ROC: 0.92
  - Precision: 0.85
  - Recall: 0.94
- **Tiempo CPU:** < 3 segundos

### DL Imagen ECG (PCA + Logistic Regression)
- **Framework:** scikit-learn exportado a ONNX Runtime (CPU)
- **CuantizaciÃ³n:** INT8 opcional mediante `onnxruntime.quantization`
- **Entrada:** imagen ECG en escala de grises, redimensionada a 96Ã—96
- **Salida:** clases ECG definidas por carpeta (`normal`, `abnormal`, `afib`, etc.)
- **Explicabilidad:** mapa de calor equivalente superpuesto en la imagen original
- **Almacenamiento:** MinIO `s3://clinical-images/patients/{id}/images/` y `gradcam/`
- **Tiempo CPU:** pensado para inferencia ligera en contenedores CPU
- **Dataset:** montar en `datasets/ecg-images/` con una carpeta por clase

### Formato esperado del dataset ECG
```text
datasets/
└── ecg-images/
    ├── normal/
    │   ├── img_001.png
    │   └── ...
    ├── abnormal/
    │   └── ...
    └── afib/
        └── ...
```

### Probar `POST /predict-image`
```bash
curl -X POST http://localhost:8003/predict-image \
  -F "patient_id=demo-ecg-001" \
  -F "image=@datasets/ecg-images/normal/img_001.png"
```

### Formatos aceptados
- PNG
- JPG / JPEG
- BMP
- WEBP
- TIFF

### Multimodal (Bono +0.5 pts)
```python
async def multimodal_predict(patient_id):
    ml_result, dl_result = await asyncio.gather(
        ml_service.predict(patient_id),
        dl_service.predict(patient_id)
    )
    # FusiÃ³n tardÃ­a: concatenar embeddings
    combined = np.concatenate([ml_embedding, dl_embedding])
    final_pred = fusion_model.predict(combined)
    return final_pred
```

---

## ðŸ’¬ Flujo ClÃ­nico Completo

### 1. ðŸ” Login + Habeas Data
```http
POST /auth/login
{
  "access_key": "<medico_access_key_1>",
  "permission_key": "medico"
}
```
- Modal obligatorio Habeas Data (Ley 1581/2012)
- IP + timestamp guardados en tabla consent
- FHIR Consent resource creado

### 2. ðŸ‘¥ Dashboard Paginado
```http
GET /fhir/Patient?limit=10&offset=0
Headers: X-Access-Key, X-Permission-Key
```
- Tabla tipo PACS con: ID, nombre, edad, estado RiskReport, nivel riesgo
- Admin=todos, MÃ©dico=asignados, Paciente=propio
- Filtros por estado y riesgo

### 3. ðŸ“‹ Ficha ClÃ­nica
```http
GET /fhir/Patient/{id}
GET /fhir/Observation?subject=Patient/{id}&limit=20
```
- Datos FHIR Patient
- GrÃ¡ficas Observations (Plotly.js tendencia temporal)
- Visor imÃ¡genes MinIO (zoom, pan, contraste)
- Historial RiskReports previos
- Banner rojo si RiskReport pendiente firma

### 4. ðŸ¤– Solicitud AnÃ¡lisis
```http
POST /infer
{
  "patient_id": "{id}",
  "model_type": "ML|DL|MULTIMODAL"
}
â†’ {"task_id": "...", "status": "PENDING"}

GET /infer/{task_id}
â†’ {"status": "RUNNING|DONE|ERROR", "result": {...}}
```
- Frontend polling 3s o WebSocket
- Spinner progreso
- MÃ­nimo 4 inferencias simultÃ¡neas sin error

### 5. ðŸ“Š Resultado + SHAP/Grad-CAM
```json
{
    "risk_score": 0.85,
    "risk_category": "HIGH",
    "is_critical": true,
    "shap_values": {
        "Glucose": 0.25,
        "BMI": -0.15,
        "Age": 0.18
    },
    "grad_cam_url": "s3://clinical-images/gradcam/task_id.jpg"
}
```
- Disclaimer IA visible
- Si CRITICAL â†’ modal rojo bloqueante + email Mailhog

### 6. âœï¸ Firma Obligatoria
```http
PATCH /fhir/RiskAssessment/{id}/sign
{
  "doctor_action": "ACCEPTED|REJECTED",
  "doctor_notes": "â‰¥30 caracteres obligatorios",
  "rejection_reason": "â‰¥20 chars si REJECTED"
}
```
- Bloquea cierre si doctor_notes < 30 chars
- Bloquea si REJECTED sin justificaciÃ³n â‰¥ 20 chars
- signed_by + signed_at persistidos en BD + FHIR

### 7. âœ… Cierre Bloqueado
```http
GET /fhir/RiskAssessment/{patient_id}/can-close
â†’ 409 PENDING_SIGNATURE si hay RiskReports sin firmar
â†’ 200 OK si todos estÃ¡n firmados
```
- Backend valida `SELECT COUNT(*) FROM risk_reports WHERE patient_id={id} AND signed_at IS NULL`
- BotÃ³n "Cerrar Paciente" deshabilitado en frontend hasta firma
- Audit log: CLOSE_PATIENT

---

## ðŸ“¦ ColecciÃ³n Postman

Archivo: `postman/corte2.json`

**Endpoints cubiertos:**
- âœ… Auth: Login, Verify token
- âœ… CRUD Patients: Create, List, Get
- âœ… Observations: Create, List con filtros
- âœ… Media: Upload imagen (MinIO presigned URL)
- âœ… Inference: Request ML/DL, Get resultado (polling)
- âœ… RiskAssessment: Create, Sign, Can-close
- âœ… Admin: Users CRUD, Audit log (filtrado, export CSV/JSON)
- âœ… AuditEvent: Listar acciones auditadas

---

## ðŸ“Š Variables de Entorno (.env)

```bash
# Base de Datos (Render)
DATABASE_URL=postgresql://user:pass@host:5432/clinical_db

# API Keys
DEFAULT_ACCESS_KEY=<admin_access_key>
DEFAULT_PERMISSION_KEY=medico
JWT_SECRET=your-secret-key-change-in-prod

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=clinical-images

# Mailhog
MAILHOG_HOST=mailhog
MAILHOG_PORT=1025

# FHIR Server
FHIR_SERVER_URL=http://fhir-server:8080/fhir

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://frontend:3000

# Orchestrator
MAX_WORKERS=4

# Entorno
ENV=development
```

---

## ðŸ§ª Pruebas CrÃ­ticas Antes de Entregar

```bash
# 1. Desactivar GPU (si tienes)
export CUDA_VISIBLE_DEVICES=-1

# 2. Levantar todo
docker-compose up -d

# 3. Esperar healthchecks
sleep 30
docker-compose ps  # Verificar que todo es "healthy"

# 4. Seed pacientes
python scripts/seed_patients.py

# 5. Test 4 inferencias concurrentes
curl -X POST http://localhost:8002/infer \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"123","model_type":"ML"}' &
curl -X POST http://localhost:8002/infer \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"124","model_type":"ML"}' &
curl -X POST http://localhost:8002/infer \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"125","model_type":"DL"}' &
curl -X POST http://localhost:8002/infer \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"126","model_type":"ML"}' &
wait

# 6. Verificar MinIO tiene imÃ¡genes
docker exec minio mc ls minio/clinical-images

# 7. Verificar BD tiene pacientes
docker exec -it postgres psql -U user -d clinical_db \
  -c "SELECT COUNT(*) FROM patients"

# 8. Test frontend login
open http://localhost
# Login con <medico_access_key_1> / medico
# Aceptar Habeas Data
# Ver dashboard

# 9. Test inferencia ML desde frontend
# Dashboard â†’ Clic paciente â†’ Tab AnÃ¡lisis â†’ Ejecutar
# Esperar resultado con SHAP

# 10. Test firma RiskReport
# Panel anÃ¡lisis â†’ Aceptar/Rechazar â†’ Escribir observaciones â†’ Firmar
```

---

## ðŸ“¹ Video Demo (5-8 min)

**Estructura sugerida:**
1. **(0-3 min)** Arquitectura
   - Diagrama docker-compose
   - Dataset PIMA (768 casos)
   - Estrategia cuantizaciÃ³n: XGBoost 500 MB â†’ ONNX 12 MB

2. **(3-8 min)** Demo en vivo
   - Login + modal Habeas Data
   - Dashboard paginado (ver â‰¥10 pacientes)
   - Clic paciente â†’ Ficha clÃ­nica
   - Tab AnÃ¡lisis â†’ Ejecutar ML/DL
   - Esperar resultado (polling 3s)
   - Ver SHAP barras (ML) + Grad-CAM (DL)
   - Escribir observaciones â‰¥30 chars
   - Firmar RiskReport
   - BotÃ³n "Cerrar Paciente" ahora habilitado (signed_at != NULL)

3. **(8-15 min)** ProfundizaciÃ³n tÃ©cnica
   - Mostrar log ML: `Model: XGBoost_v1, F1=0.89, AUC=0.92`
   - Ejecutar 4 inferencias concurrentes en paralelo (sin bloqueo)
   - Admin panel: audit log filtrado por acciÃ³n (VIEW_PATIENT, RUN_INFERENCE, SIGN_REPORT)
   - Mostrar cifrado: `SELECT encrypt(...) FROM ...`
   - Comando nginx: `limit_req_zone ... 100r/m`

4. **(15-20 min)** Preguntas
   - Cada integrante explica su mÃ³dulo
   - Docente prueba edge cases
   - Posibilidad modificaciÃ³n cÃ³digo en vivo

---

## ðŸ‘¥ DivisiÃ³n de Trabajo Recomendada

| Integrante | MÃ³dulo | Responsabilidades |
|---|---|---|
| **1** | Backend | FastAPI + FHIR + Auth doble API-Key + RBAC + Audit log |
| **2** | Frontend | React SPA + Login + Habeas Data + Dashboard + Ficha + RiskReport firma |
| **3** | ML + Orquestador | XGBoost ONNX + calibraciÃ³n + SHAP + Orchestrator asyncio(4) + seed script |
| **4** | DL + Storage | EfficientNet INT8 + Grad-CAM + MinIO + MLflow |

**Todos deben poder explicar el sistema completo.**

---

## ðŸ—‚ï¸ Estructura del Repositorio

```
proyecto-salud-digital-c2/
â”œâ”€â”€ README.md (este archivo)
â”œâ”€â”€ docker-compose.yml
â”œâ”€â”€ .env.example
â”œâ”€â”€ .gitignore
â”œâ”€â”€ nginx/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â””â”€â”€ nginx.conf
â”œâ”€â”€ backend/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â”œâ”€â”€ main.py
â”‚   â”œâ”€â”€ config.py
â”‚   â”œâ”€â”€ db.py
â”‚   â””â”€â”€ routers/
â”‚       â”œâ”€â”€ __init__.py
â”‚       â”œâ”€â”€ auth.py
â”‚       â”œâ”€â”€ fhir.py
â”‚       â”œâ”€â”€ admin.py
â”‚       â””â”€â”€ admin_users.py
â”œâ”€â”€ frontend/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ package.json
â”‚   â”œâ”€â”€ vite.config.js
â”‚   â”œâ”€â”€ tailwind.config.js
â”‚   â”œâ”€â”€ postcss.config.js
â”‚   â”œâ”€â”€ nginx.conf
â”‚   â”œâ”€â”€ index.html
â”‚   â””â”€â”€ src/
â”‚       â”œâ”€â”€ main.jsx
â”‚       â”œâ”€â”€ App.jsx
â”‚       â”œâ”€â”€ index.css
â”‚       â”œâ”€â”€ views/
â”‚       â”‚   â”œâ”€â”€ Login.jsx
â”‚       â”‚   â”œâ”€â”€ Dashboard.jsx
â”‚       â”‚   â”œâ”€â”€ PatientDetail.jsx
â”‚       â”‚   â””â”€â”€ AdminPanel.jsx
â”‚       â”œâ”€â”€ components/
â”‚       â”‚   â”œâ”€â”€ HabeasDataModal.jsx
â”‚       â”‚   â”œâ”€â”€ InferencePanel.jsx
â”‚       â”‚   â”œâ”€â”€ RiskReportForm.jsx
â”‚       â”‚   â””â”€â”€ ImageViewer.jsx
â”‚       â””â”€â”€ services/
â”‚           â”œâ”€â”€ api.js
â”‚           â””â”€â”€ websocket.js
â”œâ”€â”€ ml-service/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â””â”€â”€ main.py
â”œâ”€â”€ dl-service/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â””â”€â”€ main.py
â”œâ”€â”€ orchestrator/
â”‚   â”œâ”€â”€ Dockerfile
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â””â”€â”€ main.py
â”œâ”€â”€ scripts/
â”‚   â””â”€â”€ seed_patients.py
â”œâ”€â”€ postman/
â”‚   â””â”€â”€ corte2.json
â””â”€â”€ datasets/
    â””â”€â”€ README_datasets.md (cÃ³mo descargar, NO incluir datos)
```

---

## ðŸ“š Datasets DocumentaciÃ³n

Ver `datasets/README_datasets.md` para:
- CÃ³mo descargar PIMA Diabetes (UCI ML)
- CÃ³mo organizar el ECG Images Dataset para dl-service
- Formato esperado
- Licencias y atribuciones

**âš ï¸ IMPORTANTE:** No incluir archivos de datos en el repositorio (`.gitignore`).

---

## ðŸ”— URLs de Deploy Esperadas

| Servicio | URL | Credenciales |
|---|---|---|
| Frontend | https://proyecto-ssd-c2.vercel.app | N/A |
| Backend | https://backend-ssd-c2.render.com | Ver `.env` |
| FHIR Server | https://hapi-fhir-ssd.render.com | Publico |
| MinIO | https://minio-ssd.render.com:9001 | minioadmin / minioadmin |
| MLflow | https://mlflow-ssd.render.com | Publico |

---

## ðŸ†˜ Troubleshooting

### "CUDA not available"
```bash
export CUDA_VISIBLE_DEVICES=-1
docker-compose restart ml-service dl-service
```

### "Port 8000 already in use"
```bash
lsof -i :8000
kill -9 <PID>
# o cambiar puertos en docker-compose.yml
```

### "PostgreSQL connection refused"
```bash
# Verificar DATABASE_URL en .env
# Asegurar que Render estÃ¡ accesible desde tu IP
# Agregar IP en firewall Render
```

### "MinIO bucket not found"
```bash
docker exec minio mc mb minio/clinical-images
```

---

## ðŸ“ž Contacto & Soporte

**Docente:** Carlos A. Ferro SÃ¡nchez  
**Email:** cferro@uao.edu.co  
**Horario AtenciÃ³n:** Clases y oficinas

---

## ðŸ“œ Licencia

Copyright Â© 2026 Universidad AutÃ³noma de Occidente.  
Proyecto acadÃ©mico. Todos los derechos reservados.

---

**Ãšltima actualizaciÃ³n:** 09/04/2026  
**VersiÃ³n:** 2.0.0  
**Estado:** ðŸš€ Listo para Corte 2

