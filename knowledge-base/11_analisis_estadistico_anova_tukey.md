# Análisis Estadístico: Mecánica ANOVA + Tukey HSD (validado)

> **Origen de este archivo**: reenfoque solicitado por el usuario — antes de diseñar la infraestructura del pipeline (ingesta, validación, n8n), se valida el núcleo estadístico (RN-EST) contra un dataset de referencia con linaje directo al marco teórico de la tesis (Fisher/Rothamsted, §2.1). Este archivo documenta la mecánica exacta y un hallazgo crítico de implementación.

## Dataset de referencia usado

`npk` — experimento clásico N-P-K de Fisher/Rothamsted sobre rendimiento de arvejas, 6 bloques, diseño factorial fraccionado. Fuente: mirror público [Rdatasets/MASS/npk](https://vincentarelbundock.github.io/Rdatasets/doc/MASS/npk.html) (24 observaciones, columnas `block`, `N`, `P`, `K`, `yield`). Elegido por compartir linaje directo con la cita de Fisher/Rothamsted del marco teórico (§2.1 de la tesis) y por replicar exactamente el patrón de fórmula que la propia tesis especifica: `rendimiento ~ C(tratamiento) + C(bloque)` (§4.7, RN-EST-01).

## Metodología de validación

Dos métodos **independientes** deben coincidir para confiar en una implementación:

1. **statsmodels**: `ols("rendimiento ~ C(block) + C(N)", data=df).fit()` + `sm.stats.anova_lm(modelo, typ=1)` (sumas de cuadrados secuenciales — Tipo I, correcto para diseño balanceado con bloques).
2. **Fórmulas clásicas de RCBD** (Cochran & Cox / Montgomery, ambos citados en la tesis) calculadas a mano: SS_total, SS_bloque, SS_tratamiento por suma de cuadrados de desvíos ponderados, SS_error por diferencia.

### Resultado de la validación (coincide exactamente)

| Fuente de variación | df | SS | F | p |
|---|---|---|---|---|
| Bloque | 5 | 343.295 | 3.395 | 0.0262 |
| Tratamiento (N) | 1 | 189.282 | 9.360 | **0.0071** |
| Error | 17 | 343.788 | — | — |

`statsmodels` y el cálculo manual coinciden en SS, F y p hasta el 4º decimal → el motor de ANOVA vía `statsmodels.stats.anova_lm` es confiable para el patrón RCBD de la tesis.

Diagnóstico de supuestos sobre este dataset (limpio, de cátedra): Shapiro-Wilk p=0.65 (normalidad OK), Levene p=0.94 (homocedasticidad OK) — caso de referencia válido para ANOVA sin necesidad de alternativas.

## ⚠️ Hallazgo crítico: `pairwise_tukeyhsd` naive da resultados INCORRECTOS en diseños con bloqueo

**El bug**: `statsmodels.stats.multicomp.pairwise_tukeyhsd(endog, groups, alpha)` — la función estándar y "obvia" para Tukey HSD en Python — calcula su propia varianza agrupada a partir de los grupos crudos. **Ignora por completo cualquier factor de bloqueo del modelo.**

En este dataset:

| Método | p-valor para N=0 vs N=1 |
|---|---|
| ANOVA con bloque (F-test, correcto) | **0.0071** |
| `pairwise_tukeyhsd` naive (ignora bloque) | 0.0221 ❌ |
| Tukey HSD calculado a mano con `MS_error` del modelo bloqueado | **0.0071** ✅ |

La diferencia no es un redondeo — es una discrepancia sustantiva (0.0221 vs 0.0071) causada porque `pairwise_tukeyhsd` usa una varianza residual mayor (no reducida por el bloqueo) que la varianza residual real del modelo `rendimiento ~ C(tratamiento) + C(bloque)`. En un ensayo real esto puede cambiar la conclusión de "significativo" a "no significativo" o viceversa, según el umbral de α elegido.

**Implicación directa para el Anexo A de la tesis**: el script base de la tesis (Anexo A) solo muestra `anova_lm` + Shapiro-Wilk — no incluye Tukey. Si se extiende ingenuamente con `pairwise_tukeyhsd`, el módulo estadístico (RN-EST-03, "resultados de la prueba de comparación de medias") producirá resultados incorrectos en **todo diseño con bloqueo** (que es exactamente el diseño RCBD que la tesis usa como ejemplo canónico de fórmula).

## Implementación correcta de Tukey HSD para diseños bloqueados

Dos caminos viables, ambos verificados:

**Opción A — Cálculo manual con `psturng` (Python puro, recomendado para no depender de R)**:
1. Ajustar el modelo completo con bloque: `modelo = ols("rendimiento ~ C(bloque) + C(tratamiento)", data=df).fit()`.
2. Extraer `MS_error` y `df_error` de la tabla ANOVA del modelo completo (no de los grupos crudos).
3. Para cada par de niveles de tratamiento `(i, j)`: `q = |media_i - media_j| / sqrt(MS_error * (1/n_i + 1/n_j) / 2)`.
4. p-valor: `statsmodels.stats.libqsturng.psturng(q, k, df_error)` donde `k` = nº de niveles del tratamiento.
5. Validado en este documento: reproduce exactamente el p-valor de la ANOVA bloqueada (0.0071 = 0.0071).

**Opción B — R vía `rpy2`** (ya mencionado como alternativa en §2.4 de la tesis): `TukeyHSD(aov(rendimiento ~ bloque + tratamiento, data))` de R sí calcula correctamente el HSD usando el `MS_error` del modelo completo — no tiene el bug de `pairwise_tukeyhsd` de Python. Viable si el equipo prefiere no reimplementar la Opción A.

**Decisión pendiente para el equipo**: elegir Opción A (Python puro, sin dependencia de R) vs. Opción B (rpy2). Ver `10_preguntas_abiertas.md` — se agrega como pregunta de prioridad Alta.

## Impacto en las reglas de negocio existentes

`05_reglas_de_negocio.md` → **RN-EST-03 debe actualizarse**: la generación de "resultados de la prueba de comparación de medias" no puede delegarse a `pairwise_tukeyhsd` directo cuando el modelo incluye un factor de bloque — debe usar el `MS_error` del modelo completo (Opción A) o R vía `rpy2` (Opción B). Ver también `09_decisiones_y_supuestos.md` para la decisión formal (DD-07, a agregar).

## Próximo paso técnico sugerido

Antes de tocar `pipeline/ingestion.py` o cualquier módulo de n8n: implementar y testear `pipeline/analysis.py` (o un prototipo previo) con la Opción A, usando este mismo dataset `npk` como fixture de test con resultado conocido (p=0.0071 para N, p=0.0262 para bloque) como test de regresión — si algún refactor futuro rompe estos números, el test falla inmediatamente.
