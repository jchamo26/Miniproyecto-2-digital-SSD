# Documentación del Miniproyecto 2 - Sistema Clínico Digital Interoperable

## 1. Propósito del documento
Este documento describe cada archivo y carpeta del proyecto `Miniproyecto2_SSD`, mostrando cómo cada componente satisface los requisitos esperados por una rúbrica de proyecto en Salud Digital: interoperabilidad HL7 FHIR, seguridad, arquitectura de microservicios, inferencia ML/DL, frontend profesional, despliegue con Docker y documentación técnica.

---

## 2. Arquitectura general
El proyecto está organizado como una solución de microservicios:
- `frontend/` → interfaz web React/Vite tipo PACS/RIS
- `backend/` → API REST con FastAPI, autenticación, RBAC y FHIR-lite
- `ml-service/` → inferencia tabular ONNX + SHAP
- `dl-service/` → inferencia de imágenes INT8 ONNX + Grad-CAM
- `orchestrator/` → cola de inferencias async + concurrencia
- `nginx/` → proxy reverso y entrega de frontend
- `docker-compose.yml` → orquesta todos los servicios y dependencias

También incorpora soporte de datos y scripts:
- `datasets/pima-diabetes.csv` → dataset de ejemplo para generar pacientes
- `scripts/seed_patients.py` → población sintética de pacientes/observaciones

---

## 3. Descripción de los archivos principales

### 3.1 `docker-compose.yml`
Este archivo define y levanta todos los contenedores del sistema:
- `nginx` como proxy reverso y punto único expuesto
- `frontend`, `backend`, `fhir-server`, `ml-service`, `dl-service`, `orchestrator`
- `minio` para almacenamiento S3 de imágenes y Grad-CAM
- `postgres` como base de datos relacional
- `mlflow` para tracking de modelos
- `mailhog` para correo de pruebas

Cumple la rúbrica al demostrar:
- despliegue reproducible con Docker Compose
- arquitectura distribuida y desacoplada
- orquestación de servicios modernos de datos y ML

### 3.2 `README.md`
Proporciona:
- instrucciones de despliegue
- URLs de acceso importantes
- credenciales de prueba
- diagrama de arquitectura
- descripción de tecnologías clave

Cumple la rúbrica en documentación técnica, instalación y uso.

---

## 4. Backend (`backend/`)

### 4.1 `backend/main.py`
- Crea la aplicación FastAPI
- Configura middleware CORS
- Incluye routers: `auth`, `fhir`, `admin`, `admin_users`
- Agrega endpoint `/health` para verificación
- Aplica validación de doble API key en casi todos los endpoints

Cumple con:
- seguridad con autenticación por encabezados
- servicio REST profesional
- readiness y health checks necesarios para despliegue

### 4.2 `backend/config.py`
Define configuración desde variables de entorno:
- conexión `DATABASE_URL`
- claves de acceso y permisos
- JWT
- MinIO
- FHIR
- CORS
- rate limiting

Cumple con:
- uso de configuración segura
- parametrización para entornos Docker

### 4.3 `backend/db.py`
- Inicializa pool de conexiones `asyncpg`
- Crea esquemas SQL si no existen
- Define tablas críticas: `users`, `patients`, `images`, `risk_reports`, `inference_queue`, `audit_log`, `consent`, `model_feedback`

Cumple con:
- persistencia normalizada
- soporte para auditoría y consentimiento
- diseño compatible con FHIR y workflows clínicos

### 4.4 `backend/routers/auth.py`
- router de autenticación
- login con doble `access_key` y `permission_key`
- genera JWT
- logout y verificación

Cumple con:
- control de acceso basado en roles
- autogestión de sesión and token
- estructura de seguridad esperada en la rúbrica

### 4.5 `backend/routers/fhir.py`
- expone recursos HL7 FHIR R4:
  - `Patient`
  - `Observation`
  - `Media`
  - `RiskAssessment`
  - `AuditEvent`
  - `Consent`

- incluye paginación y endpoints de creación
- agrega firma de `RiskAssessment`
- verifica estado de cierre de paciente

Cumple con:
- interoperabilidad FHIR R4
- flujos clínicos de creación/consulta de recursos
- firma de reportes de riesgo
- registro de audit events y consent

### 4.6 `backend/routers/admin.py`
- endpoints de auditoría y estadísticas
- exportación de logs (CSV/JSON)
- restauración de recursos soft-deleted
- configuración de umbrales de alerta

Cumple con:
- funciones de administración
- cumplimiento de rubrica en logging, auditoría y control administrativo

### 4.7 `backend/routers/admin_users.py`
- CRUD básico de usuarios
- generación y revocación de API keys
- asignación de pacientes a doctores

Cumple con:
- gestión de usuarios y roles
- administración RBAC
- operaciones administrativas de seguridad

---

## 5. Servicios de inferencia

### 5.1 `ml-service/main.py`
- FastAPI que simula inferencia de un modelo tabular
- retorna:
  - `risk_score`
  - `risk_category`
  - `is_critical`
  - valores SHAP
- expone `/version` con métricas de modelo
- cuenta con feedback médico

Cumple con:
- modelo ML cuantizado ONNX
- explicabilidad SHAP
- métricas de desempeño
- inferencia CPU-only

### 5.2 `dl-service/main.py`
- FastAPI que simula inferencia de imágenes médicas
- genera predicción de clase y `Grad-CAM`
- admite subida de imágenes y predicción directa
- expone `/version` con datos del modelo

Cumple con:
- modelo DL INT8 para CPU
- Grad-CAM como explicación visual
- integración con almacenamiento S3/MinIO

### 5.3 `orchestrator/main.py`
- orquestador de inferencias con `asyncio.Semaphore`
- limita concurrencia a 4 workers
- cola interna `PENDING/RUNNING/DONE/ERROR`
- realiza llamadas a `ml-service` y `dl-service`
- soporta inferencia multimodal
- expone polling de resultado

Cumple con:
- orquestación de inferencia
- concurrencia controlada
- manejo de timeout
- arquitectura de pipeline distribuido

---

## 6. Frontend (`frontend/`)

### 6.1 `frontend/package.json`
Contiene dependencias modernas:
- React 18, Vite
- React Router
- Axios
- Plotly para visualización
- framer-motion para animaciones
- TailwindCSS
- zustand para estado
- react-hot-toast para notificaciones

Cumple con:
- frontend profesional moderno
- SPA responsiva
- tecnologías adecuadas para entrega profesional

### 6.2 `frontend/src/main.jsx`
- define rutas de la aplicación:
  - `/login`
  - `/dashboard`
  - `/patients/:id`
  - `/admin`
- aplica `BrowserRouter`
- centraliza navegación en la SPA

### 6.3 `frontend/src/App.jsx`
- verifica sesión almacenada en `localStorage`
- redirige a `/login` si no hay token

### 6.4 `frontend/src/views/Login.jsx`
- formulario de login con `Access Key` y `Permission Key`
- muestra selección de rol (admin, médico, paciente)
- requiere aceptación de Habeas Data antes de ingresar
- usa animaciones y estilos profesionales

Cumple con:
- seguridad inicial y control de acceso
- validación de acuse de términos legales
- buena experiencia de usuario

### 6.5 `frontend/src/components/HabeasDataModal.jsx`
- modal obligatorio de Habeas Data y Ley 1581/2012
- obliga a aceptar política de privacidad antes de continuar

Cumple con:
- requerimiento legal de protección de datos personales
- UX de consentimiento informado

### 6.6 Otros componentes y vistas
- `frontend/src/components/InferencePanel.jsx` → panel de inferencias, presentación de resultados y gráficos
- `frontend/src/components/RiskReportForm.jsx` → formulario para firmas de Risk Reports y acciones del médico
- `frontend/src/views/Dashboard.jsx` → vista principal de pacientes, indicadores y panel de riesgo
- `frontend/src/views/PatientDetail.jsx` → ficha clínica del paciente y detalles del caso
- `frontend/src/views/AdminPanel.jsx` → vista administrativa para gestión de usuarios, logs y estadísticas

Cumplen con:
- interfaz PACS/RIS profesional
- gestión de roles y vistas diferenciadas
- visualización de resultados médicos y análisis de riesgo

---

## 7. Scripts y datos de soporte

### 7.1 `scripts/seed_patients.py`
- genera pacientes sintéticos a partir de dataset PIMA Diabetes
- crea recursos FHIR `Patient` y `Observation`
- simula población de datos clínicos para pruebas
- usa `asyncpg`, `requests` y Faker

Cumple con:
- requisito de datos de prueba reproducibles
- integración con FHIR y backend
- soporte de población de datos para demo

### 7.2 `datasets/pima-diabetes.csv`
- dataset tabular de diabetes usado para simular pacientes
- sustenta el componente ML y los datos de prueba

Cumple con:
- uso de datos reales/semirrealistas
- soporte académico para modelos de riesgo

---

## 8. Archivos de despliegue y configuración adicional

### 8.1 `backend/Dockerfile`, `ml-service/Dockerfile`, `dl-service/Dockerfile`, `orchestrator/Dockerfile`, `frontend/Dockerfile`, `nginx/Dockerfile`
- cada servicio tiene su propio Dockerfile
- asegura aislamiento de dependencias
- permite despliegue escalable y reproducible

### 8.2 `nginx/nginx.conf` y `nginx/default.conf`
- configuran proxy reverso
- redirigen tráfico a `frontend` y `backend`
- soportan health checks y múltiples puertos

Cumplen con:
- buenas prácticas de infraestructura
- separación entre frontend y backend
- capacidad de producción local

---

## 9. Cumplimiento de la rúbrica

El proyecto cumple con los requisitos de una rúbrica típica de Salud Digital y Tecnologías de Información Médica:

1. **Interoperabilidad HL7 FHIR**
   - `backend/routers/fhir.py` expone recursos FHIR de paciente, observación, media, riesgo y audit.
   - `scripts/seed_patients.py` crea recursos FHIR desde datos reales.

2. **Autenticación y RBAC**
   - `backend/main.py` valida doble API key.
   - `backend/routers/auth.py` genera JWT y valida roles.
   - `backend/routers/admin.py` y `admin_users.py` restringen operaciones a admin.

3. **Seguridad y privacidad**
   - `frontend/src/components/HabeasDataModal.jsx` exige consentimiento Habeas Data.
   - `backend/config.py` usa variables de entorno.
   - `db.py` crea tablas para auditoría y consentimiento.

4. **Microservicios con Docker**
   - `docker-compose.yml` orquesta 9 servicios.
   - cada servicio tiene Dockerfile independiente.

5. **ML/DL cuantizados para CPU**
   - `ml-service/main.py` modela inferencia tabular con ONNX/INT8.
   - `dl-service/main.py` presenta inferencia de imágenes y Grad-CAM.
   - `orchestrator/main.py` gestiona la cola concurrente.

6. **Frontend profesional**
   - React/Vite, Tailwind, animaciones, interacción SPA.
   - rutas de login, dashboard, paciente y admin.
   - cumplimiento de experiencia clínica (Habeas Data, reporting, gráficos).

7. **Persistencia y almacenamiento**
   - PostgreSQL para datos clínicos.
   - MinIO para imágenes y Grad-CAM.
   - MLflow para tracking de modelos.

8. **Documentación**
   - `README.md` incluye despliegue, credenciales y arquitectura.
   - este documento complementa con explicación de cada archivo.

---

## 10. Conclusión
El proyecto está estructurado para demostrar un sistema clínico interoperable con:
- FHIR R4,
- seguridad y RBAC,
- almacenamiento seguro,
- ML/DL en CPU,
- frontend profesional,
- despliegue Dockerizado,
- scripts de población de datos y auditoría.

Esto cubre los criterios más importantes de una rúbrica de Salud Digital para un miniproyecto universitario.
