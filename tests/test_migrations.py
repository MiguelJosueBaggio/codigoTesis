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
_TABLA_USUARIO_TELEGRAM_ESPERADA = {"usuario_telegram"}
_TABLA_RECHAZO_AUTORIZACION_ESPERADA = {"rechazo_autorizacion"}
_TABLA_SUGERENCIA_IA_ESPERADA = {"sugerencia_ia"}


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


def test_migracion_0003_crea_usuario_telegram_en_sqlite(tmp_path, monkeypatch):
    """Change telegram-interaction-layer (C-13): migracion `0003` extiende
    el esquema de `0002` con la tabla RBAC, sin tocarlo."""
    db_path = tmp_path / "migracion_usuario_telegram.db"
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
    assert _TABLA_USUARIO_TELEGRAM_ESPERADA <= tablas


def test_migracion_0003_paridad_con_base_metadata(tmp_path, monkeypatch):
    """La migracion 0003 (artefacto versionado) debe crear el MISMO conjunto
    de tablas que `Base.metadata` (fuente unica del esquema, DD-11)."""
    from pipeline.models import Base

    db_path = tmp_path / "migracion_0003_paridad.db"
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


def test_migracion_downgrade_0003_a_0002_elimina_solo_usuario_telegram(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_usuario_telegram_downgrade.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLAS_SESION_ESPERADAS <= tablas
    assert not (_TABLA_USUARIO_TELEGRAM_ESPERADA & tablas)


def test_migracion_upgrade_downgrade_upgrade_0003_es_reversible(tmp_path, monkeypatch):
    """1.3: verificar upgrade->downgrade->upgrade sobre SQLite real."""
    db_path = tmp_path / "migracion_0003_ciclo.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002")
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLA_USUARIO_TELEGRAM_ESPERADA <= tablas


def test_migracion_0004_crea_rechazo_autorizacion_en_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_rechazo_autorizacion.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLA_RECHAZO_AUTORIZACION_ESPERADA <= tablas


def test_migracion_0004_paridad_con_base_metadata(tmp_path, monkeypatch):
    from pipeline.models import Base

    db_path = tmp_path / "migracion_0004_paridad.db"
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


def test_migracion_downgrade_0004_a_0003_elimina_solo_rechazo_autorizacion(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_rechazo_autorizacion_downgrade.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0003")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert _TABLA_USUARIO_TELEGRAM_ESPERADA <= tablas
    assert not (_TABLA_RECHAZO_AUTORIZACION_ESPERADA & tablas)


def test_migracion_0005_crea_sugerencia_ia_en_sqlite(tmp_path, monkeypatch):
    """Change ai-support-standardization (C-09): migracion `0005` extiende el
    esquema de `0004` con la tabla `sugerencia_ia`, sin tocarlo."""
    db_path = tmp_path / "migracion_sugerencia_ia.db"
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
    assert _TABLA_SUGERENCIA_IA_ESPERADA <= tablas


def test_migracion_0005_paridad_con_base_metadata(tmp_path, monkeypatch):
    from pipeline.models import Base

    db_path = tmp_path / "migracion_0005_paridad.db"
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


def test_migracion_0005_siembra_los_pasos_de_confirmacion_ia(tmp_path, monkeypatch):
    """Task 8.3: el seed de `config_paso_sesion` para `confirmacion_ia` va en
    la migracion 0005 (RN-SES-03: la secuencia de pasos es DATA)."""
    db_path = tmp_path / "migracion_0005_seed.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            filas = conn.execute(
                sa.text(
                    "SELECT paso, tipo_respuesta FROM config_paso_sesion "
                    "WHERE tipo_sesion = 'confirmacion_ia' ORDER BY paso"
                )
            ).all()
    finally:
        engine.dispose()

    assert [tuple(fila) for fila in filas] == [(0, "choice"), (1, "texto")]


def test_migracion_downgrade_0005_a_0004_elimina_sugerencia_ia_y_el_seed(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_sugerencia_ia_downgrade.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
        with engine.connect() as conn:
            filas = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM config_paso_sesion WHERE tipo_sesion = 'confirmacion_ia'"
                )
            ).scalar_one()
    finally:
        engine.dispose()

    assert _TABLA_RECHAZO_AUTORIZACION_ESPERADA <= tablas
    assert not (_TABLA_SUGERENCIA_IA_ESPERADA & tablas)
    assert filas == 0


def test_migracion_upgrade_downgrade_upgrade_0005_es_reversible(tmp_path, monkeypatch):
    db_path = tmp_path / "migracion_0005_ciclo.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = _alembic_config(url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004")
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        tablas = set(sa.inspect(engine).get_table_names())
        with engine.connect() as conn:
            cantidad = conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM config_paso_sesion WHERE tipo_sesion = 'confirmacion_ia'"
                )
            ).scalar_one()
    finally:
        engine.dispose()

    assert _TABLA_SUGERENCIA_IA_ESPERADA <= tablas
    assert cantidad == 2


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
