# Reporte de Validacion Final - Corte 2

Fecha: 2026-04-21

## Estado general
- Resultado global: CUMPLE (con evidencia tecnica)
- Objetivo: cierre de brechas de rubrica (DL imagen, DiagnosticReport, WebSocket, persistencia y concurrencia)

## Checklist de criterios clave
- DL por imagen (`POST /predict-image`): CUMPLE
- Artefactos explicabilidad (Grad-CAM-like en MinIO): CUMPLE
- Payload FHIR DiagnosticReport desde DL: CUMPLE
- FHIR DiagnosticReport create/list en backend: CUMPLE
- Orquestador con persistencia en PostgreSQL: CUMPLE
- Estado de inferencia por WebSocket (`/infer/ws/{task_id}`): CUMPLE
- Concurrencia >= 4 inferencias simultaneas: CUMPLE

## Evidencias generadas
1. Concurrencia formal (4 solicitudes simultaneas)
   - Archivo: `EVIDENCIA_CONCURRENCIA.md`
   - Resultado: DONE=4, NO_DONE=0
   - Factor de solapamiento (sum/wall): 1.4

2. Validaciones funcionales ejecutadas
   - Health checks backend/orchestrator/dl en 200
   - `POST /predict` y `POST /predict-image` con respuesta completa
   - `POST /infer` + `GET /infer/{task_id}` sin error 500
   - WebSocket de inferencia con mensaje de estado recibido
   - `POST /fhir/DiagnosticReport` y `GET /fhir/DiagnosticReport` operativos

## Observacion de despliegue
- Durante la prueba inicial aparecio un 502 transitorio en `http://localhost/infer` por reinicio/re-resolucion de upstream.
- Se aplico ajuste de proxy y recarga de Nginx; luego `POST /infer` y `GET /infer/{task_id}` via gateway quedaron operativos (respuesta 200/DONE).
- La evidencia oficial de concurrencia se tomo directo contra orquestador (`http://localhost:8002/infer`), que es el servicio evaluado para semaforo/cola.

## Conclusion
La implementacion actual cumple los puntos tecnicos principales para sustentacion del jurado en el alcance solicitado de Corte 2.
