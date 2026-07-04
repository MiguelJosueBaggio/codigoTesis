# Captura Offline de Datos de Campo vía OCR Zonal por Plantilla

> **Origen de este archivo**: extensión de alcance analizada para el problema real de captura del dato en campo. El alcance v1.0 (`01_vision_y_objetivos.md`, §Fuera de alcance, y §1.8 de la tesis) asume que la entrada ya llega como CSV/Excel estructurado y excluye explícitamente fuentes no tabulares (imágenes, escaneos). Pero las condiciones reales de un ensayo agrícola a campo suelen tener conectividad poco confiable y ningún dispositivo digital durable disponible en el punto de captura — es una restricción real confirmada, no hipotética. La captura en papel es a menudo la única opción práctica. Este archivo documenta una capacidad **opcional** que resuelve ese hueco sin romper el pipeline existente: convierte planillas de papel fotografiadas en el mismo formato tabular que `pipeline/ingestion.py` ya espera. No es OCR general de texto libre (poco confiable), sino **OCR zonal basado en plantilla de layout fijo**.

## Por qué existe esta capacidad

El pipeline (`02_descripcion_general.md`, `08_arquitectura_propuesta.md`) arranca en la carpeta de ingesta monitoreada, asumiendo que alguien ya digitó el dato a CSV/Excel. Ese "alguien digita" es exactamente el paso manual propenso a error de transcripción que la tesis busca reducir (`01_vision_y_objetivos.md`, §Propósito). Si el dato nace en papel a campo, la transcripción manual sigue ocurriendo — solo que fuera del alcance del sistema, sin trazabilidad.

La capacidad aquí descrita mueve ese punto de transcripción **dentro** del sistema y bajo las mismas garantías de auditoría (RN-AUD-01/02) y confirmación humana (filosofía RN-IA-01/02/03) que ya rigen al resto del pipeline. El dato deja de "nacer" en un CSV manual de origen incierto y pasa a nacer de una plantilla física conocida, leída de forma reproducible y auditada.

Es una capacidad **opcional y fuera del camino crítico** (ver `CHANGES.md`, change C-11): el pipeline funciona sin ella; la habilita solo cuando el caso de estudio real (bloqueante de `10_preguntas_abiertas.md`) confirme captura en papel.

## Restricción de diseño no negociable: OCR zonal, no OCR general

La decisión central (formalizada en `09_decisiones_y_supuestos.md`, DD-08) es **no** intentar reconocimiento de escritura libre. El OCR de manuscritos generales es poco confiable y su tasa de error contaminaría el dato en origen. En su lugar, se diseña la captura para que el reconocimiento sea lo más determinístico posible. Los siete pilares:

### 1. Plantilla imprimible de layout fijo con posiciones conocidas

Un formulario de papel diseñado con posiciones de campo fijas y conocidas de antemano (ensayo, bloque, tratamiento, unidad experimental, variable respuesta, etc. — las mismas entidades ya modeladas en `04_modelo_de_datos.md`). El OCR **solo lee dentro de zonas / *bounding boxes* predefinidas por la plantilla**, nunca texto libre a lo largo de un documento arbitrario. Cada campo del diccionario de variables (`config/data_dictionary.json`, C-02) tiene una zona rectangular asociada en coordenadas relativas de la plantilla.

### 2. Casilleros segmentados tipo "peine" para entrada numérica

Los campos numéricos (rendimiento, peso, altura, conteos) se capturan en casilleros segmentados de un dígito por casilla (*comb fields*, como en formularios impositivos o cheques bancarios). Un dígito aislado en una casilla delimitada es mucho más confiable de reconocer que escritura numérica conectada. Esto reduce drásticamente la ambigüedad frente a lectura de números manuscritos corridos.

### 3. Checkboxes / burbujas (OMR) para campos categóricos

Los campos categóricos (código de tratamiento, nivel de factor, categorías del catálogo de valores admisibles) se capturan como casillas de verificación o burbujas para relleno — **OMR (Optical Mark Recognition)** en lugar de texto manuscrito. Detectar si una burbuja está rellena o no es casi infalible comparado con reconocer caracteres, y mapea directamente a la lista de valores admisibles del diccionario (RN-VAL-04).

### 4. Marcadores fiduciales para corrección de perspectiva

Marcadores de alineación en las esquinas de la plantilla (por ejemplo marcadores **ArUco** o códigos QR) para corregir rotación y distorsión de perspectiva. Una foto de teléfono tomada a campo —no un escaneo de cama plana— rara vez estará perfectamente alineada; los fiduciales permiten detectar las cuatro esquinas y aplicar una transformación de perspectiva (*homografía*) que "endereza" la imagen antes de recortar las zonas. Sin este paso, las *bounding boxes* de la plantilla no coincidirían con los campos reales de la foto.

### 5. Doble señal de confianza (motor OCR + reglas de validación existentes)

No se confía únicamente en el score de confianza del motor OCR. Se combinan **dos** señales independientes:

- **(a) Confianza propia del motor OCR** por campo (el score que reporta Tesseract/PaddleOCR para cada lectura).
- **(b) Validación cruzada contra las reglas ya existentes** de `05_reglas_de_negocio.md`: tipo (**RN-VAL-02**), rango (**RN-VAL-03**) y lista de valores admisibles (**RN-VAL-04**), tomadas del diccionario de variables.

Ejemplo: si el OCR lee `8` para un campo cuyo rango válido en el diccionario es `0.0`–`5.0`, eso es una señal fuerte de mala lectura **aunque el motor OCR reporte alta confianza en el carácter**. La regla de dominio contradice al motor. Este cruce atrapa errores que la confianza del motor por sí sola no detecta. La lectura se marca para revisión cuando *cualquiera* de las dos señales falla (baja confianza del motor **o** violación de RN-VAL).

### 6. Confirmación humana para lecturas de baja confianza (misma filosofía que RN-IA)

Toda lectura por debajo del umbral de confianza requiere confirmación humana antes de aceptarse como dato válido. Esto sigue **exactamente** la filosofía ya establecida para el apoyo de IA en **RN-IA-01/02/03** (`05_reglas_de_negocio.md`): nada se acepta como dato válido sin confirmación humana cuando la confianza está bajo umbral, y la confirmación —quién confirmó, cuándo, cuál fue la lectura OCR original vs. el valor confirmado— se registra en la bitácora de auditoría según **RN-AUD-01/02**.

Es una extensión natural del concepto de bitácora ya existente: la bitácora puede registrar "este dato fue leído por OCR con confianza X, confirmado por el usuario Y en el momento Z, lectura original W corregida a V". La cadena de custodia del dato (`01_vision_y_objetivos.md`, §Propósito) se preserva desde el papel.

**Cómo se materializa la confirmación**: ⚠ **ACTUALIZADO por DD-09** (ver `13_interaccion_telegram_y_sesiones.md`). La redacción original de este párrafo decía que la confirmación se implementaba como un **paso de revisión por CLI** (consistente con la lectura CLI-first de DD-05 y con la resolución "sin web UI" de `10_preguntas_abiertas.md`). Eso quedó **superado**: DD-09 refina DD-05 a *cero interacción directa del usuario; Telegram como único canal humano*. La confirmación ahora se materializa como un **mensaje de Telegram con botones *inline*** que muestra la referencia al *crop* de la zona dudosa, la lectura OCR y el score, y pide confirmar o corregir; el workflow de n8n se **pausa** ("Wait for Webhook") y se **reanuda** con el clic del usuario. Sigue sin ser una aplicación web propia (eso se conserva de DD-05) y la CLI sigue siendo el mecanismo interno con que n8n invoca el pipeline OCR — pero el humano ya **no** teclea en una terminal. Ver RN-OCR-04 (corregida) y el flujo `confirmacion_ocr` de `13_*`.

### 7. Ejecución totalmente offline / local

El procesamiento OCR corre **local y offline** (Tesseract o extracción zonal basada en OpenCV), **nunca** vía APIs de nube (Google Document AI, AWS Textract, Azure Form Recognizer). Dos razones independientes, ambas ya establecidas en esta KB:

- **(a) Sin conectividad confiable a campo** — la misma restricción real que motiva la captura en papel.
- **(b) Confidencialidad del dato del ensayo** — la gestión ética de datos (§3.7 de la tesis, referenciada en `03_actores_y_roles.md`; y el principio de credenciales/permisos mínimos de `08_arquitectura_propuesta.md`, §Seguridad) implica que el dato no debe salir de la institución hacia un servicio de nube de terceros sin autorización explícita.

## Alternativas rechazadas / despriorizadas

Documentadas con su razonamiento (ver también `09_decisiones_y_supuestos.md`, DD-08):

- **OCR general de texto libre sin plantilla** — rechazado: demasiado poco confiable, en especial para escritura manuscrita. La tasa de error contaminaría el dato en origen, contradiciendo el objetivo mismo de la tesis (reducir errores de transcripción).
- **APIs de OCR en la nube** (Google Document AI, AWS Textract, Azure Form Recognizer) — rechazadas para este proyecto en particular por el requisito offline + confidencialidad (§3.7), **a pesar de** tener mejor precisión bruta de manuscritos que las opciones locales. El trade-off de precisión se compensa con el diseño estructurado de la plantilla (peine + OMR), que reduce la dificultad del reconocimiento a un nivel que las herramientas locales sí cubren bien.
- **Captura digital en el momento de la toma vía tablet/formularios móviles (ODK / KoboToolbox)** — fue la **primera** alternativa considerada y es, en abstracto, más simple. Se dejó de lado porque **no resuelve el problema real**: la fragilidad de los dispositivos digitales y la conectividad poco confiable a campo hacen que la captura en papel sea el *fallback* más robusto en la práctica. El papel no se queda sin batería ni pierde señal.

## Arquitectura mínima sugerida (pipeline de captura OCR)

Cadena de procesamiento propuesta, de la plantilla en blanco al dato normalizado que entra al pipeline existente:

```
1. Generación de plantilla
   └─ Formulario de layout fijo (zonas por campo del data_dictionary.json)
      + casilleros peine (numéricos) + burbujas OMR (categóricos)
      + marcadores fiduciales (ArUco/QR) en las 4 esquinas
                    │
                    ▼
2. Captura foto/escaneo a campo
   └─ Foto de teléfono del formulario completado a mano
                    │
                    ▼
3. Corrección de alineación
   └─ Detección de fiduciales (OpenCV cv2.aruco) → homografía →
      imagen "enderezada" y a escala canónica de la plantilla
                    │
                    ▼
4. Extracción zonal
   └─ Recorte a las bounding boxes conocidas de la plantilla
      (una imagen por campo)
                    │
                    ▼
5. OCR / OMR por campo
   ├─ Numéricos (peine): Tesseract con whitelist de dígitos
   │  (--psm por casilla, tessedit_char_whitelist=0123456789.)
   └─ Categóricos (burbujas): detección de relleno OMR
      (umbral de densidad de píxeles por burbuja vía OpenCV)
                    │
                    ▼
6. Doble chequeo de confianza  (RN-OCR-03)
   ├─ (a) score de confianza del motor OCR por campo
   └─ (b) cross-check contra RN-VAL-02 (tipo) / RN-VAL-03 (rango) /
          RN-VAL-04 (lista de valores admisibles)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
   confianza OK          baja confianza / viola RN-VAL
          │                   │
          │                   ▼
          │            7. Confirmación humana (RN-OCR-04)
          │               └─ Mensaje Telegram con botones (DD-09,
          │                  reemplaza el "por CLI" original):
          │                  muestra crop del campo + lectura OCR + score,
          │                  pide confirmar/corregir; workflow en pausa
          │                  (Wait for Webhook) → clic → reanuda; registra
          │                  original vs. confirmado en bitácora (RN-AUD-02)
          │                   │
          └─────────┬─────────┘
                    ▼
8. Normalización a la forma tabular de ingesta  (RN-OCR-07)
   └─ Ensambla las lecturas confirmadas en el MISMO shape (DataFrame/CSV)
      que pipeline/ingestion.py ya espera de fuentes CSV/Excel
                    │
                    ▼
   ── entra al pipeline existente SIN cambios ──
   ingestion → validation (RN-VAL) → transformation (RN-TRA)
   → persistence + bitácora (RN-AUD)
```

**Punto clave de integración**: este es un **método de entrada alternativo que alimenta el mismo módulo `pipeline/ingestion.py`** (`08_arquitectura_propuesta.md`, Anexo C — "ingestion.py: Módulo de ingesta y validación estructural"), **no** un pipeline paralelo. El dato OCR-extraído-y-confirmado se normaliza a la forma que el módulo de ingesta ya espera de fuentes CSV/Excel, y a partir de ahí recorre el pipeline existente (RN-VAL / RN-TRA / RN-AUD) sin modificación. Todo lo que ya está construido y testeado aguas abajo se reutiliza intacto.

## Librerías candidatas concretas

| Rol en el pipeline | Librería candidata | Notas |
|---|---|---|
| OCR de dígitos (campos peine) | **Tesseract** vía `pytesseract` | Configurar `tessedit_char_whitelist=0123456789.` y `--psm` adecuado por casilla; ejecuta 100% local |
| Motor OCR alternativo | **PaddleOCR** | Mejor precisión en algunos manuscritos; evaluar empíricamente vs. Tesseract (pregunta abierta, ver abajo) |
| Detección de fiduciales / homografía | **OpenCV** `cv2.aruco` (marcadores ArUco) | Detecta esquinas y corrige perspectiva; alternativa: QR en esquinas |
| Preprocesamiento de imagen | **`opencv-python`** | Recorte por bounding box, binarización, corrección de contraste, detección de relleno OMR (densidad de píxeles por burbuja) |

Todas son librerías locales, sin dependencia de servicios de nube — consistente con RN-OCR-05.

## Reglas de negocio asociadas

Esta capacidad introduce el dominio **RN-OCR** en `05_reglas_de_negocio.md` (RN-OCR-01 a RN-OCR-07). En resumen: extracción zonal obligatoria (RN-OCR-01), captura estructurada peine/OMR con fiduciales (RN-OCR-02), doble señal de confianza (RN-OCR-03), confirmación humana bajo umbral (RN-OCR-04), ejecución offline/local (RN-OCR-05), auditoría de lecturas y confirmaciones (RN-OCR-06) y convergencia a la pipeline de ingesta existente (RN-OCR-07). Ver ese archivo para el detalle normativo.

## Preguntas abiertas específicas

Se agregan a `10_preguntas_abiertas.md` (ver ese archivo): elección empírica del motor OCR (Tesseract vs. PaddleOCR), diseño físico y logística de impresión del formulario, quién imprime/distribuye/recolecta las planillas a campo, y si conviene testear un prototipo de formulario antes del diseño y despliegue completo.

## Próximo paso técnico sugerido

Antes de invertir en el diseño completo: construir un **prototipo mínimo de formulario de una sola variable** (por ejemplo un solo campo numérico peine + un campo OMR + fiduciales), fotografiarlo con un teléfono en condiciones realistas y medir la tasa de acierto de Tesseract vs. PaddleOCR sobre esa muestra. Ese experimento resuelve la pregunta del motor y valida que el enfoque zonal + fiducial funciona antes de diseñar la plantilla completa del caso de estudio real. El resultado debe compararse contra el mismo criterio de correctitud que el resto del sistema: la doble señal de confianza (RN-OCR-03) sobre datos con valor conocido.
