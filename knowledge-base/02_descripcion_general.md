# Descripción General

## Stack tecnológico

| Capa | Tecnologías | Versión mínima / notas |
|---|---|---|
| Orquestación | n8n (open source, workflows visuales basados en nodos) | Soporta nodos de código JS y Python |
| Procesamiento | Python | ≥ 3.10 |
| Manipulación de datos | pandas, NumPy | — |
| Validación declarativa | great_expectations | Reglas expresadas en JSON, ejecutables sobre DataFrames de pandas |
| Análisis estadístico | statsmodels, scipy | ANOVA vía `statsmodels.stats.anova_lm`, diagnósticos vía `scipy.stats` |
| Visualización de diagnósticos | matplotlib | Gráficos Q-Q, residuos vs. ajustados (PNG) |
| Persistencia — desarrollo | SQLite | Sin complejidad operativa adicional |
| Persistencia — producción | PostgreSQL | Para volumen/concurrencia mayor |
| Control de versiones | Git | Cada ejecución auditada referencia el hash del commit |
| Gestión de dependencias | pip + `requirements.txt` (versiones fijadas) | Alternativas mencionadas: conda, Poetry — no elegido explícitamente |

**Suposición**: el repositorio de código es el mismo que este (`tesis-automatizacion-ensayos-agricolas`), no un repo separado del "sistema" vs. la "tesis" — a confirmar con el equipo.

## Arquitectura general

Arquitectura en 4 capas con responsabilidades estrictamente separadas (§4.2 de la tesis):

```
Fuentes de datos (CSV/Excel)
        │
        ▼
┌─────────────────────────────┐
│  CAPA DE ORQUESTACIÓN (n8n) │  triggers, reintentos c/backoff exponencial,
│                              │  escalamiento a notificación humana, logging
└──────────────┬───────────────┘
               │ invoca (CLI o llamada directa)
               ▼
┌─────────────────────────────┐
│  CAPA DE PROCESAMIENTO      │  desacoplada de n8n, invocable por CLI
│  (scripts Python)           │  ingesta → validación → transformación
└──────────────┬───────────────┘
               ▼
┌─────────────────────────────┐
│  CAPA DE PERSISTENCIA       │  SQLite (dev) / PostgreSQL (prod)
│                              │  dataset validado + catálogo + bitácora
└──────────────┬───────────────┘
               ▼
┌─────────────────────────────┐
│  CAPA DE ANÁLISIS           │  módulo Python independiente, parametrizable
│  ESTADÍSTICO                │  (fórmula R-style, tipo de análisis)
└──────────────┬───────────────┘
               ▼
   Reportes (CSV / HTML / PNG / YAML de config)
```

**Justificación de la separación en capas**: facilita mantenimiento independiente, sustitución de tecnologías específicas sin afectar el resto (p.ej. cambiar n8n por otro orquestador no debería tocar la capa de procesamiento), y comprensión del flujo a alto nivel. La capa de procesamiento es la más crítica de desacoplar: debe poder invocarse desde línea de comandos para pruebas/desarrollo sin depender de n8n.

**Diagrama de arquitectura definitivo**: pendiente — la tesis lo marca explícitamente como *"a reemplazar cuando se finalice la implementación"* (§4.9 y Anexo B). Ver `10_preguntas_abiertas.md`.

## Integraciones externas

| Servicio | Propósito | Tipo |
|---|---|---|
| n8n (conectores nativos) | Detección de nuevos archivos, triggers programados, notificaciones | Nativo n8n / webhook |
| LLM / servicio de IA (no especificado cuál) | Estandarización semiautomática de campos con alta variabilidad léxica, detección de anomalías, sugerencias de corrección | Apoyo opcional — **requiere aprobación humana explícita antes de aplicar cualquier cambio**; toda decisión (aprobación/rechazo) se registra en la bitácora de auditoría |

**Suposición (baja confianza)**: la tesis no especifica qué proveedor de LLM/IA se usaría. Ver `10_preguntas_abiertas.md`.

## API REST

No aplica — el sistema no expone una API REST de cara a usuarios finales. La interacción es vía archivos de entrada (CSV/Excel) + workflows de n8n + invocación CLI de los módulos Python. **Pendiente de confirmar** si se requiere una interfaz propia además del dashboard nativo de n8n (ver `10_preguntas_abiertas.md`).
