# Workflows n8n — Pipeline de Automatización de Ensayos Agrícolas (C-08)

> Change `n8n-orchestration-workflows`. Ver `openspec/changes/n8n-orchestration-workflows/design.md`
> para las decisiones (D-1..D-10) detrás de cada elección de este directorio.

## Qué hay acá

| Archivo | Rol |
|---|---|
| `pipeline_principal.json` | Workflow del Flujo 1 completo: triggers → ingestion → validation → transformation → persistence → (IF `analysis_config.yaml`) → analysis → mover archivo. |
| `ejecutar_etapa_con_reintentos.json` | Sub-workflow genérico invocado una vez por etapa (Execute Workflow). Ejecuta el comando recibido, clasifica el exit code (0/1/2, D-4) y aplica backoff exponencial real (D-5) ante fallo transitorio. |
| `escalamiento_notificacion.json` | Error workflow: se activa cuando el principal termina en Stop and Error (fallo persistente). Registra el payload y contiene un nodo Telegram **deshabilitado** — el enganche que C-13 activará. |

## Por qué no hay evidencia de ejecución real en este change (D-9)

**No hay una instancia de n8n instalada en la máquina de desarrollo de este change.** En vez de fingir un runtime n8n en los tests (lo que validaría un mock, no el sistema), la verificación se hizo en 3 capas complementarias:

1. **Estructural (pytest)** — `tests/test_n8n_workflows.py`: los 3 JSON de este directorio se testean como datos (parseables, nodos esperados, orden de conexiones, comandos `{{$env.PYTHON_BIN}} -m pipeline.<etapa>`, Wait exponencial, límite de reintentos por env, nodo Telegram `disabled: true`, settings de logging, cero rutas absolutas/credenciales).
2. **E2E de la cadena CLI (pytest + subprocess)** — `tests/test_cli_chain.py`: ejecuta por `subprocess` EXACTAMENTE los mismos comandos que estos JSON arman, contra SQLite temporal real, cubriendo happy path, fallo de datos, fallo transitorio con reintento exitoso y fallo persistente.
3. **Este runbook** — los pasos de abajo, para ejecutarse manualmente cuando exista una instancia real. Es prerequisito documentado de C-10 (evaluación empírica).

La mecánica *interna* de n8n (que el nodo Wait realmente espere `base * 2^intento` segundos, que el loop de reintentos reanude visualmente en el dashboard, que Execute Command reporte `exitCode` como dato en vez de fallar el nodo) sólo queda verificada por las capas 1 y 2 más este runbook — no por un mock. Es un trade-off aceptado y documentado, no escondido.

## Pasos de verificación manual (cuando exista la instancia)

1. **Desplegar n8n self-hosted** en la misma máquina que este repo (acceso a filesystem y a `DATABASE_URL`) — tarea operativa, fuera de este change (Open Question 4 del design, sigue abierta).
2. **Configurar las variables de entorno** de `.env.example` (sección "Orquestación n8n") en el entorno donde corre n8n: `PYTHON_BIN` (ruta absoluta al intérprete del venv del proyecto), `PIPELINE_ROOT`, `PIPELINE_CARPETA_ENTRADA`, `PIPELINE_CARPETA_CORRIDAS`, `PIPELINE_REINTENTOS_MAX`, `PIPELINE_BACKOFF_BASE_SEGUNDOS`, `PIPELINE_ANALYSIS_CONFIG`, además de la ya existente `DATABASE_URL`.
3. **Importar los 3 JSON** de este directorio en n8n (Workflows → Import from File).
4. **Re-vincular el Execute Workflow**: al importar, n8n reasigna IDs internos a cada workflow — abrir los nodos `Ejecutar con Reintentos: *` de `pipeline_principal.json` y volver a seleccionar `Ejecutar Etapa Con Reintentos` como workflow destino (el `workflowId` exportado es simbólico, no el ID real de la instancia). Mismo paso para el `errorWorkflow` en Settings del workflow principal → `Escalamiento: Notificación Humana`.
5. **Verificar la semántica de `exitCode` del nodo Execute Command en la versión instalada**: confirmar que un exit code ≠ 0 con `continueOnFail: true` deja `exitCode` disponible como dato en `$json.exitCode` (no como excepción de nodo) — el diseño ya enruta explícitamente sobre ese campo (D-9, Riesgo documentado) precisamente porque esta semántica varía entre versiones de n8n.
6. **Crear `PIPELINE_CARPETA_ENTRADA`** con subcarpetas `procesados/` y `errores/` si no existen (el workflow las crea on-demand, pero conviene confirmarlas antes del primer disparo).
7. **Activar** `pipeline_principal.json`.
8. **Soltar un archivo sintético** (nunca un caso real) en `PIPELINE_CARPETA_ENTRADA` y verificar en el dashboard de n8n:
   - Las 5 etapas corren en orden y cada una crea sus artefactos en `PIPELINE_CARPETA_CORRIDAS/<run_id>/`.
   - El archivo se mueve a `procesados/` al terminar con éxito.
   - `settings.saveDataSuccessExecution` deja el log de la ejecución visible en el dashboard.
9. **Probar el reintento real**: apagar temporalmente el acceso a `DATABASE_URL` (ej. renombrar el archivo SQLite) antes de soltar un archivo; confirmar en el dashboard que el nodo `Esperar Backoff Exponencial` espera progresivamente más (5s, 10s, 20s) entre los 3 intentos, y que al restaurar el acceso antes de agotarlos la corrida termina en éxito.
10. **Probar el escalamiento real**: repetir el paso anterior sin restaurar el acceso — confirmar que tras `PIPELINE_REINTENTOS_MAX` intentos la ejecución del workflow principal queda marcada como **fallida** (Stop and Error) y que `escalamiento_notificacion.json` se disparó (verificar su log de ejecuciones) con el payload esperado.
11. **Probar el trigger de barrido**: colocar un archivo directamente en `PIPELINE_CARPETA_ENTRADA` con el workflow desactivado, luego activarlo — confirmar que el `Schedule Trigger` (o una ejecución manual del mismo) lo recoge en el siguiente barrido horario.
12. **Documentar los resultados** de estos 11 pasos como evidencia de la capa 3 antes de que el equipo dé por verificada la capa de orquestación para C-10.

## Convención de comandos (recordatorio, ver D-1/D-10 en design.md)

Cada etapa se invoca como `{{$env.PYTHON_BIN}} -m pipeline.<etapa> ...` — nunca un `import`. El contrato de exit codes es transversal a los 5 CLIs (D-4):

- `0` — éxito.
- `1` — error de dominio/datos (no se reintenta; termina en `procesados/` como rechazo).
- `2` — error transitorio de infraestructura (se reintenta con backoff exponencial; agotados los intentos, escala y termina en `errores/`).
