"""Fixtures compartidos para la suite de tests del pipeline."""

from pathlib import Path

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def npk_df() -> pd.DataFrame:
    """Carga el dataset de referencia `npk` (Fisher/Rothamsted, 6 bloques, 24 filas).

    La columna original `yield` fue renombrada a `rendimiento` en el CSV versionado
    localmente (`tests/fixtures/npk.csv`) porque `yield` es palabra reservada de
    Python y rompe el parseo de fórmulas de patsy/statsmodels (ver D4 en
    openspec/changes/anova-tukey-core/design.md).

    Se lee el CSV local (nunca se descarga en runtime) para reproducibilidad
    determinista (RN-GLB-02, D5).
    """
    df = pd.read_csv(FIXTURES_DIR / "npk.csv")
    return df


@pytest.fixture
def db_engine(tmp_path):
    """Engine de SQLite REAL en un archivo temporal (Decision 10, design.md de
    persistence-audit-module / C-06): PROHIBIDO mockear la base en tests de
    persistencia/auditoria (regla dura del proyecto) -- se valida contra un
    motor real para sostener la paridad de esquema DD-03.

    El esquema se crea via `Base.metadata.create_all` (atajo valido para
    tests unitarios de modelos/persistencia, Decision 10); la migracion
    Alembic en si se ejercita por separado en `tests/test_migrations.py`.
    """
    from pipeline.db import build_engine
    from pipeline.models import Base

    db_path = tmp_path / "test_ensayos.db"
    engine = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Una `Session` real por test, ligada a `db_engine` (sin mocks)."""
    from pipeline.db import build_session_factory

    factory = build_session_factory(db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def dataset_persistencia_df() -> pd.DataFrame:
    """Dataset tidy sintetico con jerarquia explicita (Decision 5, OPEN QUESTION 1
    RESUELTA del design de persistence-audit-module / C-06): columnas
    `codigo_ensayo`, `ambiente`, `tratamiento`, `id_unidad`, `variable`, `valor`.

    Solo datos sinteticos (regla dura): ningun cultivo/institucion/region real.
    """
    return pd.read_csv(FIXTURES_DIR / "dataset_persistencia_sintetico.csv")


@pytest.fixture
def dataset_dca_df() -> pd.DataFrame:
    """Dataset sintetico DCA (un solo factor, un unico ambiente/bloque) en el
    formato largo que consume `pipeline.persistence.persist` (change
    statistical-analysis-module / C-07, tarea 1.3): 3 niveles de
    `tratamiento` (A/B/C), 4 repeticiones cada uno, variable de respuesta
    unica `rendimiento`.
    """
    return pd.read_csv(FIXTURES_DIR / "dataset_dca_sintetico.csv")


@pytest.fixture
def dataset_bca_df() -> pd.DataFrame:
    """Dataset sintetico BCA (bloque + tratamiento) en el formato largo que
    consume `pipeline.persistence.persist` (change statistical-analysis-module
    / C-07, tarea 1.3): 2 bloques (`ambiente`), 3 tratamientos, una
    observacion por celda bloque x tratamiento.
    """
    return pd.read_csv(FIXTURES_DIR / "dataset_bca_sintetico.csv")
