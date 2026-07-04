"""Modulo de conexion a la base de datos (engine + Session factory).

Change `persistence-audit-module` (C-06), Decision 7 del design: aisla la
construccion del engine/`Session` del codigo de dominio (`pipeline
.persistence`) y de los tests, que inyectan su propia `DATABASE_URL`
apuntando a un SQLite temporal (Decision 10 -- SQLite real, sin mocks).

El connection string se obtiene EXCLUSIVAMENTE de la variable de entorno
`DATABASE_URL` (DD-11, spec: "Configuracion de conexion por unica
DATABASE_URL"). Este modulo NUNCA hardcodea un connection string ni
credenciales; el default de desarrollo (`sqlite:///./ensayos.db`) vive
unicamente en `.env.example`, no en codigo.
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_DATABASE_URL_ENV_VAR = "DATABASE_URL"


class DatabaseUrlNotConfiguredError(RuntimeError):
    """La variable de entorno `DATABASE_URL` no esta configurada.

    Fail-closed: mejor un error explicito y claro que resolver en silencio
    a un connection string implicito (DD-11).
    """


def get_database_url() -> str:
    """Devuelve el connection string configurado en `DATABASE_URL`.

    Raises:
        DatabaseUrlNotConfiguredError: si la variable de entorno no esta
            definida o esta vacia.
    """
    url = os.environ.get(_DATABASE_URL_ENV_VAR)
    if not url:
        raise DatabaseUrlNotConfiguredError(
            f"La variable de entorno '{_DATABASE_URL_ENV_VAR}' no esta "
            "configurada. Definila (ver .env.example) antes de conectar "
            "a la base de datos."
        )
    return url


def build_engine(database_url: Optional[str] = None) -> Engine:
    """Construye un `Engine` de SQLAlchemy.

    Args:
        database_url: connection string explicito (usado por los tests
            para apuntar a un SQLite temporal). Si se omite, se toma de
            `DATABASE_URL` (`get_database_url`).
    """
    url = database_url if database_url is not None else get_database_url()
    return create_engine(url)


def build_session_factory(engine: Engine) -> sessionmaker:
    """Expone una factory de `Session` ligada a `engine`.

    `expire_on_commit=False`: tras el `commit` atomico de `persist()`
    (Decision 5, design.md), el caller sigue necesitando leer los atributos
    del objeto devuelto (p. ej. `Ejecucion.id`) sin disparar una consulta
    adicional contra una sesion que puede ya estar cerrada.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def build_session(engine: Engine) -> Session:
    """Atajo: una `Session` lista para usar, ligada a `engine`."""
    return build_session_factory(engine)()
