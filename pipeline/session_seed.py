"""Seed de `config_paso_sesion` (RN-SES-03/DD-10) para `setup_ensayo` y
`carga_dato` -- change `telegram-interaction-layer` (C-13), grupo 4 del
tasks.md.

La secuencia de pasos es DATA, nunca codigo (RN-SES-03): este modulo
INSERTA filas en `config_paso_sesion`; el motor (`pipeline.session_engine`)
y la CLI (`pipeline.session_cli`) nunca bifurcan por `tipo_sesion`.
Idempotente: no duplica filas ya sembradas (mismo `tipo_sesion` + `paso`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from pipeline.data_dictionary import DataDictionary, load_data_dictionary
from pipeline.models import ConfigPasoSesion

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DICTIONARY_PATH_DEFAULT = _REPO_ROOT / "config" / "data_dictionary.json"

# setup_ensayo (Decision 4 del design): 3 pasos de texto libre -- el
# Ingeniero entrega, CONVERSANDO, el codigo del ensayo, las variables del
# diccionario (JSON) y el diseno experimental + formula del modelo (JSON).
# `pipeline.setup_ensayo` ensambla estos 3 pasos en los config files; la
# decision metodologica sigue siendo juicio experto (KB 13 §6).
_PASOS_SETUP_ENSAYO = (
    {
        "paso": 0,
        "prompt": "Enviame el codigo del ensayo (identificador unico, texto libre).",
        "tipo_respuesta": "texto",
        "regla_validacion": {"tipo_dato": "texto_libre", "obligatorio": True},
    },
    {
        "paso": 1,
        "prompt": (
            "Enviame las variables del diccionario como JSON: una lista de objetos "
            "{nombre_canonico, descripcion, tipo_dato, obligatorio, unidad?, rango?, "
            "valores_admisibles?} (ver config/data_dictionary.schema.json)."
        ),
        "tipo_respuesta": "texto",
        "regla_validacion": {"tipo_dato": "texto_libre", "obligatorio": True},
    },
    {
        "paso": 2,
        "prompt": (
            "Enviame el diseno experimental y la formula del modelo como JSON: "
            '{"formula": "...", "tipo": "anova", "alpha": 0.05, '
            '"metodo_comparacion": "tukey", "factor": "tratamiento"}.'
        ),
        "tipo_respuesta": "texto",
        "regla_validacion": {"tipo_dato": "texto_libre", "obligatorio": True},
    },
)


def _tipo_respuesta_para_variable(tipo_dato: str) -> str:
    if tipo_dato in ("entero", "real"):
        return "numero"
    if tipo_dato == "categorico":
        return "choice"
    return "texto"


def _fila_para_variable(paso: int, variable) -> dict:
    return {
        "paso": paso,
        "prompt": f"{variable.descripcion} ({variable.nombre_canonico})",
        "tipo_respuesta": _tipo_respuesta_para_variable(variable.tipo_dato),
        "regla_validacion": {
            "tipo_dato": variable.tipo_dato,
            "obligatorio": variable.obligatorio,
            "unidad": variable.unidad,
            "rango": variable.rango,
            "valores_admisibles": variable.valores_admisibles,
        },
    }


def _sembrar(session: Session, tipo_sesion: str, filas: list) -> int:
    """Inserta cada fila de `filas` si no existe ya (mismo `tipo_sesion` +
    `paso`) -- idempotente, seguro de correr en cada despliegue."""
    creadas = 0
    for fila in filas:
        ya_existe = session.execute(
            select(ConfigPasoSesion).where(
                ConfigPasoSesion.tipo_sesion == tipo_sesion,
                ConfigPasoSesion.paso == fila["paso"],
            )
        ).scalar_one_or_none()
        if ya_existe is not None:
            continue
        session.add(ConfigPasoSesion(tipo_sesion=tipo_sesion, **fila))
        creadas += 1
    session.commit()
    return creadas


def sembrar_setup_ensayo(session: Session) -> int:
    """Siembra los 3 pasos fijos de `setup_ensayo` (idempotente). Devuelve
    la cantidad de filas nuevas creadas en esta corrida."""
    return _sembrar(session, "setup_ensayo", list(_PASOS_SETUP_ENSAYO))


def sembrar_carga_dato(
    session: Session, diccionario: Optional[DataDictionary] = None
) -> int:
    """Siembra un paso de `carga_dato` por cada variable del diccionario
    vigente (idempotente). Si se omite `diccionario`, carga el vigente en
    `config/data_dictionary.json` (Decision 4 del design)."""
    if diccionario is None:
        diccionario = load_data_dictionary(_DATA_DICTIONARY_PATH_DEFAULT)

    filas = [_fila_para_variable(indice, variable) for indice, variable in enumerate(diccionario)]
    return _sembrar(session, "carga_dato", filas)
