"""Suite TDD del modulo de transformacion y estandarizacion (change transformation-module / C-05).

Cubre:
- Seccion 2: contrato del modulo — `transform` devuelve un outcome con
  `df_tidy` + bitacora (RN-TRA-02, Decision 1 del design).
- Seccion 3: normalizacion de nombres de columna a snake_case canonico
  (RN-TRA-03, Decision 3).
- Seccion 4: estandarizacion de categoricos via tabla de correspondencias
  (RN-TRA-04, Decision 2).
- Seccion 5: conversion de unidades a la unidad canonica (RN-TRA-05, Decision 2).
- Seccion 6: dataset tidy + preservacion de identificadores jerarquicos
  (RN-TRA-06, Decision 5).
- Seccion 7: bitacora atomica, serializable y reproducible (RN-TRA-02, Decision 4).
- Seccion 8: fixture sintetico + guardarrail anti-caso-real.

NO valida los *datos* (eso es C-04): el modulo recibe un DataFrame ya
materializado que se asume ya paso la validacion (RN-TRA-01). NO usa
`great_expectations`: DD-04 gobierna la validacion, no la transformacion
(ver Context del design.md del change).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.data_dictionary import load_data_dictionary

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DICCIONARIO_PATH = FIXTURES_DIR / "data_dictionary_sintetico.json"
DATASET_A_TRANSFORMAR_PATH = FIXTURES_DIR / "dataset_sintetico_a_transformar.csv"


@pytest.fixture(scope="module")
def diccionario():
    """DataDictionary tipado del fixture sintetico de C-02."""
    return load_data_dictionary(DICCIONARIO_PATH)


@pytest.fixture
def df_crudo() -> pd.DataFrame:
    """Dataset sintetico crudo con nombres de columna sin normalizar
    (`"Id Unidad"`, `"Variable Respuesta 1"`, `"variable-respuesta-2"`, ...),
    variantes categoricas de `tratamiento` (`"t1"`, `"trat-1"`) y
    `variable_respuesta_1` en una unidad de origen distinta de la canonica
    (los valores crudos, multiplicados por 2.0, coinciden con
    `dataset_sintetico.csv` de C-04 — mismo dato sintetico, distinta unidad)."""
    return pd.read_csv(DATASET_A_TRANSFORMAR_PATH)


# ---------------------------------------------------------------------------
# Seccion 2: contrato del modulo — outcome con df_tidy + bitacora (RN-TRA-02)
# ---------------------------------------------------------------------------


class TestContratoTransform:
    def test_transform_devuelve_outcome_con_df_tidy_y_bitacora(self, diccionario, df_crudo):
        """2.1/2.2: `transform(df, diccionario, reglas)` devuelve un
        `TransformationOutcome` con `df_tidy: pd.DataFrame` y
        `operaciones: list[OperacionTransformacion]`."""
        from pipeline.transformation import TransformationOutcome, transform

        resultado = transform(df_crudo, diccionario)

        assert isinstance(resultado, TransformationOutcome)
        assert isinstance(resultado.df_tidy, pd.DataFrame)
        assert isinstance(resultado.operaciones, list)


# ---------------------------------------------------------------------------
# Seccion 3: normalizacion de nombres de columna (RN-TRA-03, Decision 3)
# ---------------------------------------------------------------------------


class TestNormalizacionNombres:
    def test_nombres_crudos_se_mapean_al_canonico(self, diccionario, df_crudo):
        """3.1: columnas crudas que difieren del canonico en capitalizacion/
        espaciado/separadores (`"Variable Respuesta 1"`,
        `"variable-respuesta-2"`) se renombran a su `nombre_canonico`, y la
        bitacora registra la operacion `normalizacion_nombre`."""
        from pipeline.transformation import TIPO_NORMALIZACION_NOMBRE, transform

        resultado = transform(df_crudo, diccionario)

        assert "variable_respuesta_1" in resultado.df_tidy.columns
        assert "Variable Respuesta 1" not in resultado.df_tidy.columns

        operaciones_nombre = [
            op for op in resultado.operaciones if op.tipo == TIPO_NORMALIZACION_NOMBRE
        ]
        columnas_renombradas = {op.columna for op in operaciones_nombre}
        assert "variable_respuesta_1" in columnas_renombradas
        assert "variable_respuesta_2" in columnas_renombradas

    def test_nombres_canonicos_distintos_no_colisionan(self, diccionario, df_crudo):
        """3.3 TRIANGULATE: `variable_respuesta_1` y `variable_respuesta_2`
        no colisionan — cada una se mapea a su propio nombre canonico."""
        from pipeline.transformation import transform

        resultado = transform(df_crudo, diccionario)

        assert "variable_respuesta_1" in resultado.df_tidy.columns
        assert "variable_respuesta_2" in resultado.df_tidy.columns
        assert not resultado.df_tidy["variable_respuesta_1"].equals(
            resultado.df_tidy["variable_respuesta_2"]
        )

    def test_columna_ya_canonica_no_genera_operacion(self, diccionario):
        """Una columna ya nombrada con su `nombre_canonico` no se toca ni
        genera entrada de bitacora de normalizacion de nombre."""
        from pipeline.transformation import TIPO_NORMALIZACION_NOMBRE, transform

        df = pd.DataFrame({"id_unidad": [1, 2], "bloque": ["B1", "B2"]})
        resultado = transform(df, diccionario)

        assert list(resultado.df_tidy.columns) == ["id_unidad", "bloque"]
        assert not any(op.tipo == TIPO_NORMALIZACION_NOMBRE for op in resultado.operaciones)


# ---------------------------------------------------------------------------
# Seccion 4: estandarizacion de categoricos (RN-TRA-04, Decision 2)
# ---------------------------------------------------------------------------


class TestEstandarizacionCategorica:
    def test_variantes_se_llevan_a_forma_canonica(self, diccionario, df_crudo):
        """4.1: con `reglas.correspondencias = {"tratamiento": {"t1": "T1",
        "trat-1": "T1"}}`, las variantes se llevan a `"T1"` (que pertenece a
        `valores_admisibles` de `tratamiento`), y la bitacora registra
        `estandarizacion_categorica` con el nº de registros afectados."""
        from pipeline.transformation import (
            TIPO_ESTANDARIZACION_CATEGORICA,
            TransformationRules,
            transform,
        )

        reglas = TransformationRules(
            correspondencias={"tratamiento": {"t1": "T1", "trat-1": "T1"}}
        )
        resultado = transform(df_crudo, diccionario, reglas)

        variable_tratamiento = diccionario.get("tratamiento")
        assert set(resultado.df_tidy["tratamiento"]).issubset(
            set(variable_tratamiento.valores_admisibles)
        )
        assert (resultado.df_tidy["tratamiento"] == "T1").sum() == 4  # t1,trat-1,t1,trat-1

        operacion = next(
            op for op in resultado.operaciones if op.tipo == TIPO_ESTANDARIZACION_CATEGORICA
        )
        assert operacion.columna == "tratamiento"
        assert operacion.registros_afectados == 4

    def test_categorico_ya_canonico_no_se_altera_ni_registra(self, diccionario):
        """4.3 TRIANGULATE: una columna categorica ya canonica (sin
        variantes) no se altera y NO genera entrada de bitacora (0 registros
        afectados)."""
        from pipeline.transformation import (
            TIPO_ESTANDARIZACION_CATEGORICA,
            TransformationRules,
            transform,
        )

        df = pd.DataFrame({"tratamiento": ["T1", "T2", "T3"]})
        reglas = TransformationRules(correspondencias={"tratamiento": {"t1": "T1"}})
        resultado = transform(df, diccionario, reglas)

        assert list(resultado.df_tidy["tratamiento"]) == ["T1", "T2", "T3"]
        assert not any(
            op.tipo == TIPO_ESTANDARIZACION_CATEGORICA for op in resultado.operaciones
        )


# ---------------------------------------------------------------------------
# Seccion 5: conversion de unidades (RN-TRA-05, Decision 2)
# ---------------------------------------------------------------------------


class TestConversionUnidades:
    def test_columna_en_unidad_no_canonica_se_convierte(self, diccionario, df_crudo):
        """5.1: con `reglas.conversiones = {"variable_respuesta_1":
        ConversionUnidad(unidad_origen, factor, offset)}`, `df_tidy` tiene
        los valores en la unidad canonica, y la bitacora registra
        `conversion_unidad` con nº de registros y muestra antes/despues.

        Los valores crudos del fixture estan en una unidad de origen tal que
        multiplicados por 2.0 coinciden con `dataset_sintetico.csv` de C-04
        (12.5, 45.0, 78.3, 33.7, 60.2, 91.4)."""
        from pipeline.transformation import (
            TIPO_CONVERSION_UNIDAD,
            ConversionUnidad,
            TransformationRules,
            transform,
        )

        reglas = TransformationRules(
            conversiones={
                "variable_respuesta_1": ConversionUnidad(
                    unidad_origen="unidad_alterna", factor=2.0, offset=0.0
                )
            }
        )
        resultado = transform(df_crudo, diccionario, reglas)

        valores_esperados = [12.5, 45.0, 78.3, 33.7, 60.2, 91.4]
        assert resultado.df_tidy["variable_respuesta_1"].tolist() == pytest.approx(
            valores_esperados
        )

        operacion = next(
            op for op in resultado.operaciones if op.tipo == TIPO_CONVERSION_UNIDAD
        )
        assert operacion.columna == "variable_respuesta_1"
        assert operacion.registros_afectados == 6
        assert len(operacion.muestra_antes) > 0
        assert len(operacion.muestra_despues) > 0

    def test_conversion_con_offset_distinto_de_cero(self, diccionario):
        """5.3 TRIANGULATE: un factor + offset != 0 (escala con
        desplazamiento) fuerza la logica real de conversion lineal — rompe
        cualquier Fake It que solo multiplicara sin sumar el offset."""
        from pipeline.transformation import ConversionUnidad, TransformationRules, transform

        df = pd.DataFrame({"variable_respuesta_1": [0.0, 10.0, 20.0]})
        reglas = TransformationRules(
            conversiones={
                "variable_respuesta_1": ConversionUnidad(
                    unidad_origen="unidad_desplazada", factor=1.0, offset=5.0
                )
            }
        )
        resultado = transform(df, diccionario, reglas)

        assert resultado.df_tidy["variable_respuesta_1"].tolist() == pytest.approx(
            [5.0, 15.0, 25.0]
        )

    def test_columna_ya_canonica_sin_conversion_declarada_no_se_altera(self, diccionario):
        """5.3 TRIANGULATE: una columna ya en unidad canonica, sin conversion
        declarada en `reglas`, no se altera ni registra operacion."""
        from pipeline.transformation import (
            TIPO_CONVERSION_UNIDAD,
            TransformationRules,
            transform,
        )

        df = pd.DataFrame({"variable_respuesta_1": [12.5, 45.0]})
        resultado = transform(df, diccionario, TransformationRules())

        assert resultado.df_tidy["variable_respuesta_1"].tolist() == [12.5, 45.0]
        assert not any(op.tipo == TIPO_CONVERSION_UNIDAD for op in resultado.operaciones)


# ---------------------------------------------------------------------------
# Seccion 6: dataset tidy + preservacion de identificadores (RN-TRA-06, Decision 5)
# ---------------------------------------------------------------------------


class TestDatasetTidy:
    def test_tidy_preserva_identificadores_y_cardinalidad(self, diccionario, df_crudo):
        """6.1: tras transformar, `df_tidy` tiene una columna por variable con
        nombre canonico, conserva los identificadores de diseño (`id_unidad`,
        `bloque`, `tratamiento`) y mantiene la misma cardinalidad de filas
        que la entrada."""
        from pipeline.transformation import TransformationRules, transform

        reglas = TransformationRules(
            correspondencias={"tratamiento": {"t1": "T1", "trat-1": "T1"}}
        )
        resultado = transform(df_crudo, diccionario, reglas)

        for identificador in ("id_unidad", "bloque", "tratamiento"):
            assert identificador in resultado.df_tidy.columns

        assert len(resultado.df_tidy) == len(df_crudo)
        assert list(resultado.df_tidy["id_unidad"]) == list(df_crudo["Id Unidad"])


# ---------------------------------------------------------------------------
# Seccion 7: bitacora atomica, serializable y reproducible (RN-TRA-02, Decision 4)
# ---------------------------------------------------------------------------


class TestBitacora:
    def _reglas_completas(self):
        from pipeline.transformation import ConversionUnidad, TransformationRules

        return TransformationRules(
            correspondencias={"tratamiento": {"t1": "T1", "trat-1": "T1"}},
            conversiones={
                "variable_respuesta_1": ConversionUnidad(
                    unidad_origen="unidad_alterna", factor=2.0, offset=0.0
                )
            },
        )

    def test_cada_operacion_aplicada_produce_una_entrada(self, diccionario, df_crudo):
        """7.1: sobre un dataset que requiere las tres operaciones, la
        bitacora contiene una entrada por operacion que afecto >=1 registro,
        cada una con tipo/columna/registros_afectados/muestra antes-despues."""
        from pipeline.transformation import (
            TIPO_CONVERSION_UNIDAD,
            TIPO_ESTANDARIZACION_CATEGORICA,
            TIPO_NORMALIZACION_NOMBRE,
            transform,
        )

        resultado = transform(df_crudo, diccionario, self._reglas_completas())

        tipos_presentes = {op.tipo for op in resultado.operaciones}
        assert TIPO_NORMALIZACION_NOMBRE in tipos_presentes
        assert TIPO_ESTANDARIZACION_CATEGORICA in tipos_presentes
        assert TIPO_CONVERSION_UNIDAD in tipos_presentes

        for operacion in resultado.operaciones:
            assert operacion.registros_afectados >= 1
            assert operacion.tipo
            assert operacion.columna
            assert isinstance(operacion.muestra_antes, list)
            assert isinstance(operacion.muestra_despues, list)

    def test_operacion_sin_efecto_no_genera_entrada(self, diccionario):
        """7.2: consolidado con Secciones 3-5 — una operacion sin efecto (0
        registros) no genera entrada de bitacora."""
        from pipeline.transformation import TransformationRules, transform

        df = pd.DataFrame({"id_unidad": [1], "bloque": ["B1"], "tratamiento": ["T1"]})
        resultado = transform(
            df,
            diccionario,
            TransformationRules(correspondencias={"tratamiento": {"t1": "T1"}}),
        )

        assert resultado.operaciones == []

    def test_bitacora_es_serializable_a_json(self, diccionario, df_crudo):
        """7.3: la bitacora es serializable (`json.dumps` de `to_dict()` de
        cada `OperacionTransformacion`) para alimentar C-06."""
        from pipeline.transformation import transform

        resultado = transform(df_crudo, diccionario, self._reglas_completas())

        bitacora_json = json.dumps([op.to_dict() for op in resultado.operaciones])
        bitacora_reconstruida = json.loads(bitacora_json)

        assert len(bitacora_reconstruida) == len(resultado.operaciones)
        for entrada in bitacora_reconstruida:
            assert set(entrada.keys()) == {
                "tipo",
                "columna",
                "registros_afectados",
                "muestra_antes",
                "muestra_despues",
            }

    def test_reproducibilidad_misma_entrada_mismas_reglas(self, diccionario, df_crudo):
        """7.4 TRIANGULATE: transformar el mismo dataset con las mismas
        reglas dos veces produce `df_tidy` y bitacora identicos (RN-GLB-02)."""
        from pipeline.transformation import transform

        reglas = self._reglas_completas()
        resultado_1 = transform(df_crudo, diccionario, reglas)
        resultado_2 = transform(df_crudo, diccionario, reglas)

        pd.testing.assert_frame_equal(resultado_1.df_tidy, resultado_2.df_tidy)
        assert [op.to_dict() for op in resultado_1.operaciones] == [
            op.to_dict() for op in resultado_2.operaciones
        ]


# ---------------------------------------------------------------------------
# Seccion 1 (requisito transversal): transformacion exclusiva de validos,
# sin re-validacion ni great_expectations (RN-TRA-01)
# ---------------------------------------------------------------------------


class TestNoRevalidacion:
    def test_conserva_cardinalidad(self, diccionario, df_crudo):
        """El modulo no descarta ni agrega filas (RN-TRA-01)."""
        from pipeline.transformation import transform

        resultado = transform(df_crudo, diccionario)
        assert len(resultado.df_tidy) == len(df_crudo)

    def test_no_importa_ni_usa_great_expectations(self):
        """El modulo no importa ni utiliza `great_expectations`: DD-04
        gobierna la validacion (C-04), no la transformacion (C-05). Se
        inspeccionan los statements `import` del modulo (no el docstring,
        que SI menciona el termino al documentar este mismo matiz)."""
        import ast
        import inspect

        import pipeline.transformation as modulo_transformacion

        arbol = ast.parse(inspect.getsource(modulo_transformacion))
        modulos_importados = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos_importados.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                modulos_importados.add(nodo.module)

        assert not any("great_expectations" in modulo for modulo in modulos_importados)


# ---------------------------------------------------------------------------
# Seccion 8: fixture sintetico + guardarrail anti-caso-real
# ---------------------------------------------------------------------------


# Mismos terminos prohibidos que el guardarrail de C-02/C-04
# (tests/test_data_dictionary.py, tests/test_validation.py): su sola
# aparicion indicaria que se colo un caso de estudio real
# (cultivo/institucion/region/campana).
TERMINOS_DE_DOMINIO_REAL_PROHIBIDOS = (
    "inta",
    "cuyo",
    "mendoza",
    "san juan",
    "universidad",
    "soja",
    "maiz",
    "trigo",
    "girasol",
    "campaña 2024",
    "campaña 2025",
    "2024-2025",
)


class TestGuardarrailAntiCasoReal:
    def test_fixture_a_transformar_usa_identificadores_genericos(self):
        """8.2: el fixture de transformacion reusa los identificadores
        genericos de C-02 y no nombra cultivo, institucion, region ni
        campaña real."""
        texto = DATASET_A_TRANSFORMAR_PATH.read_text(encoding="utf-8").lower()

        for termino in TERMINOS_DE_DOMINIO_REAL_PROHIBIDOS:
            assert termino not in texto, (
                f"Termino de dominio real '{termino}' filtrado en el fixture a transformar"
            )

        assert "id unidad" in texto or "id_unidad" in texto
        assert "variable respuesta 1" in texto or "variable_respuesta_1" in texto
        assert any(codigo in texto for codigo in ("t1", "t2", "t3", "trat-1"))
        assert any(codigo in texto for codigo in ("b1", "b2", "b3", "b4"))


# ---------------------------------------------------------------------------
# Seccion 9: CLI fino por archivos (D-1/D-2/D-3, change n8n-orchestration-workflows)
# ---------------------------------------------------------------------------


class TestTransformationRulesLoader:
    def test_from_dict_construye_correspondencias_y_conversiones(self):
        """4.1/4.2: `TransformationRules.from_dict` carga correspondencias y
        conversiones desde un dict plano (la forma que produce `json.load`)."""
        from pipeline.transformation import ConversionUnidad, TransformationRules

        datos = {
            "correspondencias": {"tratamiento": {"t1": "T1", "trat-1": "T1"}},
            "conversiones": {
                "variable_respuesta_1": {"unidad_origen": "unidad_generica_x2", "factor": 0.5}
            },
        }

        reglas = TransformationRules.from_dict(datos)

        assert reglas.correspondencias == {"tratamiento": {"t1": "T1", "trat-1": "T1"}}
        assert reglas.conversiones == {
            "variable_respuesta_1": ConversionUnidad(unidad_origen="unidad_generica_x2", factor=0.5)
        }

    def test_from_json_lee_un_archivo_de_reglas(self, tmp_path):
        """4.1/4.2 TRIANGULATE: `TransformationRules.from_json` lee el mismo
        contrato desde un archivo `.json` en disco (el que recibe `--rules`)."""
        from pipeline.transformation import TransformationRules

        ruta_reglas = tmp_path / "reglas.json"
        ruta_reglas.write_text(
            json.dumps({"correspondencias": {"tratamiento": {"t1": "T1"}}, "conversiones": {}}),
            encoding="utf-8",
        )

        reglas = TransformationRules.from_json(ruta_reglas)

        assert reglas.correspondencias == {"tratamiento": {"t1": "T1"}}
        assert reglas.conversiones == {}


class TestCLI:
    def test_cli_produce_tidy_y_bitacora_serializada_con_reglas(
        self, tmp_path, diccionario, df_crudo
    ):
        """4.1/4.2: `main` sobre el artefacto pickle de validos (crudo) + un
        `--rules` JSON produce `tidy.pkl` (renombrado + correspondencias +
        conversiones aplicadas) y `operaciones.json` con la bitacora atomica
        serializada (RN-TRA-02), sin tocar `transform`/`TransformationRules`."""
        from pipeline.transformation import main

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        artefacto_entrada = corrida_dir / "validos.pkl"
        df_crudo.to_pickle(artefacto_entrada)

        ruta_reglas = tmp_path / "reglas.json"
        ruta_reglas.write_text(
            json.dumps(
                {
                    "correspondencias": {"tratamiento": {"t1": "T1", "trat-1": "T1"}},
                    "conversiones": {
                        "variable_respuesta_1": {
                            "unidad_origen": "unidad_generica_x2",
                            "factor": 0.5,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        exit_code = main(
            [
                str(artefacto_entrada),
                "--dictionary-path",
                str(DICCIONARIO_PATH),
                "--rules",
                str(ruta_reglas),
                "--output-dir",
                str(corrida_dir),
            ]
        )

        assert exit_code == 0
        assert (corrida_dir / "tidy.pkl").exists()
        assert (corrida_dir / "operaciones.json").exists()

        tidy = pd.read_pickle(corrida_dir / "tidy.pkl")
        assert "variable_respuesta_1" in tidy.columns
        assert set(tidy["tratamiento"]) <= {"T1", "T2", "T3"}
        # Conversion aplicada: valores crudos (*2.0) ahora en unidad canonica.
        assert tidy.loc[tidy["tratamiento"] == "T1", "variable_respuesta_1"].tolist()[0] == pytest.approx(3.125)

        operaciones = json.loads((corrida_dir / "operaciones.json").read_text(encoding="utf-8"))
        tipos = {op["tipo"] for op in operaciones}
        assert "normalizacion_nombre" in tipos
        assert "estandarizacion_categorica" in tipos
        assert "conversion_unidad" in tipos

    def test_cli_sin_rules_no_aplica_correspondencia_ni_conversion(self, tmp_path, df_crudo):
        """4.3 TRIANGULATE: sin `--rules`, el comportamiento es equivalente a
        `transform(df, diccionario)` sin reglas -- solo normalizacion de
        nombres, ninguna correspondencia categorica ni conversion de unidad."""
        from pipeline.transformation import main

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        artefacto_entrada = corrida_dir / "validos.pkl"
        df_crudo.to_pickle(artefacto_entrada)

        exit_code = main(
            [
                str(artefacto_entrada),
                "--dictionary-path",
                str(DICCIONARIO_PATH),
                "--output-dir",
                str(corrida_dir),
            ]
        )

        assert exit_code == 0
        operaciones = json.loads((corrida_dir / "operaciones.json").read_text(encoding="utf-8"))
        tipos = {op["tipo"] for op in operaciones}
        assert "estandarizacion_categorica" not in tipos
        assert "conversion_unidad" not in tipos

    def test_cli_json_de_reglas_malformado_sale_exit_code_1(self, tmp_path, df_crudo):
        """4.3 TRIANGULATE: un `--rules` que no es JSON valido es un error de
        configuracion determinista (dominio) -- exit 1, no se reintenta
        (D-4): reintentar un JSON malformado nunca lo arregla."""
        from pipeline.transformation import main

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        artefacto_entrada = corrida_dir / "validos.pkl"
        df_crudo.to_pickle(artefacto_entrada)

        ruta_reglas = tmp_path / "reglas_malformadas.json"
        ruta_reglas.write_text("{ esto no es json valido ][", encoding="utf-8")

        exit_code = main(
            [
                str(artefacto_entrada),
                "--dictionary-path",
                str(DICCIONARIO_PATH),
                "--rules",
                str(ruta_reglas),
                "--output-dir",
                str(corrida_dir),
            ]
        )

        assert exit_code == 1
