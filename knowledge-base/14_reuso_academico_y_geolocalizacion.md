# Reuso Académico del Dataset y Correlación Climática por Geolocalización

> **Origen de este archivo**: idea del usuario, identificada como ausente de la tesis y de la base de conocimiento en una revisión explícita. Documenta dos líneas de investigación futura relacionadas entre sí, **ninguna construida todavía**: (a) darle valor de investigación académica al dataset acumulado por el sistema más allá del propósito inmediato de cada ensayo individual, y (b) usar la geolocalización de Ambiente (`04_modelo_de_datos.md`, DD-12) para correlacionar resultados con datos climáticos externos. Es trabajo futuro (§7.4 de la tesis), no una capacidad en construcción — no tiene change asignado en `CHANGES.md`.

## Por qué existen estas dos ideas

El sistema, tal como está diseñado, procesa cada ensayo de forma individual: ingesta, valida, transforma, persiste y analiza un ensayo a la vez, con foco en producir el reporte de ese ensayo puntual. Pero la persistencia auditable (RN-AUD, change C-06) tiene un efecto secundario valioso que la tesis no explota todavía: con el tiempo, el sistema acumula un dataset multi-ensayo, multi-campaña, con trazabilidad completa y calidad de dato garantizada por el mismo pipeline de validación. Ese acumulado tiene un valor que ningún ensayo individual tiene por sí solo.

Dos usos concretos de ese valor:

### 1. Reuso académico del dataset acumulado

Un dataset multi-ensayo con trazabilidad completa habilita preguntas de investigación que un ensayo individual no puede responder: meta-análisis entre campañas y sitios, comparación de tratamientos a través de contextos institucionales distintos, y una base de entrenamiento/validación confiable para los componentes de IA que la tesis ya contempla como épica opcional (`05_reglas_de_negocio.md`, dominio RN-IA). Es, además, un aporte genuino más allá del sistema en sí: el sistema no solo automatiza un proceso, también genera un activo de investigación reutilizable.

### 2. Correlación climática vía geolocalización

Con `Ambiente.latitud` y `Ambiente.longitud` disponibles (DD-12), un análisis futuro podría cruzar los resultados de cada ensayo contra datos climáticos externos de la zona (temperatura, precipitación, humedad) para explicar parte de la varianza residual que el diseño de bloqueo no captura — una fuente de variación ambiental real en ensayos agrícolas, distinta del efecto de bloque. Esto también habilita análisis propiamente espacial (SIG): mapear variabilidad de resultados por región, cruzar contra capas de suelo o clima de terceros.

## Por qué NO se construye ahora

Dos razones, ambas ya discutidas con el equipo:

- **Tensión con la confidencialidad ya establecida (§3.7)**: el reuso académico de datos más allá del propósito para el que fueron cargados requiere autorización explícita de la institución titular de cada ensayo — no es automático ni gratuito. Habilitar esto de verdad exige diseñar un mecanismo de consentimiento/licenciamiento por ensayo (quién autoriza, qué alcance tiene la autorización, cómo se audita), que hoy no existe y que tiene nivel de gobernanza alto por tocar control de acceso a datos.
- **Prioridad y secuencia**: el camino crítico de la tesis (9 changes) todavía no arrancó y el Capítulo 5 sigue bloqueado por la elección del caso de estudio real. Construir una capacidad nueva —por más valiosa que sea— que no es necesaria para cerrar la tesis compite por la misma atención del equipo que hoy necesita el camino crítico.

## Qué SÍ se hizo ahora

Se agregó el campo de geolocalización a la entidad Ambiente (DD-12) porque el costo de agregarlo en este momento —antes de que el diccionario de variables y el esquema de persistencia estén construidos— es marginal, mientras que agregarlo después de tener datos reales cargados sería una migración de esquema. El campo queda disponible, sin uso funcional en v1, como una apuesta de bajo costo sobre un valor de investigación futuro.

## Qué haría falta para construir esto de verdad (alcance, no comprometido)

Para que el reuso académico sea una capacidad real y no solo una idea:

- Un mecanismo de autorización por ensayo (¿quién de la institución titular autoriza?, ¿qué alcance tiene: solo agregados/estadísticas, o el dato crudo?), probablemente materializado como un atributo nuevo en la entidad Ensayo y una pregunta más en el flujo de setup guiado por Telegram (`13_interaccion_telegram_y_sesiones.md`).
- Un módulo de consulta/exportación que opere **a través de** varios ensayos — hoy ningún módulo del sistema tiene esa capacidad; todo el acceso está diseñado ensayo por ensayo.
- Gobernanza alta o crítica, dado que toca control de acceso a datos con implicancias fuera del sistema (autorización legal/institucional, no solo técnica).

Para que la correlación climática sea una capacidad real:

- Elegir una fuente de datos climáticos externa (por ejemplo, un servicio de reanálisis climático o una red de estaciones meteorológicas del área del caso de estudio) — pregunta abierta, no evaluada todavía.
- Un módulo nuevo que consuma esa fuente externa por coordenada y fecha, y lo integre como covariable opcional del módulo de análisis estadístico (`pipeline/analysis_core.py`), sin romper el análisis existente cuando no hay geolocalización disponible.

## Preguntas abiertas específicas

Se agregan a `10_preguntas_abiertas.md`: mecanismo de autorización/consentimiento por ensayo para reuso académico, fuente de datos climáticos a integrar, y si corresponde tratar esto como un change opcional futuro (post-tesis) o como una línea de investigación que queda fuera del alcance de cualquier change.
