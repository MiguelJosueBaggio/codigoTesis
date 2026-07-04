# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — Modelo ETL en vez de ELT
**Decisión**: el pipeline sigue el modelo ETL (extraer → transformar → cargar), no ELT.
**Contexto**: había que elegir entre transformar antes o después de cargar al repositorio destino.
**Alternativas consideradas**: ELT (cargar primero, transformar en el almacén destino).
**Justificación**: volúmenes moderados (miles a decenas de miles de registros/campaña), transformaciones con lógica de dominio agronómico compleja, y la separación transformación/carga permite control granular de calidad antes de persistir (§2.3).
**Trade-offs aceptados**: menos aprovechamiento de cómputo del almacén destino, pero mayor control de calidad pre-carga.

### DD-02 — n8n como orquestador (no Airflow/Prefect)
**Decisión**: usar n8n para la capa de orquestación.
**Contexto**: existen alternativas de orquestación más "enterprise" (Apache Airflow, Prefect).
**Alternativas consideradas**: Airflow, Prefect.
**Justificación**: menor curva de aprendizaje, despliegue simple en local/nube pequeña, interfaz visual accesible a usuarios con perfiles técnicos distintos, capacidades suficientes para los requisitos (triggers, reintentos, logs, integración con Python) (§2.3).
**Trade-offs aceptados**: menor capacidad de orquestación compleja/distribuida a gran escala frente a Airflow.

### DD-03 — SQLite en desarrollo, PostgreSQL en producción
**Decisión**: persistencia dual según entorno.
**Contexto**: se necesitaba una tecnología de persistencia que satisficiera requisitos de volumen/concurrencia/portabilidad sin complejidad operativa innecesaria (§4.2).
**Justificación**: SQLite no requiere infraestructura de servidor para desarrollo/pruebas; PostgreSQL cubre concurrencia y volumen en producción.
**Trade-offs aceptados**: necesidad de mantener compatibilidad de esquema/queries entre ambos motores.

### DD-04 — Validación declarativa con `great_expectations`
**Decisión**: las reglas de validación se expresan en JSON serializable vía `great_expectations`, no como código Python imperativo ad hoc.
**Justificación**: reglas inspeccionables/auditables por alguien sin necesidad de leer el código Python; ejecutables directamente sobre DataFrames de pandas; reportes HTML/JSON automáticos (§4.4).

### DD-05 — Capa de procesamiento desacoplada de n8n
**Decisión**: los scripts Python del pipeline son invocables directamente por CLI, independientes de n8n.
**Justificación**: permite pruebas/desarrollo sin levantar el orquestador; permite integrar con orquestadores alternativos sin modificar el código de procesamiento (§4.2).

### DD-06 — IA como apoyo supervisado, nunca autónomo
**Decisión**: los componentes de IA (estandarización léxica, detección de anomalías) solo generan sugerencias; ningún cambio se aplica sin aprobación humana explícita registrada en bitácora.
**Justificación**: preservar la integridad epistémica del proceso científico — cambios no auditables al dato invalidarían la reproducibilidad (§2.6).

### DD-07 — Tukey HSD en diseños bloqueados: no usar `pairwise_tukeyhsd` directo
**Decisión**: la comparación de medias post-ANOVA (Tukey HSD) para diseños con bloqueo (RCBD) se calcula manualmente a partir del `MS_error` del modelo completo (bloque + tratamiento) + `statsmodels.stats.libqsturng.psturng` — nunca vía `pairwise_tukeyhsd(endog, groups)` directo sobre los grupos crudos. **Implementación construida (resuelve la pregunta abierta que antes figuraba aquí)**: se eligió y construyó la **Opción A, Python puro vía `psturng`** — función `tukey_hsd` en `pipeline/analysis_core.py`, validada con 45 pruebas automáticas. La alternativa por R/`rpy2` (Opción B) queda documentada abajo como alternativa considerada, no como pendiente de decisión.
**Contexto**: validación cruzada (Método 1 vs. 2 vs. 3, ver `11_analisis_estadistico_anova_tukey.md`) sobre el dataset de referencia `npk` (Fisher/Rothamsted) mostró que `pairwise_tukeyhsd` da p=0.0221 mientras que el cálculo correcto (y la ANOVA bloqueada) da p=0.0071 — una discrepancia sustantiva, no un redondeo.
**Alternativas consideradas**: usar `pairwise_tukeyhsd` tal cual (descartado — matemáticamente incorrecto para RCBD); usar `rpy2` + R `TukeyHSD` (viable, agrega dependencia de R).
**Justificación**: la corrección matemática del resultado estadístico es el requisito no negociable de esta tesis (RNF de reproducibilidad y correctitud, §4.1) — un Tukey HSD incorrecto invalidaría cualquier conclusión de comparación de medias reportada en el Capítulo 5.
**Trade-offs aceptados**: la Opción A (Python puro) requiere una función custom en vez de una librería estándar lista para usar; queda como código propio a testear exhaustivamente (test de regresión con el fixture `npk`, ver `11_analisis_estadistico_anova_tukey.md`).

### DD-08 — Captura offline en papel vía OCR zonal por plantilla (no OCR libre, no nube, no captura móvil)
**Decisión**: para habilitar la captura de datos a campo cuando el origen es papel, se adopta **OCR zonal basado en plantilla de layout fijo** (zonas conocidas + casilleros peine para numéricos + OMR para categóricos + marcadores fiduciales), ejecutado local y offline, con confirmación humana para lecturas de baja confianza. Es una capacidad opcional que converge al módulo de ingesta existente (`pipeline/ingestion.py`), no un pipeline paralelo. Ver `12_captura_offline_ocr.md` y el dominio RN-OCR en `05_reglas_de_negocio.md`. **Nota (DD-09)**: la confirmación humana, que en la redacción original de DD-08/RN-OCR-04 era "por CLI", se materializa ahora **por Telegram** (ver DD-09 y `13_interaccion_telegram_y_sesiones.md`); el resto de DD-08 (OCR zonal, offline, convergencia a ingesta) permanece intacto.
**Contexto**: el alcance v1.0 (`01_vision_y_objetivos.md`, §Fuera de alcance; §1.8 de la tesis) asume entrada CSV/Excel ya estructurada. Pero las condiciones reales de campo —conectividad no confiable y ausencia de dispositivos digitales durables en el punto de captura— hacen que la planilla de papel sea a menudo la única opción práctica; el paso de transcripción manual a CSV quedaba fuera del sistema, sin trazabilidad.
**Alternativas consideradas**: (a) OCR general de texto libre sin plantilla — descartado por baja confiabilidad, en especial con manuscritos; (b) APIs de OCR en la nube (Google Document AI, AWS Textract, Azure Form Recognizer) — descartadas pese a su mayor precisión bruta, por el requisito offline y la confidencialidad del dato del ensayo (§3.7); (c) captura digital en el momento de la toma vía tablet/formularios móviles (ODK/KoboToolbox) — primera alternativa evaluada y más simple en abstracto, descartada porque no resuelve el problema real (fragilidad de dispositivos y conectividad a campo — el papel es el *fallback* más robusto).
**Justificación**: el diseño estructurado de la plantilla (peine + OMR + fiduciales) reduce la dificultad del reconocimiento a un nivel que las herramientas locales cubren bien, evitando la nube. La doble señal de confianza (motor OCR + cruce contra RN-VAL) y la confirmación humana (filosofía RN-IA) mantienen la captura bajo las mismas garantías de auditoría (RN-AUD) que el resto del pipeline, preservando la cadena de custodia del dato desde el papel.
**Trade-offs aceptados**: se resigna la mayor precisión bruta de las APIs de nube y la comodidad de la captura móvil; a cambio se gana robustez a campo, confidencialidad y trazabilidad. Requiere diseñar e imprimir una plantilla física por caso de estudio y construir código propio de extracción zonal (no hay librería lista para usar end-to-end), a testear con un prototipo antes del diseño completo (ver `10_preguntas_abiertas.md`).

### DD-09 — Interacción cero-CLI: Telegram + eventos como único canal humano (refina/supersede DD-05)

**Decisión**: el usuario final **no tiene ninguna interacción directa con la CLI ni con ninguna interfaz técnica**. El sistema completo es 100% orientado a eventos, orquestado por n8n, con **Telegram como único punto de contacto humano** — tanto para notificaciones como para confirmaciones interactivas y carga de datos. La CLI sigue existiendo, pero **exclusivamente como mecanismo interno con que n8n invoca los módulos `pipeline/*.py`** — nunca algo que un humano teclee. Se introducen dos roles (**Ingeniero**, **Ayudante**) y un **motor genérico de sesiones dirigido por datos** respaldado por la base de datos. Ver `13_interaccion_telegram_y_sesiones.md` y el dominio RN-SES en `05_reglas_de_negocio.md`.

**Relación con DD-05 (explícita — no se sobrescribe en silencio)**: **DD-09 refina y supersede parcialmente a DD-05**. DD-05 estableció "capa de procesamiento desacoplada de n8n, invocable por CLI" y, junto con la resolución de la pregunta "¿UI propia?" en `10_preguntas_abiertas.md`, se había leído como *"CLI-first / sin web UI"*. DD-09 **mantiene** dos cosas de DD-05: (1) **no hay web UI propia**, y (2) **el desacoplamiento CLI de la capa de procesamiento sigue intacto** (n8n invoca `pipeline/*.py` por CLI, testeable sin orquestador). Lo que DD-09 **reemplaza** es la premisa de que un humano usa esa CLI: pasa de *"CLI-first" (el usuario opera por CLI)* a *"cero interacción directa del usuario; Telegram + eventos; la CLI es interna de n8n"*. En consecuencia, **RN-OCR-04 se corrige** (la confirmación humana ya no es "por CLI" sino por Telegram) y varios flujos de `07_flujos_principales.md` se reexpresan como orientados a eventos.

**Contexto**: los actores reales del proyecto (incluidos ayudantes de campo con sólo un teléfono, ver `12_captura_offline_ocr.md`) no pueden razonablemente operar una terminal. La lectura CLI-first presuponía humanos frente a una consola editando `analysis_config.yaml` a mano (Flujo 3) o corriendo comandos de confirmación (RN-OCR-04). El refinamiento elimina esa fricción sin agregar un componente arquitectónico nuevo, apoyándose en el nodo Telegram nativo de n8n.

**Alternativas consideradas**:
- **Mantener CLI-first (DD-05 tal cual)** — descartado: irrealista para ayudantes de campo; deja la interacción humana fuera de un canal auditable y cómodo.
- **WhatsApp Business API** como canal humano — descartado: requiere verificación de negocio, potenciales costos por conversación y ventanas de 24h para *template messages*. Telegram no impone ninguna de esas fricciones y tiene nodo nativo en n8n.
- **Construir una web UI propia** — descartado: contradice el "no web UI" que se conserva de DD-05; agrega una capa no contemplada en el Anexo C.
- **Hardcodear un árbol de conversación por rol en n8n** (rama distinta por rol/paso dentro del grafo del workflow) — descartado por costo de construcción y mantenimiento: cada tipo de pregunta nuevo obligaría a modificar el grafo del workflow. Se adopta en su lugar el **motor genérico de sesiones dirigido por datos** (secuencia de pasos como configuración, un único loop genérico en n8n; ver RN-SES-03/04).

**Justificación**: Telegram entra como trigger/salida más dentro de la orquestación ya existente (DD-02), sin backend de mensajería propio; es gratuito, soporta botones *inline* (ideales para el patrón confirmar/rechazar de RN-IA/RN-OCR) y su mecanismo "Wait for Webhook" de n8n hace viable el *human-in-the-loop* asíncrono (pausar el workflow hasta el clic del usuario). El motor genérico de sesiones reduce el costo marginal de agregar flujos nuevos (flujo nuevo = datos de configuración, no código de workflow).

**Trade-offs aceptados**:
- **Confidencialidad parcial, documentada honestamente**: los chats de **bots** de Telegram **NO son end-to-end encrypted** (el E2E de Telegram es sólo para "Secret Chats", donde los bots no participan). El tráfico está cifrado en tránsito y no expuesto públicamente —mejor que un canal abierto o email sin cifrar— pero **NO** es confidencialidad nivel Signal. Esto es una tensión consciente con la sensibilidad del dato que motivó prohibir el OCR en la nube (RN-OCR-05, §3.7): se acepta el matiz por el beneficio operativo, pero se registra como lo que es, sin sobrevender.
- **Costo único del motor genérico**: el patrón de sesiones dirigido por datos reduce N costos incrementales futuros a cambio de **un costo fijo inicial** (construir la tabla `sesion`, el *resolver* de "paso siguiente"/"tipo de sesión", y el manejo de timeout/abandono). Es un intercambio favorable para un sistema que crecerá en tipos de interacción, pero **no es gratis**.
- **Frontera de la automatización**: el setup inicial de un ensayo (fórmula del modelo, diseño experimental, diccionario) sigue siendo una decisión experta irreductible (coherente con "el sistema procesa, no diseña, ensayos", `01_vision_y_objetivos.md`). DD-09 sólo automatiza **cómo** el experto entrega esa configuración (conversación guiada por Telegram en vez de editar JSON/YAML), no el juicio en sí.

### DD-10 — Parámetros concretos del motor de sesiones y RBAC (resuelve preguntas abiertas de DD-09)

**Decisión**: se fijan cuatro parámetros que DD-09 había dejado abiertos:
1. **Timeout de sesión** (RN-SES-07): **24 horas**, uniforme para los cuatro `tipo_sesion` (no diferenciado por rol).
2. **Formato de configuración de pasos** (RN-SES-03): **JSON en base de datos**, tabla `config_paso_sesion` (una fila por paso), no archivo YAML versionado ni tabla relacional rígida.
3. **Sub-permisos del rol Ingeniero**: **no se implementan** para el alcance de esta tesis; el rol Ingeniero se mantiene único (sin volver a separar Estadístico/Experto de dominio de cara al bot). Queda anotado como extensión posible en §7.4 (trabajo futuro).
4. **Default de autoría del reporte** (RN-EST-07): el reporte auto-generado se entrega **siempre**, sin esperar la elección del ingeniero; no hay *deadline* para que elija redactar su propia narrativa.

**Contexto**: `13_interaccion_telegram_y_sesiones.md` (§4.6, §4.3) y `10_preguntas_abiertas.md` dejaban estos cuatro puntos explícitamente pendientes tras diseñar DD-09. Se resolvieron en conjunto porque las cuatro son decisiones de parámetro/alcance sobre el mismo subsistema (motor de sesiones + RBAC), no decisiones arquitectónicas nuevas.

**Alternativas consideradas**:
- Timeout diferenciado por `tipo_sesion` (ej. 1h para setup del ingeniero, 24-48h para carga a campo) — más realista respecto a las condiciones de conectividad, mayor precisión, pero se descartó por ahora a favor de la regla única para no sumar parámetros a justificar; queda como refinamiento posible si la evidencia de campo lo pide.
- Timeout corto y uniforme (30-45 min) — mejor higiene de datos, pero riesgo alto de expirar sesiones en medio de un corte de señal real a campo (escenario esperable en el caso de estudio).
- Configuración de pasos en YAML versionado en git — más auditable en Pull Requests, pero requiere deploy para cualquier cambio de flujo, contradiciendo el espíritu de "la secuencia es dato" (§4.3 de `13_interaccion_telegram_y_sesiones.md`).
- Configuración de pasos en tabla relacional normalizada (una fila tipada por paso) — más consultable por SQL estándar, pero más rígida ante metadata de paso no anticipada.
- Separar de nuevo Estadístico/Experto de dominio como roles distintos de cara al bot — más fiel a `03_actores_y_roles.md` original, pero sobre-ingeniería para un equipo chico y un único caso de estudio; sumaría un segundo flujo de setup guiado sin necesidad probada.
- Deadline explícito (ej. 24h) para la elección de autoría del reporte, con caída automática al modo auto-generado — más prolijo metodológicamente, pero suma un segundo timeout a justificar junto con el de RN-SES-07, sin necesidad real (el reporte auto-generado ya se entrega igual).

**Justificación**: en las cuatro decisiones se priorizó **simplicidad de implementación y de justificación en la tesis** por sobre precisión/flexibilidad máxima, dado que el alcance es un caso de estudio único con un equipo reducido — consistente con el criterio ya aplicado en DD-02 (n8n sobre Airflow) y DD-03 (SQLite/PostgreSQL): la complejidad se agrega cuando hay evidencia real que la pida, no por adelantado.

**Trade-offs aceptados**:
- Sesiones abandonadas pueden quedar "vivas" hasta 24h (vs. un timeout diferenciado más ajustado por tipo).
- El RBAC no distingue autoridad de configuración estadística vs. de dominio agronómico dentro del rol Ingeniero — si el caso de estudio real exige esa separación, habrá que extender RBAC y el flujo de `setup_ensayo` (ver pregunta de baja prioridad en `10_preguntas_abiertas.md`).

### DD-11 — Stack concreto de persistencia: SQLAlchemy ORM + Alembic, PK autoincremental, `DATABASE_URL` única

**Decisión**: se fijan cuatro parámetros técnicos de la capa de persistencia (`pipeline/persistence.py`, change C-06) que quedaban implícitos o sin decidir tras DD-03:
1. **Capa de acceso a datos**: **SQLAlchemy ORM** (modelos declarativos), no SQLAlchemy Core ni SQL crudo por motor.
2. **Versionado de esquema**: **Alembic**, con migraciones versionadas en el repositorio.
3. **Estrategia de clave primaria**: **entero autoincremental** (`INTEGER PRIMARY KEY` / `SERIAL`) para todas las entidades del modelo (Ensayo, Ambiente, Tratamiento, UnidadExperimental, Observación, Ejecución, Sesión), no UUID.
4. **Variables de entorno de conexión**: **una única `DATABASE_URL`** con el connection string completo, documentada en `.env.example`, en vez de variables separadas por componente (`DB_HOST`/`DB_PORT`/etc.). Resuelve la pregunta abierta de prioridad Media sobre nombres de variables de entorno.

**Contexto**: DD-03 estableció "SQLite en desarrollo, PostgreSQL en producción, mismo esquema en ambos motores", pero no especificó cómo se sostiene esa paridad de esquema en la práctica ni el resto del stack de persistencia. Sin estas decisiones, el change C-06 (governance CRÍTICO) no tiene una base técnica concreta sobre la cual empezar a construir.

**Alternativas consideradas**:
- SQLAlchemy Core (sin ORM) — mismo motor de traducción de dialectos, pero exige escribir a mano las relaciones 1-a-N del modelo (Ensayo→Ambiente→UnidadExperimental→Observación) en vez de declararlas como clases; se descartó por el volumen de relaciones jerárquicas del dominio.
- SQL crudo con adaptadores condicionales por motor — cero dependencias nuevas, pero mantener DD-03 se vuelve trabajo manual propenso a que los esquemas diverjan sin que nadie lo note; contradice el espíritu de auditabilidad del proyecto.
- Sin migraciones formales (recrear esquema con `metadata.create_all` en cada entorno) — simple para un caso de estudio único, pero pierde trazabilidad si el esquema cambia después de tener datos reales cargados; se descartó a favor de Alembic por la misma filosofía de auditabilidad que motivó RN-AUD.
- UUID como clave primaria — útil si en el futuro algo genera IDs fuera de la base de datos (el bot de Telegram creando una sesión antes de escribir, sincronización offline del módulo OCR), pero el sistema no es distribuido: toda escritura pasa por el mismo backend de persistencia. Se descarta por ahora; si el diseño se vuelve distribuido más adelante, es un cambio localizado (ver trade-offs).
- Variables de entorno separadas por componente (`DB_HOST`, `DB_PORT`, etc.) — preferible en algunos entornos de despliegue (ciertos PaaS, secretos inyectados por Kubernetes), pero para el alcance de esta tesis suma variables a documentar sin beneficio claro.

**Justificación**: mismo criterio que DD-02, DD-03 y DD-10 — priorizar simplicidad de implementación y de justificación metodológica para el alcance de un caso de estudio único, evitando complejidad anticipatoria sin necesidad probada. SQLAlchemy + Alembic es además el stack estándar de facto del ecosistema Python para este tipo de proyecto, lo que facilita que el equipo (4 autores) y un eventual lector externo de la tesis lo reconozcan sin curva de aprendizaje adicional.

**Trade-offs aceptados**: si el sistema evolucionara hacia una arquitectura distribuida o con generación de IDs fuera de la base (por ejemplo, IDs de sesión generados por el bot de Telegram antes de la escritura), migrar de entero autoincremental a UUID requeriría una migración de esquema explícita vía Alembic — costo diferido, no descartado, solo pospuesto hasta que haya evidencia real que lo justifique.

### DD-12 — Geolocalización opcional de Ambiente, con precisión exacta

**Decisión**: la entidad Ambiente incorpora dos atributos opcionales, `latitud` y `longitud` (WGS84, grados decimales), capturados con **precisión exacta** — no redondeados ni ofuscados por defecto —, protegidos por el mismo régimen de confidencialidad que ya rige el resto del dato del ensayo (control de acceso, auditoría, sin compartir con terceros sin autorización expresa; ver §3.7 de la tesis y DD-09).

**Contexto**: el equipo identificó dos líneas de investigación futura que dependen de tener geolocalización confiable en el dato: (a) la posibilidad de correlacionar los resultados de un ensayo con datos climáticos externos de la zona (temperatura, precipitación) para explicar o corregir parte de la varianza residual no capturada por el diseño de bloqueo, y (b) el reuso académico del dataset acumulado para análisis espacial (SIG) y meta-análisis entre ensayos. Ninguna de las dos capacidades se construye todavía —quedan documentadas como trabajo futuro en `14_reuso_academico_y_geolocalizacion.md`—, pero el campo se agrega **ahora** porque el diccionario de variables (change C-02) y el esquema de persistencia (change C-06) todavía no están construidos: agregar el campo en este momento es prácticamente gratis, mientras que agregarlo después de tener el caso de estudio real cargado sería una migración de esquema sobre datos ya existentes.

**Alternativas consideradas**:
- **No agregar el campo ahora, esperar a que la capacidad de correlación climática o reuso académico se construya de verdad** — descartada: pierde la ventana de costo mínimo (schema todavía no poblado) y obligaría a una migración retroactiva más cara.
- **Coordenadas redondeadas a una grilla por defecto** (ej. 2 decimales, ~1 km), con posibilidad de solicitar precisión completa — más conservador en términos de privacidad, pero degrada la utilidad para análisis de microclima fino y agrega una decisión de nivel de redondeo sin necesidad probada. Se descarta a favor de reutilizar el régimen de confidencialidad ya existente en vez de inventar uno nuevo específico para este campo.
- **Campo obligatorio** — descartado: no todos los casos de estudio van a tener coordenadas disponibles o relevantes al momento del alta del ensayo; forzar el dato bloquearía el flujo de configuración sin necesidad.

**Justificación**: mismo criterio de simplicidad ya aplicado en DD-10/DD-11 — evitar mecanismos de privacidad nuevos cuando el mecanismo existente (control de acceso + auditoría de §3.7) ya cubre el caso; y aprovechar el momento de costo mínimo para agregar un campo que habilita valor de investigación futuro genuino sin comprometerse todavía a construir ese futuro.

**Trade-offs aceptados**: el campo queda definido y disponible, pero **sin uso funcional en v1** — no hay todavía ningún módulo que lo consuma (ni correlación climática ni exportación para SIG). Es deuda de alcance documentada, no deuda técnica oculta. Si el caso de estudio real no tiene coordenadas disponibles, el campo simplemente queda nulo sin afectar el resto del pipeline.

## Supuestos inferidos

### SU-01 — Volumen de datos moderado
**Supuesto**: los ensayos manejan del orden de miles a decenas de miles de registros por campaña.
**Origen**: §2.3, justificación de la elección ETL.
**Riesgo si es falso**: si el volumen real es mucho mayor, SQLite en dev y el diseño ETL síncrono podrían no escalar; podría requerirse revisar hacia ELT o procesamiento distribuido.
**Cómo validar**: medir volumen real del caso de estudio elegido (ver `10_preguntas_abiertas.md`).

### SU-02 — Diseños experimentales convencionales únicamente
**Supuesto**: el sistema cubre diseño completamente aleatorio (DCA) y bloques completos al azar (BCA), posiblemente factorial — no medidas repetidas ni modelos mixtos de alta dimensionalidad.
**Origen**: §1.8 (alcances y limitaciones).
**Riesgo si es falso**: si el caso de estudio real requiere modelos mixtos (multi-ambiente, efectos aleatorios), el módulo de análisis (Anexo A, basado en `statsmodels.formula.api.ols`) no los soporta out-of-the-box — se menciona como trabajo futuro (extensión vía `statsmodels` LMM o `rpy2` a R) (§7.4).
**Cómo validar**: confirmar el diseño experimental del caso de estudio antes de fijar el alcance del módulo estadístico v1.

### SU-03 — Formatos de entrada tabulares únicamente
**Supuesto**: las fuentes de datos son siempre CSV/Excel con estructura de una fila por unidad experimental.
**Origen**: §3.3, §1.8 (limitaciones — no se integran sensores remotos, imágenes satelitales, datos no estructurados).
**Riesgo si es falso**: bajo — está explícitamente fuera de alcance, no es una ambigüedad sino una decisión de scope.
**Cómo validar**: no aplica (decisión de scope documentada, no supuesto a verificar).

### SU-04 — Repo único para tesis + software
**Supuesto**: el código del sistema (`pipeline/`, `config/`, etc.) vive en el mismo repositorio Git que la redacción de la tesis (`tesis-automatizacion-ensayos-agricolas`), no en un repo separado.
**Origen**: decisión operativa del usuario al crear este repositorio (ver memoria del proyecto — PDF excluido de versionado, resto del contenido sí).
**Riesgo si es falso**: si en algún momento se decide separar, habrá que migrar `pipeline/`, `config/`, `tests/`, etc. a un repo propio.
**Cómo validar**: confirmar con el equipo (4 autores) antes de que el volumen de código crezca demasiado para hacer el split costoso.
