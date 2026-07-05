# Workflows n8n — Pipeline de Automatización de Ensayos Agrícolas (C-08 + C-13)

> Change `n8n-orchestration-workflows` (C-08) y `telegram-interaction-layer` (C-13). Ver
> `openspec/changes/n8n-orchestration-workflows/design.md` (D-1..D-10) y
> `openspec/changes/telegram-interaction-layer/design.md` (D-1..D-9) para las decisiones
> detrás de cada elección de este directorio.

## Qué hay acá

| Archivo | Rol |
|---|---|
| `pipeline_principal.json` | Workflow del Flujo 1 completo: triggers → ingestion → validation → transformation → persistence → (IF `analysis_config.yaml`) → analysis → mover archivo. |
| `ejecutar_etapa_con_reintentos.json` | Sub-workflow genérico invocado una vez por etapa (Execute Workflow). Ejecuta el comando recibido, clasifica el exit code (0/1/2, D-4) y aplica backoff exponencial real (D-5) ante fallo transitorio. |
| `escalamiento_notificacion.json` | Error workflow: se activa cuando el principal termina en Stop and Error (fallo persistente). Registra el payload y **envía efectivamente un mensaje de Telegram** (C-13, D-7 — antes de C-13 el nodo quedaba deshabilitado como enganche documentado). |
| `interaccion_telegram.json` | **(C-13)** Loop genérico único: Telegram Trigger (mensajes + callbacks) → RBAC + motor de sesiones vía `pipeline.session_cli` → router por resultado (rechazo / reintento / completada / prompt siguiente). Ver §"Interacción Telegram (C-13)" más abajo. |

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

---

## Interacción Telegram (C-13)

`interaccion_telegram.json` es la **superficie humana única** del sistema (DD-09): ningún usuario final toca la CLI ni edita archivos de configuración. El único mecanismo interno que invoca Python es `python -m pipeline.session_cli <resolver|avanzar|expirar|finalizar_setup>` (Execute Command, contrato JSON stdin/stdout, exit code **siempre 0** — D-2 del design). El grafo del workflow no se ramifica por `tipo_sesion`: agregar un paso a `setup_ensayo`/`carga_dato`/`confirmacion_ocr`/`confirmacion_ia` es una fila nueva en `config_paso_sesion` (RN-SES-03), nunca un cambio de este JSON.

### 8.1 — Alta de la credencial de Telegram + importación + republicación

1. **Crear el bot** con [@BotFather](https://t.me/BotFather) y obtener el `TELEGRAM_BOT_TOKEN`.
2. **Cargar la credencial en n8n** (Credentials → New → Telegram API), pegando el token ahí — **nunca** en un archivo del repo ni en `.env`. El nombre sugerido es `Telegram Bot (Ensayos Agricolas)`, para que coincida con la referencia simbólica que traen los JSON exportados (`credentials.telegramApi.name`).
3. **Importar `interaccion_telegram.json`** (Workflows → Import from File) y, si corresponde, la versión actualizada de `escalamiento_notificacion.json` (nodo Telegram ahora habilitado, D-7).
4. **Re-vincular la credencial**: igual que con `workflowId` en C-08, el `credentials.telegramApi.id` exportado (`telegram_bot_ensayos_agricolas`) es **simbólico** — abrir cada nodo Telegram (`Trigger: Mensaje o Callback de Telegram`, `Enviar Rechazo`, `Enviar Reintento`, `Enviar Confirmacion de Setup`, `Enviar Confirmacion de Carga`, `Enviar Prompt Siguiente`, `Enviar Confirmacion con Botones`, `Enviar OCR No Disponible`, y el nodo de `escalamiento_notificacion.json`) y re-seleccionar la credencial real de la instancia.
5. **⚠️ Procedimiento de republicación tras `n8n import:workflow` (CLI)**: importar por línea de comandos **desactiva y despublica** el workflow importado — un `activeVersionId` o `workflow_published_version` desincronizado deja el bot **inactivo silenciosamente** aunque el workflow aparezca en el listado. Dos alternativas:
   - **Recomendada**: importar por la **UI** (Workflows → Import from File) en vez de la CLI — la UI no tiene este problema.
   - Si se **debe** usar `n8n import:workflow`: detener la instancia de n8n, actualizar manualmente `workflow_published_version`/`activeVersionId` en la base de datos de n8n para que apunten a la versión recién importada, y reiniciar. Confirmar contra el comportamiento real de la versión de n8n instalada (2.28.6) antes de depender de este paso en producción.
   - En ambos casos: **activar** el workflow explícitamente después de importar y verificar en el dashboard que queda `Active`.
6. Configurar `PIPELINE_CARPETA_CORRIDAS` (ya usada por C-08) — `interaccion_telegram.json` reutiliza `PIPELINE_CARPETA_CORRIDAS/telegram_cli/` como scratch para los payloads JSON que arma antes de invocar `session_cli`.
7. Ejecutar la migración Alembic hasta `head` (`0001`→`0004`) contra `DATABASE_URL` de producción — crea `usuario_telegram` y `rechazo_autorizacion` (grupo 1/2 de este change) además de las tablas ya existentes.

### 8.2 — Seed de `usuario_telegram` (Administrador, fuera del repo)

El arranque de la autorización tiene un problema del huevo y la gallina: nadie puede autorizarse a sí mismo por Telegram porque, hasta que exista al menos una fila en `usuario_telegram`, **todo** `telegram_user_id` es rechazado (fail-closed, D-1). Por eso el seed inicial es una **tarea operativa del Administrador del sistema** (KB 03), no un flujo conversacional:

```bash
# Ejemplo -- ejecutar con DATABASE_URL apuntando a la base de produccion.
# NO es un comando expuesto a usuarios finales (DD-05/DD-09): es un script
# de una sola vez que corre el Administrador durante el despliegue.
"{PYTHON_BIN}" -c "
from datetime import datetime, timezone
from pipeline.db import build_engine, build_session
from pipeline.models import UsuarioTelegram

engine = build_engine()  # toma DATABASE_URL del entorno
session = build_session(engine)
ahora = datetime.now(timezone.utc)
session.add(UsuarioTelegram(
    telegram_user_id='<telegram_user_id real del Ingeniero>',
    rol='ingeniero',
    created_at=ahora,
    updated_at=ahora,
))
session.commit()
session.close()
engine.dispose()
"
```

Repetir con `rol='ayudante'` (y opcionalmente `ensayo_id` una vez que el ensayo exista) para cada Ayudante autorizado. El `telegram_user_id` real se obtiene pidiéndole a la persona que le escriba al bot [@userinfobot](https://t.me/userinfobot) (o equivalente) y comunique el id numérico por un canal fuera de banda — **nunca** se auto-registra desde el propio bot.

### 8.3 — Nota de confidencialidad honesta (DD-09/D-8)

Los chats de un bot de Telegram viajan cifrados **en tránsito** (TLS), pero **no** son cifrado end-to-end (a diferencia de los chats secretos de Telegram entre personas) — el propio Telegram, y por extensión cualquier operador con acceso a la infraestructura del bot, puede en principio inspeccionar el contenido de los mensajes. Esto está en tensión con RN-OCR-05/§3.7 (los datos de un ensayo pueden considerarse sensibles). Se documenta **honestamente**, sin sobrevender: este change acepta ese trade-off a cambio del beneficio operativo (canal único, nodo nativo, cero fricción de despliegue de una app propia) para el alcance de la tesis. Si el caso de estudio real maneja datos que requieren confidencialidad de nivel superior, esta decisión debe revisarse antes de producción real (fuera de alcance de C-13).

### 8.4 — Trigger programado de `session_cli expirar` (RN-SES-07, 24h)

`pipeline.session_engine.expirar_sesiones_vencidas` (C-12) necesita que algo la dispare periódicamente — el motor no tiene scheduler interno (Decision 3 del design de `session-engine`). Agregar, en la misma instancia de n8n, un workflow mínimo con:

- Un **Schedule Trigger** (p. ej. cada hora, mismo patrón que `Trigger: Barrido Programado` de `pipeline_principal.json`).
- Un **Execute Command** que invoque `python -m pipeline.session_cli expirar` (sin payload de stdin, o `{}`) — mismo contrato JSON/exit-0 que el resto de `session_cli`.

Esto barre toda sesión `abierta` cuya `updated_at` supere las 24h (DD-10) y la transiciona a `expirada`, liberando a ese `telegram_user_id` para iniciar una sesión nueva. No requiere un workflow nuevo exportado en este directorio (es operativo, dos nodos) — se documenta aquí como el punto de enganche pendiente de crear en la instancia real.
