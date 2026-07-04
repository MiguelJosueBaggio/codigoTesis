# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **Automatización de Ensayos Agrícolas** (Tesis de Magíster en Sistemas de Información, UTN FR Mendoza).
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

---

## Cómo usar este documento

1. Identificá el próximo change pendiente `[ ]` respetando el orden de **Dependencias**.
2. Leé los archivos listados en **Leer antes** de ese change (son la especificación — vienen de la tesis vía `knowledge-base/`).
3. Ejecutá `/opsx:propose C-NN-nombre-del-change` para generar proposal, design y tasks.
4. Implementá con `/opsx:apply` y cerrá con `/opsx:archive` cuando el change esté completo.
5. Marcá el checkbox `[x]` en este archivo y continuá con el siguiente change desbloqueado.

**Advertencia especial de este proyecto**: 3 preguntas de prioridad Alta en `knowledge-base/10_preguntas_abiertas.md` no están resueltas (caso de estudio real, necesidad de UI propia, quién ejecuta la línea base manual). Ningún change asume una respuesta — donde corresponde, quedan marcadas explícitamente como **BLOQUEANTE** o **NOTA** dentro del change afectado. No las resuelvas de forma unilateral: son decisión del equipo de tesis (4 autores) + director.

**Reenfoque (post-generación del roadmap)**: se validó primero la mecánica ANOVA+Tukey (ver `knowledge-base/11_analisis_estadistico_anova_tukey.md`) antes de construir el resto del pipeline, y se encontró un bug crítico: `pairwise_tukeyhsd` da p-valores incorrectos en diseños bloqueados. Se inserta **C-00b anova-tukey-core** como prerequisito de C-07, SIN depender de C-06 — el núcleo estadístico (fórmula → tabla ANOVA → Tukey HSD correcto → diagnóstico de supuestos) es una función pura que opera sobre un DataFrame de pandas y no necesita persistencia ni auditoría para ser validada y testeada. C-07 más adelante lo integra al pipeline completo (I/O de base de datos, bitácora).

---

## Árbol de dependencias

```
C-00b anova-tukey-core (NUEVO — sin dependencias, [x] completado)
└── (se integra a) C-07 statistical-analysis-module

C-01 foundation-setup
└── C-02 data-dictionary-schema
    ├── C-03 ingestion-module ───────────┐
    │   └── C-11 ocr-field-capture (opcional)  ← método de entrada alternativo;
    │                                            converge a pipeline/ingestion.py
    └── C-04 validation-engine ──────────┤
        └── C-05 transformation-module   │  (C-03 y C-04 se desarrollan
            └── C-06 persistence-audit-module   en paralelo contra el
                ├── C-07 statistical-analysis-module  contrato de C-02;
                │   (envuelve a C-00b con I/O + auditoría)
                │   └── C-08 n8n-orchestration-workflows  ← join: requiere
                │       │                                    C-03,C-04,C-05,
                │       │                                    C-06,C-07)
                │       ├── C-10 case-study-evaluation  ⚠ BLOQUEADO
                │       └── C-13 telegram-interaction-layer  ← capa cero-CLI
                │           (requiere C-08 + C-12; se relaciona con C-11:
                │            el OCR es un método de entrada dentro de una sesión)
                ├── C-09 ai-support-standardization (opcional)
                └── C-12 session-engine  ← motor genérico de sesiones (DD-09);
                    nueva entidad `sesion` sobre la persistencia de C-06
```

> **Refinamiento (interacción cero-CLI por Telegram — DD-09, ver `knowledge-base/13_interaccion_telegram_y_sesiones.md`)**: el usuario refinó DD-05 (que era "CLI-first") a DD-09 ("cero interacción directa del usuario; Telegram como único canal humano; la CLI es interna de n8n"). Esto agrega dos changes **fuera del camino crítico** de la tesis (igual que C-09 y C-11): **C-12** `session-engine` (motor genérico de máquina de estados de sesión, dirigido por datos, sobre la persistencia de C-06) y **C-13** `telegram-interaction-layer` (bot de Telegram + roles Ingeniero/Ayudante + flujos guiados + confirmaciones *human-in-the-loop*). **Decisión de por qué DOS changes y no uno**: son atómicamente separables y tienen governance distinto — el motor de sesiones (C-12) es lógica de estado + persistencia (MEDIO), testeable de forma aislada contra la base de datos sin Telegram; la capa Telegram (C-13) es cableado de orquestación + RBAC + wiring del nodo Telegram (ALTO), y **consume** el motor de C-12. Juntar ambos en un change violaría la atomicidad de ~4-6h y mezclaría dos niveles de governance. C-12 puede construirse en cuanto C-06 cierre; C-13 requiere además C-08 (para tener workflows que pausar/reanudar).

### Paralelismo por fase

**GATE 0**: C-01 ✓
  → C-02 data-dictionary-schema        [Agente A]  (único sucesor, sin fork todavía)

**GATE 1**: C-02 ✓                     ← FORK
  → C-03 ingestion-module              [Agente A]
  → C-04 validation-engine             [Agente B]  (ambos desarrollan contra el contrato `data_dictionary.json` + fixture sintético de C-02, sin esperarse mutuamente)

**GATE 2**: C-03 ✓ y C-04 ✓ (join)
  → C-05 transformation-module         [Agente A o B — el que quede libre primero]
  → C-11 ocr-field-capture             [opcional — puede arrancar en cuanto C-03 ✓; requiere también C-02. No bloquea el camino crítico; asignar a un agente libre solo si el caso de estudio confirma captura en papel]

**GATE 3**: C-05 ✓
  → C-06 persistence-audit-module      [Agente A]

**GATE 4**: C-06 ✓                     ← FORK
  → C-07 statistical-analysis-module   [Agente A]
  → C-09 ai-support-standardization    [Agente B — opcional, Épica 6]
  → C-08 n8n-orchestration-workflows   [Agente C — puede empezar a cablear ingestion→validation→transformation→persistence de inmediato; el nodo de análisis se agrega cuando C-07 cierre]
  → C-12 session-engine                [opcional — puede arrancar en cuanto C-06 ✓; agrega la entidad `sesion` sobre la persistencia. No bloquea el camino crítico]

**GATE 5**: C-07 ✓ y C-08 ✓ (join; C-09 no bloquea — es opcional)
  → C-10 case-study-evaluation         ⚠ **BLOQUEADO** — no asignar a ningún agente hasta que el equipo de tesis resuelva las 3 preguntas de prioridad Alta de `knowledge-base/10_preguntas_abiertas.md`. Governance CRITICO: solo análisis, ningún código sin aprobación explícita.
  → C-13 telegram-interaction-layer    [opcional — requiere C-08 ✓ y C-12 ✓; cablea el bot de Telegram, los roles y los flujos guiados. Se relaciona con C-11 (el OCR es un método de entrada dentro de una sesión). No bloquea el camino crítico]

### Camino crítico (9 changes — mínimo irreducible)

```
C-01 → C-02 → C-03* / C-04* → C-05 → C-06 → C-07 → C-08 → C-10
```
`*` C-03 y C-04 son ambos indispensables y se ejecutan en paralelo (no es una bifurcación opcional, es un join obligatorio antes de C-05). C-09 (IA de apoyo), C-11 (captura OCR), C-12 (motor de sesiones) y C-13 (capa Telegram) quedan **fuera** del camino crítico: la IA de apoyo es Épica opcional con supervisión (§2.6); la captura OCR es una extensión de alcance (DD-08) que solo se habilita si el caso de estudio confirma captura en papel; y C-12/C-13 son el refinamiento de interacción cero-CLI (DD-09) — mejoran radicalmente cómo interactúan los usuarios, pero el pipeline y la evaluación empírica (camino crítico a Cap. 5) funcionan sin ellos.

### Plan óptimo con 3 agentes

| Paso | Agente A (Backend Core) | Agente B (Backend Aux) | Agente C (Orquestación) |
|------|--------------------------|--------------------------|---------------------------|
| 1 | C-01 foundation-setup | — | — |
| 2 | C-02 data-dictionary-schema | — | — |
| 3 | C-03 ingestion-module | C-04 validation-engine | — |
| 4 | C-05 transformation-module | — | — |
| 5 | C-06 persistence-audit-module | — | — |
| 6 | C-07 statistical-analysis-module | C-09 ai-support-standardization (opcional) | C-08 n8n-orchestration-workflows (wiring parcial: ingestion→validation→transformation→persistence) |
| 7 | — (soporte a C-08: nodo de análisis) | — | C-08 n8n-orchestration-workflows (cierre: agrega nodo de análisis, e2e) |
| 8 | ⚠ C-10 case-study-evaluation — **NO ARRANCAR**: requiere decisión humana explícita del equipo de tesis sobre las 3 preguntas Alta prioridad antes de asignar a cualquier agente | | |

---

## FASE PRE — Validación de núcleo estadístico

> C-00b se ejecuta en paralelo a C-01/C-02/C-03/C-04/C-05 (no tiene dependencias) para desbloquear a C-07 tempranamente con el componente crítico de análisis ya validado y testeado.

### [C-00b] `anova-tukey-core`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/analysis_core.py`: núcleo estadístico puro (sin persistencia, sin n8n)
  - Tabla ANOVA (Tipo I secuencial) mediante `statsmodels.formula.api.ols` + `anova_lm`
  - Corrección de Tukey HSD para diseños bloqueados: uso del `MS_error` del modelo **completo** (bloque + tratamiento), evitando el bug de `pairwise_tukeyhsd` naive que ignora el bloqueo
  - Diagnóstico de supuestos: normalidad (Shapiro-Wilk) + homocedasticidad (Levene) sobre residuos del modelo
  - Soporte para diseños factoriales con interacciones, con documentación explícita de confusión (aliasing) en designs de media fracción
  - Alternativa no paramétrica: Kruskal-Wallis (rank-based)
  - Capa no-bloqueante de sanity-checks: detección de matriz rango-deficiente, violaciones de supuestos, tamaño de grupo insuficiente (advisory, nunca levanta excepción)
  - Transformaciones de respuesta (log / sqrt / inverse) como remedio ante violación de supuestos
  - Dataset de regresión versionado: `npk` (R MASS::npk, descargado una vez, pinneado en `tests/fixtures/npk.csv`)
  - 38 tests strict TDD (RED → GREEN → TRIANGULATE → REFACTOR): dos casos mínimo por comportamiento, validación de valores de referencia contra fixture `npk` hasta el 4º decimal, anti-regresión del bug DD-07 pinneado explícitamente
- **Dependencias**: ninguna (módulo puro sobre pandas/statsmodels/scipy)
- **Governance**: MEDIO (matemática estadística crítica + valores de referencia pinneados, pero módulo aislado sin I/O ni persistencia)
- **Leer antes**:
  - `knowledge-base/11_analisis_estadistico_anova_tukey.md` (hallazgo del bug, matemática correcta, validación contra `npk`)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-EST-01 a RN-EST-06 (y RN-GLB-01)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-07 (bug de Tukey, decisión Python-puro), §DD-03, §DD-04

---

## FASE 0 — Fundamentos

> C-01 y C-02 son estrictamente secuenciales: no hay nada que paralelizar hasta tener el scaffold y el contrato de datos.

### [C-01] `foundation-setup`
- **Estado**: `[x]` completado
- **Scope**:
  - Scaffold del repositorio exactamente como define el Anexo C de la tesis: `pipeline/` con los 5 módulos como stubs (`ingestion.py`, `validation.py`, `transformation.py`, `persistence.py`, `analysis.py` — firma de función definida, sin lógica), `config/` (`data_dictionary.json`, `analysis_config.yaml` como placeholders vacíos), `tests/`, `n8n_workflows/`, `docs/`
  - `requirements.txt` con versiones fijadas: pandas, numpy, great_expectations, statsmodels, scipy, matplotlib
  - `.env.example` documentando `DATABASE_URL` y demás variables inferidas (marcar explícitamente como supuesto de baja confianza, ver KB 08)
  - `README.md` con instrucciones de instalación (entorno virtual + `pip install -r requirements.txt`)
  - Tests: smoke test que importa los 5 módulos stub sin error
- **Dependencias**: ninguna
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios (Anexo C)
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-01 a DD-05
  - `knowledge-base/08_arquitectura_propuesta.md` §Variables de entorno

### [C-02] `data-dictionary-schema`
- **Estado**: `[x]` completado
- **Scope**:
  - Definir el schema JSON de `config/data_dictionary.json`: nombre canónico (`snake_case`), descripción, tipo de dato, unidad de medida, rango min/max, lista de valores admisibles, obligatoriedad, reglas de validación cruzada
  - Loader Python que parsea y valida el propio `data_dictionary.json` contra su meta-schema (rechaza diccionarios mal formados)
  - Dataset fixture **sintético** (NO el caso de estudio real) para poder testear ingestion/validation en paralelo sin bloquear por el caso de estudio pendiente
  - Tests: schema válido, schema inválido (falta campo obligatorio), tipos de dato incorrectos en la definición
- **Dependencias**: `C-01`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Diccionario de variables
  - `knowledge-base/05_reglas_de_negocio.md` §RN-VAL-01 a RN-VAL-08
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-04
  - `knowledge-base/10_preguntas_abiertas.md` (bloqueante: caso de estudio real aún no definido — usar solo fixture sintético en este change)

---

## FASE 1 — Pipeline de procesamiento core

> C-03 y C-04 se desarrollan en paralelo (GATE 1): ambos consumen el contrato `data_dictionary.json` de C-02 y el fixture sintético, no se necesitan mutuamente hasta la integración en C-08.

### [C-03] `ingestion-module`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/ingestion.py`: lectura de CSV/Excel (`pandas.read_csv`/`read_excel`)
  - Detección y reporte de problemas de codificación/formato antes de continuar (RN-ING-02)
  - Validación de estructura (nº de columnas, nombres con tolerancia configurable de capitalización/espaciado) contra `config/data_dictionary.json` (RN-ING-03)
  - Ante error estructural: detiene el pipeline, emite informe (archivo, fecha/hora, descripción) (RN-ING-04)
  - Invocable de forma independiente por CLI (DD-05 — desacoplado de n8n)
  - Tests: CSV válido, Excel válido, archivo corrupto, columnas faltantes/renombradas, encoding inválido
- **Dependencias**: `C-01, C-02`
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-001
  - `knowledge-base/05_reglas_de_negocio.md` §RN-ING-01 a RN-ING-04
  - `knowledge-base/07_flujos_principales.md` §Flujo 1, pasos 1-2
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-05

### [C-04] `validation-engine`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/validation.py` usando `great_expectations`
  - Expectation suite generada dinámicamente desde `config/data_dictionary.json`: tipo (RN-VAL-02), rango (RN-VAL-03), lista de valores (RN-VAL-04), unicidad de clave primaria (RN-VAL-05), completitud de obligatorios (RN-VAL-06)
  - Reglas de consistencia cruzada configurables entre pares/grupos de variables (RN-VAL-07)
  - Salida dual obligatoria: dataset de válidos + dataset de rechazados con detalle registro/campo/regla violada (RN-VAL-08)
  - Reporte de validación en HTML o JSON
  - Tests: registro válido, y un caso por cada tipo de violación (tipo, rango, lista, unicidad, completitud, cruzada) sobre el fixture sintético de C-02
- **Dependencias**: `C-02`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-002
  - `knowledge-base/05_reglas_de_negocio.md` §RN-VAL-01 a RN-VAL-08
  - `knowledge-base/04_modelo_de_datos.md` §Diccionario de variables
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-04

### [C-05] `transformation-module`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/transformation.py`
  - Procesa únicamente el dataset de registros válidos (RN-TRA-01)
  - Normalización de nombres de columna a `snake_case` sin caracteres especiales (RN-TRA-03)
  - Estandarización de categóricas vía tabla de correspondencias del catálogo (RN-TRA-04)
  - Conversión de unidades a la unidad canónica del diccionario cuando difiere (RN-TRA-05)
  - Construcción del dataset final en formato *tidy*, preservando identificadores jerárquicos del diseño experimental (RN-TRA-06)
  - Cada operación de transformación es atómica y queda documentada (nº registros afectados + muestra antes/después) para alimentar la bitácora de C-06 (RN-TRA-02)
  - Tests: normalización de nombres, estandarización categórica, conversión de unidad, formato tidy resultante, registro de operación atómica
- **Dependencias**: `C-03, C-04`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-003
  - `knowledge-base/05_reglas_de_negocio.md` §RN-TRA-01 a RN-TRA-06
  - `knowledge-base/07_flujos_principales.md` §Flujo 1, paso 5

### [C-11] `ocr-field-capture` (opcional — extensión de alcance)
- **Estado**: `[ ]` pendiente
- **Scope**:
  - Método de entrada **alternativo** para captura offline de datos de campo en papel vía **OCR zonal por plantilla** — no un pipeline paralelo: converge al mismo `pipeline/ingestion.py` (RN-OCR-07)
  - Generación de plantilla imprimible de layout fijo con zonas por campo del diccionario (`config/data_dictionary.json`), casilleros peine para numéricos, burbujas OMR para categóricos, marcadores fiduciales (ArUco/QR) en las esquinas (RN-OCR-01, RN-OCR-02)
  - Corrección de alineación/perspectiva vía detección de fiduciales (OpenCV `cv2.aruco` → homografía) antes de la extracción zonal
  - Extracción zonal (recorte a bounding boxes conocidas) + OCR por campo (Tesseract con whitelist de dígitos para peine; detección de relleno OMR para burbujas)
  - Doble señal de confianza: score del motor OCR + cross-check contra RN-VAL-02/03/04 (RN-OCR-03)
  - Paso de confirmación humana **por Telegram** (botones *inline*, workflow en pausa vía "Wait for Webhook") para lecturas de baja confianza, con registro de lectura original vs. confirmada en la bitácora (RN-OCR-04 **corregida por DD-09**, RN-OCR-06) — cuando C-13 esté disponible, esta confirmación es el flujo `confirmacion_ocr` de una sesión (ver C-13 y `knowledge-base/13_interaccion_telegram_y_sesiones.md`). Nota: la redacción anterior decía "por CLI (DD-05)"; quedó superada
  - Ejecución 100% local/offline; **prohibidas** las APIs de OCR en la nube (RN-OCR-05)
  - Normalización de la salida confirmada a la misma forma tabular que `pipeline/ingestion.py` espera de CSV/Excel; de ahí recorre el pipeline existente sin cambios
  - Tests: detección de fiduciales y corrección de perspectiva, extracción zonal correcta, OCR de dígitos en peine, detección OMR de burbuja rellena/vacía, cross-check que marca para revisión una lectura fuera de rango pese a alta confianza del motor, registro de confirmación humana en bitácora
  - **NOTA**: el motor OCR concreto (Tesseract vs. PaddleOCR) es pregunta abierta de prioridad Media — evaluar empíricamente con un prototipo de una sola variable antes del diseño completo (ver `knowledge-base/10_preguntas_abiertas.md`). Change opcional: no bloquea C-08 ni C-10; solo se implementa si el caso de estudio real confirma captura en papel.
- **Dependencias**: `C-02, C-03`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/12_captura_offline_ocr.md`
  - `knowledge-base/05_reglas_de_negocio.md` §RN-OCR-01 a RN-OCR-07 (y RN-VAL-02/03/04, RN-AUD-01/02, RN-IA-01/02/03 referenciadas)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-08 (y DD-05, DD-09 — la confirmación es por Telegram, no por CLI)
  - `knowledge-base/13_interaccion_telegram_y_sesiones.md` §3.2 (OCR como método de entrada dentro de una sesión)

---

## FASE 2 — Persistencia y análisis

### [C-06] `persistence-audit-module`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/persistence.py`
  - Esquema de base de datos (SQLite dev / PostgreSQL prod, mismo esquema en ambos motores — DD-03) para las entidades de dominio (Ensayo, Ambiente, Tratamiento, UnidadExperimental, Observación) y de sistema (Ejecución, BitácoraTransformación)
  - Stack concreto (DD-11): modelos declarativos de **SQLAlchemy ORM**, migraciones versionadas con **Alembic**, clave primaria **entero autoincremental** en todas las entidades, conexión configurada vía una única variable de entorno **`DATABASE_URL`** (`.env.example`)
  - Entidad Ambiente incluye `latitud`/`longitud` opcionales (DD-12) — sin uso funcional en v1, reservado para trabajo futuro (ver `knowledge-base/14_reuso_academico_y_geolocalizacion.md`)
  - Registro de Ejecución: id único, timestamps inicio/fin, hash del commit Git, hash SHA-256 del archivo de entrada, conteos leídos/válidos/rechazados/almacenados, errores/advertencias (RN-AUD-01)
  - Bitácora de transformaciones enlazada a cada Ejecución, que permite reconstruir el estado del dato en cualquier punto (RN-AUD-02)
  - Script/job de backup automático del dataset + bitácora + código a ubicación distinta del repositorio principal (RN-AUD-03)
  - Tests: persistencia del dataset transformado, reconstrucción del estado del dato desde la bitácora, paridad de esquema SQLite/PostgreSQL
- **Dependencias**: `C-01, C-05`
- **Governance**: CRITICO — es el módulo de audit trail y el modelo de sistema que toda la trazabilidad del pipeline referencia; sin este registro correcto, RN-AUD-02 (reconstrucción del dato) y la reproducibilidad (RN-GLB-02) quedan comprometidas.
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-004
  - `knowledge-base/05_reglas_de_negocio.md` §RN-AUD-01 a RN-AUD-03
  - `knowledge-base/04_modelo_de_datos.md` §Entidades Ejecución, Bitácora de transformaciones
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-03

### [C-07] `statistical-analysis-module`
- **Estado**: `[x]` completado
- **Scope**:
  - `pipeline/analysis.py`
  - Recibe como parámetros: id del dataset persistido, fórmula del modelo R-style (`statsmodels.formula.api.ols`), tipo de análisis (ANOVA, Kruskal-Wallis, GLM — LMM queda fuera de v1, ver nota), parámetros adicionales (nivel de significancia, método de comparación de medias) (RN-EST-01)
  - Tabla de resultados en CSV + HTML (RN-EST-02)
  - Diagnóstico de supuestos: normalidad de residuos (Shapiro-Wilk), homocedasticidad (Levene/Bartlett), apalancamiento/outliers, gráficos Q-Q y residuos-vs-ajustados en PNG vía matplotlib (RN-EST-03)
  - YAML de configuración que documenta exactamente qué se ejecutó, re-ejecutable con un único comando (RN-EST-04)
  - Invocable standalone sobre cualquier dataset ya almacenado, o encadenado al pipeline (RN-EST-05)
  - Tests: ANOVA sobre diseño DCA, ANOVA sobre diseño BCA, diagnóstico detecta violación de normalidad/homocedasticidad, reproducibilidad (misma entrada + mismo código → mismo output)
  - **NOTA**: extensión a modelos lineales mixtos (LMM) es pregunta abierta de prioridad Baja (§7.4 de la tesis) — no implementar en este change, dejar como extensión futura documentada
- **Dependencias**: `C-06`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-005
  - `knowledge-base/05_reglas_de_negocio.md` §RN-EST-01 a RN-EST-05
  - `knowledge-base/07_flujos_principales.md` §Flujo 3
  - `knowledge-base/09_decisiones_y_supuestos.md` §SU-02

---

## FASE 3 — Orquestación e IA de apoyo

> C-07, C-08 y C-09 se abren en fork desde GATE 4 (C-06 ✓). C-08 puede empezar a cablear los primeros 4 módulos de inmediato; el nodo de análisis se agrega cuando C-07 cierre. C-09 es opcional y no bloquea el camino crítico.

### [C-08] `n8n-orchestration-workflows`
- **Estado**: `[x]` completado
- **Scope**:
  - `n8n_workflows/` — export JSON del workflow completo: trigger (archivo nuevo detectado / programación horaria / invocación manual) → invoca `ingestion` → `validation` → `transformation` → `persistence` → (opcional) `analysis`
  - Reintentos automáticos con backoff exponencial ante fallos transitorios de infraestructura (RN-GLB-03)
  - Escalamiento a notificación humana cuando el fallo persiste
  - Logging de cada ejecución del workflow en n8n
  - Invocación de los módulos Python vía CLI, respetando el desacoplamiento de DD-05 (n8n nunca importa código Python directamente)
  - Tests: ejecución e2e sobre el fixture sintético de C-02, simulación de fallo transitorio con reintento exitoso, simulación de fallo persistente con notificación
  - **NOTA / BLOQUEANTE PARCIAL**: la pregunta de prioridad Alta "¿el sistema necesita una interfaz de usuario propia además del dashboard nativo de n8n?" (`knowledge-base/10_preguntas_abiertas.md`) sigue sin resolver. Este change asume que **no** (interacción vía archivos + n8n UI nativo, consistente con el Alcance v1.0). Si el equipo de tesis decide que sí se requiere UI propia, hace falta un change adicional no contemplado en el Anexo C — no lo asumas ni lo implementes acá.
- **Dependencias**: `C-03, C-04, C-05, C-06, C-07`
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/02_descripcion_general.md` §Arquitectura general (capa de orquestación)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-GLB-01 a RN-GLB-03
  - `knowledge-base/07_flujos_principales.md` §Flujo 1
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-02
  - `knowledge-base/10_preguntas_abiertas.md` (pregunta Alta: necesidad de UI propia)

### [C-09] `ai-support-standardization` (opcional — Épica 6)
- **Estado**: `[ ]` pendiente
- **Scope**:
  - Componente de sugerencia: estandarización léxica de categóricas con alta variabilidad, detección de anomalías estadísticas
  - Proveedor LLM/IA concreto queda sin definir en la tesis (pregunta Media prioridad) — implementar detrás de una interfaz *pluggable* con un provider mock por defecto, para no bloquear el resto del pipeline
  - Ningún cambio se aplica de forma autónoma (RN-IA-01); toda sugerencia requiere aprobación humana explícita antes de aplicarse (RN-IA-02)
  - Aprobación o rechazo, con justificación, queda registrado en la bitácora de auditoría vía `pipeline/persistence.py` (RN-IA-03)
  - Un cambio aprobado se aplica únicamente a través de `pipeline/transformation.py`, nunca directo desde el componente de IA
  - Tests: sugerencia generada + aprobada se refleja en dataset y bitácora; sugerencia rechazada no modifica el dataset; intento de aplicar sin aprobación falla explícitamente
  - **NOTA**: proveedor de IA/LLM no definido (pregunta Media prioridad) — este change puede posponerse sin bloquear C-08 ni C-10, la tesis lo marca como Épica opcional con supervisión
- **Dependencias**: `C-05, C-06`
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` §US-006
  - `knowledge-base/05_reglas_de_negocio.md` §RN-IA-01 a RN-IA-03
  - `knowledge-base/07_flujos_principales.md` §Flujo 4
  - `knowledge-base/10_preguntas_abiertas.md` (pregunta Media: proveedor de IA/LLM)

### [C-12] `session-engine` (opcional — refinamiento de interacción, DD-09)
- **Estado**: `[ ]` pendiente
- **Scope**:
  - Motor genérico de máquina de estados de sesión, **dirigido por datos**, sobre la capa de persistencia existente (C-06) — no un almacén separado (RN-SES-02)
  - Nueva entidad de sistema `sesion` (`session_id`, `telegram_user_id`, `ensayo_id` nullable, `tipo_sesion`, `paso_actual`, `respuestas_acumuladas`, `estado`, timestamps) agregada al esquema SQLite/PostgreSQL de C-06
  - Secuencia de pasos de cada `tipo_sesion` definida como **configuración/datos** (lista ordenada de definiciones de pregunta: prompt, tipo esperado `texto`/`numero`/`foto`/`choice`, referencia a RN-VAL/diccionario), NO como código (RN-SES-03)
  - *Resolver* genérico: dado un `telegram_user_id`, busca sesión abierta → si existe, valida/almacena/avanza el paso; si no, resuelve el `tipo_sesion` por rol y crea sesión en paso 0 (RN-SES-04). La reanudación sale gratis de esta búsqueda
  - Validación por paso (RN-SES-05) y registro de cada evento de sesión en la bitácora (RN-SES-06, liga con RN-AUD)
  - Manejo de estados `expirada`/`abandonada` (RN-SES-07) — contemplar los estados desde el inicio; el umbral exacto de timeout es pregunta abierta (no lo fijes unilateralmente)
  - Testeable de forma aislada contra la base de datos, **sin** depender de Telegram (Telegram es C-13)
  - Tests: creación de sesión, avance de paso con respuesta válida, rechazo de respuesta inválida (no avanza), reanudación de sesión abierta existente, resolución de tipo por rol, finalización al último paso, transición a expirada/abandonada
  - **NOTA**: el formato concreto de la config de pasos (JSON con schema propio / tabla en BD / YAML) y la duración del timeout son preguntas abiertas de prioridad Media/Baja (ver `knowledge-base/10_preguntas_abiertas.md`). Change opcional: no bloquea el camino crítico
- **Dependencias**: `C-06`
- **Governance**: MEDIO — agrega una entidad a la capa de persistencia (C-06 es CRITICO), pero el motor en sí es lógica de estado/negocio testeable de forma aislada; su auditoría de eventos (RN-SES-06) debe respetar la cadena de custodia de RN-AUD
- **Leer antes**:
  - `knowledge-base/13_interaccion_telegram_y_sesiones.md` §4 (motor genérico de sesiones) y §5 (catálogo de eventos)
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SES-01 a RN-SES-07 (y RN-VAL-02/03/04, RN-AUD-01/02 referenciadas)
  - `knowledge-base/04_modelo_de_datos.md` §Entidades de sistema (la `sesion` se agrega aquí)
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-09

### [C-13] `telegram-interaction-layer` (opcional — refinamiento de interacción, DD-09)
- **Estado**: `[ ]` pendiente
- **Scope**:
  - Cableado del **nodo Telegram nativo de n8n**: envío (mensajes, fotos, botones *inline*) + Telegram Trigger (mensajes entrantes y *callbacks* de botón) (RN-SES-01)
  - **Único loop genérico** de n8n que consume el motor de sesiones de C-12: mensaje entrante → resolver sesión → prompt siguiente (RN-SES-04); NO un árbol de conversación hardcodeado por rol
  - RBAC mínimo `telegram_user_id → rol` (`ingeniero` | `ayudante`), acotado por `ensayo_id` cuando corresponde (ver `knowledge-base/03_actores_y_roles.md` §RBAC)
  - Flujo `setup_ensayo` (Ingeniero): construye `config/data_dictionary.json` y `config/analysis_config.yaml` a partir de las respuestas guiadas (Flujo 5) — la decisión sigue siendo experta, sólo cambia el medio de entrega
  - Flujo `carga_dato` (Ayudante): pide dato campo por campo, ofrece texto o **foto para OCR**; la foto se integra con C-11 (RN-OCR) como método de entrada dentro de la sesión (Flujo 6)
  - Confirmaciones *human-in-the-loop* asíncronas (`confirmacion_ocr`/`confirmacion_ia`): mensaje con botones → workflow **en pausa** (n8n "Wait for Webhook") → clic → **reanuda** con el valor confirmado → bitácora (Flujo 7). **Reemplaza** la confirmación "por CLI" de la redacción anterior de RN-OCR-04 (ahora corregida a Telegram)
  - Notificación de resultados al ingeniero + elección de autoría del reporte (RN-EST-07)
  - Escalamiento por Telegram de fallos persistentes (RN-GLB-03, canal concreto)
  - Tests (e2e sobre el fixture sintético de C-02, simulando eventos de Telegram): setup guiado completo genera los config files, carga por texto, carga por foto que dispara confirmación bajo umbral, confirmación por botón reanuda el workflow, RBAC rechaza a un ayudante intentando setup, escalamiento por Telegram
  - **NOTA / relación con capacidades opcionales**: C-13 se relaciona con **C-11** (OCR) — el OCR es un método de entrada dentro de una sesión, no un sistema paralelo; y con **C-09** (IA) — las confirmaciones de IA usan el mismo mecanismo de sesión. Change opcional: no bloquea C-10 ni el camino crítico
  - **NOTA de confidencialidad (DD-09)**: los chats de bot de Telegram NO son E2E; cifrado en tránsito pero no confidencialidad nivel Signal. Documentado honestamente — considerar la sensibilidad del dato (tensión con RN-OCR-05/§3.7) al desplegar
- **Dependencias**: `C-08, C-12` (se relaciona con `C-09` y `C-11`)
- **Governance**: ALTO — maneja el RBAC (autorización de aplicación) y es la superficie humana única del sistema + inyección de configuración de ensayos; cablea orquestación (como C-08). Proponer y revisar antes de escribir wiring que afecte config de usuario
- **Leer antes**:
  - `knowledge-base/13_interaccion_telegram_y_sesiones.md` (completo)
  - `knowledge-base/03_actores_y_roles.md` §Roles operativos y §RBAC
  - `knowledge-base/05_reglas_de_negocio.md` §RN-SES, §RN-OCR-04 (corregida), §RN-EST-07, §RN-GLB-03
  - `knowledge-base/07_flujos_principales.md` §Flujos 5, 6, 7
  - `knowledge-base/09_decisiones_y_supuestos.md` §DD-09 (y DD-05, DD-02, DD-08)
  - `knowledge-base/10_preguntas_abiertas.md` (preguntas de C-12/C-13: timeout, formato de config, sub-permisos, default de reporte)

---

## FASE 4 — Validación empírica (bloqueada)

> Esta fase es el bloqueante central de la tesis (ver `knowledge-base/10_preguntas_abiertas.md`, inconsistencia IN-01): el Capítulo 5 (Resultados) está vacío hasta que exista evidencia real. Pero **no se puede empezar a implementar C-10 sin que el equipo de tesis resuelva 3 preguntas de prioridad Alta primero**. No las resuelvas de forma unilateral.

### [C-10] `case-study-evaluation`
- **Estado**: `[ ]` pendiente — **⚠ BLOQUEADO, no asignar a ningún agente todavía**
- **Scope**:
  - Selección del caso de estudio real (ensayo agrícola concreto, institución, cultivo) y relevamiento del diccionario de variables definitivo junto a expertos de dominio agronómico — **BLOQUEADO** por pregunta Alta prioridad sin resolver
  - Definición de quién ejecuta la línea base manual y con qué datos, para poder comparar en §5.3 — **BLOQUEADO** por pregunta Alta prioridad sin resolver
  - Ejecución del pipeline completo (C-01 a C-08) sobre los datos reales del caso de estudio una vez definido
  - Medición de métricas operativas: tiempo total de procesamiento, tasa de error detectado, completitud del dataset, consistencia del dataset (§3.6)
  - Comparación automatizado vs. manual para verificar H1 (tasa de error residual menor), H2 (≥50% reducción de tiempo), H3 (mejora de auditabilidad/trazabilidad)
  - Completar Cap. 5 de la tesis (§5.1, §5.2, §5.3) y el diagrama de arquitectura definitivo (Anexo B) con evidencia real
- **Dependencias**: `C-08`
- **Governance**: CRITICO — análisis únicamente; no se escribe código de este change sin aprobación explícita del equipo de tesis (4 autores) + director sobre las 3 preguntas de prioridad Alta involucradas
- **Leer antes**:
  - `knowledge-base/10_preguntas_abiertas.md` (completo — 3 preguntas Alta prioridad + inconsistencia IN-01)
  - `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito, §Hipótesis H1-H3
  - `knowledge-base/09_decisiones_y_supuestos.md` §SU-01, §SU-04

---

## Resumen

| Change | Fase | Governance | Dependencias | Estado |
|--------|------|------------|---------------|--------|
| C-00b anova-tukey-core | PRE | MEDIO | — | `[x]` |
| C-01 foundation-setup | 0 | BAJO | — | `[x]` |
| C-02 data-dictionary-schema | 0 | MEDIO | C-01 | `[x]` |
| C-03 ingestion-module | 1 | BAJO | C-01, C-02 | `[x]` |
| C-04 validation-engine | 1 | MEDIO | C-02 | `[x]` |
| C-05 transformation-module | 1 | MEDIO | C-03, C-04 | `[x]` |
| C-06 persistence-audit-module | 2 | CRITICO | C-01, C-05 | `[x]` |
| C-07 statistical-analysis-module | 2 | MEDIO | C-06 | `[x]` |
| C-08 n8n-orchestration-workflows | 3 | ALTO | C-03, C-04, C-05, C-06, C-07 | `[x]` |
| C-09 ai-support-standardization (opcional) | 3 | ALTO | C-05, C-06 | `[ ]` |
| C-10 case-study-evaluation | 4 | CRITICO | C-08 | `[ ]` ⚠ BLOQUEADO |
| C-11 ocr-field-capture (opcional) | 1 | MEDIO | C-02, C-03 | `[ ]` |
| C-12 session-engine (opcional) | 3 | MEDIO | C-06 | `[x]` |
| C-13 telegram-interaction-layer (opcional) | 3 | ALTO | C-08, C-12 | `[ ]` |

**Camino crítico**: 9 changes (C-01, C-02, C-03, C-04, C-05, C-06, C-07, C-08, C-10 — C-09, C-11, C-12 y C-13 son opcionales, fuera del camino crítico).
**Gates de paralelismo**: 5 (GATE 0 a GATE 4; GATE 5 abre C-10 —bloqueado— y C-13).
**Primer change recomendado**: `C-01` (foundation-setup).

Para arrancar: `/opsx:propose C-01-foundation-setup`
