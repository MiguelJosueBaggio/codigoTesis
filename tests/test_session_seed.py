"""Tests de `pipeline.session_seed` -- change `telegram-interaction-layer`
(C-13), grupo 4 del tasks.md (RN-SES-03/DD-10: la secuencia de pasos es
DATA, nunca codigo). SQLite real via `db_session` (regla dura C-06).
"""

from __future__ import annotations

from pathlib import Path

from pipeline.data_dictionary import load_data_dictionary
from pipeline.models import ConfigPasoSesion
from pipeline.session_seed import sembrar_carga_dato, sembrar_setup_ensayo

_DICCIONARIO_PATH = Path(__file__).parent.parent / "config" / "data_dictionary.json"


def test_sembrar_setup_ensayo_crea_tres_pasos(db_session):
    creadas = sembrar_setup_ensayo(db_session)

    assert creadas == 3
    pasos = (
        db_session.query(ConfigPasoSesion)
        .filter_by(tipo_sesion="setup_ensayo")
        .order_by(ConfigPasoSesion.paso)
        .all()
    )
    assert [p.paso for p in pasos] == [0, 1, 2]


def test_sembrar_setup_ensayo_es_idempotente(db_session):
    sembrar_setup_ensayo(db_session)
    segunda_corrida = sembrar_setup_ensayo(db_session)

    assert segunda_corrida == 0
    total = db_session.query(ConfigPasoSesion).filter_by(tipo_sesion="setup_ensayo").count()
    assert total == 3


def test_sembrar_carga_dato_crea_un_paso_por_variable(db_session):
    diccionario = load_data_dictionary(_DICCIONARIO_PATH)

    creadas = sembrar_carga_dato(db_session, diccionario)

    assert creadas == len(list(diccionario))
    pasos = db_session.query(ConfigPasoSesion).filter_by(tipo_sesion="carga_dato").all()
    assert len(pasos) == len(list(diccionario))


def test_sembrar_carga_dato_mapea_tipo_respuesta_por_tipo_dato(db_session):
    diccionario = load_data_dictionary(_DICCIONARIO_PATH)

    sembrar_carga_dato(db_session, diccionario)

    paso_valor = (
        db_session.query(ConfigPasoSesion)
        .filter_by(tipo_sesion="carga_dato")
        .filter(ConfigPasoSesion.prompt.like("%valor%"))
        .first()
    )
    assert paso_valor is not None
    assert paso_valor.tipo_respuesta == "numero"

    paso_ambiente = (
        db_session.query(ConfigPasoSesion)
        .filter_by(tipo_sesion="carga_dato")
        .filter(ConfigPasoSesion.prompt.like("%ambiente%"))
        .first()
    )
    assert paso_ambiente is not None
    assert paso_ambiente.tipo_respuesta == "choice"
