# Arquitectura Propuesta

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---|---|---|
| Arquitectura en capas (orquestación / procesamiento / persistencia / análisis) | Todo el sistema | Separa responsabilidades, permite sustituir tecnología por capa sin afectar el resto (§4.2) |
| ETL (Extract-Transform-Load) | Pipeline de ingesta → validación → transformación → persistencia | Volúmenes moderados, transformaciones con lógica de dominio compleja; control granular de calidad antes de cargar (§2.3) |
| Validación declarativa | Módulo de validación vía `great_expectations` | Reglas inspeccionables/auditables sin leer código Python (§4.4) |
| Desacoplamiento CLI | Capa de procesamiento invocable independiente de n8n | Testeable en desarrollo sin depender del orquestador; interfaces documentadas para integrarse con orquestadores alternativos (§4.2) |
| Audit log / event sourcing parcial | Capa de persistencia + bitácora de transformaciones | Trazabilidad completa: reconstruir estado del dato en cualquier punto del pipeline (§4.6) |
| Human-in-the-loop | Componente de IA de apoyo | Ningún cambio autónomo sin aprobación humana registrada (§2.6) |

## Estructura de directorios

Definida explícitamente en el **Anexo C** de la tesis — es la fuente de verdad para el scaffold del repositorio de código:

```
pipeline/
├── ingestion.py       — Módulo de ingesta y validación estructural
├── validation.py      — Motor de validación de calidad del dato
├── transformation.py  — Módulo de transformación y estandarización
├── persistence.py     — Módulo de persistencia y auditoría
└── analysis.py        — Módulo de análisis estadístico

config/
├── data_dictionary.json    — Diccionario de variables y reglas de validación
└── analysis_config.yaml    — Parámetros del análisis estadístico

tests/                 — Suite de pruebas unitarias e integración
n8n_workflows/          — Exportaciones de los workflows de n8n en formato JSON
docs/                   — Documentación técnica

requirements.txt        — Dependencias Python fijadas con versiones exactas
README.md               — Instrucciones de instalación, configuración y uso
```

## Seguridad

- **Autenticación/Autorización**: no descrita a nivel de aplicación (no hay usuarios de sistema formales) — control de acceso es a nivel de infraestructura.
- **Gestión de credenciales**: variables de entorno, nunca en código fuente (§4.8).
- **Cifrado**: en tránsito, para comunicaciones entre componentes.
- **Permisos mínimos**: cada componente del pipeline limitado al acceso estrictamente necesario para su función.
- **Backups**: dataset, bitácora y código respaldados automáticamente en ubicación distinta al repositorio principal.

## Variables de entorno

**No enumeradas explícitamente en la tesis** — se infiere (baja confianza) que existirán al menos:

| Variable | Descripción (inferida) | Sensible |
|---|---|---|
| `DATABASE_URL` | Connection string SQLite/PostgreSQL | Sí |
| Credenciales n8n (según modo de despliegue) | Auth del dashboard/API de n8n | Sí |
| Credenciales del proveedor de IA (si se implementa Épica 6) | API key del LLM usado para apoyo | Sí |

**Suposición marcada como incierta** — ver `10_preguntas_abiertas.md`. Se deben definir con precisión en la fase de implementación (Anexo A: "entorno virtual con dependencias fijadas en `requirements.txt`").
