"""Tests de la migracion inicial de Alembic -- change persistence-audit-module
(C-06). Spec: "Paridad de esquema SQLite/PostgreSQL".

Corre la migracion REAL (`alembic upgrade`/`downgrade`) contra un SQLite real
en un archivo temporal (Decision 10 -- prohibido mockear la base); a
diferencia de los tests de modelos/persistencia, aca NO se usa
`Base.metadata.create_all` porque el objetivo es validar que la migracion en
si (el artefacto versionado que corre en produccion) funciona.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent

_TABLAS_ESPERADAS = {
    "ensayo",
    "ambiente",
    "tratamiento",
    "unidad_experimental",
    "observacion",
    "ejecucion",
    "bitacora_transformacion",
}

_TABLAS_SESION_ESPERADAS = {"sesion", "config_paso_sesion", "evento_sesion"}


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def test_migracion_inicial_crea_las_siete_tablas_en_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLAS_ESPERADAS <= tablas


def test_migracion_downgrade_elimina_las_siete_tablas(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_downgrade.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()

    assert tablas == set()


def test_migracion_0002_crea_las_tres_tablas_de_sesion_en_sqlite(tmp_path, monkeypatch):
    """Change session-engine (C-12): migracion `0002` extiende el esquema
    de `0001` con las tablas del motor de sesiones, sin tocarlo."""
    db_path = tmp_path / "migracion_sesion.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLAS_ESPERADAS <= tablas
    assert _TABLAS_SESION_ESPERADAS <= tablas


def test_migracion_0002_paridad_con_base_metadata(tmp_path, monkeypatch):
    """La migracion 0002 (artefacto versionado) debe crear el MISMO conjunto
    de tablas que `Base.metadata` (fuente unica del esquema, DD-11)."""
    from pipeline.models import Base

    db_path = tmp_path / "migracion_paridad.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas_migracion = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()

    assert tablas_migracion == set(Base.metadata.tables.keys())


def test_migracion_downgrade_a_0001_elimina_solo_las_tablas_de_sesion(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_sesion_downgrade.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0001")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLAS_ESPERADAS <= tablas
    assert not (_TABLAS_SESION_ESPERADAS & tablas)


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_TEST_URL"),
    reason=(
        "Requiere POSTGRES_TEST_URL apuntando a un PostgreSQL disponible "
        "(paridad DD-03, Decision 10 del design)"
    ),
)
def test_migracion_inicial_corre_identica_en_postgresql(monkeypatch):
    url = os.environ["POSTGRES_TEST_URL"]
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    engine = sa.create_engine(url)
    try:
        command.upgrade(cfg, "head")
        tablas = set(sa.inspect(engine).get_table_names())
        assert _TABLAS_ESPERADAS <= tablas
    finally:
        command.downgrade(cfg, "base")
        engine.dispose()
