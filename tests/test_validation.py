"""Suite TDD del motor de validacion declarativa (change validation-engine / C-04).

Cubre:
- Seccion 2: generacion dinamica de la expectation suite desde el diccionario
  de C-02 (RN-VAL-02..06) — declarativa, serializable, sin if/else imperativos
  (DD-04 / RN-VAL-01).
- Seccion 3: reglas de consistencia cruzada (RN-VAL-07) via expectations
  multi-columna; operador no soportado -> fail-closed.
- Seccion 4: ejecucion + salida dual valida/rechazada (RN-VAL-08).
- Seccion 5: fixture sintetico extendido con variantes invalidas + guardarrail
  anti-caso-real.
- Seccion 6: un caso negativo por cada tipo de violacion (tipo, rango, lista,
  unicidad, completitud, cruzada).
- Seccion 7: reporte de validacion JSON.

NO valida la *forma* del diccionario (eso es C-02) ni parsea archivos crudos
(eso es C-03): el motor recibe un DataFrame ya materializado.
"""

from pathlib import Path

import pandas as pd
import pytest

from pipeline.data_dictionary import load_data_dictionary

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DICCIONARIO_PATH = FIXTURES_DIR / "data_dictionary_sintetico.json"
DATASET_VALIDO_PATH = FIXTURES_DIR / "dataset_sintetico.csv"
DATASET_INVALIDO_PATH = FIXTURES_DIR / "dataset_sintetico_invalido.csv"

# Indices (0-based) de las variantes del dataset mixto
# `dataset_sintetico_invalido.csv` — una por tipo de violacion (RN-VAL-03..07):
FILAS_VALIDAS = {0, 7}
FILA_RANGO = 1          # variable_respuesta_1 = 150.5 > max 100
FILA_LISTA = 2          # bloque = B9, fuera de valores_admisibles
FILAS_UNICIDAD = {3, 4}  # id_unidad = 104 duplicado (ambas ocurrencias)
FILA_COMPLETITUD = 5    # variable_respuesta_1 vacia siendo obligatoria
FILA_CRUZADA = 6        # fecha_inicio > fecha_fin (regla orden_fechas)
FILA_MULTIPLE = 8       # rango (999.9) + lista (tratamiento T9) a la vez


@pytest.fixture(scope="module")
def diccionario():
    """DataDictionary tipado del fixture sintetico de C-02."""
    return load_data_dictionary(DICCIONARIO_PATH)


@pytest.fixture
def df_valido() -> pd.DataFrame:
    """Dataset sintetico integramente valido, con dtypes ya materializados
    (las fechas llegan parseadas: responsabilidad de C-03/C-05, ver design)."""
    return pd.read_csv(DATASET_VALIDO_PATH, parse_dates=["fecha_inicio", "fecha_fin"])


@pytest.fixture
def df_mixto() -> pd.DataFrame:
    """Dataset mixto: filas validas + una variante invalida por cada tipo de
    violacion (ver constantes FILA_*)."""
    return pd.read_csv(DATASET_INVALIDO_PATH, parse_dates=["fecha_inicio", "fecha_fin"])


def _expectations_json(suite) -> list:
    """Representacion serializada (declarativa) de la suite: lista de dicts
    {type, kwargs, meta}. Inspeccionar la suite por su forma serializada es
    exactamente la propiedad que DD-04 exige (reglas legibles sin leer codigo)."""
    return suite.to_json_dict()["expectations"]


def _de_columna(expectations: list, columna: str) -> list:
    return [e for e in expectations if e["kwargs"].get("column") == columna]


def _tipos(expectations: list) -> set:
    return {e["type"] for e in expectations}


# ---------------------------------------------------------------------------
# Seccion 2: generacion dinamica de la expectation suite (RN-VAL-02..06)
# ---------------------------------------------------------------------------


class TestConstruirSuite:
    def test_cada_variable_produce_las_expectations_de_sus_atributos(self, diccionario):
        """2.1 RED: la suite se deriva de los atributos de cada variable del
        diccionario — tipo (RN-VAL-02) para toda variable, rango (RN-VAL-03)
        para numericas con rango, lista (RN-VAL-04) para categoricas,
        no-nulidad (RN-VAL-06) para obligatorias, unicidad (RN-VAL-05) para
        la clave primaria."""
        from pipeline.validation import construir_suite

        suite = construir_suite(diccionario)
        expectations = _expectations_json(suite)

        # RN-VAL-02: toda variable del diccionario tiene una expectation de tipo.
        tipos_de_expectation_de_tipo = {
            "expect_column_values_to_be_in_type_list",
            "expect_column_values_to_be_of_type",
        }
        for variable in diccionario:
            de_tipo = [
                e
                for e in _de_columna(expectations, variable.nombre_canonico)
                if e["type"] in tipos_de_expectation_de_tipo
            ]
            assert de_tipo, f"'{variable.nombre_canonico}' sin expectation de tipo (RN-VAL-02)"
            assert all(e["meta"]["regla"] == "tipo" for e in de_tipo)

        # RN-VAL-03: numericas con rango -> expectation de rango con min/max del diccionario.
        vr1 = _de_columna(expectations, "variable_respuesta_1")
        rango = [e for e in vr1 if e["type"] == "expect_column_values_to_be_between"]
        assert len(rango) == 1
        assert rango[0]["kwargs"]["min_value"] == 0
        assert rango[0]["kwargs"]["max_value"] == 100
        assert rango[0]["meta"]["regla"] == "rango"

        vr2 = _de_columna(expectations, "variable_respuesta_2")
        rango2 = [e for e in vr2 if e["type"] == "expect_column_values_to_be_between"]
        assert len(rango2) == 1
        assert rango2[0]["kwargs"]["max_value"] == 50

        # RN-VAL-04: categoricas -> pertenencia al conjunto de valores admisibles.
        for columna, admisibles in (
            ("bloque", ["B1", "B2", "B3", "B4"]),
            ("tratamiento", ["T1", "T2", "T3"]),
        ):
            en_lista = [
                e
                for e in _de_columna(expectations, columna)
                if e["type"] == "expect_column_values_to_be_in_set"
            ]
            assert len(en_lista) == 1, f"'{columna}' sin expectation de lista (RN-VAL-04)"
            assert en_lista[0]["kwargs"]["value_set"] == admisibles
            assert en_lista[0]["meta"]["regla"] == "lista"

        # RN-VAL-06: toda obligatoria -> expectation de no-nulidad; opcional -> no.
        for variable in diccionario:
            not_null = [
                e
                for e in _de_columna(expectations, variable.nombre_canonico)
                if e["type"] == "expect_column_values_to_not_be_null"
            ]
            if variable.obligatorio:
                assert len(not_null) == 1, (
                    f"'{variable.nombre_canonico}' obligatoria sin no-nulidad (RN-VAL-06)"
                )
                assert not_null[0]["meta"]["regla"] == "completitud"
            else:
                assert not_null == []

        # RN-VAL-05: la clave primaria (inferida: primera entero+obligatoria =
        # id_unidad) -> expectation de unicidad; ninguna otra columna la tiene.
        unicas = [e for e in expectations if e["type"] == "expect_column_values_to_be_unique"]
        assert len(unicas) == 1
        assert unicas[0]["kwargs"]["column"] == "id_unidad"
        assert unicas[0]["meta"]["regla"] == "unicidad"

    def test_clave_primaria_explicita_prevalece_sobre_la_inferencia(self, diccionario):
        """2.1: el parametro `clave_primaria` designa la clave; la inferencia
        es solo el default."""
        from pipeline.validation import construir_suite

        suite = construir_suite(diccionario, clave_primaria="bloque")
        expectations = _expectations_json(suite)

        unicas = [e for e in expectations if e["type"] == "expect_column_values_to_be_unique"]
        assert len(unicas) == 1
        assert unicas[0]["kwargs"]["column"] == "bloque"

    def test_suite_es_declarativa_serializable_y_sin_comparaciones_imperativas(
        self, diccionario
    ):
        """2.3 RED+GREEN (DD-04 / RN-VAL-01): la suite es un artefacto
        declarativo serializable a JSON (inspeccionable sin leer codigo) y el
        modulo del motor NO contiene comparaciones de magnitud imperativas
        (`if valor > limite`) que decidan la validez de un dato."""
        import ast
        import inspect
        import json

        from pipeline import validation
        from pipeline.validation import construir_suite

        # Declarativa: serializable a JSON y de vuelta, sin perder las reglas.
        suite = construir_suite(diccionario)
        serializada = json.dumps(suite.to_json_dict())
        reglas = {e["meta"]["regla"] for e in json.loads(serializada)["expectations"]}
        assert {"tipo", "rango", "lista", "completitud", "unicidad"}.issubset(reglas)

        # Tripwire mecanico anti-DD-04: ninguna comparacion de magnitud
        # (<, <=, >, >=) en todo el modulo. Cualquier regla imperativa del
        # estilo `if valor > maximo: rechazar` la dispara.
        arbol = ast.parse(inspect.getsource(validation))
        comparaciones_de_magnitud = [
            nodo
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Compare)
            and any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in nodo.ops)
        ]
        assert comparaciones_de_magnitud == [], (
            "pipeline/validation.py contiene comparaciones de magnitud imperativas; "
            "las reglas de validacion DEBEN ser expectations declarativas (DD-04)"
        )

    def test_variable_nueva_en_el_diccionario_amplia_la_suite_sin_tocar_el_motor(
        self,
    ):
        """2.4 TRIANGULATE: agregar una variable al diccionario (en memoria)
        incorpora sus expectations a la suite generada, sin modificar el
        codigo de `pipeline/validation.py`."""
        from pipeline.data_dictionary import DataDictionary, VariableDefinition
        from pipeline.validation import construir_suite

        base = load_data_dictionary(DICCIONARIO_PATH)
        extra = VariableDefinition(
            nombre_canonico="variable_respuesta_3",
            descripcion="Variable numerica generica agregada en memoria",
            tipo_dato="real",
            obligatorio=True,
            unidad="unidad_generica",
            rango={"min": -10, "max": 10},
        )
        variables = {v.nombre_canonico: v for v in base}
        variables[extra.nombre_canonico] = extra
        ampliado = DataDictionary(_variables=variables, reglas_cruzadas=base.reglas_cruzadas)

        expectations = _expectations_json(construir_suite(ampliado))
        de_la_nueva = _de_columna(expectations, "variable_respuesta_3")

        assert {e["meta"]["regla"] for e in de_la_nueva} == {"tipo", "rango", "completitud"}
        rango = [e for e in de_la_nueva if e["meta"]["regla"] == "rango"][0]
        assert rango["kwargs"]["min_value"] == -10
        assert rango["kwargs"]["max_value"] == 10


# ---------------------------------------------------------------------------
# Seccion 3: reglas de consistencia cruzada (RN-VAL-07)
# ---------------------------------------------------------------------------


class TestReglasCruzadas:
    def test_regla_menor_igual_se_traduce_a_expectation_multicolumna(self, diccionario):
        """3.1 RED: la regla `{id: orden_fechas, operador: menor_igual,
        campos: [fecha_inicio, fecha_fin]}` del fixture produce la expectation
        multi-columna que verifica `fecha_inicio <= fecha_fin`."""
        from pipeline.validation import construir_suite

        expectations = _expectations_json(construir_suite(diccionario))
        cruzadas = [e for e in expectations if e["meta"].get("regla") == "orden_fechas"]

        assert len(cruzadas) == 1, "la regla cruzada 'orden_fechas' no esta en la suite"
        cruzada = cruzadas[0]
        # a <= b  ===  b >= a  (expect_column_pair_values_a_to_be_greater_than_b
        # con column_A = fecha_fin, column_B = fecha_inicio, or_equal=True).
        assert cruzada["type"] == "expect_column_pair_values_a_to_be_greater_than_b"
        assert cruzada["kwargs"]["column_A"] == "fecha_fin"
        assert cruzada["kwargs"]["column_B"] == "fecha_inicio"
        assert cruzada["kwargs"]["or_equal"] is True

    def test_operador_no_soportado_falla_explicitamente(self):
        """3.3 RED: un `operador` fuera de la tabla de mapeo levanta un error
        fail-closed que identifica la regla y el operador; NUNCA se ignora la
        regla en silencio (seria un falso negativo grave)."""
        from pipeline.data_dictionary import CrossFieldRule, DataDictionary
        from pipeline.validation import UnsupportedOperatorError, construir_suite

        base = load_data_dictionary(DICCIONARIO_PATH)
        regla_rara = CrossFieldRule(
            id="regla_no_mapeable",
            operador="distinto",
            campos=["fecha_inicio", "fecha_fin"],
        )
        con_regla_rara = DataDictionary(
            _variables={v.nombre_canonico: v for v in base},
            reglas_cruzadas=(regla_rara,),
        )

        with pytest.raises(UnsupportedOperatorError) as exc_info:
            construir_suite(con_regla_rara)

        mensaje = str(exc_info.value)
        assert "regla_no_mapeable" in mensaje
        assert "distinto" in mensaje


# ---------------------------------------------------------------------------
# Seccion 4: ejecucion y salida dual validos/rechazados (RN-VAL-08)
# ---------------------------------------------------------------------------


class TestSalidaDual:
    def test_dataset_integramente_valido_no_produce_rechazos(self, diccionario, df_valido):
        """4.1 RED: el dataset sintetico de C-02 (todas las filas cumplen
        tipo, rango, lista, unicidad, completitud y la regla cruzada) produce
        salida dual con todos los registros en validos, rechazados vacio y
        detalle vacio."""
        from pipeline.validation import validate

        outcome = validate(df_valido, diccionario)

        pd.testing.assert_frame_equal(outcome.df_validos, df_valido)
        assert outcome.df_rechazados.empty
        assert outcome.detalle_rechazos == []
        assert outcome.resultado_ge.success is True

    def test_dataset_mixto_particiona_cada_fila_en_exactamente_un_dataset(
        self, diccionario, df_mixto
    ):
        """4.4 RED+GREEN: cada fila de entrada cae en exactamente uno de los
        dos datasets; el detalle identifica registro/campo/regla."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        indices_validos = set(outcome.df_validos.index)
        indices_rechazados = set(outcome.df_rechazados.index)

        # Particion exacta: union = todas las filas, interseccion vacia.
        assert indices_validos | indices_rechazados == set(df_mixto.index)
        assert indices_validos & indices_rechazados == set()
        assert indices_validos == FILAS_VALIDAS

        # Las filas rechazadas conservan sus datos originales.
        pd.testing.assert_frame_equal(
            outcome.df_rechazados, df_mixto.loc[sorted(indices_rechazados)]
        )

        # El detalle identifica registro, campo y regla de cada violacion.
        detalles = {
            (d.indice_registro, d.campo, d.regla) for d in outcome.detalle_rechazos
        }
        assert (FILA_RANGO, "variable_respuesta_1", "rango") in detalles
        assert (FILA_LISTA, "bloque", "lista") in detalles
        for fila in FILAS_UNICIDAD:
            assert (fila, "id_unidad", "unicidad") in detalles
        assert (FILA_COMPLETITUD, "variable_respuesta_1", "completitud") in detalles
        assert (FILA_CRUZADA, "fecha_inicio,fecha_fin", "orden_fechas") in detalles

        # Todo detalle refiere a una fila rechazada (nunca a una valida).
        assert {d.indice_registro for d in outcome.detalle_rechazos} == indices_rechazados


# ---------------------------------------------------------------------------
# Seccion 5: fixture sintetico extendido — guardarrail anti-caso-real
# ---------------------------------------------------------------------------

# Mismos terminos prohibidos que el guardarrail de C-02
# (tests/test_data_dictionary.py): su sola aparicion indicaria que se colo un
# caso de estudio real (cultivo/institucion/region/campana).
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
    def test_variantes_invalidas_usan_identificadores_genericos(self):
        """5.2: las variantes invalidas reusan los identificadores genericos
        de C-02 y no nombran cultivo, institucion, region ni campana real."""
        texto = DATASET_INVALIDO_PATH.read_text(encoding="utf-8").lower()

        for termino in TERMINOS_DE_DOMINIO_REAL_PROHIBIDOS:
            assert termino not in texto, (
                f"Termino de dominio real '{termino}' filtrado en el fixture invalido"
            )

        # Identificadores genericos de C-02 presentes (encabezado + codigos).
        assert "id_unidad" in texto
        assert "variable_respuesta_1" in texto
        assert any(codigo in texto for codigo in ("t1", "t2", "t3"))
        assert any(codigo in texto for codigo in ("b1", "b2", "b3", "b4"))


# ---------------------------------------------------------------------------
# Seccion 6: un caso negativo por cada tipo de violacion (RN-VAL-02..07)
# ---------------------------------------------------------------------------


class TestCasosNegativosPorViolacion:
    def test_violacion_de_tipo_rechaza_el_registro(self, diccionario, df_valido):
        """6.1 (RN-VAL-02): un valor de tipo incorrecto manda el registro a
        rechazados; el detalle identifica campo y regla de tipo.

        La variante vive en memoria (no en CSV): un tipo mezclado solo puede
        materializarse como columna `object`, cosa que un CSV no representa."""
        from pipeline.validation import validate

        df = df_valido.copy()
        df["variable_respuesta_1"] = df["variable_respuesta_1"].astype("object")
        df.loc[3, "variable_respuesta_1"] = "no_numerico"

        outcome = validate(df, diccionario)

        assert 3 in set(outcome.df_rechazados.index)
        assert 3 not in set(outcome.df_validos.index)
        assert any(
            d.indice_registro == 3
            and d.campo == "variable_respuesta_1"
            and d.regla == "tipo"
            for d in outcome.detalle_rechazos
        )

    def test_violacion_de_rango_rechaza_el_registro(self, diccionario, df_mixto):
        """6.2 (RN-VAL-03): numerico fuera de {min,max} -> rechazado con
        detalle de campo y regla de rango."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        assert FILA_RANGO in set(outcome.df_rechazados.index)
        detalle = [
            d
            for d in outcome.detalle_rechazos
            if d.indice_registro == FILA_RANGO and d.regla == "rango"
        ]
        assert len(detalle) == 1
        assert detalle[0].campo == "variable_respuesta_1"
        assert detalle[0].valor_observado == 150.5

    def test_violacion_de_lista_rechaza_el_registro(self, diccionario, df_mixto):
        """6.3 (RN-VAL-04): categorico fuera de valores_admisibles ->
        rechazado con detalle de campo y regla de lista."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        assert FILA_LISTA in set(outcome.df_rechazados.index)
        detalle = [
            d
            for d in outcome.detalle_rechazos
            if d.indice_registro == FILA_LISTA and d.regla == "lista"
        ]
        assert len(detalle) == 1
        assert detalle[0].campo == "bloque"
        assert detalle[0].valor_observado == "B9"

    def test_violacion_de_unicidad_rechaza_ambos_duplicados(self, diccionario, df_mixto):
        """6.4 (RN-VAL-05): clave primaria duplicada -> TODAS las ocurrencias
        del duplicado quedan en rechazados, con campo clave y regla."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        assert FILAS_UNICIDAD <= set(outcome.df_rechazados.index)
        for fila in FILAS_UNICIDAD:
            detalle = [
                d
                for d in outcome.detalle_rechazos
                if d.indice_registro == fila and d.regla == "unicidad"
            ]
            assert len(detalle) == 1
            assert detalle[0].campo == "id_unidad"
            assert detalle[0].valor_observado == 104

    def test_violacion_de_completitud_rechaza_el_registro(self, diccionario, df_mixto):
        """6.5 (RN-VAL-06): obligatorio nulo -> rechazado con detalle de campo
        y regla de completitud."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        assert FILA_COMPLETITUD in set(outcome.df_rechazados.index)
        detalle = [
            d
            for d in outcome.detalle_rechazos
            if d.indice_registro == FILA_COMPLETITUD and d.regla == "completitud"
        ]
        assert len(detalle) == 1
        assert detalle[0].campo == "variable_respuesta_1"
        assert pd.isna(detalle[0].valor_observado)

    def test_violacion_cruzada_rechaza_el_registro(self, diccionario, df_mixto):
        """6.6 (RN-VAL-07): fecha_inicio > fecha_fin -> rechazado; el detalle
        identifica la regla cruzada por su `id` y los campos involucrados."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        assert FILA_CRUZADA in set(outcome.df_rechazados.index)
        detalle = [
            d
            for d in outcome.detalle_rechazos
            if d.indice_registro == FILA_CRUZADA and d.regla == "orden_fechas"
        ]
        assert len(detalle) == 1
        assert detalle[0].campo == "fecha_inicio,fecha_fin"
        assert detalle[0].valor_observado["fecha_inicio"] > detalle[0].valor_observado["fecha_fin"]

    def test_registro_con_multiples_violaciones_aparece_una_sola_vez(
        self, diccionario, df_mixto
    ):
        """6.7 TRIANGULATE: un registro que viola varias reglas a la vez
        (rango + lista) aparece UNA sola vez en rechazados, con una entrada
        de detalle por cada regla violada."""
        from pipeline.validation import validate

        outcome = validate(df_mixto, diccionario)

        apariciones = list(outcome.df_rechazados.index).count(FILA_MULTIPLE)
        assert apariciones == 1

        reglas_de_la_fila = {
            d.regla for d in outcome.detalle_rechazos if d.indice_registro == FILA_MULTIPLE
        }
        assert {"rango", "lista"} <= reglas_de_la_fila


# ---------------------------------------------------------------------------
# Seccion 7: reporte de validacion (JSON)
# ---------------------------------------------------------------------------


class TestReporte:
    def test_reporte_contiene_resultado_y_detalle_de_rechazos(self, diccionario, df_mixto):
        """7.1 RED: el reporte de una validacion con rechazos contiene el
        resultado de great_expectations y el detalle registro/campo/regla,
        y es serializable a JSON (US-002 / RN-VAL-08)."""
        import json

        from pipeline.validation import generar_reporte, validate

        outcome = validate(df_mixto, diccionario)
        reporte = generar_reporte(outcome)

        # Serializable a JSON de punta a punta (inspeccionable sin Python).
        texto = json.dumps(reporte)
        recuperado = json.loads(texto)

        # Contiene el resultado crudo de GX (trazabilidad).
        assert recuperado["resultado_ge"]["success"] is False
        assert len(recuperado["resultado_ge"]["results"]) > 0

        # Contiene el detalle de rechazos con registro/campo/regla.
        detalles = recuperado["detalle_rechazos"]
        assert {"indice_registro", "campo", "regla", "valor_observado"} <= set(detalles[0])
        assert {
            (d["indice_registro"], d["campo"], d["regla"]) for d in detalles
        } >= {
            (FILA_RANGO, "variable_respuesta_1", "rango"),
            (FILA_LISTA, "bloque", "lista"),
            (FILA_CRUZADA, "fecha_inicio,fecha_fin", "orden_fechas"),
        }

        # Resumen de la particion dual.
        assert recuperado["resumen"]["total_registros"] == len(df_mixto)
        assert recuperado["resumen"]["registros_validos"] == len(FILAS_VALIDAS)
        assert recuperado["resumen"]["registros_rechazados"] == len(df_mixto) - len(FILAS_VALIDAS)


# ---------------------------------------------------------------------------
# Seccion 8: CLI fino por archivos (RN-VAL-08, D-1/D-2/D-3, change
# n8n-orchestration-workflows) -- entrypoint que n8n invoca (DD-05/DD-09)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_produce_salida_dual_por_archivos_y_actualiza_manifest(self, tmp_path, df_mixto):
        """3.1/3.2: `main` sobre el artefacto pickle de ingesta (dataset
        mixto con rechazos parciales) produce validos.pkl/rechazados.pkl,
        rechazados.csv + reporte_validacion.json legibles, y ACTUALIZA (no
        pisa) el manifest.json que dejo la etapa anterior con los conteos de
        esta etapa (D-3) -- exit 0 (RN-GLB-01: rechazos parciales no es
        fallo de la corrida)."""
        import json

        from pipeline.validation import main

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        artefacto_entrada = corrida_dir / "ingerido.pkl"
        df_mixto.to_pickle(artefacto_entrada)
        (corrida_dir / "manifest.json").write_text(
            json.dumps({"ruta_archivo_entrada": str(DATASET_INVALIDO_PATH), "registros_leidos": len(df_mixto)}),
            encoding="utf-8",
        )

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
        assert (corrida_dir / "validos.pkl").exists()
        assert (corrida_dir / "rechazados.pkl").exists()
        assert (corrida_dir / "rechazados.csv").exists()
        assert (corrida_dir / "reporte_validacion.json").exists()

        manifest = json.loads((corrida_dir / "manifest.json").read_text(encoding="utf-8"))
        # Conserva lo que escribio la etapa anterior (D-3: acumulativo).
        assert manifest["ruta_archivo_entrada"] == str(DATASET_INVALIDO_PATH)
        assert manifest["registros_leidos"] == len(df_mixto)
        # Agrega los conteos propios de esta etapa.
        assert manifest["registros_validos"] == len(FILAS_VALIDAS)
        assert manifest["registros_rechazados"] == len(df_mixto) - len(FILAS_VALIDAS)

        reporte = json.loads((corrida_dir / "reporte_validacion.json").read_text(encoding="utf-8"))
        assert reporte["resumen"]["registros_validos"] == len(FILAS_VALIDAS)

    def test_cli_artefacto_de_entrada_ilegible_sale_exit_code_2(self, tmp_path):
        """3.3 TRIANGULATE: un artefacto de entrada corrupto (no es un
        pickle valido) -- fallo REAL de infraestructura del handoff entre
        etapas -- sale con exit code 2, distinto del exit 0 de rechazos
        parciales de datos (RN-GLB-03: n8n solo reintenta el 2)."""
        from pipeline.validation import main

        artefacto_corrupto = tmp_path / "no_es_un_pickle_valido.pkl"
        artefacto_corrupto.write_bytes(b"esto no es un pickle valido, solo bytes sueltos")

        exit_code = main(
            [
                str(artefacto_corrupto),
                "--dictionary-path",
                str(DICCIONARIO_PATH),
                "--output-dir",
                str(tmp_path / "salida"),
            ]
        )

        assert exit_code == 2
