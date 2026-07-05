"""Construccion de `config/data_dictionary.json` + `config/analysis_config.yaml`
desde `respuestas_acumuladas` de una sesion `setup_ensayo` -- change
`telegram-interaction-layer` (C-13), Decision 4 del design, grupo 4 del
tasks.md.

La secuencia de pasos de `setup_ensayo` (sembrada por `pipeline.session_seed`,
RN-SES-03/DD-10) acumula, en `respuestas_acumuladas`, tres respuestas de
texto libre (paso "0": codigo del ensayo; paso "1": lista de variables del
diccionario como JSON; paso "2": diseno experimental + formula del modelo
como JSON). Este modulo NO decide el contenido (eso sigue siendo juicio
experto del Ingeniero, KB 13 §6) -- solo lo ENSAMBLA y lo escribe.

Escritura atomica (temp + rename, D-4): el diccionario se meta-valida
(`pipeline.data_dictionary.load_data_dictionary`) ANTES de reemplazar el
archivo destino; si la validacion falla, NINGUN archivo destino se toca y la
sesion NO se marca `completada` (revierte a `abierta` para permitir
corregir la ultima respuesta -- `pipeline.session_engine.avanzar`, C-12,
ya transiciono la sesion a `completada` al responder el ultimo paso porque
valida solo la FORMA minima de cada respuesta individual, no el ensamblado
completo; `finalizar_setup` es el punto de la arquitectura donde se decide
la completitud REAL de un `setup_ensayo`, sin tocar el contrato de C-12).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import yaml
from sqlalchemy.orm import Session

from pipeline.analysis import ConfigAnalisis
from pipeline.data_dictionary import DataDictionaryError, load_data_dictionary
from pipeline.models import Sesion

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DICTIONARY_PATH = _REPO_ROOT / "config" / "data_dictionary.json"
DEFAULT_ANALYSIS_CONFIG_PATH = _REPO_ROOT / "config" / "analysis_config.yaml"

_PASO_CODIGO_ENSAYO = "0"
_PASO_VARIABLES = "1"
_PASO_ANALISIS = "2"


class SetupEnsayoError(Exception):
    """Base de los errores propios de la construccion de configs de setup_ensayo."""


class RespuestasIncompletasError(SetupEnsayoError):
    """`respuestas_acumuladas` no tiene los tres pasos esperados de `setup_ensayo`."""


class RespuestasMalFormadasError(SetupEnsayoError):
    """El contenido de un paso no es el JSON/forma esperada (paso 1 o 2)."""


@dataclass(frozen=True)
class ResultadoFinalizarSetup:
    """Resultado de `finalizar_setup`.

    Attributes:
        ok: si ambos archivos de config se escribieron y la sesion quedo
            `completada`.
        error: motivo de fallo (solo si `not ok`).
        data_dictionary_path/analysis_config_path: rutas escritas (solo si `ok`).
    """

    ok: bool
    error: Optional[str] = None
    data_dictionary_path: Optional[Path] = None
    analysis_config_path: Optional[Path] = None


def _parsear_variables(respuestas: dict) -> list:
    crudo = respuestas.get(_PASO_VARIABLES)
    if crudo is None:
        raise RespuestasIncompletasError(
            f"Falta el paso '{_PASO_VARIABLES}' (variables del diccionario) en respuestas_acumuladas."
        )
    try:
        variables = json.loads(crudo) if isinstance(crudo, str) else crudo
    except json.JSONDecodeError as exc:
        raise RespuestasMalFormadasError(
            f"El paso '{_PASO_VARIABLES}' no es JSON valido: {exc}"
        ) from exc
    if not isinstance(variables, list):
        raise RespuestasMalFormadasError(
            f"El paso '{_PASO_VARIABLES}' debe ser una lista de definiciones de variable."
        )
    return variables


def _parsear_analisis(respuestas: dict) -> dict:
    crudo = respuestas.get(_PASO_ANALISIS)
    if crudo is None:
        raise RespuestasIncompletasError(
            f"Falta el paso '{_PASO_ANALISIS}' (diseno experimental/formula) en respuestas_acumuladas."
        )
    try:
        analisis = json.loads(crudo) if isinstance(crudo, str) else crudo
    except json.JSONDecodeError as exc:
        raise RespuestasMalFormadasError(
            f"El paso '{_PASO_ANALISIS}' no es JSON valido: {exc}"
        ) from exc
    if not isinstance(analisis, dict) or "formula" not in analisis:
        raise RespuestasMalFormadasError(
            f"El paso '{_PASO_ANALISIS}' debe ser un objeto JSON con al menos 'formula'."
        )
    return analisis


def construir_contenido_desde_respuestas(respuestas_acumuladas: dict) -> tuple[dict, ConfigAnalisis]:
    """Ensambla el contenido de `data_dictionary.json` y el `ConfigAnalisis`
    (para `analysis_config.yaml`) a partir de `respuestas_acumuladas` de una
    sesion `setup_ensayo` completa.

    Levanta `RespuestasIncompletasError`/`RespuestasMalFormadasError` si
    falta algun paso o su contenido no tiene la forma esperada -- NUNCA
    devuelve una estructura a medio construir.
    """
    if _PASO_CODIGO_ENSAYO not in respuestas_acumuladas:
        raise RespuestasIncompletasError(
            f"Falta el paso '{_PASO_CODIGO_ENSAYO}' (codigo del ensayo) en respuestas_acumuladas."
        )

    variables = _parsear_variables(respuestas_acumuladas)
    analisis = _parsear_analisis(respuestas_acumuladas)

    contenido_diccionario = {"variables": variables, "reglas_cruzadas": []}

    config_analisis = ConfigAnalisis(
        dataset_id=None,
        formula=analisis["formula"],
        tipo=analisis.get("tipo", "anova"),
        alpha=float(analisis.get("alpha", 0.05)),
        metodo_comparacion=analisis.get("metodo_comparacion", "tukey"),
        factor=analisis.get("factor"),
        commit_git=None,
        ejecucion_id=None,
        directorio_salida=analisis.get("directorio_salida", "analisis"),
    )
    return contenido_diccionario, config_analisis


def _escribir_temp_en_mismo_directorio(destino: Path, sufijo: str) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, ruta_temp = tempfile.mkstemp(dir=destino.parent, suffix=sufijo)
    os.close(fd)
    return Path(ruta_temp)


def finalizar_setup(
    session: Session,
    sesion_id: int,
    ahora: datetime,
    dictionary_path: Optional[Union[str, Path]] = None,
    analysis_config_path: Optional[Union[str, Path]] = None,
) -> ResultadoFinalizarSetup:
    """Construye y escribe atomicamente los config files de una sesion
    `setup_ensayo` completa (D-4).

    Escritura atomica: ambos archivos se escriben primero en temporales del
    MISMO directorio (rename atomico en el mismo filesystem) y el
    diccionario se meta-valida (`load_data_dictionary`) ANTES de reemplazar
    ningun destino. Si la sesion no es `setup_ensayo`, no esta `completada`,
    o el contenido ensamblado es invalido, NINGUN archivo destino se toca y
    la sesion se revierte a `abierta` (si estaba `completada`) para permitir
    corregir la respuesta -- `session_engine.avanzar` (C-12, contrato
    intacto) ya la habia marcado `completada` al responder el ultimo paso,
    validando solo la forma minima de esa respuesta, no el ensamblado
    completo de las tres respuestas de `setup_ensayo`.
    """
    ruta_diccionario = Path(dictionary_path) if dictionary_path is not None else DEFAULT_DATA_DICTIONARY_PATH
    ruta_analisis = Path(analysis_config_path) if analysis_config_path is not None else DEFAULT_ANALYSIS_CONFIG_PATH

    sesion = session.get(Sesion, sesion_id)
    if sesion is None:
        return ResultadoFinalizarSetup(ok=False, error=f"No existe la sesion {sesion_id}.")
    if sesion.tipo_sesion != "setup_ensayo":
        return ResultadoFinalizarSetup(
            ok=False, error=f"La sesion {sesion_id} no es de tipo 'setup_ensayo'."
        )
    if sesion.estado != "completada":
        return ResultadoFinalizarSetup(
            ok=False, error=f"La sesion {sesion_id} todavia no esta 'completada'."
        )

    def _revertir_y_fallar(motivo: str) -> ResultadoFinalizarSetup:
        sesion.estado = "abierta"
        sesion.updated_at = ahora
        session.commit()
        return ResultadoFinalizarSetup(ok=False, error=motivo)

    try:
        contenido_diccionario, config_analisis = construir_contenido_desde_respuestas(
            sesion.respuestas_acumuladas
        )
    except SetupEnsayoError as exc:
        return _revertir_y_fallar(str(exc))

    temp_diccionario = _escribir_temp_en_mismo_directorio(ruta_diccionario, ".data_dictionary.tmp")
    try:
        with temp_diccionario.open("w", encoding="utf-8") as fh:
            json.dump(contenido_diccionario, fh, ensure_ascii=False, indent=2)

        try:
            load_data_dictionary(temp_diccionario)
        except DataDictionaryError as exc:
            return _revertir_y_fallar(f"El diccionario ensamblado es invalido: {exc}")

        temp_analisis = _escribir_temp_en_mismo_directorio(ruta_analisis, ".analysis_config.tmp")
        try:
            with temp_analisis.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(config_analisis.to_dict(), fh, allow_unicode=True, sort_keys=False)

            # Ambas validaciones ya pasaron -- recien aqui se tocan los
            # destinos reales, y con rename atomico (mismo filesystem).
            os.replace(temp_diccionario, ruta_diccionario)
            os.replace(temp_analisis, ruta_analisis)
        finally:
            temp_analisis.unlink(missing_ok=True)
    finally:
        temp_diccionario.unlink(missing_ok=True)

    return ResultadoFinalizarSetup(
        ok=True, data_dictionary_path=ruta_diccionario, analysis_config_path=ruta_analisis
    )
