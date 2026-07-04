# Reglas de Negocio

Cada regla tiene un código único `RN-{DOMINIO}-{NN}` para trazabilidad. Extraídas de los requisitos funcionales/no funcionales (§4.1) y las secciones de diseño de cada módulo (§4.4–4.8).

## Dominio: Ingesta (RN-ING)

- **RN-ING-01**: El sistema debe leer archivos de datos crudos en formato CSV y Excel.
- **RN-ING-02**: Debe detectar y reportar problemas de codificación/formato que impidan la lectura correcta antes de continuar.
- **RN-ING-03**: Debe validar la estructura del archivo (nº de columnas, nombres — con tolerancia configurable de capitalización/espaciado) contra el esquema declarado antes de procesar.
- **RN-ING-04**: Cualquier problema estructural detiene el procesamiento; no avanza a fases siguientes hasta que se corrija — genera informe con archivo, fecha/hora y descripción del problema.

## Dominio: Validación (RN-VAL)

- **RN-VAL-01**: Toda regla de validación se expresa de forma declarativa (JSON) vía `great_expectations`, inspeccionable sin leer código Python.
- **RN-VAL-02** (tipo): cada columna debe contener valores del tipo esperado (enteros, reales, fechas).
- **RN-VAL-03** (rango): valores numéricos deben estar dentro de límites plausibles del diccionario.
- **RN-VAL-04** (lista): valores categóricos deben pertenecer al catálogo de términos admisibles.
- **RN-VAL-05** (unicidad): no deben existir duplicados en la clave primaria del dataset.
- **RN-VAL-06** (completitud): todo campo obligatorio debe tener valor no nulo — un faltante en campo obligatorio genera rechazo del registro.
- **RN-VAL-07** (consistencia cruzada): deben verificarse relaciones lógicas entre pares/grupos de variables (ej. fecha de siembra ≤ fecha de cosecha).
- **RN-VAL-08**: el proceso produce **dos salidas obligatorias**: dataset de registros válidos y dataset de registros rechazados con detalle de error por registro/campo/regla violada.

## Dominio: Transformación (RN-TRA)

- **RN-TRA-01**: Solo se transforman registros que superaron validación.
- **RN-TRA-02**: cada operación de transformación es atómica, documentada en código y registrada en bitácora (nº registros afectados + muestra antes/después).
- **RN-TRA-03**: nombres de columna se normalizan a `snake_case` minúsculas sin caracteres especiales.
- **RN-TRA-04**: valores categóricos se estandarizan vía tabla de correspondencias del catálogo (variantes → forma canónica).
- **RN-TRA-05**: se aplican conversiones de unidad cuando la unidad de origen difiere de la canónica del diccionario.
- **RN-TRA-06**: el dataset final debe estar en formato *tidy* (una fila = una observación, una columna = una variable), preservando identificadores jerárquicos del diseño experimental.

## Dominio: Persistencia y auditoría (RN-AUD)

- **RN-AUD-01**: cada ejecución del pipeline se registra con: id único, fecha/hora inicio-fin, hash del commit Git, hash SHA-256 del archivo de entrada, conteos (leídos/válidos/rechazados/almacenados), errores/advertencias.
- **RN-AUD-02**: toda transformación aplicada debe quedar registrada de forma que se pueda reconstruir el estado del dato en cualquier punto del pipeline.
- **RN-AUD-03**: los respaldos (dataset, bitácora, código) se programan automáticamente y se almacenan en ubicación distinta al repositorio principal.

## Dominio: Análisis estadístico (RN-EST)

- **RN-EST-01**: el módulo recibe como parámetros: id del dataset, fórmula del modelo (R-style, ej. `rendimiento ~ C(tratamiento) + C(bloque)`), tipo de análisis (ANOVA, LMM, Kruskal-Wallis, etc.), parámetros adicionales (nivel de significancia, método de comparación de medias).
- **RN-EST-02**: debe producir tabla de resultados (CSV + HTML) del modelo correspondiente.
- **RN-EST-03**: debe producir diagnóstico de supuestos: normalidad de residuos (Shapiro-Wilk), homocedasticidad (Levene/Bartlett), apalancamiento/influencia (outliers), gráficos residuos-vs-ajustados y Q-Q normal (PNG).
- **RN-EST-04**: debe producir un archivo YAML que registre exactamente qué análisis se ejecutó, con qué parámetros y sobre qué versión del dataset — el análisis debe ser re-ejecutable con un único comando.
- **RN-EST-05**: puede invocarse encadenado al pipeline o de forma independiente sobre cualquier dataset ya almacenado.
- **RN-EST-06** (comparación de medias en diseños bloqueados): cuando el modelo incluye un factor de bloque (`C(bloque)`), la prueba de comparación de medias (Tukey HSD u otra) **no puede usar `statsmodels.stats.multicomp.pairwise_tukeyhsd` de forma directa sobre los grupos crudos** — esa función ignora el bloqueo y produce p-valores incorrectos (validado empíricamente, ver `11_analisis_estadistico_anova_tukey.md`). Debe calcularse con el `MS_error` y grados de libertad del modelo completo (bloque + tratamiento), vía `psturng` (Python puro) o `TukeyHSD()` de R (vía `rpy2`).
- **RN-EST-07** (autoría del reporte final — extensión de RN-EST-02, **no** contradicción): una vez producida la tabla de resultados (RN-EST-02, CSV/HTML), el **Ingeniero responsable del ensayo** (ver `03_actores_y_roles.md`) elige el modo del **informe interpretativo**: **(a) auto-generado por el sistema** (narrativa/plantilla armada automáticamente sobre la salida de RN-EST-02) o **(b) auto-redactado** (el ingeniero escribe él mismo la interpretación/narrativa). RN-EST-02 sigue generando la tabla de resultados en ambos casos; lo que RN-EST-07 agrega es que la *autoría de la narrativa* pasa a ser una elección explícita, ofrecida por Telegram al notificar los resultados (ver `13_interaccion_telegram_y_sesiones.md`, DD-09). **Default (DD-10)**: el reporte auto-generado se entrega **siempre** apenas termina el análisis, sin esperar la elección del ingeniero; el bot pregunta en paralelo si quiere redactar su propia interpretación, pero la ausencia de respuesta **no bloquea** nada — no hay *deadline*. La elección de autoría propia, si llega, se registra y complementa el reporte ya entregado.

## Dominio: IA de apoyo (RN-IA)

- **RN-IA-01**: ningún cambio al dato puede ser aplicado de forma autónoma por un componente de IA.
- **RN-IA-02**: toda sugerencia de IA (estandarización, corrección) requiere aprobación explícita de un operador humano antes de aplicarse.
- **RN-IA-03**: cada aprobación o rechazo de una sugerencia de IA queda registrado en la bitácora de auditoría.

## Dominio: Captura offline por OCR zonal (RN-OCR)

> Dominio nuevo, específico del **método de entrada alternativo por OCR** (planilla de papel fotografiada a campo) documentado en `12_captura_offline_ocr.md`. Se modela como dominio propio `RN-OCR` —y no como extensión de `RN-ING`— porque estas reglas gobiernan el mecanismo de captura por imagen (plantilla, fiduciales, confianza de reconocimiento, confirmación humana), no la ingesta tabular general de CSV/Excel; el dato que producen converge a la ingesta existente (RN-OCR-07) y de ahí recorre el pipeline (RN-VAL/RN-TRA/RN-AUD) sin cambios. Es una capacidad **opcional** (ver `CHANGES.md`, C-11).

- **RN-OCR-01** (extracción zonal): el OCR solo lee dentro de zonas / *bounding boxes* predefinidas por la plantilla de layout fijo — nunca texto libre a lo largo de un documento arbitrario. Cada zona corresponde a un campo del diccionario de variables (`config/data_dictionary.json`).
- **RN-OCR-02** (captura estructurada): la plantilla debe usar casilleros segmentados tipo "peine" (un dígito por casilla) para campos numéricos, checkboxes/burbujas (OMR) para campos categóricos, y marcadores fiduciales (ArUco/QR) en las esquinas para corrección de rotación/perspectiva antes de la extracción zonal.
- **RN-OCR-03** (doble señal de confianza): la aceptación de una lectura exige combinar dos señales independientes: (a) el score de confianza propio del motor OCR y (b) la validación cruzada contra las reglas existentes RN-VAL-02 (tipo), RN-VAL-03 (rango) y RN-VAL-04 (lista de valores admisibles). Una lectura que viola una regla de dominio se marca para revisión aunque el motor reporte alta confianza (ej.: OCR lee `8` en un campo cuyo rango válido es `0.0`–`5.0`).
- **RN-OCR-04** (confirmación humana bajo umbral): toda lectura por debajo del umbral de confianza (o que viole una RN-VAL) requiere confirmación humana explícita antes de aceptarse como dato válido, replicando la filosofía de RN-IA-01/02/03 — ningún dato de baja confianza se acepta de forma autónoma. La confirmación se materializa como **un mensaje de Telegram con botones *inline*** (confirmar / corregir), consistente con **DD-09** (interacción cero-CLI, Telegram como único canal humano). El workflow de n8n se **pausa** en ese punto (mecanismo "Wait for Webhook") y se **reanuda** cuando llega el clic del usuario. Ver `13_interaccion_telegram_y_sesiones.md`. — **CORRECCIÓN (DD-09)**: la redacción anterior decía "un paso de revisión por CLI (consistente con DD-05)"; eso quedó **superado**. La confirmación NO es por CLI: el usuario no interactúa con ninguna terminal (ver DD-09, que refina DD-05). La CLI es sólo el mecanismo interno con que n8n invoca `pipeline/*.py`.
- **RN-OCR-05** (ejecución offline/local): el procesamiento OCR/OMR debe ejecutarse local y offline (Tesseract/OpenCV); queda **prohibido** el uso de APIs de OCR en la nube (Google Document AI, AWS Textract, Azure Form Recognizer), por el requisito de conectividad no confiable a campo y por la confidencialidad del dato del ensayo (§3.7 de la tesis).
- **RN-OCR-06** (auditoría de la lectura): cada lectura OCR y su eventual confirmación humana se registran en la bitácora de auditoría (RN-AUD-01/02): score del motor, lectura original, valor confirmado, quién confirmó y cuándo — preservando la cadena de custodia del dato desde el papel.
- **RN-OCR-07** (convergencia a la ingesta existente): el dato OCR-extraído-y-confirmado se normaliza a la misma forma tabular que `pipeline/ingestion.py` espera de fuentes CSV/Excel, y recorre el pipeline existente (RN-VAL → RN-TRA → RN-AUD) sin modificación. No se crea un pipeline paralelo.

## Dominio: Motor de sesiones e interacción por Telegram (RN-SES)

> Dominio nuevo, específico de la **capa de interacción cero-CLI por Telegram** documentada en `13_interaccion_telegram_y_sesiones.md` (decisión formal: DD-09, que refina DD-05). Gobierna la máquina de estados genérica que media TODA interacción humana con el sistema (setup de ensayo, carga de datos, confirmaciones OCR/IA). Se modela como dominio propio `RN-SES` —y no como extensión de `RN-ING`— porque estas reglas gobiernan el mecanismo conversacional/estado de sesión, no la ingesta tabular. El dato que una sesión produce converge al pipeline existente (ingesta → RN-VAL → RN-TRA → RN-AUD) sin cambios. Es una capacidad de dos changes: C-12 (motor) y C-13 (bot + roles), ver `CHANGES.md`.

- **RN-SES-01** (canal humano único): toda interacción humana con el sistema ocurre por Telegram; ningún usuario final interactúa con la CLI ni con archivos de configuración a mano. La CLI queda como mecanismo interno con que n8n invoca `pipeline/*.py` (consistente con DD-05, refinado por DD-09). El nodo Telegram nativo de n8n (envío + Telegram Trigger) es el único punto de contacto.
- **RN-SES-02** (entidad de sesión persistida): cada interacción se modela como una entidad `sesion` (entidad de sistema nueva en la capa de persistencia existente, ver `04_modelo_de_datos.md`) con: `session_id`, `telegram_user_id`, `ensayo_id` (nullable — las sesiones de setup existen antes que el ensayo), `tipo_sesion` (`setup_ensayo` | `carga_dato` | `confirmacion_ocr` | `confirmacion_ia`, extensible), `paso_actual`, `respuestas_acumuladas`, `estado` (`abierta` | `completada` | `abandonada` | `expirada`), timestamps.
- **RN-SES-03** (secuencia de pasos como configuración, no como código): la secuencia de pasos de cada `tipo_sesion` se define como **datos/configuración** (lista ordenada de definiciones de pregunta: texto del prompt, tipo de respuesta esperada `texto`/`numero`/`foto`/`choice`, referencia a la RN-VAL/diccionario aplicable), **nunca** como bifurcaciones hardcodeadas en el grafo del workflow de n8n. Agregar una pregunta = agregar una entrada de configuración, no editar el workflow. **Formato concreto (DD-10)**: la configuración vive como **JSON en la base de datos**, en una tabla `config_paso_sesion` (una fila por paso: `tipo_sesion`, `paso`, `prompt`, `tipo_respuesta`, `regla_validacion`) — no como archivo YAML versionado en git ni como tabla relacional rígida. Se eligió así por coherencia con "la secuencia es dato, no código": queda editable sin redeploy si más adelante existe un panel de administración.
- **RN-SES-04** (resolución reanudar-vs-nueva): ante un mensaje entrante de un `telegram_user_id`, el sistema **primero busca una sesión `abierta`** para ese usuario. Si existe, el mensaje se trata como la respuesta al `paso_actual` (se valida, se almacena, se avanza). Si no existe, se resuelve el `tipo_sesion` según el rol del usuario (ingeniero sin setup activo → ofrecer `setup_ensayo`; ayudante de un ensayo activo → ofrecer `carga_dato`) y se crea una sesión nueva en el paso 0. La reanudación de una sesión previa sale gratis de esta misma búsqueda.
- **RN-SES-05** (validación por paso): cada respuesta entrante se valida contra la regla referenciada por el paso (tipo/rango/lista del diccionario, RN-VAL-02/03/04) antes de almacenarse y avanzar. Una respuesta inválida no avanza la sesión: se re-pregunta.
- **RN-SES-06** (auditoría de eventos de sesión): cada paso respondido se registra en la bitácora de auditoría (misma cadena de custodia que RN-AUD-01/02 y que las confirmaciones OCR/IA de RN-OCR-06): qué se preguntó, qué respondió el usuario, cuándo, en qué sesión. Las confirmaciones bajo umbral (`confirmacion_ocr`/`confirmacion_ia`) registran lectura/sugerencia original vs. valor confirmado (liga con RN-OCR-04, RN-IA-03).
- **RN-SES-07** (timeout/abandono): una sesión `abierta` sin respuesta por demasiado tiempo debe transicionar a `expirada`/`abandonada` según una política definida, siguiendo la filosofía de escalamiento de RN-GLB-03. **Umbral (DD-10)**: **24 horas**, uniforme para los cuatro `tipo_sesion` (no se distingue por rol/tipo). Se eligió un único valor por simplicidad de implementación y de justificación metodológica, aceptando como trade-off que una sesión abandonada pueda quedar "viva" hasta 24h antes de expirar.

## Dominio: Excepciones globales

- **RN-GLB-01** (tolerancia a fallos): un error en el procesamiento de un registro individual no debe interrumpir el procesamiento del resto del dataset; debe reportarse claramente qué registros fallaron y por qué.
- **RN-GLB-02** (reproducibilidad): la ejecución del pipeline con los mismos datos de entrada y la misma versión de código debe producir resultados idénticos en cualquier entorno que satisfaga las dependencias fijadas.
- **RN-GLB-03** (reintentos): fallos transitorios a nivel de orquestación (n8n) se reintentan automáticamente con retardo exponencial; fallos persistentes escalan a notificación humana. **Canal concreto de escalamiento (DD-09)**: la "notificación humana" se materializa como un **mensaje de Telegram** — el mismo canal único de la capa de interacción (ver `13_interaccion_telegram_y_sesiones.md`, RN-SES-01). N reintentos fallidos en cualquier etapa del pipeline disparan un mensaje de escalamiento por Telegram.
