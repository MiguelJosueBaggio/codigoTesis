"""Loader del diccionario de variables (change data-dictionary-schema / C-02).

`config/data_dictionary.json` es el contrato de datos central del pipeline:
la ingesta (C-03) valida estructura contra el, el motor de validacion (C-04)
genera su expectation suite de `great_expectations` a partir de el, y la
transformacion (C-05) normaliza hacia sus unidades y nombres canonicos.

Este modulo es la UNICA puerta de entrada a ese contrato: parsea el JSON,
lo meta-valida contra el meta-schema declarativo (`config/data_dictionary
.schema.json`, JSON Schema Draft 2020-12) y contra la integridad referencial
de `reglas_cruzadas` (que JSON Schema no puede expresar), y devuelve una
representacion tipada en memoria. Ante cualquier diccionario mal formado
levanta `DataDictionaryError` (o una subclase) con un mensaje que identifica
la causa; nunca devuelve una estructura a medio validar.

NO valida los *datos* de un ensayo contra el diccionario (eso es C-04); NO
ejecuta las reglas cruzadas contra datos (tambien C-04). Este modulo valida
exclusivamente la validez estructural del propio diccionario (Decision 4,
design.md del change).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "config" / "data_dictionary.schema.json"


class DataDictionaryError(Exception):
    """Base de todos los errores del contrato del diccionario de variables."""


class DataDictionarySchemaError(DataDictionaryError):
    """El documento no cumple la forma declarada por el meta-schema (JSON Schema)."""


class DataDictionaryReferentialError(DataDictionaryError):
    """Una regla cruzada referencia una variable que no existe en el diccionario.

    Integridad referencial que JSON Schema no puede expresar (no puede cruzar
    el valor de un campo contra las claves hermanas del documento): se
    verifica en un segundo pase minimo en Python (Decision 4, design.md).
    """


@dataclass(frozen=True)
class VariableDefinition:
    """Definicion tipada de una variable del diccionario."""

    nombre_canonico: str
    descripcion: str
    tipo_dato: str
    obligatorio: bool
    unidad: Optional[str] = None
    rango: Optional[dict] = None
    valores_admisibles: Optional[list] = None


@dataclass(frozen=True)
class CrossFieldRule:
    """Regla de validacion cruzada entre dos o mas variables (RN-VAL-07).

    Su *forma* la mete-valida el meta-schema; su *ejecucion* contra datos
    reales pertenece a C-04. Este modulo solo garantiza que `campos`
    referencia variables existentes.
    """

    id: str
    operador: str
    campos: list
    descripcion: Optional[str] = None


@dataclass(frozen=True)
class DataDictionary:
    """Contenedor tipado del diccionario completo, con lookup por nombre_canonico."""

    _variables: dict = field(default_factory=dict)
    reglas_cruzadas: tuple = field(default_factory=tuple)

    def get(self, nombre_canonico: str) -> VariableDefinition:
        """Devuelve la definicion de la variable `nombre_canonico`.

        Lanza `KeyError` si no existe (el diccionario ya fue meta-validado
        en `load_data_dictionary`, asi que un lookup fallido aca es un error
        de uso del caller, no de datos mal formados).
        """
        return self._variables[nombre_canonico]

    def __contains__(self, nombre_canonico: str) -> bool:
        return nombre_canonico in self._variables

    def __iter__(self):
        return iter(self._variables.values())


def _cargar_meta_schema() -> dict:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _identificar_variable(contenido: dict, path: list) -> Optional[str]:
    """Si `path` (el `absolute_path` de un error de jsonschema) apunta dentro
    de `variables/<indice>/...`, devuelve el `nombre_canonico` de esa
    variable para que el mensaje de error la identifique por nombre en vez
    de por indice posicional."""
    if len(path) >= 2 and path[0] == "variables" and isinstance(path[1], int):
        variables = contenido.get("variables", [])
        indice = path[1]
        if 0 <= indice < len(variables):
            return variables[indice].get("nombre_canonico")
    return None


def _meta_validar(contenido: dict) -> None:
    """Valida `contenido` contra el meta-schema declarativo. Levanta
    `DataDictionarySchemaError` con el primer error encontrado, identificando
    la variable (por `nombre_canonico`) y el campo/ruta dentro del documento."""
    schema = _cargar_meta_schema()
    validador = jsonschema.Draft202012Validator(schema)
    errores = sorted(validador.iter_errors(contenido), key=lambda e: list(e.path))

    if errores:
        primero = errores[0]
        ruta_partes = list(primero.path)
        ruta = "/".join(str(parte) for parte in ruta_partes) or "<raiz>"
        nombre_variable = _identificar_variable(contenido, ruta_partes)

        if nombre_variable:
            raise DataDictionarySchemaError(
                f"Variable '{nombre_variable}' no cumple el meta-schema "
                f"(en '{ruta}'): {primero.message}"
            )
        raise DataDictionarySchemaError(
            f"El diccionario no cumple el meta-schema en '{ruta}': {primero.message}"
        )


def _validar_integridad_referencial(contenido: dict) -> None:
    """Verifica que cada `campos` de cada regla cruzada referencia una
    variable existente en el diccionario. Esto es integridad referencial de
    un artefacto de configuracion (cruzar un campo contra las claves
    hermanas del documento), no una regla de validacion de datos del
    ensayo — por eso vive en Python y no en el meta-schema JSON Schema
    (Decision 4, design.md)."""
    nombres_definidos = {
        variable["nombre_canonico"] for variable in contenido.get("variables", [])
    }

    for regla in contenido.get("reglas_cruzadas", []):
        for nombre_campo in regla["campos"]:
            if nombre_campo not in nombres_definidos:
                raise DataDictionaryReferentialError(
                    f"La regla cruzada '{regla['id']}' referencia la variable "
                    f"inexistente '{nombre_campo}'"
                )


def _construir_variable(datos: dict) -> VariableDefinition:
    return VariableDefinition(
        nombre_canonico=datos["nombre_canonico"],
        descripcion=datos["descripcion"],
        tipo_dato=datos["tipo_dato"],
        obligatorio=datos["obligatorio"],
        unidad=datos.get("unidad"),
        rango=datos.get("rango"),
        valores_admisibles=datos.get("valores_admisibles"),
    )


def _construir_regla(datos: dict) -> CrossFieldRule:
    return CrossFieldRule(
        id=datos["id"],
        operador=datos["operador"],
        campos=list(datos["campos"]),
        descripcion=datos.get("descripcion"),
    )


def load_data_dictionary(path: Union[str, Path]) -> DataDictionary:
    """Parsea, meta-valida y devuelve la representacion tipada del
    diccionario de variables en `path`.

    Ante cualquier diccionario mal formado (JSON invalido, incumplimiento
    del meta-schema, o regla cruzada con integridad referencial rota)
    levanta `DataDictionaryError` (o una subclase) y NUNCA devuelve una
    estructura a medio validar.
    """
    ruta = Path(path)

    try:
        with ruta.open(encoding="utf-8") as fh:
            contenido = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataDictionarySchemaError(f"El archivo '{ruta}' no es JSON valido: {exc}") from exc

    _meta_validar(contenido)
    _validar_integridad_referencial(contenido)

    variables = {
        datos["nombre_canonico"]: _construir_variable(datos)
        for datos in contenido.get("variables", [])
    }
    reglas = tuple(_construir_regla(datos) for datos in contenido.get("reglas_cruzadas", []))

    return DataDictionary(_variables=variables, reglas_cruzadas=reglas)
