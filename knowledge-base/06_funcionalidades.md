# Funcionalidades

Organizadas por **épica** (los 5 grupos funcionales de §4.1 de la tesis) y luego por historia de usuario.

## Épica 1: Ingesta de datos

### US-001 — Cargar archivo crudo de ensayo
**Como** investigador/analista de datos
**Quiero** que el sistema lea archivos CSV/Excel con datos crudos del ensayo
**Para** iniciar el pipeline de procesamiento sin transcripción manual

**Criterios de aceptación**:
- [ ] Lee formatos CSV y Excel
- [ ] Detecta y reporta problemas de codificación/formato antes de procesar
- [ ] Valida estructura (columnas, nombres con tolerancia de capitalización/espaciado) contra el esquema esperado
- [ ] Ante error estructural, detiene el pipeline y emite informe (archivo, fecha/hora, descripción)

**Reglas relacionadas**: RN-ING-01 a RN-ING-04

## Épica 2: Validación de calidad del dato

### US-002 — Validar registros contra el diccionario de variables
**Como** investigador/analista de datos
**Quiero** que cada registro se valide automáticamente contra las reglas del diccionario de variables
**Para** detectar errores antes de que lleguen al análisis estadístico

**Criterios de aceptación**:
- [ ] Aplica validaciones de tipo, rango, lista, unicidad, completitud y consistencia cruzada
- [ ] Genera reporte de validación (registro, campo, regla violada) en HTML o JSON
- [ ] Produce dataset de válidos + dataset de rechazados con detalle

**Reglas relacionadas**: RN-VAL-01 a RN-VAL-08

## Épica 3: Transformación y estandarización

### US-003 — Normalizar y estandarizar el dataset validado
**Como** estadístico
**Quiero** recibir el dataset en formato *tidy* con nomenclatura estandarizada
**Para** poder ejecutar el análisis sin preprocesamiento manual adicional

**Criterios de aceptación**:
- [ ] Nombres de columna normalizados a `snake_case`
- [ ] Variables categóricas estandarizadas vía catálogo de correspondencias
- [ ] Unidades convertidas a la unidad canónica cuando corresponde
- [ ] Dataset resultante en formato tidy con identificadores jerárquicos del diseño experimental

**Reglas relacionadas**: RN-TRA-01 a RN-TRA-06

## Épica 4: Persistencia y auditoría

### US-004 — Persistir dataset y generar bitácora de auditoría
**Como** auditor externo / director del ensayo
**Quiero** que cada ejecución del pipeline quede registrada con detalle verificable
**Para** poder reconstruir la historia del dato y auditar el proceso

**Criterios de aceptación**:
- [ ] Bitácora registra id de ejecución, timestamps, hash de commit, hash SHA-256 del archivo de entrada, conteos y errores
- [ ] Bitácora de transformaciones permite reconstruir el estado del dato en cualquier punto
- [ ] Backups automáticos en ubicación separada del repo principal

**Reglas relacionadas**: RN-AUD-01 a RN-AUD-03

## Épica 5: Análisis estadístico automatizado

### US-005 — Ejecutar análisis estadístico reproducible
**Como** estadístico
**Quiero** ejecutar ANOVA (u otro modelo apropiado) de forma parametrizada
**Para** obtener resultados reproducibles y documentados

**Criterios de aceptación**:
- [ ] Recibe fórmula del modelo (R-style), tipo de análisis y parámetros adicionales
- [ ] Genera tabla de resultados en CSV y HTML
- [ ] Genera diagnóstico de supuestos (normalidad, homocedasticidad, outliers) con gráficos PNG
- [ ] Genera YAML de configuración que documenta el análisis exacto ejecutado, re-ejecutable con un comando
- [ ] Puede ejecutarse standalone sobre cualquier dataset ya almacenado

**Reglas relacionadas**: RN-EST-01 a RN-EST-05

## Épica 6: Apoyo de IA en calidad de dato (opcional, con supervisión)

### US-006 — Recibir sugerencias de estandarización de IA con aprobación humana
**Como** experto de dominio agronómico
**Quiero** revisar y aprobar/rechazar sugerencias de estandarización generadas por IA
**Para** beneficiarme de la automatización sin perder control sobre el dato

**Criterios de aceptación**:
- [ ] IA nunca aplica cambios sin aprobación explícita
- [ ] Toda aprobación/rechazo queda en bitácora de auditoría

**Reglas relacionadas**: RN-IA-01 a RN-IA-03

---

**Nota**: las funcionalidades de esta KB derivan de los requisitos funcionales de la tesis (§4.1), que son la especificación pero **no el estado actual de implementación** — al día de esta KB, el software aún no existe (ver `CHANGES.md` cuando se genere y `10_preguntas_abiertas.md`).
