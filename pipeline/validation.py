"""Motor de validacion declarativa de datos (change validation-engine / C-04).

Guardian de calidad entre la ingesta (C-03) y el analisis (C-06/C-07): valida
un DataFrame de pandas contra el diccionario de variables de C-02 y produce
la salida dual valida/rechazada que exige RN-VAL-08.

Disciplina DD-04 / RN-VAL-01 (regla dura del proyecto): las reglas de
validacion NUNCA se escriben como comparaciones imperativas `if`/`else` en
Python. Este modulo solo TRADUCE los atributos declarativos del diccionario
(`config/data_dictionary.json`, cargado por `pipeline.data_dictionary`) a
expectations declarativas de `great_expectations`. La suite resultante es
serializable a JSON e inspeccionable sin leer codigo; quien decide "que es
invalido" es el motor de great_expectations, no este codigo.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import great_expectations as gx
import pandas as pd
from great_expectations.core.expectation_suite import ExpectationSuite

from pipeline.data_dictionary import (
    CrossFieldRule,
    DataDictionary,
    DataDictionaryError,
    VariableDefinition,
    load_data_dictionary,
)

_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "config" / "data_dictionary.json"


class ValidationEngineError(Exception):
    """Base de los errores del motor de validacion."""


class UnsupportedOperatorError(ValidationEngineError):
    """Una regla cruzada declara un `operador` que el motor no sabe traducir.

    Fail-closed (Decision 3 del design): ignorar una regla de validacion en
    silencio seria un falso negativo grave (dato malo pasando como bueno),
    asi que el generador falla explicitamente identificando regla y operador.
    Ampliar el enum de operadores es aditivo: se agrega una entrada a
    `_constructor_por_operador` y su test.
    """


# Mapeo declarativo tipo_dato -> expectation de tipo (RN-VAL-02).
# Verificado empiricamente contra great_expectations 1.18.2 + pandas 3.0.3
# (ver Decision 1 del design del change):
# - Los tipos numericos y de fecha usan `expect_column_values_to_be_in_type_list`;
#   "Int64Dtype"/"Float64Dtype" (nombres de clase pandas) son la unica forma en
#   que GX 1.x resuelve los dtypes nullable de extension; "int"/"float" cubren
#   la rama per-row sobre columnas `object` mixtas.
# - `categorico` y `texto_libre` usan `expect_column_values_to_be_of_type("str")`
#   porque el dtype `str` por defecto de pandas 3 (PDEP-14) no matchea ningun
#   nombre en `in_type_list` (esa expectation compara instancias de dtype),
#   mientras que `of_type` compara `dtype.type` (-> `str` nativo) y funciona
#   tanto en modo agregado como per-row sobre columnas `object`.
_TIPOS_ADMISIBLES_POR_TIPO_DATO: dict = {
    "entero": ["int64", "int32", "Int64Dtype", "int"],
    "real": ["float64", "int64", "Float64Dtype", "Int64Dtype", "float", "int"],
    "fecha": ["datetime64", "datetime64[ns]", "datetime64[us]", "Timestamp", "datetime"],
}
_TIPO_NATIVO_POR_TIPO_DATO: dict = {
    "categorico": "str",
    "texto_libre": "str",
}


def _expectation_de_tipo(variable: VariableDefinition):
    """Traduce el `tipo_dato` declarado a su expectation de tipo (RN-VAL-02)."""
    meta = {"regla": "tipo"}
    if variable.tipo_dato in _TIPO_NATIVO_POR_TIPO_DATO:
        return gx.expectations.ExpectColumnValuesToBeOfType(
            column=variable.nombre_canonico,
            type_=_TIPO_NATIVO_POR_TIPO_DATO[variable.tipo_dato],
            meta=meta,
        )
    return gx.expectations.ExpectColumnValuesToBeInTypeList(
        column=variable.nombre_canonico,
        type_list=_TIPOS_ADMISIBLES_POR_TIPO_DATO[variable.tipo_dato],
        meta=meta,
    )


def _expectations_de_variable(variable: VariableDefinition) -> list:
    """Emite las expectations que corresponden a los atributos poblados de
    una variable del diccionario (tabla de mapeo de la Decision 1)."""
    expectations = [_expectation_de_tipo(variable)]

    if variable.rango is not None:
        expectations.append(
            gx.expectations.ExpectColumnValuesToBeBetween(
                column=variable.nombre_canonico,
                min_value=variable.rango["min"],
                max_value=variable.rango["max"],
                meta={"regla": "rango"},
            )
        )

    if variable.valores_admisibles is not None:
        expectations.append(
            gx.expectations.ExpectColumnValuesToBeInSet(
                column=variable.nombre_canonico,
                value_set=list(variable.valores_admisibles),
                meta={"regla": "lista"},
            )
        )

    if variable.obligatorio:
        expectations.append(
            gx.expectations.ExpectColumnValuesToNotBeNull(
                column=variable.nombre_canonico,
                meta={"regla": "completitud"},
            )
        )

    return expectations


# Mapeo declarativo operador-de-regla-cruzada -> expectation multi-columna
# (RN-VAL-07, Decision 3 del design). La regla cruzada ya es un dato
# declarativo en el diccionario (C-02); aca solo se TRADUCE a otro objeto
# declarativo (la expectation de par de columnas). La comparacion entre
# columnas la ejecuta el motor vectorizado de great_expectations, no un `if`
# fila a fila en Python — asi la regla sigue siendo inspeccionable sin leer
# codigo (DD-04). Si el caso real exigiera una relacion que ninguna
# expectation nativa exprese (ej. formula entre 3+ columnas), el escape
# correcto es una custom Expectation de GX (subclase registrada, declarativa
# y serializable) — NUNCA un chequeo imperativo en pandas.
def _pair_greater_than(campos: list, or_equal: bool, meta: dict):
    # campos = [a, b] esperando `a <op> b`  ===  `b > a` (o >=):
    # column_A = b, column_B = a.
    campo_a, campo_b = campos
    return gx.expectations.ExpectColumnPairValuesAToBeGreaterThanB(
        column_A=campo_b, column_B=campo_a, or_equal=or_equal, meta=meta
    )


def _pair_equal(campos: list, meta: dict):
    campo_a, campo_b = campos
    return gx.expectations.ExpectColumnPairValuesToBeEqual(
        column_A=campo_a, column_B=campo_b, meta=meta
    )


_constructor_por_operador: dict = {
    "menor_igual": lambda campos, meta: _pair_greater_than(campos, True, meta),
    "menor": lambda campos, meta: _pair_greater_than(campos, False, meta),
    "igual": _pair_equal,
}


def _expectation_de_regla_cruzada(regla: CrossFieldRule):
    """Traduce una `CrossFieldRule` del diccionario a su expectation
    multi-columna (RN-VAL-07). Operador desconocido -> fail-closed."""
    constructor = _constructor_por_operador.get(regla.operador)
    if constructor is None:
        raise UnsupportedOperatorError(
            f"La regla cruzada '{regla.id}' declara el operador '{regla.operador}', "
            f"que el motor no sabe traducir a una expectation "
            f"(soportados: {sorted(_constructor_por_operador)}). "
            "No se ignora la regla: agregarla al mapeo es un cambio aditivo."
        )
    return constructor(regla.campos, {"regla": regla.id, "campos": list(regla.campos)})


def _resolver_clave_primaria(
    diccionario: DataDictionary,
    clave_primaria: Union[str, list, None],
) -> list:
    """Resuelve sobre que columna(s) aplicar unicidad (RN-VAL-05).

    Preferentemente la designa el llamador; si no, se infiere la primera
    variable `entero` + obligatoria del diccionario (comodidad para el
    fixture sintetico — esto es seleccion de configuracion en tiempo de
    traduccion, no una regla de validacion de datos)."""
    if isinstance(clave_primaria, str):
        return [clave_primaria]
    if clave_primaria is not None:
        return list(clave_primaria)

    inferida = next(
        (v.nombre_canonico for v in diccionario if v.tipo_dato == "entero" and v.obligatorio),
        None,
    )
    return [inferida] if inferida is not None else []


def construir_suite(
    diccionario: DataDictionary,
    clave_primaria: Union[str, list, None] = None,
) -> ExpectationSuite:
    """Genera dinamicamente la expectation suite desde el diccionario (C-02).

    Recorre cada `VariableDefinition` y emite las expectations declarativas
    que corresponden a sus atributos: tipo (RN-VAL-02), rango (RN-VAL-03),
    valores admisibles (RN-VAL-04), unicidad de la clave primaria (RN-VAL-05)
    y completitud de obligatorios (RN-VAL-06). Cambiar el diccionario cambia
    la validacion sin tocar este codigo.

    Args:
        diccionario: representacion tipada de `config/data_dictionary.json`.
        clave_primaria: columna(s) sobre las que exigir unicidad; si se omite
            se infiere la primera variable `entero` obligatoria.

    Returns:
        `ExpectationSuite` declarativa, serializable a JSON (DD-04).
    """
    expectations = []
    for variable in diccionario:
        expectations.extend(_expectations_de_variable(variable))

    for columna_clave in _resolver_clave_primaria(diccionario, clave_primaria):
        expectations.append(
            gx.expectations.ExpectColumnValuesToBeUnique(
                column=columna_clave,
                meta={"regla": "unicidad"},
            )
        )

    for regla in diccionario.reglas_cruzadas:
        expectations.append(_expectation_de_regla_cruzada(regla))

    return gx.ExpectationSuite(name="validacion_datos_ensayo", expectations=expectations)


@dataclass(frozen=True)
class RejectionDetail:
    """Detalle de una violacion: identifica registro, campo y regla (RN-VAL-08).

    `valor_observado` es el valor que viola la regla (para reglas cruzadas,
    un dict {campo: valor} con los valores involucrados)."""

    indice_registro: Any
    campo: str
    regla: str
    valor_observado: Any


@dataclass(frozen=True)
class ValidationOutcome:
    """Salida dual obligatoria de la validacion (RN-VAL-08).

    - `df_validos`: filas sin ninguna expectation violada.
    - `df_rechazados`: filas con al menos una expectation violada.
    - `detalle_rechazos`: un `RejectionDetail` por cada (fila, campo, regla).
    - `resultado_ge`: resultado crudo de great_expectations (trazabilidad y
      reporte)."""

    df_validos: pd.DataFrame
    df_rechazados: pd.DataFrame
    detalle_rechazos: list = field(default_factory=list)
    resultado_ge: Any = None


def _campos_de(config: Any) -> list:
    """Columnas afectadas por una expectation, leidas de su forma declarativa
    (el `meta.campos` que graba `construir_suite` para reglas cruzadas, o el
    `column` de los kwargs para expectations de una columna)."""
    meta = config.meta or {}
    if "campos" in meta:
        return list(meta["campos"])
    return [config.kwargs["column"]]


def _detalle_de_indice(df: pd.DataFrame, indice: Any, campos: list, regla: str) -> RejectionDetail:
    if len(campos) == 1:
        return RejectionDetail(indice, campos[0], regla, df.at[indice, campos[0]])
    return RejectionDetail(
        indice,
        ",".join(campos),
        regla,
        {campo: df.at[indice, campo] for campo in campos},
    )


def validate(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    clave_primaria: Union[str, list, None] = None,
) -> ValidationOutcome:
    """Valida un DataFrame contra el diccionario y produce la salida dual
    validos/rechazados con detalle por registro/campo/regla (RN-VAL-08).

    Supuesto (ver Riesgos del design): el DataFrame llega con los dtypes ya
    materializados — en particular las fechas parseadas (`pd.to_datetime`).
    El parseo es responsabilidad de la ingesta (C-03) / transformacion (C-05),
    nunca de este modulo.

    Blindaje DD-04 — por que esta funcion NO es validacion imperativa: la
    decision "que es invalido" la toma la suite declarativa ejecutada por el
    motor de great_expectations (`result_format="COMPLETE"`). Lo que sigue al
    `batch.validate(...)` es INDEXADO MECANICO dirigido por ese resultado:
    se unen los `unexpected_index_list` que GX reporta por expectation y se
    particiona el DataFrame con `df.loc` / `df.drop`. Aca no se compara
    ningun valor contra ningun limite.

    Args:
        df: datos del ensayo a validar (DataFrame de pandas).
        diccionario: contrato de datos tipado (C-02).
        clave_primaria: columna(s) de unicidad; si se omite se infiere
            (ver `construir_suite`).

    Returns:
        `ValidationOutcome` con la particion dual, el detalle de rechazos y
        el resultado crudo de great_expectations.
    """
    suite = construir_suite(diccionario, clave_primaria=clave_primaria)

    contexto = gx.get_context(mode="ephemeral")
    batch = contexto.data_sources.pandas_default.read_dataframe(df)
    resultado = batch.validate(suite, result_format="COMPLETE")

    detalle_rechazos: list = []
    indices_rechazados: set = set()

    for res in resultado.results:
        if res.success:
            continue

        config = res.expectation_config
        regla = (config.meta or {}).get("regla", config.type)
        campos = _campos_de(config)

        indices = res.result.get("unexpected_index_list")
        if indices is None:
            # Falla AGREGADA (expectation de tipo sobre una columna de dtype
            # homogeneo incorrecto): GX no reporta indices porque el dtype de
            # la columna entera es incorrecto -> ningun valor tiene el tipo
            # declarado y se rechazan todas las filas (Decision 2 del design).
            indices = list(df.index)

        for indice in indices:
            indices_rechazados.add(indice)
            detalle_rechazos.append(_detalle_de_indice(df, indice, campos, regla))

    indices_ordenados = sorted(indices_rechazados)
    df_rechazados = df.loc[indices_ordenados]
    df_validos = df.drop(index=indices_ordenados)

    return ValidationOutcome(
        df_validos=df_validos,
        df_rechazados=df_rechazados,
        detalle_rechazos=detalle_rechazos,
        resultado_ge=resultado,
    )


def _valor_json_seguro(valor: Any) -> Any:
    """Convierte un valor observado (escalares numpy/pandas, Timestamp, NaN,
    dicts de reglas cruzadas) a su equivalente JSON-serializable. Es
    conversion de formato para el reporte, no logica de validacion."""
    if isinstance(valor, dict):
        return {clave: _valor_json_seguro(v) for clave, v in valor.items()}
    if valor is None or (not isinstance(valor, (list, tuple)) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if hasattr(valor, "item"):  # escalares numpy (int64, float64, bool_)
        return valor.item()
    return valor


def generar_reporte(outcome: ValidationOutcome) -> dict:
    """Genera el reporte de validacion en JSON (US-002 / RN-VAL-08).

    Serializa el resultado crudo de great_expectations
    (`resultado_ge.to_json_dict()`, trazabilidad completa por expectation)
    junto con el detalle de rechazos por registro/campo/regla y un resumen
    de la particion dual. El dict devuelto es `json.dumps`-able tal cual.

    Via HTML (documentada, no construida — Decision 2 del design): los Data
    Docs nativos de GX (`context.build_data_docs()`) generan un reporte HTML
    navegable a partir de este mismo resultado, sin dependencias fuera de
    `great_expectations`; exigen un `DataContext` persistente (estructura de
    directorios `gx/`), por eso el default del motor es JSON y el HTML queda
    como opcion de la capa de orquestacion (C-08) si el equipo lo prioriza.

    Args:
        outcome: salida dual devuelta por `validate`.

    Returns:
        dict JSON-serializable con `resultado_ge`, `detalle_rechazos` y
        `resumen`.
    """
    return {
        "resultado_ge": outcome.resultado_ge.to_json_dict(),
        "detalle_rechazos": [
            {
                "indice_registro": _valor_json_seguro(detalle.indice_registro),
                "campo": detalle.campo,
                "regla": detalle.regla,
                "valor_observado": _valor_json_seguro(detalle.valor_observado),
            }
            for detalle in outcome.detalle_rechazos
        ],
        "resumen": {
            "total_registros": len(outcome.df_validos) + len(outcome.df_rechazados),
            "registros_validos": len(outcome.df_validos),
            "registros_rechazados": len(outcome.df_rechazados),
        },
    }


# --- CLI fino por archivos (D-1, D-2, D-3, change n8n-orchestration-workflows) ---
# n8n invoca este modulo SOLO por CLI (DD-05); el `main()` solo lee el
# artefacto pickle que dejo la ingesta, invoca `validate`/`generar_reporte`
# (logica intacta) y serializa la salida dual a archivos + manifest.json.
# Patron identico a `pipeline/ingestion.py` (`main()` fino, lógica testeada
# afuera).


def _actualizar_manifest(directorio: Path, datos: dict) -> None:
    """Crea/actualiza `manifest.json` en `directorio` (D-3): acumulativo --
    cada etapa agrega su propio bloque sin pisar lo que dejaron las
    anteriores. Duplicado deliberadamente por modulo (mismo patron que
    `_commit_git_actual` en `persistence.py`/`analysis.py`) para no acoplar
    los CLIs entre si."""
    ruta_manifest = directorio / "manifest.json"
    manifest: dict = {}
    if ruta_manifest.exists():
        with ruta_manifest.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    manifest.update(datos)
    with ruta_manifest.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.validation",
        description=(
            "Valida el artefacto pickle producido por la ingesta contra el "
            "diccionario de variables y escribe la salida dual "
            "validos/rechazados a archivos (RN-VAL-08). Entrypoint interno "
            "para que n8n invoque el modulo (DD-05/DD-09); no es una "
            "interfaz para usuarios humanos."
        ),
    )
    parser.add_argument(
        "artefacto_entrada", help="Ruta al artefacto pickle (DataFrame crudo) de la ingesta"
    )
    parser.add_argument(
        "--dictionary-path",
        default=None,
        help="Ruta al diccionario de variables (default: config/data_dictionary.json)",
    )
    parser.add_argument(
        "--clave-primaria",
        default=None,
        help="Columna de unicidad; si se omite, se infiere (ver construir_suite)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directorio de la corrida donde escribir los artefactos y el manifest.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI fino sobre `validate`/`generar_reporte` (DD-05/DD-09).

    Exit codes (D-4): `0` exito (incluye rechazos parciales, RN-GLB-01: la
    corrida no fallo, solo particiono datos); `1` error de dominio (el
    diccionario esta mal formado, o una regla cruzada declara un operador no
    soportado -- `ValidationEngineError`); `2` fallo transitorio de
    infraestructura (el artefacto de entrada o el diccionario son
    ilegibles -- nunca se reintenta un error de datos, RN-GLB-03).
    """
    args = _parse_args(argv)

    try:
        df = pd.read_pickle(args.artefacto_entrada)
    except (OSError, pickle.UnpicklingError, EOFError, ValueError) as exc:
        print(
            json.dumps(
                {"error": f"No se pudo leer el artefacto de entrada: {exc}"}, ensure_ascii=False
            ),
            file=sys.stderr,
        )
        return 2

    dictionary_path = args.dictionary_path or _DEFAULT_DICT_PATH
    try:
        diccionario = load_data_dictionary(dictionary_path)
    except OSError as exc:
        print(
            json.dumps({"error": f"Fallo de infraestructura: {exc}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    except DataDictionaryError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    try:
        outcome = validate(df, diccionario, clave_primaria=args.clave_primaria)
    except ValidationEngineError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        outcome.df_validos.to_pickle(output_dir / "validos.pkl")
        outcome.df_rechazados.to_pickle(output_dir / "rechazados.pkl")
        outcome.df_rechazados.to_csv(output_dir / "rechazados.csv", index=True)
        reporte = generar_reporte(outcome)
        with (output_dir / "reporte_validacion.json").open("w", encoding="utf-8") as fh:
            json.dump(reporte, fh, ensure_ascii=False, indent=2)
        _actualizar_manifest(
            output_dir,
            {
                "registros_validos": len(outcome.df_validos),
                "registros_rechazados": len(outcome.df_rechazados),
            },
        )
    except OSError as exc:
        print(
            json.dumps(
                {"error": f"No se pudieron escribir los artefactos de salida: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        f"Validacion completada: {len(outcome.df_validos)} validos, "
        f"{len(outcome.df_rechazados)} rechazados"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
