# Paquete de Sustentacion - Corte 2

Fecha: 2026-04-21

## Objetivo
Este documento organiza la evidencia principal del proyecto para sustentacion ante jurado. Su funcion es permitir una revision rapida, mostrando que criterio se demuestra, con que endpoint, en que archivo y en que componente del sistema.

## Evidencias base del cierre

### 1. Reporte final de validacion
- Archivo: `REPORTE_VALIDACION_FINAL.md`
- Funcion: consolidar el estado final del sistema y el cumplimiento tecnico del corte.
- Contiene:
  - checklist de criterios cumplidos
  - validacion de DL por imagen
  - validacion de DiagnosticReport
  - validacion de WebSocket
  - validacion de persistencia en orquestador
  - observacion del 502 transitorio ya resuelto

### 2. Evidencia formal de concurrencia
- Archivo: `EVIDENCIA_CONCURRENCIA.md`
- Funcion: demostrar la concurrencia minima solicitada para inferencias.
- Resultado clave:
  - 4 solicitudes simultaneas
  - DONE=4
  - factor de solapamiento: 1.4

### 3. Documentacion tecnica ampliada
- Archivo: `DOCUMENTACION_MINIPROYECTO2.md`
- Funcion: describir la arquitectura, carpetas, archivos y cumplimiento general de la rubrica.

## Trazabilidad criterio -> evidencia

| Criterio evaluable | Evidencia principal | Endpoint o flujo | Archivos clave |
|---|---|---|---|
| Autenticacion por doble llave | Login y verify con `access_key` + `permission_key` | `POST /auth/login`, `GET /auth/verify` | `backend/routers/auth.py`, `backend/main.py` |
| RBAC y administracion | Restricciones admin/medico/paciente | `/admin/*`, `/admin/users/*` | `backend/routers/admin.py`, `backend/routers/admin_users.py` |
| Interoperabilidad HL7 FHIR | Recursos Patient, Observation, RiskAssessment, DiagnosticReport, AuditEvent, Consent | `/fhir/*` | `backend/routers/fhir.py` |
| Persistencia clinica | Tablas de usuarios, pacientes, reportes, cola y auditoria | Inicializacion de esquema | `backend/db.py` |
| Inferencia ML tabular | Riesgo, categoria y explicabilidad tipo SHAP | `POST /predict` en ML service | `ml-service/main.py` |
| Inferencia DL por imagen | Prediccion, artifacto Grad-CAM-like y payload DiagnosticReport | `POST /predict`, `POST /predict-image` en DL service | `dl-service/main.py` |
| Orquestacion asincrona | Cola, estados, persistencia y multiplexacion de modelos | `POST /infer`, `GET /infer/{task_id}` | `orchestrator/main.py` |
| WebSocket de inferencia | Streaming de estados hasta DONE o ERROR | `GET ws /infer/ws/{task_id}` | `orchestrator/main.py` |
| Proxy y acceso unificado | Exposicion via gateway y proteccion de rutas | `http://localhost/*` | `nginx/nginx.conf`, `docker-compose.yml` |
| Concurrencia >= 4 | 4 solicitudes simultaneas exitosas | `http://localhost:8002/infer` | `EVIDENCIA_CONCURRENCIA.md`, `orchestrator/main.py` |

## Endpoints recomendados para demo en vivo

### Flujo 1. Autenticacion
- `POST /auth/login`
- `GET /auth/verify`

### Flujo 2. Consulta clinica FHIR
- `GET /fhir/Patient?limit=10&offset=0`
- `GET /fhir/Patient/{id}`
- `GET /fhir/Observation?subject=Patient/{id}`

### Flujo 3. Inferencia asincrona
- `POST /infer`
- `GET /infer/{task_id}`
- `GET ws /infer/ws/{task_id}`

### Flujo 4. Evidencia de resultado clinico
- `POST /fhir/RiskAssessment`
- `PATCH /fhir/RiskAssessment/{id}/sign`
- `GET /fhir/RiskAssessment/{patient_id}/can-close`

### Flujo 5. DiagnosticReport y evidencia DL
- `POST /predict-image`
- `POST /fhir/DiagnosticReport`
- `GET /fhir/DiagnosticReport?patient_id={id}`

## Archivos que conviene tener abiertos durante la sustentacion
- `REPORTE_VALIDACION_FINAL.md`
- `EVIDENCIA_CONCURRENCIA.md`
- `backend/routers/fhir.py`
- `orchestrator/main.py`
- `dl-service/main.py`
- `nginx/nginx.conf`
- `docker-compose.yml`

## Orden sugerido de sustentacion
1. Mostrar arquitectura general y servicios en `docker-compose.yml`.
2. Mostrar autenticacion por doble llave y roles en backend.
3. Mostrar recursos FHIR y flujo clinico.
4. Mostrar inferencia ML, DL y multimodal.
5. Mostrar cola asincrona, persistencia y WebSocket del orquestador.
6. Cerrar con `REPORTE_VALIDACION_FINAL.md` y `EVIDENCIA_CONCURRENCIA.md`.

## Mensaje corto para el jurado
El proyecto cumple los criterios tecnicos de Corte 2 en autenticacion, interoperabilidad FHIR, inferencia ML/DL, explicabilidad, orquestacion asincrona, persistencia y concurrencia. La evidencia de cierre esta consolidada en los archivos `REPORTE_VALIDACION_FINAL.md` y `EVIDENCIA_CONCURRENCIA.md`.