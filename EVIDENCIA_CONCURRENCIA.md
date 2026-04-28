# Evidencia de Concurrencia (Corte 2)

- Fecha de ejecución: 2026-04-21 00:10:45
- Endpoint: http://localhost:8002/infer + /infer/{task_id}
- Solicitudes simultáneas: 4
- Resultado: DONE=4, NO_DONE=0

## Métricas agregadas
- Tiempo de pared total (wall clock): 0.5 s
- Suma de duraciones individuales: 0.7 s
- Factor de solapamiento (sum/wall): 1.4

## Detalle por solicitud

```text

idx model      task_id                              status elapsed_s polls erro
                                                                           r_ms
                                                                           g   
--- -----      -------                              ------ --------- ----- ----
  1 ML         a2f690fa-7109-4643-be67-d7797025f5e2 DONE         0,2     0     
  2 DL         5e41a23f-6f60-4c3c-895a-dcadc7023438 DONE        0,19     0     
  3 MULTIMODAL b88048d6-d4c9-473e-bb47-07b40761aa05 DONE        0,16     1     
  4 DL         60b46195-acc1-48ac-b5b8-b5a1b0ac858f DONE        0,15     0
```
