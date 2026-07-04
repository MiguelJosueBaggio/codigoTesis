"""Tests TDD para pipeline/analysis.py (change statistical-analysis-module, C-07).

Reglas duras verificadas por esta suite (ver tasks.md):
- DD-07/RN-EST-06: Tukey SIEMPRE del núcleo (`analysis_core.tukey_hsd`), nunca
  `pairwise_tukeyhsd` naive sobre grupos crudos — anti-regresión pinneada
  sobre `npk` (grupo 4).
- SQLite real para persistencia (sin mocks) vía los fixtures `db_session`.
- PNG: aserción por existencia/tamaño, nunca contenido de píxeles.
- Fixtures sintéticos únicamente (o `npk`, ya versionado como fixture de
  referencia del núcleo).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from pipeline.analysis import (
    AnalysisError,
    DatasetNoEncontradoError,
    TipoAnalisisNoSoportadoError,
    analizar,
    cargar_dataset,
    diagnostico_extendido,
    ejecutar_analisis,
    escribir_config_yaml,
    escribir_tabla_resultados,
    generar_graficos_diagnostico,
    leer_config_yaml,
    main,
    re_ejecutar_desde_config,
)
from pipeline.models import Ensayo
from pipeline.persistence import RunMetadata, persist
from pipeline.transformation import TransformationOutcome


def _persistir(session, df_tidy, tmp_path, contenido="contenido"):
    """Persiste `df_tidy` vía `pipeline.persistence.persist` en SQLite real
    (nunca mock, regla dura del proyecto), devolviendo la `Ejecucion`."""
    archivo = tmp_path / f"entrada_{abs(hash(contenido))}.csv"
    archivo.write_text(contenido, encoding="utf-8")
    outcome = TransformationOutcome(df_tidy=df_tidy, operaciones=[])
    run_metadata = RunMetadata(
        ruta_archivo_entrada=archivo,
        registros_leidos=len(df_tidy),
        registros_validos=len(df_tidy),
        registros_rechazados=0,
    )
    return persist(outcome, run_metadata, session)


def _ensayo_id_por_codigo(session, codigo: str) -> int:
    return session.execute(select(Ensayo).where(Ensayo.codigo == codigo)).scalar_one().id


# --- Grupo 2: Lectura del dataset persistido por id (RN-EST-05, D2/D3) ------


class TestCargarDataset:
    def test_reconstruye_tidy_desde_entidades_persistidas(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-cargar")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")

        tidy = cargar_dataset(db_session, ensayo_id)

        assert len(tidy) == len(dataset_dca_df)
        assert "tratamiento" in tidy.columns
        assert "bloque" in tidy.columns
        assert "rendimiento" in tidy.columns
        assert set(tidy["tratamiento"]) == {"A", "B", "C"}
        assert set(tidy["bloque"]) == {"Campo1"}

    def test_id_inexistente_levanta_error_explicito(self, db_session):
        with pytest.raises(DatasetNoEncontradoError):
            cargar_dataset(db_session, 999999)

    def test_mapeo_roles_sobreescrito_por_parametro(self, db_session, dataset_bca_df, tmp_path):
        _persistir(db_session, dataset_bca_df, tmp_path, contenido="bca-mapeo")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-BCA-01")

        tidy = cargar_dataset(
            db_session, ensayo_id, mapeo_roles={"tratamiento": "N", "bloque": "block"}
        )

        assert "N" in tidy.columns
        assert "block" in tidy.columns
        assert "tratamiento" not in tidy.columns
        assert "bloque" not in tidy.columns


# --- Grupo 3: Dispatch del análisis delegando en el núcleo (RN-EST-01, D1) --


class TestEjecutarAnalisisDispatch:
    def test_anova_dca_produce_tabla_del_nucleo(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-anova")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        resultado = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="anova")

        assert "C(tratamiento)" in resultado.tabla.index
        assert "Residual" in resultado.tabla.index
        for columna in ("df", "sum_sq", "F", "PR(>F)"):
            assert columna in resultado.tabla.columns

    def test_anova_bca_produce_tabla_bloqueada_y_tukey(self, db_session, dataset_bca_df, tmp_path):
        _persistir(db_session, dataset_bca_df, tmp_path, contenido="bca-anova")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-BCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(bloque) + C(tratamiento)", tipo="anova", factor="tratamiento"
        )

        assert "C(bloque)" in resultado.tabla.index
        assert "C(tratamiento)" in resultado.tabla.index
        assert resultado.tukey is not None
        assert {"group1", "group2", "meandiff", "p_value", "reject"} <= set(resultado.tukey.columns)

    def test_kruskal_devuelve_resultado_del_nucleo(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-kruskal")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="kruskal", factor="tratamiento"
        )

        assert {"statistic", "p_value", "reject"} <= set(resultado.tabla.columns)

    def test_tipo_lmm_no_soportado_rechaza_con_error_claro(self, dataset_dca_df):
        with pytest.raises(TipoAnalisisNoSoportadoError, match="LMM"):
            ejecutar_analisis(dataset_dca_df, "rendimiento ~ C(tratamiento)", tipo="lmm")

    def test_glm_gaussiano_minimo_happy_path(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-glm")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        resultado = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="glm")

        assert "p_value" in resultado.tabla.columns
        assert len(resultado.tabla) > 0

    def test_glm_familia_no_gaussiana_rechazada(self, dataset_dca_df):
        with pytest.raises(AnalysisError):
            ejecutar_analisis(
                dataset_dca_df, "rendimiento ~ C(tratamiento)", tipo="glm", familia_glm="poisson"
            )


# --- Grupo 4: Blindaje DD-07 / RN-EST-06 (anti-regresión Tukey) -------------


class TestAntiRegresionTukeyDD07:
    def test_pvalor_bloqueado_coincide_con_nucleo_no_con_naive(self, db_session, npk_df, tmp_path):
        df_tidy_npk = pd.DataFrame(
            {
                "codigo_ensayo": "E-NPK-01",
                "ambiente": npk_df["block"].astype(str),
                "tratamiento": npk_df["N"].astype(str),
                "id_unidad": npk_df["rownames"].astype(str),
                "variable": "rendimiento",
                "valor": npk_df["rendimiento"],
            }
        )
        _persistir(db_session, df_tidy_npk, tmp_path, contenido="npk-antiregresion")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-NPK-01")

        df = cargar_dataset(
            db_session, ensayo_id, mapeo_roles={"tratamiento": "N", "bloque": "block"}
        )

        resultado = ejecutar_analisis(df, "rendimiento ~ C(block) + C(N)", tipo="anova", factor="N")

        fila = resultado.tukey.iloc[0]
        assert fila["p_value"] == pytest.approx(0.0071, abs=1e-4)
        assert fila["p_value"] != pytest.approx(0.0221, abs=1e-4)


# --- Grupo 5: Tabla de resultados CSV + HTML (RN-EST-02) --------------------


class TestReporteTablaCsvHtml:
    def test_se_generan_csv_y_html_con_mismos_valores(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-csvhtml")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)
        resultado = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="anova")

        directorio = tmp_path / "salida_csvhtml"
        ruta_csv, ruta_html = escribir_tabla_resultados(resultado.tabla, directorio)

        assert ruta_csv.exists() and ruta_csv.stat().st_size > 0
        assert ruta_html.exists() and ruta_html.stat().st_size > 0

        releido = pd.read_csv(ruta_csv, index_col=0)
        assert releido["F"].to_numpy() == pytest.approx(resultado.tabla["F"].to_numpy(), nan_ok=True)

    def test_segundo_tipo_kruskal_tambien_materializa_tabla(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-kruskal-csv")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)
        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="kruskal", factor="tratamiento"
        )

        directorio = tmp_path / "salida_kruskal"
        ruta_csv, ruta_html = escribir_tabla_resultados(resultado.tabla, directorio, nombre_base="kruskal")

        assert ruta_csv.exists() and ruta_csv.stat().st_size > 0
        assert ruta_html.exists() and ruta_html.stat().st_size > 0


# --- Grupo 6: Diagnóstico de supuestos con PNG (RN-EST-03, D4, OQ3/OQ4) -----


class TestDiagnosticoConPng:
    def test_se_generan_png_qq_y_residuos(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-png")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)
        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="anova", factor="tratamiento"
        )

        directorio = tmp_path / "salida_png"
        ruta_qq, ruta_residuos = generar_graficos_diagnostico(resultado.modelo, directorio)

        assert ruta_qq.exists() and ruta_qq.stat().st_size > 0
        assert ruta_residuos.exists() and ruta_residuos.stat().st_size > 0

    def test_diagnostico_detecta_violacion_normalidad(self):
        df = pd.DataFrame(
            {
                "tratamiento": ["A"] * 10 + ["B"] * 10,
                "rendimiento": (
                    [1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 1.02, 0.98, 50.0]
                    + [2.0, 2.1, 1.9, 2.0, 2.05, 1.95, 2.0, 2.02, 1.98, 80.0]
                ),
            }
        )

        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="anova", factor="tratamiento"
        )

        assert resultado.diagnosticos["shapiro"]["p_value"] < 0.05

    def test_diagnostico_detecta_violacion_homocedasticidad(self):
        rng = np.random.default_rng(seed=42)
        grupo_a = rng.normal(10, 1, 20)
        grupo_b = rng.normal(10, 60, 20)
        df = pd.DataFrame(
            {
                "tratamiento": ["A"] * 20 + ["B"] * 20,
                "rendimiento": np.concatenate([grupo_a, grupo_b]),
            }
        )

        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="anova", factor="tratamiento"
        )

        assert resultado.diagnosticos["levene"]["p_value"] < 0.05

    def test_diagnostico_extendido_cooks_y_bartlett(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-extendido")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)
        resultado = ejecutar_analisis(
            df, "rendimiento ~ C(tratamiento)", tipo="anova", factor="tratamiento"
        )

        extendido = diagnostico_extendido(
            resultado.modelo, df, "rendimiento ~ C(tratamiento)", "tratamiento", top_n=3
        )

        assert len(extendido["cooks_distance_top"]) == 3
        assert "cooks_distance" in extendido["cooks_distance_top"].columns
        assert "p_value" in extendido["bartlett"]


# --- Grupo 7: Config YAML re-ejecutable (RN-EST-04, D5) ---------------------


class TestConfigYamlReejecutable:
    def test_analizar_escribe_yaml_reejecutable_y_reproduce_tabla(
        self, db_session, dataset_dca_df, tmp_path
    ):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-yaml")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")

        directorio = tmp_path / "salida_yaml"
        reporte = analizar(
            directorio_salida=directorio,
            formula="rendimiento ~ C(tratamiento)",
            tipo="anova",
            session=db_session,
            dataset_id=ensayo_id,
            factor="tratamiento",
        )

        assert reporte.ruta_yaml.exists()
        config = leer_config_yaml(reporte.ruta_yaml)
        assert config["dataset_id"] == ensayo_id
        assert config["formula"] == "rendimiento ~ C(tratamiento)"
        assert config["tipo"] == "anova"
        assert "commit_git" in config

        reporte_2 = re_ejecutar_desde_config(reporte.ruta_yaml, session=db_session)

        pd.testing.assert_frame_equal(
            reporte.resultado_analisis.tabla.reset_index(drop=True),
            reporte_2.resultado_analisis.tabla.reset_index(drop=True),
        )


# --- Grupo 8: Reproducibilidad (RN-GLB-02, D6) ------------------------------


class TestReproducibilidad:
    def test_misma_corrida_dos_veces_tablas_identicas(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-repro")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        r1 = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="anova")
        r2 = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="anova")

        pd.testing.assert_frame_equal(r1.tabla, r2.tabla)

    def test_tabla_no_incluye_timestamps_ni_nonces(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-notimestamp")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)
        resultado = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="anova")

        columnas = {c.lower() for c in resultado.tabla.columns}
        assert not any(("time" in c) or ("fecha" in c) or ("nonce" in c) for c in columnas)

    def test_reproducibilidad_segundo_tipo_kruskal(self, db_session, dataset_dca_df, tmp_path):
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-repro-kw")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        r1 = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="kruskal", factor="tratamiento")
        r2 = ejecutar_analisis(df, "rendimiento ~ C(tratamiento)", tipo="kruskal", factor="tratamiento")

        pd.testing.assert_frame_equal(r1.tabla, r2.tabla)


# --- Grupo 9: CLI fino (RN-EST-05, DD-09, patrón ingestion.py) --------------


class TestCliFino:
    def test_main_standalone_por_id_exitoso(self, dataset_dca_df, tmp_path, monkeypatch):
        from pipeline.db import build_engine, build_session_factory
        from pipeline.models import Base

        db_path = tmp_path / "cli_test.db"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)

        engine = build_engine(database_url)
        Base.metadata.create_all(engine)
        session = build_session_factory(engine)()
        try:
            _persistir(session, dataset_dca_df, tmp_path, contenido="dca-cli-main")
            ensayo_id = _ensayo_id_por_codigo(session, "E-DCA-01")
        finally:
            session.close()
        engine.dispose()

        directorio_salida = tmp_path / "salida_cli"
        codigo = main(
            [
                "--dataset-id",
                str(ensayo_id),
                "--formula",
                "rendimiento ~ C(tratamiento)",
                "--tipo",
                "anova",
                "--factor",
                "tratamiento",
                "--output-dir",
                str(directorio_salida),
            ]
        )

        assert codigo == 0
        assert (directorio_salida / "resultados.csv").exists()
        assert (directorio_salida / "config.yaml").exists()

    def test_main_error_dataset_inexistente_codigo_no_cero_y_stderr(self, tmp_path, monkeypatch, capsys):
        from pipeline.db import build_engine
        from pipeline.models import Base

        db_path = tmp_path / "cli_test_error.db"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        engine = build_engine(database_url)
        Base.metadata.create_all(engine)
        engine.dispose()

        codigo = main(
            ["--dataset-id", "999999", "--formula", "rendimiento ~ C(tratamiento)"]
        )

        assert codigo != 0
        capturado = capsys.readouterr()
        assert "error" in capturado.err.lower()

    def test_analizar_encadenado_con_dataframe_directo(self, db_session, dataset_dca_df, tmp_path):
        """Invocación encadenada (RN-EST-05): `analizar` recibe un `df` tidy
        ya armado (como lo entregaría un paso previo del pipeline en
        proceso), sin pasar por `session`/`dataset_id`."""
        _persistir(db_session, dataset_dca_df, tmp_path, contenido="dca-encadenado")
        ensayo_id = _ensayo_id_por_codigo(db_session, "E-DCA-01")
        df = cargar_dataset(db_session, ensayo_id)

        directorio = tmp_path / "salida_encadenado"
        reporte = analizar(
            directorio_salida=directorio,
            formula="rendimiento ~ C(tratamiento)",
            tipo="anova",
            df=df,
        )

        assert reporte.ruta_csv.exists()
        assert not reporte.resultado_analisis.tabla.empty

    def test_analizar_sin_df_ni_session_dataset_id_levanta_error(self, tmp_path):
        with pytest.raises(AnalysisError):
            analizar(
                directorio_salida=tmp_path / "salida_invalida",
                formula="rendimiento ~ C(tratamiento)",
                tipo="anova",
            )


# --- Grupo 10: convencion de exit codes 0/1/2 (D-4, change n8n-orchestration-workflows) --


class TestConvencionExitCodes:
    def test_dataset_inexistente_es_error_de_dominio_exit_code_1(self, tmp_path, monkeypatch):
        """1.4 (D-4): `DatasetNoEncontradoError` (dataset_id inexistente en
        una base ACCESIBLE) es un error de dominio deterministico -- exit 1,
        no se reintenta (RN-GLB-03)."""
        from pipeline.analysis import main
        from pipeline.db import build_engine
        from pipeline.models import Base

        db_path = tmp_path / "cli_test_dominio.db"
        database_url = f"sqlite:///{db_path}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        engine = build_engine(database_url)
        Base.metadata.create_all(engine)
        engine.dispose()

        codigo = main(["--dataset-id", "999999", "--formula", "rendimiento ~ C(tratamiento)"])

        assert codigo == 1

    def test_base_inaccesible_es_fallo_de_infraestructura_exit_code_2(self, tmp_path, monkeypatch, capsys):
        """1.4 (D-4) TRIANGULATE: `DATABASE_URL` apuntando a un directorio
        inexistente (SQLite nunca crea el directorio padre) es un fallo REAL
        de infraestructura -- `sqlalchemy.exc.OperationalError` -- exit 2,
        distinto del exit 1 de `test_dataset_inexistente...` de arriba (esa
        base SI existe/es accesible, solo falta el registro)."""
        from pipeline.analysis import main

        ruta_inaccesible = tmp_path / "directorio_inexistente" / "cli_test_infra.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta_inaccesible}")

        codigo = main(["--dataset-id", "1", "--formula", "rendimiento ~ C(tratamiento)"])

        salida_error = capsys.readouterr().err
        assert codigo == 2
        assert "error" in salida_error.lower()
