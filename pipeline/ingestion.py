"""Modulo de ingesta de datos crudos (CSV/Excel) — change `ingestion-module` (C-03).

Es el primer eslabon del pipeline (Flujo 1, pasos 1-2): lee un archivo fuente
crudo, verifica que sea legible (RN-ING-02) y que su estructura coincida con
el diccionario de variables (RN-ING-03, C-02), y devuelve un DataFrame de
pandas **crudo** — sin renombrar ni transformar columnas (eso es C-05).

Ante cualquier problema de codificacion, formato o estructura, la ingesta
**detiene** el proceso levantando una excepcion de la jerarquia
`IngestionError`, que transporta un informe estructurado con archivo,
fecha/hora y descripcion (RN-ING-04).

NO valida los *valores* de cada registro (tipo/rango/lista/completitud/
cruzada) — eso es C-04 (`great_expectations`). NO normaliza los nombres de
columna del DataFrame devuelto ni estandariza categoricos/unidades — eso es
C-05 (RN-TRA-03/04/05); la normalizacion de nombres en este modulo es
**solo** para comparar contra el diccionario, nunca se aplica al DataFrame
devuelto (design.md, Decision 1).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Union

import pandas as pd

from pipeline.data_dictionary import DataDictionary, load_data_dictionary

_DEFAULT_DICT_PATH = Path(__file__).resolve().parent.parent / "config" / "data_dictionary.json"

_EXTENSIONES_CSV = {".csv"}
_EXTENSIONES_EXCEL = {".xlsx", ".xls"}
_EXTENSIONES_SOPORTADAS = _EXTENSIONES_CSV | _EXTENSIONES_EXCEL

_SEPARADORES_RE = re.compile(r"[\s\-_]+")


@dataclass(frozen=True)
class InformeIngesta:
    """Informe estructurado que exige RN-ING-04 ante cualquier error de ingesta.

    Transporta exactamente los tres datos requeridos: el archivo de origen,
    la fecha/hora de la deteccion (ISO-8601) y una descripcion legible del
    problema.
    """

    archivo: str
    fecha_hora: str
    descripcion: str

    def to_dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "fecha_hora": self.fecha_hora,
            "descripcion": self.descripcion,
        }


class IngestionError(Exception):
    """Base de todos los errores de dominio de la ingesta. Transporta un
    `InformeIngesta` (RN-ING-04) — archivo, fecha/hora y descripcion."""

    def __init__(self, informe: InformeIngesta) -> None:
        self.informe = informe
        super().__init__(informe.descripcion)


class EncodingError(IngestionError):
    """El archivo no pudo decodificarse con el `encoding` esperado (RN-ING-02)."""


class FormatError(IngestionError):
    """El archivo esta corrupto, tiene un formato no soportado, o no existe
    (RN-ING-02)."""


class StructureError(IngestionError):
    """La estructura del archivo (columnas) no corresponde al diccionario de
    variables, mas alla de la tolerancia configurada (RN-ING-03)."""


def _crear_informe(archivo: Union[str, Path], descripcion: str) -> InformeIngesta:
    return InformeIngesta(
        archivo=str(archivo),
        fecha_hora=datetime.now().isoformat(),
        descripcion=descripcion,
    )


def _normalizar_nombre(nombre: str) -> str:
    """Normaliza un nombre de columna a una forma canonica para compararlo de
    forma tolerante a capitalizacion y espaciado (RN-ING-03, design.md
    Decision 2): `strip` + `lower` + colapso de toda corrida de separadores
    (espacios, tabs, `-`, `_`) a un unico `_`.

    Determinista, NO fuzzy: `variable_respuesta_1` y `variable_respuesta_2`
    normalizan a formas distintas (no colisionan).
    """
    limpio = nombre.strip().lower()
    return _SEPARADORES_RE.sub("_", limpio)


def _leer_archivo(source_path: Path, encoding: str) -> pd.DataFrame:
    """Lee `source_path` despachando por extension (RN-ING-01) y traduce los
    fallos de los lectores de pandas a la jerarquia `IngestionError`
    (RN-ING-02, design.md Decision 3): intenta leer y captura el fallo,
    reportando antes de continuar en vez de adivinar el problema.
    """
    extension = source_path.suffix.lower()

    if extension not in _EXTENSIONES_SOPORTADAS:
        raise FormatError(
            _crear_informe(
                source_path,
                f"Extension '{extension or '(sin extension)'}' no soportada; "
                "se esperaba .csv, .xlsx o .xls",
            )
        )

    if not source_path.exists():
        raise FormatError(
            _crear_informe(source_path, f"El archivo '{source_path}' no existe")
        )

    try:
        if extension in _EXTENSIONES_CSV:
            return pd.read_csv(source_path, encoding=encoding)
        return pd.read_excel(source_path)
    except UnicodeDecodeError as exc:
        raise EncodingError(
            _crear_informe(
                source_path,
                f"No se pudo decodificar el archivo con encoding '{encoding}': {exc}",
            )
        ) from exc
    except (pd.errors.ParserError, ValueError, OSError) as exc:
        raise FormatError(
            _crear_informe(
                source_path, f"El archivo no pudo ser leido o parseado: {exc}"
            )
        ) from exc


def _validar_estructura(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    tolerancia: bool,
    archivo: Path,
) -> None:
    """Valida que las columnas de `df` correspondan 1:1 a los
    `nombre_canonico` de `diccionario` (RN-ING-03). En modo tolerante
    (default) compara sobre la forma normalizada de ambos lados
    (`_normalizar_nombre`); en modo estricto exige coincidencia exacta.

    Ante cualquier discrepancia levanta `StructureError` (RN-ING-04) con una
    descripcion que enumera concretamente que columnas faltan y cuales
    sobran.
    """
    nombres_esperados = {variable.nombre_canonico for variable in diccionario}
    columnas_archivo = list(df.columns)

    clave = _normalizar_nombre if tolerancia else (lambda nombre: nombre)

    normalizados_esperados = {clave(nombre): nombre for nombre in nombres_esperados}
    normalizados_archivo = {clave(str(col)): col for col in columnas_archivo}

    claves_faltantes = set(normalizados_esperados) - set(normalizados_archivo)
    claves_sobrantes = set(normalizados_archivo) - set(normalizados_esperados)

    if not claves_faltantes and not claves_sobrantes:
        return

    faltantes = sorted(normalizados_esperados[clave_] for clave_ in claves_faltantes)
    sobrantes = sorted(str(normalizados_archivo[clave_]) for clave_ in claves_sobrantes)

    partes = []
    if faltantes:
        partes.append(f"faltan columnas {faltantes}")
    if sobrantes:
        partes.append(f"sobran columnas {sobrantes}")

    descripcion = (
        "La estructura del archivo no coincide con el diccionario de variables: "
        + "; ".join(partes)
    )
    raise StructureError(_crear_informe(archivo, descripcion))


def ingest(
    source_path: Union[str, Path],
    dictionary_path: Union[str, Path, None] = None,
    tolerancia: bool = True,
    encoding: str = "utf-8",
) -> pd.DataFrame:
    """Lee un archivo fuente (CSV/Excel) y devuelve un DataFrame crudo.

    Despacha la lectura por extension de archivo (RN-ING-01: `.csv` ->
    `pandas.read_csv`, `.xlsx`/`.xls` -> `pandas.read_excel`), detecta
    problemas de codificacion/formato antes de continuar (RN-ING-02), y
    valida la estructura (numero de columnas y nombres) contra los
    `nombre_canonico` del diccionario de variables, con tolerancia
    configurable de capitalizacion/espaciado (RN-ING-03).

    El DataFrame devuelto preserva los nombres de columna originales del
    archivo — la normalizacion de nombres es solo para la comparacion
    estructural, nunca se aplica al resultado (design.md, Decision 1).

    Args:
        source_path: ruta al archivo fuente a ingerir (`.csv`, `.xlsx` o `.xls`).
        dictionary_path: ruta al diccionario de variables (C-02) contra el
            que se valida la estructura. Default: `config/data_dictionary.json`.
        tolerancia: si `True` (default), tolera diferencias de capitalizacion
            y espaciado al comparar nombres de columna; si `False`, exige
            coincidencia exacta con los `nombre_canonico`.
        encoding: encoding esperado del archivo (solo aplica a CSV). Default `utf-8`.

    Returns:
        DataFrame de pandas con los datos crudos leidos, columnas sin renombrar.

    Raises:
        EncodingError: el archivo no pudo decodificarse con `encoding` (RN-ING-02).
        FormatError: el archivo esta corrupto, tiene extension no soportada,
            o no existe (RN-ING-02).
        StructureError: las columnas del archivo no corresponden al
            diccionario, mas alla de la tolerancia configurada (RN-ING-03/04).
    """
    ruta = Path(source_path)
    df = _leer_archivo(ruta, encoding)

    ruta_diccionario = Path(dictionary_path) if dictionary_path is not None else _DEFAULT_DICT_PATH
    diccionario = load_data_dictionary(ruta_diccionario)

    _validar_estructura(df, diccionario, tolerancia, ruta)

    return df


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.ingestion",
        description=(
            "Ingesta un archivo fuente crudo (CSV/Excel) del pipeline. "
            "Entrypoint interno para que n8n invoque el modulo (DD-05/DD-09); "
            "no es una interfaz para usuarios humanos."
        ),
    )
    parser.add_argument("ruta", help="Ruta al archivo fuente a ingerir (.csv, .xlsx, .xls)")
    parser.add_argument(
        "--tolerancia-estricta",
        action="store_true",
        help="Exige coincidencia exacta de nombres de columna (default: tolerante)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding esperado del archivo CSV (default: utf-8)",
    )
    parser.add_argument(
        "--dictionary-path",
        default=None,
        help="Ruta al diccionario de variables (default: config/data_dictionary.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Ruta del artefacto pickle donde persistir el DataFrame ingerido "
            "para la etapa siguiente (D-2/D-3, change n8n-orchestration-workflows). "
            "Si se omite, el DataFrame se descarta (comportamiento previo)."
        ),
    )
    return parser.parse_args(argv)


def _actualizar_manifest(directorio: Path, datos: dict) -> None:
    """Crea/actualiza `manifest.json` en `directorio` (D-3, contrato de
    corrida): unico lugar donde viven la ruta original y los conteos que
    necesitan las etapas siguientes (n8n solo transporta rutas y exit codes).

    Duplicado deliberadamente en cada CLI del pipeline (mismo patron que
    `_commit_git_actual` en `persistence.py`/`analysis.py`, Decision 3 de
    `transformation.py`): evita acoplar los modulos entre si por un helper
    compartido."""
    ruta_manifest = directorio / "manifest.json"
    manifest: dict = {}
    if ruta_manifest.exists():
        with ruta_manifest.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    manifest.update(datos)
    with ruta_manifest.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI fino sobre `ingest` (DD-05, refinado por DD-09).

    La logica de ingesta vive en `ingest` (testeable directamente); este
    entrypoint solo parsea argumentos, invoca `ingest`, y ante
    `IngestionError` serializa el informe (JSON) a stderr devolviendo un
    codigo de salida no-cero. En exito, reporta un resumen (filas/columnas)
    y retorna 0.
    """
    args = _parse_args(argv)

    try:
        df = ingest(
            args.ruta,
            dictionary_path=args.dictionary_path,
            tolerancia=not args.tolerancia_estricta,
            encoding=args.encoding,
        )
    except IngestionError as exc:
        # Error de dominio/datos (RN-ING-04, D-4 change n8n-orchestration-workflows):
        # deterministico, n8n NO debe reintentarlo -- exit 1.
        print(json.dumps(exc.informe.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except OSError as exc:
        # Fallo transitorio de infraestructura (D-4): p. ej. el diccionario de
        # variables (`--dictionary-path`) es inaccesible. Nunca envuelto en
        # `IngestionError` -- n8n SI debe reintentarlo (RN-GLB-03) -- exit 2.
        print(
            json.dumps({"error": f"Fallo de infraestructura: {exc}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    if args.output:
        try:
            ruta_output = Path(args.output)
            ruta_output.parent.mkdir(parents=True, exist_ok=True)
            df.to_pickle(ruta_output)
            _actualizar_manifest(
                ruta_output.parent,
                {"ruta_archivo_entrada": str(args.ruta), "registros_leidos": len(df)},
            )
        except OSError as exc:
            print(
                json.dumps(
                    {"error": f"No se pudo escribir el artefacto de salida: {exc}"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2

    print(f"Ingesta exitosa: {len(df)} filas, {len(df.columns)} columnas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
