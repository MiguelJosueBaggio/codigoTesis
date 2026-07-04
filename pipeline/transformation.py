"""Modulo de transformacion y estandarizacion de datos (change transformation-module / C-05).

Quinto eslabon del Flujo 1 (paso 5), entre la validacion (C-04) y la
persistencia (C-06): recibe el `DataFrame` de registros **validos** que
produce C-04 (`ValidationOutcome.df_validos`) junto con el diccionario de
variables tipado por C-02, y entrega el dataset en formato tidy — nombres de
columna canonicos (RN-TRA-03), categoricos estandarizados (RN-TRA-04) y
unidades homogeneas (RN-TRA-05) — mas una bitacora atomica de cada operacion
aplicada (RN-TRA-02).

RN-TRA-01: el modulo NO re-valida ni juzga la validez de los datos; asume que
su entrada ya supero la validacion. Preserva la cardinalidad de filas de su
entrada — no descarta ni agrega registros.

Matiz DD-04 (Context, design.md del change): DD-04 gobierna las *reglas de
validacion* (decidir que dato es invalido) y exige que se expresen como
expectations declarativas de `great_expectations`, nunca como `if`/`else`
imperativos. La transformacion **no valida**: reencuadra datos ya declarados
validos. Renombrar columnas, mapear variantes categoricas y convertir
unidades son manipulaciones imperativas legitimas de `pandas` — no son la
clase de logica que DD-04 prohibe. Lo que mantiene esta transformacion
auditable no es "declaratividad de reglas" sino la **bitacora atomica** de
RN-TRA-02. Este modulo NO importa ni usa `great_expectations`.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from pipeline.data_dictionary import DataDictionary, DataDictionaryError, load_data_dictionary

_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "config" / "data_dictionary.json"

# Misma norma determinista (no fuzzy) que usa la ingesta (C-03,
# `pipeline.ingestion._normalizar_nombre`) para comparar nombres de columna
# tolerando capitalizacion/espaciado/separadores. Se define de forma
# AUTONOMA (no se importa el simbolo privado de `ingestion.py`) para no
# acoplar los dos modulos entre si (Decision 3, design.md): si a futuro la
# norma diverge entre ingesta y transformacion, el refactor correcto es
# promoverla a un helper compartido (p. ej. `pipeline/_texto.py`), no
# duplicar divergencias. Para v1 se difiere ese refactor hasta que haya
# evidencia de que diverge.
_SEPARADORES_RE = re.compile(r"[\s\-_]+")

# Cantidad maxima de valores distintos que guarda la "muestra antes/despues"
# de una operacion en la bitacora (Decision 4): RN-TRA-02 pide una muestra,
# no el diff completo, para que la bitacora quede acotada y persistible por
# C-06 sin explotar en volumen.
_TAMANO_MUESTRA = 5

# Tipos de operacion de la bitacora (RN-TRA-02, Decision 4): constantes para
# evitar duplicar literales entre la secuencia de operaciones y sus tests.
TIPO_NORMALIZACION_NOMBRE = "normalizacion_nombre"
TIPO_ESTANDARIZACION_CATEGORICA = "estandarizacion_categorica"
TIPO_CONVERSION_UNIDAD = "conversion_unidad"


def _normalizar_nombre(nombre: str) -> str:
    """Normaliza un nombre de columna a una forma canonica para compararlo de
    forma tolerante a capitalizacion y espaciado (RN-TRA-03, Decision 3):
    `strip` + `lower` + colapso de toda corrida de separadores (espacios,
    tabs, `-`, `_`) a un unico `_`.

    Determinista, NO fuzzy: `variable_respuesta_1` y `variable_respuesta_2`
    normalizan a formas distintas (no colisionan).
    """
    limpio = nombre.strip().lower()
    return _SEPARADORES_RE.sub("_", limpio)


def _valor_json_seguro(valor: Any) -> Any:
    """Convierte un valor (escalares numpy/pandas, Timestamp, NaN) a su
    equivalente JSON-serializable, para que la muestra antes/despues de la
    bitacora sea `json.dumps`-able tal cual (RN-TRA-02)."""
    if valor is None or (not isinstance(valor, (list, tuple)) and pd.isna(valor)):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if hasattr(valor, "item"):  # escalares numpy (int64, float64, bool_)
        return valor.item()
    return valor


@dataclass(frozen=True)
class ConversionUnidad:
    """Conversion lineal de unidad de origen a la unidad canonica del
    diccionario (RN-TRA-05, Decision 2): `canonico = origen * factor + offset`.

    Lineal cubre las conversiones agronomicas usuales (kg/ha<->t/ha, cm<->m,
    y con `offset` tambien °F<->°C). Una relacion no lineal es un escape
    documentado (callable / operacion atomica ad-hoc) que se difiere hasta
    tener evidencia de necesidad (YAGNI, Riesgos del design).
    """

    unidad_origen: str
    factor: float
    offset: float = 0.0


@dataclass(frozen=True)
class TransformationRules:
    """Configuracion declarativa de transformacion que el contrato de C-02
    no contiene (Decision 2, Checkpoint RESUELTO 2026-07-03): el diccionario
    dice *cual* es la forma/unidad canonica, no *desde que* variantes/unidades
    hay que llevar el dato. Esa informacion se pasa aca, no se agrega al
    meta-schema de C-02.

    Attributes:
        correspondencias: por columna canonica, un mapa `variante ->
            forma_canonica` (RN-TRA-04). Toda forma canonica destino debe
            pertenecer a `valores_admisibles` de esa variable en el
            diccionario (el diccionario sigue siendo la fuente de verdad de
            lo canonico); este modulo no re-valida eso (RN-TRA-01) — un
            destino fuera de catalogo lo detecta la validacion (C-04) en su
            propia corrida, no la transformacion.
        conversiones: por columna canonica, una `ConversionUnidad` (RN-TRA-05).
    """

    correspondencias: Dict[str, Dict[str, str]] = field(default_factory=dict)
    conversiones: Dict[str, ConversionUnidad] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, datos: dict) -> "TransformationRules":
        """Construye `TransformationRules` desde un dict plano (la forma que
        produce `json.load` sobre un `--rules` de la CLI, D-1 change
        n8n-orchestration-workflows). Loader aditivo -- no cambia la forma en
        que `transform` consume las reglas."""
        correspondencias = dict(datos.get("correspondencias", {}))
        conversiones = {
            columna: ConversionUnidad(
                unidad_origen=valores["unidad_origen"],
                factor=valores["factor"],
                offset=valores.get("offset", 0.0),
            )
            for columna, valores in datos.get("conversiones", {}).items()
        }
        return cls(correspondencias=correspondencias, conversiones=conversiones)

    @classmethod
    def from_json(cls, ruta: Union[str, Path]) -> "TransformationRules":
        """Lee el mismo contrato de `from_dict` desde un archivo `.json` en disco."""
        with Path(ruta).open(encoding="utf-8") as fh:
            datos = json.load(fh)
        return cls.from_dict(datos)


@dataclass(frozen=True)
class OperacionTransformacion:
    """Una entrada atomica de la bitacora de transformaciones (RN-TRA-02,
    Decision 4): documenta que operacion se aplico, sobre que columna,
    cuantos registros afecto, y una muestra acotada del valor antes/despues.

    Solo se emite cuando la operacion afecta efectivamente >=1 registro/
    columna: una operacion sin efecto (columna ya canonica, categorico ya
    estandar) no ensucia la bitacora con ruido.
    """

    tipo: str
    columna: str
    registros_afectados: int
    muestra_antes: List[Any]
    muestra_despues: List[Any]

    def to_dict(self) -> dict:
        """Representacion JSON-serializable de la operacion, para que C-06 la
        persista tal cual en la cadena de auditoria (RN-AUD-02)."""
        return {
            "tipo": self.tipo,
            "columna": self.columna,
            "registros_afectados": self.registros_afectados,
            "muestra_antes": [_valor_json_seguro(v) for v in self.muestra_antes],
            "muestra_despues": [_valor_json_seguro(v) for v in self.muestra_despues],
        }


@dataclass(frozen=True)
class TransformationOutcome:
    """Salida de `transform` (RN-TRA-02, Decision 1): el dataset transformado
    y tidy, mas la bitacora atomica de las operaciones aplicadas.

    Attributes:
        df_tidy: el dataset transformado, tidy, con nombres/valores/unidades
            canonicos.
        operaciones: la bitacora atomica (RN-TRA-02); una entrada por
            operacion que afecto >=1 registro/columna.
    """

    df_tidy: pd.DataFrame
    operaciones: List[OperacionTransformacion] = field(default_factory=list)


def _normalizar_nombres_columna(
    df: pd.DataFrame, diccionario: DataDictionary
) -> "tuple[pd.DataFrame, List[OperacionTransformacion]]":
    """Mapea cada columna cruda a su `nombre_canonico` del diccionario
    (RN-TRA-03), tolerando capitalizacion/espaciado/separadores. Solo emite
    una `OperacionTransformacion` por cada columna efectivamente renombrada
    (columna ya canonica -> sin entrada de bitacora)."""
    canonicos_por_normalizado = {
        _normalizar_nombre(variable.nombre_canonico): variable.nombre_canonico
        for variable in diccionario
    }

    renombres: Dict[str, str] = {}
    for columna in df.columns:
        canonico = canonicos_por_normalizado.get(_normalizar_nombre(str(columna)))
        if canonico is not None and canonico != columna:
            renombres[columna] = canonico

    operaciones = [
        OperacionTransformacion(
            tipo=TIPO_NORMALIZACION_NOMBRE,
            columna=canonico,
            registros_afectados=len(df),
            muestra_antes=[original],
            muestra_despues=[canonico],
        )
        for original, canonico in renombres.items()
    ]

    return df.rename(columns=renombres), operaciones


def _es_nan(valor: Any) -> bool:
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):
        return False


def _muestra(valores: List[Any]) -> List[Any]:
    """Muestra acotada de valores distintos, preservando el orden de aparicion
    (Decision 4): primeros `_TAMANO_MUESTRA` valores distintos y no-nulos —
    RN-TRA-02 pide una muestra representativa, no el diff completo."""
    vistos: List[Any] = []
    for valor in valores:
        if _es_nan(valor):
            continue
        if not any(v == valor for v in vistos):
            vistos.append(valor)
        if len(vistos) >= _TAMANO_MUESTRA:
            break
    return vistos


def _estandarizar_categoricos(
    df: pd.DataFrame, reglas: TransformationRules
) -> "tuple[pd.DataFrame, List[OperacionTransformacion]]":
    """Aplica la tabla de correspondencias (`reglas.correspondencias`) por
    columna canonica, llevando cada variante a su forma canonica (RN-TRA-04).
    Una columna sin variantes presentes (ya canonica) no genera entrada de
    bitacora (0 registros afectados)."""
    df_resultado = df.copy()
    operaciones: List[OperacionTransformacion] = []

    for columna, correspondencias in reglas.correspondencias.items():
        if columna not in df_resultado.columns:
            continue

        serie = df_resultado[columna]
        mascara = serie.isin(correspondencias.keys())
        registros_afectados = int(mascara.sum())
        if registros_afectados == 0:
            continue

        antes = _muestra(serie[mascara].tolist())
        df_resultado.loc[mascara, columna] = serie[mascara].map(correspondencias)
        despues = _muestra(df_resultado.loc[mascara, columna].tolist())

        operaciones.append(
            OperacionTransformacion(
                tipo=TIPO_ESTANDARIZACION_CATEGORICA,
                columna=columna,
                registros_afectados=registros_afectados,
                muestra_antes=antes,
                muestra_despues=despues,
            )
        )

    return df_resultado, operaciones


def _convertir_unidades(
    df: pd.DataFrame, reglas: TransformationRules
) -> "tuple[pd.DataFrame, List[OperacionTransformacion]]":
    """Aplica la conversion lineal declarada (`reglas.conversiones`) por
    columna canonica (RN-TRA-05). Una columna sin conversion declarada (ya en
    unidad canonica) no se altera ni genera entrada de bitacora."""
    df_resultado = df.copy()
    operaciones: List[OperacionTransformacion] = []

    for columna, conversion in reglas.conversiones.items():
        if columna not in df_resultado.columns:
            continue

        serie = df_resultado[columna]
        mascara = serie.notna()
        registros_afectados = int(mascara.sum())
        if registros_afectados == 0:
            continue

        antes = _muestra(serie[mascara].tolist())
        df_resultado.loc[mascara, columna] = serie[mascara] * conversion.factor + conversion.offset
        despues = _muestra(df_resultado.loc[mascara, columna].tolist())

        operaciones.append(
            OperacionTransformacion(
                tipo=TIPO_CONVERSION_UNIDAD,
                columna=columna,
                registros_afectados=registros_afectados,
                muestra_antes=antes,
                muestra_despues=despues,
            )
        )

    return df_resultado, operaciones


def transform(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    reglas: Optional[TransformationRules] = None,
) -> TransformationOutcome:
    """Transforma el dataset de registros validos (C-04) a formato tidy con
    nombres/categoricos/unidades canonicos, y produce la bitacora atomica de
    cada operacion aplicada (RN-TRA-01/02/03/04/05/06).

    Ejecuta una secuencia **fija** de operaciones atomicas — (1) normalizacion
    de nombres, (2) estandarizacion de categoricos, (3) conversion de
    unidades (Decision 4) — determinista para sostener la reproducibilidad
    (RN-GLB-02): misma entrada + mismas `reglas` => mismo `df_tidy` y misma
    bitacora. El orden es necesario porque los pasos 2 y 3 operan sobre los
    nombres de columna ya canonicos que deja el paso 1.

    No descarta, agrega ni reordena filas (preserva la cardinalidad de la
    entrada, RN-TRA-06) y no re-valida los datos (RN-TRA-01).

    Args:
        df: DataFrame de registros ya validados (`ValidationOutcome.df_validos`
            de C-04), con nombres de columna crudos.
        diccionario: contrato de datos tipado (C-02) — dirige la
            normalizacion de nombres (`nombre_canonico`).
        reglas: `TransformationRules` con correspondencias categoricas y
            conversiones de unidad; si se omite, no se aplica ninguna
            (equivalente a "no hay variantes que estandarizar/convertir").

    Returns:
        `TransformationOutcome` con el dataset tidy y la bitacora atomica.
    """
    reglas_efectivas = reglas if reglas is not None else TransformationRules()

    df_actual, operaciones_nombres = _normalizar_nombres_columna(df, diccionario)
    df_actual, operaciones_categoricos = _estandarizar_categoricos(df_actual, reglas_efectivas)
    df_actual, operaciones_unidades = _convertir_unidades(df_actual, reglas_efectivas)

    operaciones = operaciones_nombres + operaciones_categoricos + operaciones_unidades

    return TransformationOutcome(df_tidy=df_actual, operaciones=operaciones)


# --- CLI fino por archivos (D-1/D-2/D-3, change n8n-orchestration-workflows) ---
# n8n invoca este modulo SOLO por CLI (DD-05); el `main()` solo lee el
# artefacto pickle de `validos.pkl` (validation), carga las reglas opcionales
# desde `--rules`, invoca `transform` (logica intacta) y serializa el
# resultado a `tidy.pkl` + `operaciones.json`. Patron identico a
# `pipeline/ingestion.py`.


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.transformation",
        description=(
            "Transforma el artefacto pickle de registros validos (validation) "
            "a formato tidy con nombres/categoricos/unidades canonicos "
            "(RN-TRA-01..06). Entrypoint interno para que n8n invoque el "
            "modulo (DD-05/DD-09); no es una interfaz para usuarios humanos."
        ),
    )
    parser.add_argument(
        "artefacto_entrada", help="Ruta al artefacto pickle (DataFrame) de registros validos"
    )
    parser.add_argument(
        "--dictionary-path",
        default=None,
        help="Ruta al diccionario de variables (default: config/data_dictionary.json)",
    )
    parser.add_argument(
        "--rules",
        default=None,
        help="Ruta a un JSON de TransformationRules (correspondencias/conversiones)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directorio de la corrida donde escribir tidy.pkl y operaciones.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI fino sobre `transform` (DD-05/DD-09).

    Exit codes (D-4): `0` exito; `1` error de dominio/configuracion (el
    diccionario esta mal formado, o el `--rules` no es JSON valido --
    reintentarlo nunca lo arregla); `2` fallo transitorio de infraestructura
    (el artefacto de entrada, el diccionario o las reglas son ilegibles por
    un problema de sistema de archivos).
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

    reglas: Optional[TransformationRules] = None
    if args.rules:
        try:
            reglas = TransformationRules.from_json(args.rules)
        except json.JSONDecodeError as exc:
            print(
                json.dumps({"error": f"JSON de reglas malformado: {exc}"}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 1
        except OSError as exc:
            print(
                json.dumps({"error": f"Fallo de infraestructura: {exc}"}, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2

    outcome = transform(df, diccionario, reglas=reglas)

    output_dir = Path(args.output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        outcome.df_tidy.to_pickle(output_dir / "tidy.pkl")
        with (output_dir / "operaciones.json").open("w", encoding="utf-8") as fh:
            json.dump(
                [operacion.to_dict() for operacion in outcome.operaciones],
                fh,
                ensure_ascii=False,
                indent=2,
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
        f"Transformacion completada: {len(outcome.df_tidy)} filas, "
        f"{len(outcome.operaciones)} operaciones"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
