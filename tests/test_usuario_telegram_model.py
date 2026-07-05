"""Tests del modelo ORM `UsuarioTelegram` (RBAC de aplicacion) -- change
`telegram-interaction-layer` (C-13), grupo 1 del tasks.md.

Spec: "RBAC de aplicacion fail-closed mapeado por telegram_user_id". SQLite
real via `db_session` (fixture de `conftest.py`, prohibido mockear la base --
regla dura del proyecto, C-06).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from pipeline.models import Base, Ensayo, UsuarioTelegram

_TABLA_ESPERADA = "usuario_telegram"


def test_tabla_usuario_telegram_esta_mapeada():
    assert _TABLA_ESPERADA in Base.metadata.tables


def test_crear_usuario_telegram_ingeniero_sin_ensayo(db_session):
    ahora = datetime.now(timezone.utc)

    usuario = UsuarioTelegram(
        telegram_user_id="tg-ing-001",
        rol="ingeniero",
        ensayo_id=None,
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(usuario)
    db_session.commit()

    persistido = db_session.get(UsuarioTelegram, usuario.id)
    assert persistido is not None
    assert persistido.rol == "ingeniero"
    assert persistido.ensayo_id is None


def test_telegram_user_id_duplicado_viola_unicidad(db_session):
    ahora = datetime.now(timezone.utc)

    db_session.add(
        UsuarioTelegram(
            telegram_user_id="tg-dup-001",
            rol="ayudante",
            created_at=ahora,
            updated_at=ahora,
        )
    )
    db_session.commit()

    db_session.add(
        UsuarioTelegram(
            telegram_user_id="tg-dup-001",
            rol="ingeniero",
            created_at=ahora,
            updated_at=ahora,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_ayudante_acotado_por_ensayo_id(db_session):
    ahora = datetime.now(timezone.utc)
    ensayo = Ensayo(codigo="ENSAYO-RBAC-001", created_at=ahora)
    db_session.add(ensayo)
    db_session.flush()

    usuario = UsuarioTelegram(
        telegram_user_id="tg-ayu-001",
        rol="ayudante",
        ensayo_id=ensayo.id,
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(usuario)
    db_session.commit()

    persistido = db_session.get(UsuarioTelegram, usuario.id)
    assert persistido.ensayo_id == ensayo.id


def test_rol_fuera_del_enum_viola_check_constraint(db_session):
    ahora = datetime.now(timezone.utc)

    db_session.add(
        UsuarioTelegram(
            telegram_user_id="tg-rol-invalido",
            rol="administrador",  # fuera de {ingeniero, ayudante}
            created_at=ahora,
            updated_at=ahora,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
