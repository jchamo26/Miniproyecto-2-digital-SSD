# Guia explicativa por componentes - Miniproyecto 2

## 1. Objetivo del sistema
El proyecto implementa una plataforma clinica interoperable con HL7 FHIR R4, autenticacion por doble API key, control de acceso por roles (admin, medico, paciente), inferencia de IA (ML y DL), y visualizacion profesional en frontend.

Se busca demostrar:
- Interoperabilidad clinica (FHIR)
- Seguridad y trazabilidad (RBAC, audit log, consentimiento)
- Integracion de IA explicable (SHAP y Grad-CAM)
- Despliegue reproducible con microservicios

## 2. Arquitectura general
El sistema esta dividido en microservicios para separar responsabilidades y facilitar mantenimiento:
- frontend: interfaz de usuario (React/Vite)
- backend: reglas de negocio, seguridad, FHIR-lite (FastAPI)
- ml-service: prediccion tabular y SHAP
- dl-service: prediccion por imagen y Grad-CAM
- orchestrator: cola y concurrencia de inferencias
- nginx: proxy reverso y punto de entrada unico
- postgres: persistencia relacional
- minio: almacenamiento de imagenes y artefactos
- mlflow: trazabilidad de experimentos/modelos
- mailhog: pruebas de notificaciones

## 3. Explicacion de cada componente

### 3.1 Frontend
Que hace:
- Permite login, dashboard, detalle de paciente, inferencia y panel admin.
- Muestra resultados de IA de forma entendible para clinica.

Por que existe:
- Proveer una experiencia tipo PACS/RIS para uso realista.

Evidencia de logro:
- Login por rol
- Listado paginado de pacientes
- Visualizacion de SHAP y Grad-CAM
- Firma de RiskAssessment desde interfaz

### 3.2 Backend
Que hace:
- Valida credenciales y permisos por rol.
- Expone endpoints de negocio y endpoints FHIR-lite.
- Aplica reglas de acceso por ownership de paciente.

Por que existe:
- Centraliza seguridad, reglas clinicas y consistencia de datos.

Evidencia de logro:
- Paciente no puede ver recursos ajenos (403)
- Paciente no puede lanzar inferencia (403)
- Medico y admin con permisos esperados
- Endpoints FHIR operativos

### 3.3 Orchestrator
Que hace:
- Recibe solicitudes de inferencia y las pone en cola.
- Ejecuta tareas con concurrencia controlada.
- Mantiene estados PENDING, RUNNING, DONE, ERROR.

Por que existe:
- Separar la ejecucion de IA del backend transaccional.

Evidencia de logro:
- Soporte de inferencias simultaneas
- Seguimiento de estado por task_id
- Control de acceso por propietario de tarea

### 3.4 ML Service
Que hace:
- Predice riesgo clinico tabular.
- Entrega score, categoria y explicacion SHAP.

Por que existe:
- Resolver casos con variables estructuradas (por ejemplo, diabetes/heart risk).

Evidencia de logro:
- Respuesta de inferencia en CPU
- Salida interpretable para clinicos

### 3.5 DL Service
Que hace:
- Predice a partir de imagen medica.
- Genera mapa de calor (Grad-CAM) y lo publica en almacenamiento.

Por que existe:
- Cubrir analitica visual en flujos clinicos.

Evidencia de logro:
- Grad-CAM visible en interfaz
- Artefactos disponibles en MinIO

### 3.6 Base de datos (PostgreSQL)
Que hace:
- Persiste usuarios, pacientes, inferencias, reportes de riesgo, auditoria y consentimiento.
- Mantiene integridad con llaves y relaciones.

Por que existe:
- Garantizar trazabilidad y consistencia.

Evidencia de logro:
- Conteos y consultas estables
- Correccion de drift de esquema para evitar errores 500

### 3.7 MinIO
Que hace:
- Guarda imagenes clinicas y resultados visuales (Grad-CAM).

Por que existe:
- Separar archivos binarios del almacenamiento relacional.

Evidencia de logro:
- Recuperacion de imagenes por llave
- Integracion con backend/dl-service/frontend

### 3.8 Nginx
Que hace:
- Publica un solo punto de entrada para frontend y APIs.
- Enruta trafico a cada microservicio.

Por que existe:
- Simplificar acceso y aproximar arquitectura de produccion.

Evidencia de logro:
- Rutas unificadas por localhost
- Gateway funcional para pruebas end-to-end

### 3.9 MLflow y Mailhog
MLflow:
- Registro de modelos, metricas y versiones.

Mailhog:
- Simulacion de correo para alertas y pruebas.

Por que existen:
- Cubrir observabilidad de IA y notificaciones sin dependencias externas.

## 4. Seguridad, cumplimiento y control
Puntos clave:
- Doble API key en endpoints
- RBAC por rol
- Restriccion por ownership de paciente y tarea
- Consentimiento (Habeas Data)
- Audit log de acciones
- Soft delete para trazabilidad

## 5. Soft delete (explicacion para sustentar)
Que es:
- Soft delete significa que el sistema no borra fisicamente una fila.
- En lugar de usar DELETE, marca el registro con una fecha en deleted_at.

Como se aplica en este proyecto:
- Cuando se cierra un paciente o se desactiva un usuario, se hace UPDATE ... SET deleted_at=NOW().
- Las consultas normales filtran WHERE deleted_at IS NULL para ocultar los eliminados.
- Si un admin necesita recuperar un registro, se puede restaurar con deleted_at=NULL.

Por que se usa:
- Mantiene trazabilidad y auditoria historica.
- Evita perdida irreversible de datos clinicos.
- Facilita cumplimiento normativo y soporte de incidentes.

Frase corta para decir en exposicion:
- En nuestro sistema, eliminar no destruye datos; solo marca deleted_at. Todo lo activo se consulta con deleted_at IS NULL, y admin puede restaurar si es necesario.

## 6. Flujo clinico resumido
1. Usuario inicia sesion segun rol.
2. Consulta pacientes permitidos por RBAC.
3. Medico solicita inferencia (ML o DL).
4. Orchestrator procesa y retorna estado/resultado.
5. Se genera y revisa RiskAssessment.
6. Medico firma y sistema deja trazabilidad.

## 7. Que decir en la sustentacion (guion corto)
1. Problema: interoperabilidad, seguridad y apoyo a decision clinica.
2. Solucion: arquitectura por microservicios con FHIR y IA explicable.
3. Seguridad: doble API key, RBAC y auditoria.
4. IA: ML tabular + DL imagen con explicabilidad.
5. Evidencia: pruebas por rol, inferencia concurrente, dashboard funcional.
6. Cierre: sistema reproducible con Docker Compose y listo para evolucion a nube.

## 8. Limitaciones actuales y plan de mejora
Limitaciones:
- Despliegue productivo publico no consolidado en una sola nube.
- Algunos componentes operan en modo demo (segun configuracion local).

Mejoras sugeridas:
- Deploy en Render/Railway/Fly para backend y orquestador
- Frontend en Vercel
- MinIO gestionado o S3 compatible
- Pipeline CI/CD con pruebas automaticas

## 9. Conclusiones
El sistema cumple una arquitectura coherente para Salud Digital academica: interoperabilidad FHIR, seguridad por roles, explicabilidad de IA y flujo clinico demostrable de punta a punta.
