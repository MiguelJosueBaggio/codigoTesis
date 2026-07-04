"""Implementacion de persistencia y auditoria -- change persistence-audit
-module (C-06).

Reemplaza el stub creado por `foundation-setup` (C-01). `persist()` corre
en UNA transaccion atomica (Decision 5, design.md): crea el registro de
Ejecucion (RN-AUD-01), persiste la bitacora de transformaciones de C-05
(RN-AUD-02) y normaliza `TransformationOutcome.df_tidy` a las entidades de
dominio del ERD via resolucion-por-clave-natural (get-or-create); si
cualquier paso falla, la transaccion completa se revierte sin dejar filas
parciales de esa corrida.

OPEN QUESTION 1 (RESUELTA 2026-07-03, design.md): el mapeo columna->entidad
para v1 usa el contrato del fixture sintetico con jerarquia explicita
(`codigo_ensayo`, `ambiente`, `tratamiento`, `id_unidad`, `variable`,
`valor`); el mapeo del caso de estudio real se difiere hasta desbloquear el
diccionario de variables (`knowledge-base/10_preguntas_abiertas.md`).

Decision 7 del design: este modulo NO construye el `Engine` -- consume una
`Session` ya ligada a uno (`pipeline.db.build_session`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Union

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from pipeline.models import (
    Ambiente,
    BitacoraTransformacion,
    Ejecucion,
    Ensayo,
    Observacion,
    Tratamiento,
    UnidadExperimental,
)
from pipeline.transformation import OperacionTransformacion, TransformationOutcome

# Mapeo columna->entidad para v1 (Decision 5, OPEN QUESTION 1 RESUELTA):
# nombres de columna del fixture sintetico con jerarquia explicita.
COLUMNA_ENSAYO = "codigo_ensayo"
COLUMNA_AMBIENTE = "ambiente"
COLUMNA_TRATAMIENTO = "tratamiento"
COLUMNA_UNIDAD = "id_unidad"
COLUMNA_VARIABLE = "variable"
COLUMNA_VALOR = "valor"

_COLUMNAS_JERARQUIA_V1: Mapping[str, str] = {
    "ensayo": COLUMNA_ENSAYO,
    "ambiente": COLUMNA_AMBIENTE,
    "tratamiento": COLUMNA_TRATAMIENTO,
    "unidad": COLUMNA_UNIDAD,
    "variable": COLUMNA_VARIABLE,
    "valor": COLUMNA_VALOR,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent


class PersistenceError(Exception):
    """Base de los errores propios de la capa de persistencia."""


@dataclass(frozen=True)
class RunMetadata:
    """Metadatos de auditoria de una corrida (RN-AUD-01), insumo de `persist`.

    Attributes:
        ruta_archivo_entrada: ruta al archivo de entrada de la corrida;
            `persist` calcula su SHA-256 (RN-AUD-01).
        registros_leidos/registros_validos/registros_rechazados: conteos
            que producen las etapas previas del pipeline (ingesta C-03,
            validacion C-04). `registros_almacenados` lo calcula `persist`
            (= filas de `df_tidy` efectivamente insertadas como
            observaciones), no se recibe aca.
        errores/advertencias: estructura serializable (listas) para la
            columna JSON homonima de `Ejecucion`.
        commit_git: hash del commit a registrar; si se omite, se
            auto-detecta con `git rev-parse HEAD` sobre el repo del
            proyecto.
    """

    ruta_archivo_entrada: Union[str, Path]
    registros_leidos: int
    registros_validos: int
    registros_rechazados: int
    errores: List[Any] = field(default_factory=list)
    advertencias: List[Any] = field(default_factory=list)
    commit_git: Optional[str] = None


def _hash_sha256_archivo(ruta: Union[str, Path]) -> str:
    """Hash SHA-256 del archivo de entrada, reproducible entre corridas
    (RN-AUD-01: "hash del archivo de entrada es SHA-256 reproducible")."""
    digest = hashlib.sha256()
    with Path(ruta).open("rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _commit_git_actual() -> Optional[str]:
    """Hash del commit Git del repo del proyecto (CLAUDE.md: "cada
    ejecucion auditada referencia el hash del commit"). Devuelve `None`
    si no hay repo Git disponible en vez de fallar la corrida completa por
    un dato de auditoria secundario."""
    try:
        resultado = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        return resultado.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def _crear_ejecucion(session: Session, run_metadata: RunMetadata) -> Ejecucion:
    """Crea la fila `ejecucion` con todos los campos de RN-AUD-01."""
    ejecucion = Ejecucion(
        iniciada_en=datetime.now(timezone.utc),
        commit_git=run_metadata.commit_git or _commit_git_actual(),
        hash_archivo_entrada=_hash_sha256_archivo(run_metadata.ruta_archivo_entrada),
        registros_leidos=run_metadata.registros_leidos,
        registros_validos=run_metadata.registros_validos,
        registros_rechazados=run_metadata.registros_rechazados,
        registros_almacenados=0,
        errores=list(run_metadata.errores),
        advertencias=list(run_metadata.advertencias),
    )
    session.add(ejecucion)
    session.flush()
    return ejecucion


def _persistir_bitacora(session: Session, ejecucion: Ejecucion, operaciones) -> None:
    """Persiste `TransformationOutcome.operaciones` (RN-AUD-02) ligadas a
    `ejecucion`, con `orden` = indice en la lista para reconstruir la
    secuencia aplicada."""
    for indice, operacion in enumerate(operaciones):
        datos = operacion.to_dict()
        session.add(
            BitacoraTransformacion(
                ejecucion_id=ejecucion.id,
                tipo=datos["tipo"],
                columna=datos["columna"],
                registros_afectados=datos["registros_afectados"],
                muestra_antes=datos["muestra_antes"],
                muestra_despues=datos["muestra_despues"],
                orden=indice,
            )
        )
    session.flush()


def _valor_o_none(valor: Any) -> Optional[Any]:
    return None if pd.isna(valor) else valor


def _get_or_create_ensayo(session: Session, codigo: Any) -> Ensayo:
    ensayo = session.execute(select(Ensayo).where(Ensayo.codigo == codigo)).scalar_one_or_none()
    if ensayo is None:
        ensayo = Ensayo(codigo=codigo, created_at=datetime.now(timezone.utc))
        session.add(ensayo)
        session.flush()
    return ensayo


def _get_or_create_ambiente(session: Session, ensayo: Ensayo, descripcion: Any) -> Ambiente:
    ambiente = session.execute(
        select(Ambiente).where(
            Ambiente.ensayo_id == ensayo.id, Ambiente.descripcion == descripcion
        )
    ).scalar_one_or_none()
    if ambiente is None:
        ambiente = Ambiente(ensayo_id=ensayo.id, descripcion=descripcion)
        session.add(ambiente)
        session.flush()
    return ambiente


def _get_or_create_tratamiento(session: Session, ensayo: Ensayo, descripcion: Any) -> Tratamiento:
    tratamiento = session.execute(
        select(Tratamiento).where(
            Tratamiento.ensayo_id == ensayo.id, Tratamiento.descripcion == descripcion
        )
    ).scalar_one_or_none()
    if tratamiento is None:
        tratamiento = Tratamiento(ensayo_id=ensayo.id, descripcion=descripcion)
        session.add(tratamiento)
        session.flush()
    return tratamiento


def _get_or_create_unidad(
    session: Session, tratamiento: Tratamiento, ambiente: Ambiente, identificador: Any
) -> UnidadExperimental:
    unidad = session.execute(
        select(UnidadExperimental).where(
            UnidadExperimental.tratamiento_id == tratamiento.id,
            UnidadExperimental.ambiente_id == ambiente.id,
            UnidadExperimental.identificador == identificador,
        )
    ).scalar_one_or_none()
    if unidad is None:
        unidad = UnidadExperimental(
            tratamiento_id=tratamiento.id,
            ambiente_id=ambiente.id,
            identificador=identificador,
        )
        session.add(unidad)
        session.flush()
    return unidad


def _persistir_dataset(
    session: Session,
    ejecucion: Ejecucion,
    df_tidy: pd.DataFrame,
    columnas: Mapping[str, str],
) -> int:
    """Normaliza `df_tidy` al ERD via get-or-create por clave natural
    (Decision 5, design.md) e inserta cada fila-observacion ligada a su
    `UnidadExperimental` y a `ejecucion`. Devuelve la cantidad de
    observaciones insertadas (= `registros_almacenados`)."""
    registros_almacenados = 0
    for _, fila in df_tidy.iterrows():
        ensayo = _get_or_create_ensayo(session, fila[columnas["ensayo"]])
        ambiente = _get_or_create_ambiente(session, ensayo, fila[columnas["ambiente"]])
        tratamiento = _get_or_create_tratamiento(session, ensayo, fila[columnas["tratamiento"]])
        unidad = _get_or_create_unidad(session, tratamiento, ambiente, fila[columnas["unidad"]])

        session.add(
            Observacion(
                unidad_experimental_id=unidad.id,
                ejecucion_id=ejecucion.id,
                variable=fila[columnas["variable"]],
                valor=_valor_o_none(fila[columnas["valor"]]),
            )
        )
        registros_almacenados += 1

    session.flush()
    return registros_almacenados


def persist(
    outcome: TransformationOutcome,
    run_metadata: RunMetadata,
    session: Session,
    columnas_jerarquia: Optional[Mapping[str, str]] = None,
) -> Ejecucion:
    """Persiste el dataset transformado, la Ejecucion y la bitacora en UNA
    transaccion atomica (Decision 5, design.md): crea `ejecucion`
    (RN-AUD-01), persiste `outcome.operaciones` como `bitacora
    _transformacion` (RN-AUD-02), y normaliza `outcome.df_tidy` a las
    entidades de dominio via get-or-create por clave natural. Si cualquier
    paso falla, la transaccion completa se revierte y no queda ninguna fila
    parcial de la corrida (ni ejecucion, ni bitacora, ni observaciones, ni
    entidades de dominio creadas en esa corrida).

    Args:
        outcome: salida de `pipeline.transformation.transform` (C-05).
        run_metadata: metadatos de auditoria de la corrida (RN-AUD-01).
        session: `Session` de SQLAlchemy ya ligada a un engine
            (`pipeline.db.build_session`); este modulo no construye el
            engine (Decision 7, design.md).
        columnas_jerarquia: mapeo columna->entidad del `df_tidy`; si se
            omite, usa el contrato v1 del fixture sintetico (OPEN QUESTION 1
            RESUELTA) -- el mapeo del caso real se difiere hasta
            desbloquear el diccionario de variables.

    Returns:
        La `Ejecucion` persistida (con `id` asignado y `finalizada_en`
        seteado tras el commit).
    """
    columnas = columnas_jerarquia if columnas_jerarquia is not None else _COLUMNAS_JERARQUIA_V1

    with session.begin():
        ejecucion = _crear_ejecucion(session, run_metadata)
        _persistir_bitacora(session, ejecucion, outcome.operaciones)
        registros_almacenados = _persistir_dataset(session, ejecucion, outcome.df_tidy, columnas)
        ejecucion.registros_almacenados = registros_almacenados
        ejecucion.finalizada_en = datetime.now(timezone.utc)

    return ejecucion


# --- CLI fino por archivos (D-1/D-2/D-3/D-4, change n8n-orchestration-workflows) --
# n8n invoca este modulo SOLO por CLI (DD-05); el `main()` lee el directorio
# de corrida completo (tidy.pkl + operaciones.json + manifest.json que
# dejaron las etapas anteriores), reconstruye `TransformationOutcome` +
# `RunMetadata`, invoca `persist` (logica intacta) y emite los ids
# resultantes por stdout + `resultado_persistencia.json` (D-3: n8n encadena
# por rutas/exit codes, nunca por datos de negocio en expresiones).

_CAMPOS_MANIFEST_REQUERIDOS = (
    "ruta_archivo_entrada",
    "registros_leidos",
    "registros_validos",
    "registros_rechazados",
)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.persistence",
        description=(
            "Persiste el dataset tidy + bitacora de una corrida del pipeline "
            "(tidy.pkl, operaciones.json, manifest.json en el directorio de "
            "corrida) y emite los ids resultantes. Entrypoint interno para "
            "que n8n invoque el modulo (DD-05/DD-09); no es una interfaz "
            "para usuarios humanos."
        ),
    )
    parser.add_argument(
        "corrida_dir",
        help="Directorio de la corrida (D-3): tidy.pkl + operaciones.json + manifest.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint CLI fino sobre `persist` (DD-05/DD-09).

    Exit codes (D-4): `0` exito; `1` error de dominio/configuracion
    (manifiesto incompleto, o `DATABASE_URL` no configurada -- reintentarlo
    nunca lo arregla); `2` fallo transitorio de infraestructura (artefactos
    ilegibles, o `DATABASE_URL` apunta a una base bloqueada/inaccesible --
    `OperationalError` de SQLAlchemy). Re-invocar el MISMO comando tras
    resolver la causa es seguro: `persist` ya es atomico (Decision 5, C-06),
    nunca deja filas parciales de un intento fallido.
    """
    from pipeline.db import DatabaseUrlNotConfiguredError, build_engine, build_session

    args = _parse_args(argv)
    corrida_dir = Path(args.corrida_dir)

    try:
        df_tidy = pd.read_pickle(corrida_dir / "tidy.pkl")
        with (corrida_dir / "operaciones.json").open(encoding="utf-8") as fh:
            operaciones_raw = json.load(fh)
        with (corrida_dir / "manifest.json").open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, pickle.UnpicklingError, EOFError, ValueError) as exc:
        print(
            json.dumps(
                {"error": f"No se pudieron leer los artefactos de la corrida: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    faltantes = [campo for campo in _CAMPOS_MANIFEST_REQUERIDOS if campo not in manifest]
    if faltantes:
        print(
            json.dumps(
                {"error": f"manifest.json incompleto: faltan los campos {faltantes}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    operaciones = [OperacionTransformacion(**datos) for datos in operaciones_raw]
    outcome = TransformationOutcome(df_tidy=df_tidy, operaciones=operaciones)
    run_metadata = RunMetadata(
        ruta_archivo_entrada=manifest["ruta_archivo_entrada"],
        registros_leidos=manifest["registros_leidos"],
        registros_validos=manifest["registros_validos"],
        registros_rechazados=manifest["registros_rechazados"],
        errores=manifest.get("errores", []),
        advertencias=manifest.get("advertencias", []),
    )

    try:
        engine = build_engine()
    except DatabaseUrlNotConfiguredError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    session = build_session(engine)
    try:
        ejecucion = persist(outcome, run_metadata, session)
        ensayo_codigo = df_tidy[COLUMNA_ENSAYO].iloc[0]
        ensayo = session.execute(select(Ensayo).where(Ensayo.codigo == ensayo_codigo)).scalar_one()
    except (OperationalError, OSError) as exc:
        print(
            json.dumps({"error": f"Fallo de infraestructura: {exc}"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    finally:
        session.close()
        engine.dispose()

    resultado = {
        "ejecucion_id": ejecucion.id,
        "ensayo_id": ensayo.id,
        "registros_almacenados": ejecucion.registros_almacenados,
    }

    try:
        with (corrida_dir / "resultado_persistencia.json").open("w", encoding="utf-8") as fh:
            json.dump(resultado, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(
            json.dumps(
                {"error": f"No se pudo escribir resultado_persistencia.json: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
