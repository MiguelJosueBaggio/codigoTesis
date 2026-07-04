# Automatización de Ensayos Agrícolas

Pipeline de ingesta, validación, transformación, análisis estadístico
(ANOVA + Tukey HSD) y persistencia auditada de datos de ensayos
agrícolas, orquestado con n8n e interacción humana exclusivamente por
Telegram. Trabajo de tesis (UTN FR Mendoza).

## Requisitos

- **Python 3.10 a 3.13** (⚠️ NO 3.14: `great_expectations` lo excluye).
  Recomendado: 3.13. En Windows: `winget install Python.Python.3.13`.
- **Git**.
- Opcional, solo para la capa de orquestación visual: **Node.js LTS**
  (18+) y **pnpm** para instalar n8n (ver abajo).

## Instalación

1. Clonar el repo y crear el entorno virtual **con Python 3.13**:

   ```bash
   # Windows
   py -3.13 -m venv .venv
   .venv\Scripts\activate

   # Unix/macOS
   python3.13 -m venv .venv
   source .venv/bin/activate
   ```

2. Instalar las dependencias fijadas:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copiar `.env.example` a `.env` y completar las variables locales
   (ver las notas dentro del propio archivo). Las esenciales:

   - `DATABASE_URL` — ej. `sqlite:///datos/ensayos.db` (desarrollo).
   - `BACKUP_DIR` — carpeta de respaldos, **fuera** del repo.
   - `PYTHON_BIN` — ruta absoluta al Python del venv (la usa n8n).
   - `PIPELINE_*` — directorios de corridas y parámetros de reintento.

4. Crear el esquema de base de datos (migraciones Alembic):

   ```bash
   python -m alembic upgrade head
   ```

5. Verificar la instalación corriendo la suite completa:

   ```bash
   python -m pytest tests/ -q
   ```

   Debe dar **217 passed, 1 skipped** (el skip es la paridad
   PostgreSQL, que solo corre si definís `POSTGRES_TEST_URL`).

## Correr el pipeline por CLI

Cada módulo expone una CLI fina (n8n invoca exactamente estos comandos;
podés correrlos a mano en el mismo orden). Convención de exit codes:
`0` OK · `1` error de datos (no reintentar) · `2` error transitorio de
infraestructura (reintentable).

```bash
# 1. Ingesta: lee CSV/Excel, valida estructura, deja ingerido.pkl en la corrida
python -m pipeline.ingestion datos.csv \
    --dictionary-path config/data_dictionary.json --output corridas/demo

# 2. Validación: calidad de datos declarativa (great_expectations),
#    salida dual validos.pkl / rechazados.csv
python -m pipeline.validation corridas/demo/ingerido.pkl \
    --dictionary-path config/data_dictionary.json --output-dir corridas/demo

# 3. Transformación: nombres canónicos, categóricos, unidades → tidy.pkl
python -m pipeline.transformation corridas/demo/validos.pkl \
    --dictionary-path config/data_dictionary.json --output-dir corridas/demo

# 4. Persistencia: escribe dataset + bitácora + auditoría en la DB
python -m pipeline.persistence corridas/demo

# 5. (Opcional) Análisis: ANOVA/Tukey, diagnósticos, CSV+HTML+PNG
python -m pipeline.analysis --dataset-id 1 --formula "respuesta ~ tratamiento" \
    --tipo anova --output-dir corridas/demo/analisis
#    ...o re-ejecutable desde YAML (RN-EST-04):
python -m pipeline.analysis --config corridas/demo/analisis/analysis_config.yaml
```

Cada etapa deja su informe JSON en el directorio de corrida y acumula
conteos en `manifest.json` (fuente única de la auditoría RN-AUD-01).
Argumentos exactos: `python -m pipeline.<modulo> --help`.

> Los tests e2e de `tests/test_cli_chain.py` ejecutan esta misma cadena
> por subprocess sobre el fixture sintético — son la referencia viva de
> cómo encadenar las CLIs.

## Orquestación con n8n (opcional para desarrollo)

Los workflows exportados viven en `n8n_workflows/` (ver su `README.md`
para el runbook completo de verificación en 3 capas).

1. Instalar n8n en el host (NO Docker: los nodos Execute Command deben
   poder invocar el Python del venv local):

   ```bash
   npm install -g n8n
   ```

   ⚠️ n8n se instala con **npm**, no con pnpm: es la única vía que su
   propio CI testea. Bajo pnpm el grafo de n8n se rompe de tres formas
   (dependencia `xlsx` servida por URL, `sqlite3` opcional descartada
   por el bloqueo de build scripts, y peers de langchain irresolubles
   con aislamiento estricto). Verificado el 2026-07-03 con pnpm 11.3 y
   n8n 2.29.3.

2. Arrancar n8n (`n8n start`), abrir `http://localhost:5678`.

3. Importar los tres JSON de `n8n_workflows/` (menú → Import from file):
   `pipeline_principal`, `ejecutar_etapa_con_reintentos`,
   `escalamiento_notificacion`.

4. Definir en n8n las variables de entorno que usan los workflows
   (`PYTHON_BIN`, `PIPELINE_*`, `DATABASE_URL`) — mismos valores que tu
   `.env`.

## Estructura del repo

| Ruta | Qué es |
|---|---|
| `pipeline/` | Los módulos Python (ingesta → … → análisis + núcleo estadístico) |
| `config/` | Diccionario de variables y configuración de análisis |
| `alembic/` | Migraciones versionadas del esquema |
| `n8n_workflows/` | Workflows n8n exportados (JSON) + runbook |
| `scripts/backup.py` | Respaldo a `BACKUP_DIR` (RN-AUD-03) |
| `tests/` | Suite completa (fixtures 100 % sintéticos) |
| `knowledge-base/` | La fuente de verdad del dominio |
| `openspec/` | Especificaciones y changes (OpenSpec) |

## Para agentes / colaboradores

Antes de tocar código, leé **`AGENTS.md`** (o su copia `CLAUDE.md`): ahí
está el stack completo, el índice de la base de conocimiento
(`knowledge-base/`), el roadmap de changes (`CHANGES.md`) y las reglas
duras del proyecto. Este README no las duplica.
