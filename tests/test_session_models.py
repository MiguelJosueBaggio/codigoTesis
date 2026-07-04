"""Tests de los modelos ORM del motor de sesiones (`pipeline/models.py`) --
change session-engine (C-12).

Spec: "Entidad de sesion persistida sobre la capa existente" y "Secuencia de
pasos como configuracion, no como codigo". SQLite real via `db_session`
(fixture de `conftest.py`, prohibido mockear la base -- regla dura del
proyecto).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from pipeline.models import Base, ConfigPasoSesion, EventoSesion, Sesion

_TABLAS_ESPERADAS = {"sesion", "config_paso_sesion", "evento_sesion"}


def test_las_tres_tablas_de_sesion_estan_mapeadas():
    nombres_tabla = set(Base.metadata.tables.keys())

    assert _TABLAS_ESPERADAS <= nombres_tabla


def test_crear_sesion_nueva_persiste_estado_inicial(db_session):
    ahora = datetime.now(timezone.utc)

    sesion = Sesion(
        telegram_user_id="tg-001",
        tipo_sesion="setup_ensayo",
        paso_actual=0,
        respuestas_acumuladas={},
        estado="abierta",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sesion)
    db_session.commit()

    persistida = db_session.get(Sesion, sesion.id)
    assert persistida is not None
    assert persistida.estado == "abierta"
    assert persistida.paso_actual == 0
    assert persistida.respuestas_acumuladas == {}
    assert persistida.ensayo_id is None


def test_ensayo_id_nullable_para_sesion_de_setup(db_session):
    ahora = datetime.now(timezone.utc)

    sesion = Sesion(
        telegram_user_id="tg-002",
        ensayo_id=None,
        tipo_sesion="setup_ensayo",
        paso_actual=0,
        respuestas_acumuladas={},
        estado="abierta",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sesion)
    db_session.commit()

    assert sesion.id is not None
    assert sesion.ensayo_id is None


def test_config_paso_sesion_con_tipo_respuesta_invalido_viola_check_constraint(db_session):
    config_invalida = ConfigPasoSesion(
        tipo_sesion="setup_ensayo",
        paso=0,
        prompt="Prompt de prueba",
        tipo_respuesta="audio",  # fuera del enum {texto, numero, foto, choice}
        regla_validacion=None,
    )
    db_session.add(config_invalida)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_evento_sesion_ligado_a_session_id(db_session):
    ahora = datetime.now(timezone.utc)
    sesion = Sesion(
        telegram_user_id="tg-003",
        tipo_sesion="carga_dato",
        paso_actual=0,
        respuestas_acumuladas={},
        estado="abierta",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sesion)
    db_session.flush()

    evento = EventoSesion(
        session_id=sesion.id,
        paso=0,
        prompt="Prompt de prueba",
        respuesta="25.5",
        timestamp=ahora,
    )
    db_session.add(evento)
    db_session.commit()

    persistido = db_session.get(EventoSesion, evento.id)
    assert persistido is not None
    assert persistido.session_id == sesion.id
