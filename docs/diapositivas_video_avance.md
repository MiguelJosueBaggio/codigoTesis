---
marp: true
theme: default
paginate: true
size: 16:9
header: 'Automatización de ensayos agrícolas'
---

<style>
section {
  background: #EEF3EC;
  color: #1E2B22;
  border-top: 10px solid #1E2B22;
  font-family: 'Calibri', 'Segoe UI', Arial, sans-serif;
}
section h1, section h2 {
  color: #1E2B22;
  font-family: 'Cambria', Georgia, serif;
}
section p, section li {
  color: #5B6B62;
}
section.title, section.closing {
  background: #1E2B22;
  color: #EEF3EC;
  border-top: none;
}
section.title h1, section.title h2, section.title h3,
section.closing h1, section.closing h2 {
  color: #EEF3EC;
  font-family: 'Cambria', Georgia, serif;
}
section.title p, section.title li,
section.closing p, section.closing li {
  color: #CFE3D4;
}
section.title strong, section.closing strong {
  color: #A66A2E;
}
strong {
  color: #1C7293;
}
table {
  border-collapse: collapse;
  margin: 0 auto;
}
table th {
  background: #1E2B22;
  color: #EEF3EC;
  padding: 10px 18px;
  font-family: 'Cambria', Georgia, serif;
}
table td {
  padding: 10px 18px;
  border-bottom: 1px solid #9FC2A8;
  color: #5B6B62;
}
blockquote {
  border-left: 6px solid #1C7293;
  background: #DCE9DF;
  color: #1E2B22;
  font-style: italic;
  padding: 0.6em 1em;
}
</style>

<!-- _class: title -->
<!-- _paginate: false -->
<!-- _header: '' -->

# Automatización de cargas de datos y análisis estadístico en ensayos agrícolas

### Diseño, implementación y validación de un flujo reproducible basado en n8n y Python

**Relator**: Nahuel Morales
Equipo de tesis: Miguel Baggio · Alejo Osorio · Ignacio Aguilar
Director: Mg. Alberto Cortez

---

## Agenda (10 min)

1. Problema y motivación
2. Pregunta de investigación y objetivos
3. Marco teórico
4. Metodología
5. Resultados preliminares
6. Discusión
7. Limitaciones y trabajo futuro

---

## El problema

- La calidad de las recomendaciones técnicas depende de la **integridad del dato**, no solo del diseño experimental
- Gestión del dato en ensayos agrícolas: **manual y frágil**
  - Planillas de papel → transcripción a hojas de cálculo → procesos ad hoc
- Cada paso manual = una oportunidad de error
  - Cifra mal transcrita, unidad confundida, tratamiento mal codificado
- **Sin registro formal de transformaciones** → imposible reconstruir la historia del dato

---

## La brecha que motiva el trabajo

> Un análisis estadístico impecable, ejecutado sobre datos de mala calidad, produce conclusiones inválidas con el mismo rigor formal que un análisis correcto.

Las herramientas para automatizar, validar y reproducir **ya existen**.

Lo que falta: integrarlas en un sistema coherente, documentado y adaptado al dato experimental agrícola.

---

## Pregunta de investigación

¿Cómo diseñar e implementar un flujo automatizado, trazable y reproducible que:

- integre la carga de datos de ensayos agrícolas
- ejecute validaciones de calidad
- garantice la trazabilidad de cada transformación
- habilite un análisis estadístico consistente

reduciendo tiempos y errores respecto de un proceso manual de referencia?

---

## Objetivos

**General**: diseñar, implementar y validar un sistema reproducible que automatice carga, validación y procesamiento de datos de ensayos agrícolas, con análisis estadístico coherente con el diseño experimental.

**Específicos** (3 de 5):
1. Definir un esquema de datos formal (variables, tipos, unidades, rangos, reglas)
2. Implementar el flujo completo (n8n + Python), con auditoría
3. Integrar un módulo de análisis estadístico reproducible

---

## Marco teórico — 4 pilares

1. **Calidad y trazabilidad del dato** en investigación experimental
2. **Automatización de flujos** (ETL) con orquestación — n8n
3. **Reproducibilidad computacional** — Python, dependencias fijas, código versionado
4. **Estadística de la experimentación agrícola** — ANOVA y sus supuestos, alternativas cuando no se cumplen

*No reemplazamos al estadístico: construimos el sistema de ingeniería que ejecuta ese análisis correctamente.*

---

## Metodología de investigación

- **Investigación aplicada orientada al diseño** — el resultado es un artefacto (el flujo), no una ley universal
- **Estudio de caso instrumental** — un ensayo real como instrumento de desarrollo y evaluación
- **Implementación incremental**, módulo por módulo:

  ingesta → validación → transformación → persistencia → análisis estadístico

  Cada módulo se prueba de forma aislada antes de integrarse.

---

## Rigor en la construcción del software

- **Desarrollo dirigido por especificaciones**: cada componente se especifica por completo antes de escribir código
- **Control de versiones**: cada resultado es trazable a una versión exacta del código
- **Ciclo estricto de pruebas**:

  prueba que falla → código mínimo que la pasa → casos límite → refactor sin romper nada

*Este ciclo es lo que permitió detectar el hallazgo que sigue.*

---

## Resultados preliminares — la base

- **Base de conocimiento**: 13 documentos canónicos (actores, reglas de negocio, modelo de datos, decisiones de arquitectura)
- **Hoja de ruta** de desarrollo: camino crítico de **9 pasos**
- **Núcleo de análisis estadístico ya construido y validado**
  - 45 pruebas automáticas, en verde
  - ANOVA, Tukey HSD, Kruskal-Wallis, diagnóstico de supuestos, transformaciones

---

## El hallazgo más valioso hasta hoy

Al validar la comparación de medias post-ANOVA:

**`pairwise_tukeyhsd` (statsmodels) calcula mal el Tukey HSD en diseños con bloqueo** — ignora el efecto del bloque.

Validado contra el dataset **npk** (Fisher, Rothamsted):

| Método | Valor p |
|---|---|
| Función estándar (ingenua) | **0,0221** |
| Cálculo correcto (bloqueo + tratamiento) | **0,0071** |

Discrepancia sustantiva — capaz de cambiar una conclusión estadística.

---

## Diseño arquitectónico completo

- **Capa de interacción por Telegram**
  - Dos roles: Ingeniero y Ayudante
  - Motor genérico de sesiones dirigido por datos
- **Captura de datos de campo por reconocimiento óptico** (capacidad opcional)
  - Para condiciones sin conectividad confiable

Diseños ya completos, en incorporación al texto de la tesis.

---

## Discusión

✅ Núcleo estadístico construido y **correcto** → responde parcialmente al objetivo de reproducibilidad
✅ Arquitectura completa **diseñada y documentada**

⏳ Validación empírica sobre un caso real → **pendiente**
⏳ Comparación contra el proceso manual → **pendiente**

🗺️ Camino crítico ya mapeado y módulos pendientes con **contrato definido** → lo que falta es ejecución, no diseño

*El hallazgo de Tukey ya demuestra el valor de construir con rigor antes de tener el caso real.*

---

## Limitaciones y trabajo futuro

**Limitación central**: la elección del caso de estudio real (ensayo, institución, cultivo) sigue pendiente.

Condiciona:
- el diccionario de variables definitivo
- la ejecución de punta a punta
- la comparación contra el proceso manual

**Próximos pasos**: ingesta, validación, transformación, persistencia auditable y orquestación en n8n, siguiendo la hoja de ruta.

**Más allá de esta tesis** (líneas documentadas, no construidas):
- Reuso académico del dataset acumulado → meta-análisis y base para componentes de IA
- Geolocalización de Ambiente → correlación con datos climáticos externos

---

<!-- _class: closing -->
<!-- _paginate: false -->

# Cierre

Las decisiones de fondo son sólidas y el núcleo crítico funciona de forma correcta y verificable.

Sobre esa base construiremos la validación empírica que falta.

**Gracias al Mg. Alberto Cortez por su guía, y al comité por su atención.**
