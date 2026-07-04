"""E2E de la cadena CLI vía `subprocess` (change `n8n-orchestration-workflows`
/ C-08, D-9 capa 2).

No hay instancia de n8n en la maquina de desarrollo (Context, design.md):
esta suite ejecuta EXACTAMENTE los mismos comandos que n8n ejecutaria (el
mismo patron `{{$env.PYTHON_BIN}} -m pipeline.<etapa>` de
`n8n_workflows/pipeline_principal.json`) via `subprocess` reales, sobre el
fixture sintetico dedicado de esta suite y una base SQLite temporal REAL
(regla dura del proyecto: nunca se mockea la base). Cubre el happy path
completo, el fallo de datos (RN-ING-04), el fallo transitorio con reintento
exitoso (re-invocabilidad segura de cada etapa) y el fallo persistente con
el payload de escalamiento estructurado (RN-GLB-03).

La capa 1 (estructural del JSON exportado) vive en
`tests/test_n8n_workflows.py`; la capa 3 (runbook manual) vive en
`n8n_workflows/README.md`.

Nota sobre el fixture: los modulos C-03/C-04/C-05 operan sobre datasets
"anchos" (una fila por unidad, contra el diccionario de C-02), mientras que
`pipeline.persistence` (C-06) espera el formato LARGO (`codigo_ensayo`,
`ambiente`, `tratamiento`, `id_unidad`, `variable`, `valor`) -- un dataset
que hoy nunca fluyo de punta a punta por las 5 etapas reales (proposal.md:
"no hay ejecucion end-to-end"). Este change NO modifica la logica de ningun
modulo (fuera de scope): en vez de eso, el fixture dedicado de esta suite
(`data_dictionary_orquestacion_sintetico.json` + el YA EXISTENTE
`dataset_persistencia_sintetico.csv`, C-06) declara el formato largo como
"canonico" en su propio diccionario -- asi ingestion/validation/
transformation lo aceptan tal cual (transformation no hace melt, solo
renombra/estandariza) y persistence lo consume con su mapeo default. Es la
forma honesta de ejercitar los 5 CLIs reales sin inventar logica de reshape
en ningun modulo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"

DICCIONARIO_PATH = FIXTURES_DIR / "data_dictionary_orquestacion_sintetico.json"
DATASET_VALIDO_PATH = FIXTURES_DIR / "dataset_persistencia_sintetico.csv"
DATASET_MALFORMADO_PATH = FIXTURES_DIR / "dataset_orquestacion_malformado.csv"

PYTHON_BIN = sys.executable


def _correr(modulo: str, *args: str, env: dict) -> subprocess.CompletedProcess:
    """Ejecuta `{PYTHON_BIN} -m pipeline.<modulo> <args>` -- EXACTAMENTE el
    patron de comando que `n8n_workflows/pipeline_principal.json` arma para
    cada etapa (D-1/D-10), como proceso real (nunca una llamada a funcion en
    memoria: eso no probaria que n8n pueda invocarlo por CLI, DD-05)."""
    return subprocess.run(
        [PYTHON_BIN, "-m", f"pipeline.{modulo}", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _env_base(database_url: str, tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    env["PYTHON_BIN"] = PYTHON_BIN
    env["PIPELINE_REINTENTOS_MAX"] = "3"
    env["PIPELINE_BACKOFF_BASE_SEGUNDOS"] = "5"
    return env


def _crear_base(database_url: str) -> None:
    from pipeline.db import build_engine
    from pipeline.models import Base

    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()


def _correr_ingestion_a_persistencia(corrida_dir: Path, env: dict, dataset_path: Path) -> dict:
    """Corre las 4 etapas obligatorias por subprocess. Devuelve un dict con
    el `CompletedProcess` de cada etapa, cortando en la primera que no
    devuelva exit 0 (RN-ING-04/RN-GLB-03: no se avanza tras un fallo)."""
    resultados: dict = {}

    resultados["ingestion"] = _correr(
        "ingestion",
        str(dataset_path),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output",
        str(corrida_dir / "ingerido.pkl"),
        env=env,
    )
    if resultados["ingestion"].returncode != 0:
        return resultados

    resultados["validation"] = _correr(
        "validation",
        str(corrida_dir / "ingerido.pkl"),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output-dir",
        str(corrida_dir),
        env=env,
    )
    if resultados["validation"].returncode != 0:
        return resultados

    resultados["transformation"] = _correr(
        "transformation",
        str(corrida_dir / "validos.pkl"),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output-dir",
        str(corrida_dir),
        env=env,
    )
    if resultados["transformation"].returncode != 0:
        return resultados

    resultados["persistence"] = _correr("persistence", str(corrida_dir), env=env)
    return resultados


def _correr_ingestion_a_transformacion(corrida_dir: Path, env: dict, dataset_path: Path) -> dict:
    """Variante de `_correr_ingestion_a_persistencia` que se DETIENE en
    transformation -- para los tests que ejercitan la persistencia por
    separado (7.3/7.4: reintento/escalamiento especificos de esa etapa, sin
    que una persistencia exitosa previa deje `resultado_persistencia.json`
    ya escrito en la corrida)."""
    resultados: dict = {}

    resultados["ingestion"] = _correr(
        "ingestion",
        str(dataset_path),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output",
        str(corrida_dir / "ingerido.pkl"),
        env=env,
    )
    if resultados["ingestion"].returncode != 0:
        return resultados

    resultados["validation"] = _correr(
        "validation",
        str(corrida_dir / "ingerido.pkl"),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output-dir",
        str(corrida_dir),
        env=env,
    )
    if resultados["validation"].returncode != 0:
        return resultados

    resultados["transformation"] = _correr(
        "transformation",
        str(corrida_dir / "validos.pkl"),
        "--dictionary-path",
        str(DICCIONARIO_PATH),
        "--output-dir",
        str(corrida_dir),
        env=env,
    )
    return resultados


class TestHappyPath:
    def test_las_5_etapas_persisten_filas_y_manifiesto_completo(self, tmp_path):
        """7.1: las 5 etapas (incluido el analisis condicional, D-8) corren
        por subprocess sobre el fixture sintetico dedicado, contra SQLite
        temporal REAL (nunca mock, regla dura C-06). Verifica filas
        persistidas + manifiesto completo + analisis condicional CON
        `analysis_config.yaml`."""
        db_path = tmp_path / "e2e_happy.db"
        database_url = f"sqlite:///{db_path}"
        _crear_base(database_url)
        env = _env_base(database_url, tmp_path)

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()

        resultados = _correr_ingestion_a_persistencia(corrida_dir, env, DATASET_VALIDO_PATH)

        for etapa, proceso in resultados.items():
            assert proceso.returncode == 0, (
                f"Etapa '{etapa}' fallo (exit {proceso.returncode}): {proceso.stderr}"
            )

        manifest = json.loads((corrida_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["registros_leidos"] == 6
        assert manifest["registros_validos"] == 6
        assert manifest["registros_rechazados"] == 0

        resultado_persistencia = json.loads(resultados["persistence"].stdout)
        ensayo_id = resultado_persistencia["ensayo_id"]
        assert resultado_persistencia["registros_almacenados"] == 6

        # Verificacion independiente contra la base real (no confiar solo
        # en lo que el CLI reporta -- SQLite real, regla dura del proyecto).
        from pipeline.db import build_engine, build_session_factory
        from pipeline.models import Observacion

        engine = build_engine(database_url)
        session = build_session_factory(engine)()
        try:
            total_observaciones = (
                session.query(Observacion).filter_by().count()
            )
        finally:
            session.close()
        engine.dispose()
        assert total_observaciones == 6

        # D-8: analisis condicional -- CON analysis_config.yaml existente,
        # la etapa de analisis (misma convencion de comando que n8n arma)
        # corre y produce artefactos, re-usando el CLI ya existente (C-07).
        from pipeline.analysis import ConfigAnalisis, escribir_config_yaml

        directorio_analisis = corrida_dir / "analisis"
        config = ConfigAnalisis(
            dataset_id=ensayo_id,
            formula="rendimiento_kg_ha ~ C(bloque) + C(tratamiento)",
            tipo="anova",
            alpha=0.05,
            metodo_comparacion="tukey",
            factor="tratamiento",
            commit_git=None,
            ejecucion_id=None,
            directorio_salida=str(directorio_analisis),
        )
        ruta_yaml = escribir_config_yaml(config, corrida_dir / "analysis_config.yaml")

        proceso_analisis = _correr("analysis", "--config", str(ruta_yaml), env=env)
        assert proceso_analisis.returncode == 0, proceso_analisis.stderr
        assert (directorio_analisis / "resultados.csv").exists()

    def test_sin_analysis_config_la_corrida_termina_en_persistencia(self, tmp_path):
        """7.1 TRIANGULATE: SIN `analysis_config.yaml`, la corrida termina
        exitosamente en persistencia -- el analisis nunca se invoca (D-8: la
        condicion la resuelve el nodo IF del workflow, esta prueba
        simplemente confirma que el CLI de analisis no es una etapa
        obligatoria de la cadena)."""
        db_path = tmp_path / "e2e_sin_analisis.db"
        database_url = f"sqlite:///{db_path}"
        _crear_base(database_url)
        env = _env_base(database_url, tmp_path)

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()

        resultados = _correr_ingestion_a_persistencia(corrida_dir, env, DATASET_VALIDO_PATH)

        for etapa, proceso in resultados.items():
            assert proceso.returncode == 0, f"Etapa '{etapa}' fallo: {proceso.stderr}"

        assert not (corrida_dir / "analysis_config.yaml").exists()
        assert not (corrida_dir / "analisis").exists()


class TestFalloDeDatos:
    def test_archivo_malformado_ingesta_exit_1_y_no_avanza(self, tmp_path):
        """7.2: un archivo malformado (falta la columna obligatoria `valor`)
        hace fallar la ingesta con exit 1 (RN-ING-04, D-4: error de dominio,
        NO se reintenta) -- NINGUNA etapa siguiente se invoca ni se crea
        ningun artefacto de validation/transformation/persistence."""
        db_path = tmp_path / "e2e_malformado.db"
        database_url = f"sqlite:///{db_path}"
        _crear_base(database_url)
        env = _env_base(database_url, tmp_path)

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()

        resultados = _correr_ingestion_a_persistencia(corrida_dir, env, DATASET_MALFORMADO_PATH)

        assert resultados["ingestion"].returncode == 1
        informe = json.loads(resultados["ingestion"].stderr)
        assert informe["descripcion"]

        assert "validation" not in resultados  # la cadena se corto -- RN-ING-04
        assert not (corrida_dir / "ingerido.pkl").exists()
        assert not (corrida_dir / "validos.pkl").exists()


class TestFalloTransitorioConReintentoExitoso:
    def test_persistencia_falla_por_infra_y_reintento_del_mismo_comando_exitoso(self, tmp_path):
        """7.3: primera invocacion de `persistence` con `DATABASE_URL`
        apuntando a un directorio inexistente (infra REAL rota) -> exit 2;
        re-invocacion del MISMO comando de persistencia con la causa
        resuelta -> exit 0. Es la propiedad exacta que el sub-workflow de
        reintentos (D-5) necesita: re-invocabilidad segura por etapa."""
        db_path_rota = tmp_path / "directorio_inexistente" / "e2e_rota.db"
        database_url_rota = f"sqlite:///{db_path_rota}"

        db_path_ok = tmp_path / "e2e_retry_ok.db"
        database_url_ok = f"sqlite:///{db_path_ok}"
        _crear_base(database_url_ok)

        env_ok = _env_base(database_url_ok, tmp_path)

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()

        # Ingesta/validacion/transformacion corren con la base YA accesible
        # (el fallo transitorio simulado es especificamente el de persistencia,
        # la etapa que toca la base de datos) -- SIN correr persistencia todavia.
        resultados = _correr_ingestion_a_transformacion(corrida_dir, env_ok, DATASET_VALIDO_PATH)
        assert resultados["transformation"].returncode == 0, resultados["transformation"].stderr

        # Primer intento de persistencia: DATABASE_URL rota.
        env_roto = _env_base(database_url_rota, tmp_path)
        primer_intento = _correr("persistence", str(corrida_dir), env=env_roto)
        assert primer_intento.returncode == 2
        assert not (corrida_dir / "resultado_persistencia.json").exists()

        # Re-invocacion del MISMO comando, misma corrida_dir, base ahora ok.
        segundo_intento = _correr("persistence", str(corrida_dir), env=env_ok)
        assert segundo_intento.returncode == 0
        resultado = json.loads(segundo_intento.stdout)
        assert resultado["registros_almacenados"] == 6


class TestFalloPersistente:
    def test_fallo_persistente_agota_reintentos_y_arma_payload_de_escalamiento(self, tmp_path):
        """7.4: exit 2 repetido hasta `PIPELINE_REINTENTOS_MAX` produce, en
        cada invocacion, un informe estructurado en stderr -- la materia
        prima con la que el sub-workflow de reintentos (D-5, seccion
        'Salida: Escalamiento' de `ejecutar_etapa_con_reintentos.json`) arma
        el payload de escalamiento (etapa, run_id, intentos, stderr, D-6).
        No se finge un runtime n8n (D-9): esta prueba verifica que el CLI
        aporta, de forma determinista, todos los datos que ese payload
        necesita."""
        db_path_rota = tmp_path / "directorio_inexistente" / "e2e_persistente.db"
        database_url_rota = f"sqlite:///{db_path_rota}"
        env_roto = _env_base(database_url_rota, tmp_path)

        db_path_ok = tmp_path / "e2e_persistente_setup.db"
        database_url_ok = f"sqlite:///{db_path_ok}"
        _crear_base(database_url_ok)
        env_ok = _env_base(database_url_ok, tmp_path)

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        resultados = _correr_ingestion_a_transformacion(corrida_dir, env_ok, DATASET_VALIDO_PATH)
        assert resultados["transformation"].returncode == 0

        max_intentos = int(env_roto["PIPELINE_REINTENTOS_MAX"])
        informes_por_intento = []
        for _ in range(max_intentos):
            proceso = _correr("persistence", str(corrida_dir), env=env_roto)
            # Cada intento sigue siendo un fallo de infra determinista (exit 2)
            # -- el sub-workflow de reintentos (D-5) necesita EXACTAMENTE esta
            # propiedad para poder distinguir "todavia transitorio" de "ya se
            # resolvio", y para saber cuando agotar los reintentos y escalar.
            assert proceso.returncode == 2
            informe = json.loads(proceso.stderr)
            assert informe["error"]  # dato con el que D-6 arma el campo 'stderr' del payload
            informes_por_intento.append(informe)

        # Determinismo: agotar los reintentos NO deja ningun estado parcial
        # -- ni un exito espurio en ningun intento intermedio, ni un
        # resultado_persistencia.json a medio escribir (D-9: el CLI aporta
        # todos los datos que el payload de escalamiento necesita -- etapa,
        # comando, exit code, stderr, run_id, intentos -- sin fingir n8n).
        assert len(informes_por_intento) == max_intentos
        assert not (corrida_dir / "resultado_persistencia.json").exists()
