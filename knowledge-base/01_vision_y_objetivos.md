# Visión y Objetivos

## Propósito del sistema

Automatizar la carga, validación, transformación y análisis estadístico de datos de ensayos agrícolas mediante un pipeline reproducible y auditable, reemplazando el proceso manual actual (planillas de cálculo, transformaciones ad hoc, documentación informal) que introduce errores de transcripción, carece de trazabilidad y dificulta la reproducibilidad científica.

El sistema articula la orquestación de flujos (n8n) con el procesamiento estructurado (Python) y un módulo de análisis estadístico reproducible (ANOVA y alternativas), registrando cada acción automatizada en una bitácora auditada que preserva la cadena de custodia del dato.

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| Investigador / analista de datos | Obtener un dataset limpio y estructurado a partir de archivos crudos, con el menor esfuerzo manual posible | Entender por qué se rechazó un registro; corregir y reingresar datos |
| Estadístico | Ejecutar análisis estadístico (ANOVA u otro) reproducible sobre el dataset validado | Verificar supuestos del modelo; comparar medias de tratamiento |
| Director del ensayo / institución | Contar con evidencia auditable de que el dato fue procesado correctamente | Comparar desempeño del pipeline vs. proceso manual; tomar decisiones técnicas confiables |
| Desarrollador / mantenedor del sistema | Mantener un pipeline modular, testeado y versionado | Extender el sistema a nuevos ensayos/diseños sin reescribir el código base |
| Experto de dominio agronómico | Validar que el diccionario de variables y las reglas de validación reflejen el conocimiento del dominio | Revisar y aprobar estandarizaciones sugeridas por IA |

## Objetivo general

Diseñar, implementar y validar un sistema reproducible para automatizar la carga, validación y procesamiento de datos de ensayos agrícolas, y ejecutar sobre ellos análisis estadístico consistente con el diseño experimental adoptado, priorizando trazabilidad, calidad del dato resultante y mantenibilidad a lo largo del tiempo.

## Objetivos específicos

1. Modelar el proceso completo de gestión del dato experimental (captura → dataset listo para análisis), identificando puntos críticos de error, cuellos de botella y lagunas de trazabilidad del flujo actual.
2. Definir un esquema de datos formal (diccionario de variables: tipo, unidad, rango, valores admisibles, obligatoriedad, reglas cruzadas) que cubra completitud, validez, consistencia y unicidad.
3. Implementar un pipeline completo (n8n + Python) con registro de ejecuciones, manejo de errores, reintentos y bitácora de auditoría.
4. Integrar un módulo de análisis estadístico reproducible y parametrizable (ANOVA u otras técnicas según diseño/supuestos) con reportes de diagnóstico explícitos.
5. Evaluar el sistema con métricas operativas (tiempo, tasa de error, completitud, consistencia) y verificación de la correcta ejecución del análisis estadístico, comparando contra el proceso manual de referencia.

## Alcance v1.0

- Ingesta de archivos CSV/Excel con datos crudos de ensayos agrícolas.
- Validación sistemática y exhaustiva contra un diccionario de variables (tipo, rango, lista, obligatoriedad, unicidad, consistencia cruzada) vía `great_expectations`.
- Transformación: normalización de nombres de columnas, estandarización de categóricas, conversión de unidades, formato *tidy*.
- Persistencia en base de datos relacional (SQLite dev / PostgreSQL prod) + bitácora de auditoría completa (ejecución, transformaciones, hashes, versión de código).
- Análisis estadístico reproducible: ANOVA y alternativas (Kruskal-Wallis, GLM, LMM) según diseño y supuestos, con diagnóstico formal (Shapiro-Wilk, Levene/Bartlett, Q-Q plot, residuos vs. ajustados).
- Diseños experimentales soportados: diseño completamente aleatorio (DCA), bloques completos al azar (BCA); potencialmente factorial.
- Componentes de IA como apoyo opcional (estandarización léxica, detección de anomalías) — **nunca aplican cambios sin aprobación humana registrada**.

## Fuera de alcance

- Corrección de deficiencias del diseño experimental (pseudoreplicación, confusión de factores, desequilibrios) — el sistema procesa, no diseña, ensayos.
- Integración de datos de sensores remotos, imágenes satelitales u otras fuentes no estructuradas.
- Modelos de series de tiempo o análisis espaciales.
- Sustitución autónoma del criterio experto por IA en decisiones de alto impacto.
- Integración con sistemas de gestión institucionales existentes (ERP, LIMS, etc.).
- Diseños experimentales de medidas repetidas o modelos mixtos de alta dimensionalidad (quedan como trabajo futuro — ver `09_decisiones_y_supuestos.md`).

## Métricas de éxito

**Operativas** (§3.6 de la tesis):
- Tiempo total de procesamiento (ingesta → dataset disponible).
- Tasa de error detectado (proporción de registros con ≥1 violación de regla).
- Completitud del dataset resultante (% campos obligatorios no nulos).
- Consistencia del dataset resultante (% registros sin violaciones de consistencia cruzada).

**Estadísticas**:
- Correctitud del análisis (comparación con cálculo manual de referencia por un experto).
- Reproducibilidad (re-ejecución sobre mismos datos/código → resultados idénticos).
- Completitud del diagnóstico de supuestos generado.

**Hipótesis de trabajo a verificar** (Cap. 5 de la tesis, actualmente pendiente de datos reales — ver `10_preguntas_abiertas.md`):
- **H1**: tasa de error residual significativamente menor que el proceso manual.
- **H2**: reducción de ≥50% en el tiempo total de preparación del dataset vs. proceso manual.
- **H3**: la trazabilidad explícita mejora auditabilidad y reduce el tiempo de reconstrucción/replicación del análisis.
