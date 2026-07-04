# Modelo de Datos

## Dominios

El modelo distingue tres tipos de entidades (§4.3 de la tesis):

1. **Entidades de dominio** — objetos del mundo real: ensayo, ambiente, tratamiento, unidad experimental, observación.
2. **Entidades de sistema** — artefactos internos del pipeline: ejecuciones, bitácoras, versiones del catálogo.
3. **Entidades de configuración** — conocimiento experto formalizado: diccionario de variables, reglas de validación.

## ERD (descripción textual)

```
Ensayo (1) ──< (N) Ambiente
Ensayo (1) ──< (N) Tratamiento
Tratamiento (1) ──< (N) UnidadExperimental
Ambiente (1) ──< (N) UnidadExperimental
UnidadExperimental (1) ──< (N) Observación

Ejecución (1) ──< (N) BitácoraTransformación
Ejecución (1) ── (1) Dataset (validado/transformado)

DiccionarioDeVariables (1) ──< (N) ReglaDeValidación

Ensayo (1) ──< (N) Sesión        (ensayo_id nullable en Sesión — nueva, DD-09)
```

## Entidades

### Ensayo
- **Atributos**: código único (combina programa + campaña agrícola + sitio experimental)
- **Relaciones**: 1 ensayo → N ambientes, N tratamientos
- **Constraints**: código único no nulo

### Ambiente
- **Atributos**: condiciones de localización y manejo del ensayo en un sitio específico; `latitud` y `longitud` (WGS84, grados decimales, **opcionales** — ver `09_decisiones_y_supuestos.md`, DD-12)
- **Relaciones**: pertenece a 1 ensayo; 1 ambiente → N unidades experimentales
- **Constraints**: `latitud` ∈ [-90, 90], `longitud` ∈ [-180, 180] cuando están presentes (mismo patrón de validación de rango que RN-VAL-03, aplicado a nivel de entidad de sistema en vez de diccionario de variables, porque Ambiente no es una variable observacional)

### Tratamiento
- **Atributos**: combinación de niveles de los factores en estudio asignada a una unidad experimental
- **Relaciones**: pertenece a 1 ensayo; 1 tratamiento → N unidades experimentales

### Unidad experimental
- **Atributos**: identificador de parcela/planta individual
- **Relaciones**: recibe 1 tratamiento, pertenece a 1 ambiente; 1 unidad → N observaciones

### Observación
- **Atributos**: variable respuesta, valor, momento de medición
- **Relaciones**: pertenece a 1 unidad experimental

### Ejecución (entidad de sistema)
- **Atributos**: id único autogenerado, fecha/hora inicio y fin, versión de código (hash commit Git), hash SHA-256 del archivo de entrada, nº registros leídos/validados/rechazados/almacenados, errores/advertencias
- **Relaciones**: 1 ejecución → N registros de bitácora de transformaciones

### Bitácora de transformaciones (entidad de sistema)
- **Atributos**: nombre de operación, columna(s) afectada(s), nº registros modificados, criterio/regla aplicada, marca temporal
- **Propósito**: permite reconstruir el estado del dataset antes de cualquier transformación específica, a partir del archivo original — trazabilidad completa (RNF)

### Sesión (entidad de sistema — nueva, ver `13_interaccion_telegram_y_sesiones.md`, DD-09)
- **Atributos**: `session_id` (id único), `telegram_user_id` (usuario de Telegram, mapea a rol vía RBAC de `03_actores_y_roles.md`), `ensayo_id` (fk **nullable** — las sesiones de `setup_ensayo` existen antes que el ensayo), `tipo_sesion` (`setup_ensayo` | `carga_dato` | `confirmacion_ocr` | `confirmacion_ia`, extensible), `paso_actual` (índice/clave del paso en la secuencia), `respuestas_acumuladas` (JSON estructurado), `estado` (`abierta` | `completada` | `abandonada` | `expirada`), `created_at`, `updated_at`
- **Relaciones**: pertenece opcionalmente a 1 Ensayo (nullable); cada evento/paso de sesión se registra en la bitácora de auditoría (RN-SES-06, liga con RN-AUD)
- **Propósito**: modela la máquina de estados genérica que media TODA interacción humana por Telegram (motor dirigido por datos, RN-SES). Es una entidad **nueva agregada a esta misma capa de persistencia**, no un almacén separado. Se implementa en el change C-12 (`session-engine`); la secuencia de pasos de cada `tipo_sesion` se define como configuración, no como código (RN-SES-03)

### Diccionario de variables (entidad de configuración)
- **Atributos por variable**: nombre canónico (`snake_case`), descripción, tipo de dato (entero, real, categórico, fecha, texto libre), unidad de medida, rango de valores plausibles (min/max), lista de valores admisibles (categóricas), obligatoriedad, reglas de validación cruzada
- **Criticidad**: su completitud y exactitud es condición necesaria para el correcto funcionamiento del validador — debe validarse con expertos del dominio antes de implementar

## Seed data inicial

**No especificado en la tesis** — el diccionario de variables y el catálogo de valores admisibles deben construirse en la fase de relevamiento (§3.5, paso 2) junto a expertos del dominio agronómico, a partir del caso de estudio real que se seleccione. Ver `10_preguntas_abiertas.md` — es un bloqueante de Alta prioridad para empezar a implementar el módulo de validación.
