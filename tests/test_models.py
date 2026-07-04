"""Tests de los modelos ORM declarativos (`pipeline/models.py`) -- change
persistence-audit-module (C-06).

Spec: "Esquema relacional de dominio y sistema via ORM declarativo" y
"Geolocalizacion opcional de Ambiente". Solo inspecciona `Base.metadata`
(sin abrir conexion) salvo los tests de CHECK constraint, que necesitan un
motor SQLite real (Decision 10 -- prohibido mockear la base).
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer
from sqlalchemy.exc import IntegrityError

from pipeline.models import Ambiente, Base

_TABLAS_ESPERADAS = {
    "ensayo",
    "ambiente",
    "tratamiento",
    "unidad_experimental",
    "observacion",
    "ejecucion",
    "bitacora_transformacion",
}


def test_todas_las_entidades_del_erd_estan_mapeadas():
    nombres_tabla = set(Base.metadata.tables.keys())

    assert _TABLAS_ESPERADAS <= nombres_tabla


def test_cada_tabla_tiene_clave_primaria_entera_autoincremental():
    for nombre in _TABLAS_ESPERADAS:
        tabla = Base.metadata.tables[nombre]
        columnas_pk = list(tabla.primary_key.columns)

        assert len(columnas_pk) == 1, f"{nombre} debe tener PK simple"
        pk = columnas_pk[0]
        assert isinstance(pk.type, Integer), f"{nombre}.{pk.name} debe ser entera"
        assert pk.autoincrement in (True, "auto"), f"{nombre}.{pk.name} debe autoincrementar"


def _tablas_referenciadas(nombre_tabla: str) -> set:
    tabla = Base.metadata.tables[nombre_tabla]
    return {fk.column.table.name for fk in tabla.foreign_keys}


def test_relaciones_jerarquicas_del_erd_declaradas():
    assert _tablas_referenciadas("ambiente") == {"ensayo"}
    assert _tablas_referenciadas("tratamiento") == {"ensayo"}
    assert _tablas_referenciadas("unidad_experimental") == {"tratamiento", "ambiente"}
    assert _tablas_referenciadas("observacion") == {"unidad_experimental", "ejecucion"}
    assert _tablas_referenciadas("bitacora_transformacion") == {"ejecucion"}


def test_ambiente_sin_coordenadas_es_valido(db_session):
    from pipeline.models import Ensayo
    from datetime import datetime, timezone

    ensayo = Ensayo(codigo="E-TEST-01", created_at=datetime.now(timezone.utc))
    db_session.add(ensayo)
    db_session.flush()

    ambiente = Ambiente(ensayo_id=ensayo.id, descripcion="Campo sin geolocalizar")
    db_session.add(ambiente)
    db_session.commit()

    assert ambiente.id is not None
    assert ambiente.latitud is None
    assert ambiente.longitud is None


def test_latitud_fuera_de_rango_viola_check_constraint(db_session):
    from pipeline.models import Ensayo
    from datetime import datetime, timezone

    ensayo = Ensayo(codigo="E-TEST-02", created_at=datetime.now(timezone.utc))
    db_session.add(ensayo)
    db_session.flush()

    ambiente_invalido = Ambiente(ensayo_id=ensayo.id, descripcion="Fuera de rango", latitud=100.0)
    db_session.add(ambiente_invalido)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_longitud_fuera_de_rango_viola_check_constraint(db_session):
    from pipeline.models import Ensayo
    from datetime import datetime, timezone

    ensayo = Ensayo(codigo="E-TEST-03", created_at=datetime.now(timezone.utc))
    db_session.add(ensayo)
    db_session.flush()

    ambiente_invalido = Ambiente(ensayo_id=ensayo.id, descripcion="Fuera de rango", longitud=-200.0)
    db_session.add(ambiente_invalido)

    with pytest.raises(IntegrityError):
        db_session.commit()
