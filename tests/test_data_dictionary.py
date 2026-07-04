"""Suite TDD del meta-schema y loader del diccionario de variables
(change data-dictionary-schema / C-02).

Cubre:
- Seccion 2: el meta-schema (`config/data_dictionary.schema.json`) es un
  JSON Schema (Draft 2020-12) valido que declara la forma de una definicion
  de variable.
- Seccion 3: el loader `load_data_dictionary` parsea + meta-valida y expone
  una representacion tipada en memoria (`DataDictionary`, `VariableDefinition`,
  `CrossFieldRule`).
- Seccion 4: rechazo de diccionarios mal formados (casos negativos).
- Seccion 5: integridad referencial de `reglas_cruzadas`.
- Seccion 6: fixture sintetico generico de referencia.

NO valida datos de un ensayo real (eso es C-04); valida exclusivamente la
forma del propio diccionario.
"""

import csv
import json
from pathlib import Path

import jsonschema
import pytest

SCHEMA_PATH = Path("config/data_dictionary.schema.json")


def _load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _diccionario_base() -> dict:
    """Diccionario minimo valido usado como punto de partida por varios tests."""
    return {
        "variables": [
            {
                "nombre_canonico": "id_unidad",
                "descripcion": "Identificador de la unidad experimental",
                "tipo_dato": "entero",
                "obligatorio": True,
            },
            {
                "nombre_canonico": "bloque",
                "descripcion": "Bloque experimental",
                "tipo_dato": "categorico",
                "obligatorio": True,
                "valores_admisibles": ["B1", "B2", "B3", "B4"],
            },
        ],
        "reglas_cruzadas": [],
    }


# ---------------------------------------------------------------------------
# Seccion 2: meta-schema declarativo (JSON Schema)
# ---------------------------------------------------------------------------


class TestMetaSchema:
    def test_es_json_schema_draft_2020_12_valido(self):
        """2.1 RED/GREEN: el archivo es un JSON Schema Draft 2020-12 sintacticamente valido."""
        schema = _load_schema()

        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        # No debe levantar SchemaError: confirma que el documento es un JSON Schema valido.
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_declara_los_atributos_de_una_definicion_de_variable(self):
        """2.1: declara los atributos requeridos por 04_modelo_de_datos.md."""
        schema = _load_schema()
        variable_def = schema["$defs"]["variable_definition"]
        propiedades = variable_def["properties"]

        atributos_esperados = {
            "nombre_canonico",
            "descripcion",
            "tipo_dato",
            "unidad",
            "rango",
            "valores_admisibles",
            "obligatorio",
        }
        assert atributos_esperados.issubset(propiedades.keys())

    def test_tipo_dato_restringido_a_enum_cerrado(self):
        """2.1/2.4: `tipo_dato` es un enum cerrado de 5 valores."""
        schema = _load_schema()
        tipo_dato_schema = schema["$defs"]["variable_definition"]["properties"]["tipo_dato"]

        assert set(tipo_dato_schema["enum"]) == {
            "entero",
            "real",
            "categorico",
            "fecha",
            "texto_libre",
        }

    def test_reglas_cruzadas_es_lista_de_nivel_superior(self):
        """2.2: `reglas_cruzadas` es una lista en la raiz del documento, no por-variable."""
        schema = _load_schema()
        assert schema["properties"]["reglas_cruzadas"]["type"] == "array"

    def test_categorico_exige_valores_admisibles_no_vacio(self):
        """2.3: tipo_dato=categorico => valores_admisibles presente y no vacio (if/then)."""
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)

        diccionario = _diccionario_base()
        diccionario["variables"][1].pop("valores_admisibles")

        errores = list(validator.iter_errors(diccionario))
        assert len(errores) > 0

    def test_rango_no_aplicable_a_no_numericos(self):
        """2.3: `rango` solo aplicable a variables entero/real."""
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)

        diccionario = _diccionario_base()
        diccionario["variables"][1]["rango"] = {"min": 0, "max": 10}  # bloque es categorico

        errores = list(validator.iter_errors(diccionario))
        assert len(errores) > 0

    def test_rango_valido_en_variable_numerica(self):
        """Caso positivo simetrico: `rango` en una variable entero/real es aceptado."""
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)

        diccionario = _diccionario_base()
        diccionario["variables"][0]["rango"] = {"min": 0, "max": 999}

        errores = list(validator.iter_errors(diccionario))
        assert errores == []

    def test_tipo_dato_fuera_de_enum_es_rechazado(self):
        """2.4 TRIANGULATE: un `tipo_dato` fuera del enum cerrado es rechazado."""
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)

        diccionario = _diccionario_base()
        diccionario["variables"][0]["tipo_dato"] = "numero"

        errores = list(validator.iter_errors(diccionario))
        assert len(errores) > 0

    def test_nombre_canonico_exige_snake_case(self):
        """2.4 TRIANGULATE: `nombre_canonico` debe respetar snake_case."""
        schema = _load_schema()
        validator = jsonschema.Draft202012Validator(schema)

        diccionario = _diccionario_base()
        diccionario["variables"][0]["nombre_canonico"] = "IdUnidad"

        errores = list(validator.iter_errors(diccionario))
        assert len(errores) > 0


# ---------------------------------------------------------------------------
# Seccion 3: loader + representacion tipada en memoria
# ---------------------------------------------------------------------------


def _escribir_diccionario(tmp_path: Path, contenido: dict) -> Path:
    ruta = tmp_path / "diccionario.json"
    ruta.write_text(json.dumps(contenido), encoding="utf-8")
    return ruta


class TestLoader:
    def test_diccionario_valido_devuelve_estructura_tipada(self, tmp_path):
        """3.1 RED/GREEN: carga un diccionario valido y expone lookup tipado por nombre_canonico."""
        from pipeline.data_dictionary import load_data_dictionary

        ruta = _escribir_diccionario(tmp_path, _diccionario_base())
        diccionario = load_data_dictionary(ruta)

        id_unidad = diccionario.get("id_unidad")
        assert id_unidad.tipo_dato == "entero"
        assert id_unidad.obligatorio is True

        bloque = diccionario.get("bloque")
        assert bloque.tipo_dato == "categorico"
        assert bloque.valores_admisibles == ["B1", "B2", "B3", "B4"]

    def test_expone_rango_y_unidad_cuando_corresponde(self, tmp_path):
        """3.1: una variable numerica con rango/unidad los expone en la estructura tipada."""
        from pipeline.data_dictionary import load_data_dictionary

        contenido = _diccionario_base()
        contenido["variables"][0]["rango"] = {"min": 0, "max": 999}
        contenido["variables"][0]["unidad"] = "unidad_generica"
        ruta = _escribir_diccionario(tmp_path, contenido)

        diccionario = load_data_dictionary(ruta)
        id_unidad = diccionario.get("id_unidad")

        assert id_unidad.rango == {"min": 0, "max": 999}
        assert id_unidad.unidad == "unidad_generica"

    def test_jerarquia_de_errores_tiene_base_comun(self):
        """3.3: `DataDictionaryError` es una excepcion valida e importable."""
        from pipeline.data_dictionary import DataDictionaryError

        assert issubclass(DataDictionaryError, Exception)

    def test_diccionario_malformado_no_devuelve_estructura_a_medias(self, tmp_path):
        """3.3: ante un diccionario invalido, el loader levanta error y no devuelve nada parcial."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        del contenido["variables"][0]["tipo_dato"]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError):
            load_data_dictionary(ruta)


# ---------------------------------------------------------------------------
# Seccion 4: rechazo de diccionarios mal formados (casos negativos)
# ---------------------------------------------------------------------------


class TestCasosNegativos:
    def test_campo_obligatorio_faltante_identifica_variable_y_campo(self, tmp_path):
        """4.1: falta `tipo_dato` en una variable -> error identifica variable y campo."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        del contenido["variables"][0]["tipo_dato"]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError) as exc_info:
            load_data_dictionary(ruta)

        mensaje = str(exc_info.value)
        assert "id_unidad" in mensaje
        assert "tipo_dato" in mensaje

    def test_tipo_dato_invalido_identifica_variable_y_valor(self, tmp_path):
        """4.2: `tipo_dato` fuera de enum -> error identifica variable y valor invalido."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        contenido["variables"][0]["tipo_dato"] = "numero"
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError) as exc_info:
            load_data_dictionary(ruta)

        mensaje = str(exc_info.value)
        assert "id_unidad" in mensaje
        assert "numero" in mensaje

    def test_categorico_sin_valores_admisibles_identifica_variable(self, tmp_path):
        """4.3: categorico sin valores_admisibles (ausente) -> error identifica la variable."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        del contenido["variables"][1]["valores_admisibles"]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError) as exc_info:
            load_data_dictionary(ruta)

        assert "bloque" in str(exc_info.value)

    def test_categorico_con_valores_admisibles_vacio_identifica_variable(self, tmp_path):
        """4.3: categorico con valores_admisibles vacia -> error identifica la variable."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        contenido["variables"][1]["valores_admisibles"] = []
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError) as exc_info:
            load_data_dictionary(ruta)

        assert "bloque" in str(exc_info.value)

    def test_rango_en_variable_no_numerica_es_rechazado(self, tmp_path):
        """4.4 TRIANGULATE: `rango` en una variable categorica es rechazado."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_base()
        contenido["variables"][1]["rango"] = {"min": 0, "max": 10}
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError):
            load_data_dictionary(ruta)

    def test_json_sintacticamente_invalido_es_rechazado(self, tmp_path):
        """4.4 TRIANGULATE: JSON mal formado (sintaxis) -> error explicito, no crash crudo."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        ruta = tmp_path / "invalido.json"
        ruta.write_text("{ esto no es json valido ", encoding="utf-8")

        with pytest.raises(DataDictionaryError):
            load_data_dictionary(ruta)


# ---------------------------------------------------------------------------
# Seccion 5: integridad referencial de reglas cruzadas
# ---------------------------------------------------------------------------


def _diccionario_con_fechas() -> dict:
    """Extiende el diccionario base con las variables de fecha usadas por
    `orden_fechas`, la regla cruzada de referencia del design (Decision 5)."""
    contenido = _diccionario_base()
    contenido["variables"].append(
        {
            "nombre_canonico": "fecha_inicio",
            "descripcion": "Fecha de inicio del ensayo",
            "tipo_dato": "fecha",
            "obligatorio": True,
        }
    )
    contenido["variables"].append(
        {
            "nombre_canonico": "fecha_fin",
            "descripcion": "Fecha de fin del ensayo",
            "tipo_dato": "fecha",
            "obligatorio": True,
        }
    )
    return contenido


class TestReglasCruzadas:
    def test_regla_bien_formada_con_campos_existentes_se_incorpora(self, tmp_path):
        """5.1 RED/GREEN: regla cruzada valida cuyos campos existen se incorpora sin error."""
        from pipeline.data_dictionary import load_data_dictionary

        contenido = _diccionario_con_fechas()
        contenido["reglas_cruzadas"] = [
            {
                "id": "orden_fechas",
                "operador": "menor_igual",
                "campos": ["fecha_inicio", "fecha_fin"],
                "descripcion": "fecha_inicio <= fecha_fin",
            }
        ]
        ruta = _escribir_diccionario(tmp_path, contenido)

        diccionario = load_data_dictionary(ruta)

        assert len(diccionario.reglas_cruzadas) == 1
        regla = diccionario.reglas_cruzadas[0]
        assert regla.id == "orden_fechas"
        assert regla.campos == ["fecha_inicio", "fecha_fin"]

    def test_regla_que_referencia_variable_inexistente_es_rechazada(self, tmp_path):
        """5.3 RED/GREEN: regla cruzada que cita una variable no definida -> error identifica
        la regla y el nombre inexistente."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_con_fechas()
        contenido["reglas_cruzadas"] = [
            {
                "id": "orden_fechas",
                "operador": "menor_igual",
                "campos": ["fecha_inicio", "fecha_inexistente"],
            }
        ]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError) as exc_info:
            load_data_dictionary(ruta)

        mensaje = str(exc_info.value)
        assert "orden_fechas" in mensaje
        assert "fecha_inexistente" in mensaje

    def test_operador_fuera_de_enum_es_rechazado(self, tmp_path):
        """5.4 TRIANGULATE: `operador` fuera del enum cerrado es rechazado."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_con_fechas()
        contenido["reglas_cruzadas"] = [
            {
                "id": "orden_fechas",
                "operador": "aproximadamente_igual",
                "campos": ["fecha_inicio", "fecha_fin"],
            }
        ]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError):
            load_data_dictionary(ruta)

    def test_campos_vacio_es_rechazado(self, tmp_path):
        """5.4 TRIANGULATE: `campos` vacio es rechazado."""
        from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary

        contenido = _diccionario_con_fechas()
        contenido["reglas_cruzadas"] = [
            {
                "id": "regla_vacia",
                "operador": "menor_igual",
                "campos": [],
            }
        ]
        ruta = _escribir_diccionario(tmp_path, contenido)

        with pytest.raises(DataDictionaryError):
            load_data_dictionary(ruta)


# ---------------------------------------------------------------------------
# Seccion 6: fixture sintetico generico de referencia
# ---------------------------------------------------------------------------

FIXTURE_DICT_PATH = Path("tests/fixtures/data_dictionary_sintetico.json")
FIXTURE_CSV_PATH = Path("tests/fixtures/dataset_sintetico.csv")

# Terminos de dominio real cuya sola aparicion en el fixture indicaria que se
# coló un caso de estudio real (cultivo/institucion/region/campana). Ninguno
# debe aparecer: el fixture es deliberadamente generico (Decision 5, design.md).
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


class TestFixtureSintetico:
    def test_diccionario_sintetico_es_valido_y_cubre_todos_los_tipos(self):
        """6.3 RED/GREEN: el fixture sintetico pasa la meta-validacion y cubre cada tipo_dato,
        una variable opcional y una regla cruzada."""
        from pipeline.data_dictionary import load_data_dictionary

        diccionario = load_data_dictionary(FIXTURE_DICT_PATH)

        tipos_presentes = {variable.tipo_dato for variable in diccionario}
        assert {"entero", "real", "categorico", "fecha"}.issubset(tipos_presentes)

        opcionales = [variable for variable in diccionario if not variable.obligatorio]
        assert len(opcionales) >= 1

        assert len(diccionario.reglas_cruzadas) >= 1

    def test_dataset_sintetico_columnas_corresponden_1_a_1_con_diccionario(self):
        """6.4 RED/GREEN: las columnas del CSV corresponden 1:1 a variables del diccionario
        y los valores respetan tipo/rango/valores_admisibles."""
        from pipeline.data_dictionary import load_data_dictionary

        diccionario = load_data_dictionary(FIXTURE_DICT_PATH)
        nombres_variables = {variable.nombre_canonico for variable in diccionario}

        with FIXTURE_CSV_PATH.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            assert set(reader.fieldnames) == nombres_variables

            filas = list(reader)

        assert len(filas) > 0

        for fila in filas:
            for nombre_columna, valor in fila.items():
                variable = diccionario.get(nombre_columna)

                if valor == "":
                    assert not variable.obligatorio, (
                        f"'{nombre_columna}' es obligatoria pero tiene un valor vacio"
                    )
                    continue

                if variable.tipo_dato == "entero":
                    assert valor.lstrip("-").isdigit()
                elif variable.tipo_dato == "real":
                    numero = float(valor)
                    if variable.rango:
                        assert variable.rango["min"] <= numero <= variable.rango["max"]
                elif variable.tipo_dato == "categorico":
                    assert valor in variable.valores_admisibles
                elif variable.tipo_dato == "fecha":
                    from datetime import date

                    date.fromisoformat(valor)

    def test_guardarrail_anti_caso_real_identificadores_genericos(self):
        """6.5: guardarrail anti-caso-real. Los identificadores del fixture son genericos
        (variable_respuesta_N, T1..T3, B1..B4, unidad_generica) y no nombran cultivo,
        institucion, region ni campana real."""
        texto_json = FIXTURE_DICT_PATH.read_text(encoding="utf-8").lower()
        texto_csv = FIXTURE_CSV_PATH.read_text(encoding="utf-8").lower()

        for termino in TERMINOS_DE_DOMINIO_REAL_PROHIBIDOS:
            assert termino not in texto_json, f"Termino de dominio real '{termino}' filtrado en el diccionario sintetico"
            assert termino not in texto_csv, f"Termino de dominio real '{termino}' filtrado en el dataset sintetico"

        # Identificadores genericos esperados, tal como los fija Decision 5 del design.
        assert "variable_respuesta_1" in texto_json
        assert "unidad_generica" in texto_json
        assert all(codigo in texto_json for codigo in ("t1", "t2", "t3"))
        assert all(codigo in texto_json for codigo in ("b1", "b2", "b3", "b4"))
