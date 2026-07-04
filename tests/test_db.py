"""Tests del modulo de conexion (`pipeline/db.py`) -- change
persistence-audit-module (C-06).

Spec: "Configuracion de conexion por unica DATABASE_URL" (DD-11) -- el
connection string se obtiene EXCLUSIVAMENTE de la variable de entorno
`DATABASE_URL`; el modulo NUNCA hardcodea un string de conexion.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from pipeline.db import (
    DatabaseUrlNotConfiguredError,
    build_engine,
    build_session_factory,
    get_database_url,
)


def test_get_database_url_lee_desde_variable_de_entorno(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'a.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    assert get_database_url() == url


def test_get_database_url_sin_variable_configurada_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(DatabaseUrlNotConfiguredError):
        get_database_url()


def test_build_engine_se_construye_desde_database_url(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    engine = build_engine()

    assert isinstance(engine, Engine)
    assert str(engine.url) == url


def test_build_engine_con_url_explicita_distinta_produce_engine_distinto(tmp_path):
    url_a = f"sqlite:///{tmp_path / 'c.db'}"
    url_b = f"sqlite:///{tmp_path / 'd.db'}"

    engine_a = build_engine(url_a)
    engine_b = build_engine(url_b)

    assert str(engine_a.url) == url_a
    assert str(engine_b.url) == url_b
    assert str(engine_a.url) != str(engine_b.url)


def test_build_session_factory_produce_sesiones_ligadas_al_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'e.db'}"
    engine = build_engine(url)
    factory = build_session_factory(engine)

    session = factory()
    try:
        assert session.get_bind() is engine
    finally:
        session.close()
