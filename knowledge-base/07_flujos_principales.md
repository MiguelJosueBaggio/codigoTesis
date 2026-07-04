# Flujos Principales

> **Actualización (interacción cero-CLI por Telegram, DD-09 — ver `13_interaccion_telegram_y_sesiones.md`)**: los flujos originales (1-4) describían a actores humanos operando por CLI o editando archivos de configuración a mano. Con DD-09 eso cambia: **ningún humano interactúa con la CLI**; toda interacción humana es por **Telegram**, y el resto es orientado a eventos. Los flujos siguientes se conservan como base del pipeline técnico (la mecánica ingesta→validación→transformación→persistencia→análisis no cambia), pero **la interacción humana de cada uno se reexpresa vía Telegram**. Se agregan además el **Flujo 5** (setup guiado de ensayo), el **Flujo 6** (carga de datos por Telegram con OCR opcional) y el **Flujo 7 / catálogo de eventos**.

## Flujo 1: Ejecución completa del pipeline (happy path)

**Disparador**: nuevo archivo detectado en ubicación monitoreada, programación horaria, o invocación manual.
**Actor**: n8n (orquestador), invocado por investigador/analista.

**Pasos**:
1. n8n detecta el trigger y dispara el workflow.
2. Módulo de ingesta (Python) lee el archivo CSV/Excel y valida su estructura.
3. Módulo de validación aplica reglas de `great_expectations` sobre cada registro.
4. Se separan registros válidos / rechazados; se genera reporte de validación.
5. Módulo de transformación normaliza, estandariza y construye el dataset *tidy* (solo sobre válidos).
6. Módulo de persistencia almacena el dataset en la base de datos y escribe la bitácora de auditoría (ejecución + transformaciones).
7. (Opcional, encadenado o standalone) Módulo de análisis estadístico ejecuta el modelo configurado y genera reportes (CSV/HTML/PNG/YAML).
8. n8n registra la ejecución completa en sus logs.

**Diagrama de secuencia**:
```
Analista → n8n → Ingesta → Validación → Transformación → Persistencia → (Análisis) → Reportes
                                                              ↓
                                                          Bitácora auditoría
```

**Casos de error**:
- Archivo con formato/codificación inválida → pipeline se detiene en ingesta, informe de error, no avanza.
- Registro individual con violación de regla → se separa a "rechazados" con detalle; el resto del dataset sigue procesándose (tolerancia a fallos, RN-GLB-01); el rechazo se **notifica por Telegram** (DD-09).
- Fallo transitorio de infraestructura (n8n) → reintento automático con backoff exponencial; si persiste, **notificación humana por Telegram** (RN-GLB-03, canal concreto por DD-09).

**Nota (DD-09)**: los resultados del paso 7 se **notifican al ingeniero por Telegram**, ofreciéndole la elección de autoría del reporte (RN-EST-07). El "actor" que dispara no teclea comandos: el trigger es un evento (archivo nuevo / foto por Telegram / programación).

## Flujo 2: Corrección y reingreso de registros rechazados

**Disparador**: reporte de validación con registros rechazados.
**Actor**: investigador/analista de datos.

**Pasos**:
1. Analista consulta el reporte de validación (registro, campo, regla violada).
2. Corrige el dato en la fuente original (fuera del sistema, ej. planilla de campo).
3. Reingresa el archivo corregido → dispara nuevamente el Flujo 1.

**Casos de error**: si el mismo error persiste, el registro vuelve a rechazarse — no hay corrección automática de datos rechazados dentro del sistema (fuera de alcance de IA autónoma, RN-IA-01).

## Flujo 3: Ejecución independiente del análisis estadístico

**Disparador**: invocación sobre un dataset ya almacenado.
**Actor**: estadístico / ingeniero.

> **Nota (DD-09)**: la configuración del análisis (`analysis_config.yaml`) ya no se edita a mano por CLI. La define el **Ingeniero** por la conversación guiada de Telegram (`tipo_sesion = setup_ensayo`, ver Flujo 5), y el sistema construye el YAML a partir de sus respuestas. La invocación del módulo `pipeline/analysis.py` la hace **n8n por CLI de forma interna** (respetando DD-05); ningún humano teclea el comando. Los pasos 1-2 siguientes se conservan como descripción de *qué* ocurre bajo el capó, no de *quién* teclea.

**Pasos**:
1. La configuración del análisis (fórmula, tipo de análisis, parámetros) proviene del setup guiado por Telegram (Flujo 5), materializada en `analysis_config.yaml`.
2. n8n invoca el módulo de análisis por CLI (interno), referenciando el id del dataset.
3. Módulo ejecuta el modelo, corre diagnósticos de supuestos, genera reportes.
4. Si un supuesto se viola, es una decisión metodológica del estadístico/ingeniero (aplicar transformación a la variable respuesta, usar alternativa no paramétrica/GLM/LMM, o documentar por qué el análisis es robusto pese a la violación) — se le comunica por Telegram.
5. Re-ejecución (mismos datos + mismo código) debe producir resultados idénticos — condición de reproducibilidad (RN-GLB-02).

**Casos de error**: violación de supuestos no es un "error" del sistema — es una decisión metodológica del estadístico, documentada en el reporte.

## Flujo 4: Sugerencia y aprobación de IA (opcional)

**Disparador**: el componente de IA detecta variabilidad léxica alta en una variable categórica o una anomalía estadística.
**Actor**: componente de IA → experto de dominio (aprobador).

**Pasos**:
1. IA genera propuesta de estandarización o marca una anomalía.
2. Propuesta se presenta al operador humano **por Telegram con botones *inline*** (aprobar / rechazar), como sesión `tipo_sesion = confirmacion_ia` (DD-09). El workflow queda **en pausa** ("Wait for Webhook") esperando el clic.
3. Operador aprueba o rechaza con un clic → el webhook **reanuda** el workflow.
4. Decisión (con justificación) se registra en bitácora de auditoría (RN-IA-03, RN-SES-06).
5. Solo si se aprueba, el cambio se aplica al dataset (vía el módulo de transformación, no directamente por la IA).

**Casos de error**: ninguna propuesta de IA se aplica sin este flujo — no hay "camino directo" de IA a dato persistido.

---

## Flujo 5: Setup guiado de un ensayo nuevo (Telegram) — NUEVO (DD-09)

**Disparador**: un **Ingeniero** registrado, sin setup de ensayo activo, escribe al bot.
**Actor**: Ingeniero (ver `03_actores_y_roles.md`).

**Pasos**:
1. Llega el mensaje; n8n busca sesión abierta para ese `telegram_user_id` (RN-SES-04). No hay → se resuelve el tipo por rol → se ofrece iniciar `setup_ensayo` y se crea sesión en paso 0.
2. El bot pregunta, paso a paso (secuencia definida como configuración, RN-SES-03), los elementos del ensayo: variables del diccionario (nombre, tipo, unidad, rango, valores admisibles, obligatoriedad), diseño experimental y fórmula del modelo.
3. Cada respuesta se valida (RN-SES-05), se acumula en `respuestas_acumuladas` y se registra en bitácora (RN-SES-06).
4. Al completar la secuencia, el sistema **construye** `config/data_dictionary.json` y `config/analysis_config.yaml` a partir de las respuestas; la sesión pasa a `completada`.
5. El ensayo queda configurado; a partir de ahí todo aguas abajo es orientado a eventos.

**Frontera (ver §6 de `13_*`)**: las decisiones (qué variables, qué rangos, qué modelo) son juicio experto irreductible del ingeniero. El sistema automatiza *cómo* se entregan (conversación en vez de editar archivos), no el juicio.

**Casos de error**: respuesta inválida → no avanza, se re-pregunta (RN-SES-05). Sesión sin actividad → `expirada`/`abandonada` según política (RN-SES-07, umbral aún no decidido).

## Flujo 6: Carga de datos de campo por Telegram, con OCR opcional — NUEVO (DD-09)

**Disparador**: un **Ayudante** de un ensayo ya configurado escribe al bot.
**Actor**: Ayudante.

**Pasos**:
1. n8n busca sesión abierta (RN-SES-04); si no hay, se ofrece `carga_dato` y se crea sesión en paso 0.
2. El bot pide el dato **campo por campo** y ofrece, para cada campo, **cómo** enviarlo: escribir el valor como **texto**, o mandar una **foto** de planilla de papel.
3a. **Texto** → se valida contra el diccionario (RN-SES-05 / RN-VAL) y se almacena.
3b. **Foto** → entra al pipeline OCR zonal (`12_captura_offline_ocr.md`, RN-OCR-01..07). Si una lectura queda bajo umbral o viola RN-VAL → dispara Flujo de confirmación (ver Flujo 7 / `confirmacion_ocr`).
4. Al completar los campos, el dato confirmado se normaliza a la forma tabular de ingesta (RN-OCR-07) y **converge al pipeline existente** (RN-VAL → RN-TRA → RN-AUD) — es el Flujo 1 aguas abajo, sin cambios.

**Punto clave**: el OCR es **uno de los métodos de entrada dentro de esta sesión**, no un sistema paralelo.

## Flujo 7: Confirmación human-in-the-loop asíncrona + catálogo de eventos — NUEVO (DD-09)

**Disparador**: cualquier lectura OCR o sugerencia IA de baja confianza en cualquier punto del pipeline.

**Mecanismo**: mensaje Telegram con botones *inline* → workflow **en pausa** (n8n "Wait for Webhook") → clic del usuario → webhook **reanuda** el workflow con el valor confirmado → registro en bitácora (RN-AUD-02, RN-SES-06: lectura original vs. valor confirmado, quién y cuándo).

**Catálogo de eventos completo** (base del sistema orientado a eventos):

```
Archivo nuevo (CSV/Excel/foto vía Telegram)
   │
   ▼
Ingesta (RN-ING)  ──(foto)──►  OCR zonal (RN-OCR)
   │
   ▼
Validación (RN-VAL)
   ├── rechazados ──► Notificación Telegram (detalle del rechazo)
   └── válidos ─────► Transformación (RN-TRA) ─► Persistencia + bitácora (RN-AUD)
                          │
                          ▼
              ¿existe analysis_config.yaml del ensayo?
                          │ sí
                          ▼
              Análisis estadístico automático (RN-EST)
                          │
                          ▼
              Notificación Telegram al ingeniero (+ elección de reporte, RN-EST-07)

EN PARALELO:  lectura OCR / sugerencia IA baja confianza
              → Telegram con botones → workflow en pausa (Wait for Webhook)
              → clic → reanuda con valor confirmado → bitácora

ESCALAMIENTO: N reintentos fallidos en cualquier etapa
              → escalamiento por Telegram (RN-GLB-03, canal concreto)
```
