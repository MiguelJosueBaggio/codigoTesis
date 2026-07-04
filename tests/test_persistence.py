"""Tests de `pipeline/persistence.py` -- change persistence-audit-module
(C-06).

Cubre los requisitos: "Registro de auditoria de cada ejecucion" (RN-AUD-01),
"Persistencia de la bitacora de transformaciones reconstruible" (RN-AUD-02) y
"Persistencia atomica del dataset transformado" (Decision 5, design.md).
Corre contra SQLite REAL via el fixture `db_session` (Decision 10 -- prohibido
mockear la base).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pipeline.models import (
    Ambiente,
    BitacoraTransformacion,
    Ejecucion,
    Ensayo,
    Observacion,
    Tratamiento,
    UnidadExperimental,
)
from pipeline.persistence import RunMetadata, persist
from pipeline.transformation import OperacionTransformacion, TransformationOutcome


def _run_metadata(tmp_path, contenido="contenido de referencia", **kwargs) -> RunMetadata:
    archivo = tmp_path / "entrada.csv"
    archivo.write_text(contenido, encoding="utf-8")
    defaults = dict(registros_leidos=6, registros_validos=6, registros_rechazados=0)
    defaults.update(kwargs)
    return RunMetadata(ruta_archivo_entrada=archivo, **defaults)


# --- Grupo 5: Registro de Ejecucion (RN-AUD-01) -----------------------------


def test_persist_crea_ejecucion_con_todos_los_campos_de_auditoria(
    db_session, dataset_persistencia_df, tmp_path
):
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=[])
    run_metadata = _run_metadata(
        tmp_path,
        registros_leidos=10,
        registros_validos=6,
        registros_rechazados=4,
        errores=["fila 3: valor fuera de rango"],
        advertencias=["fila 5: unidad duplicada"],
    )

    ejecucion = persist(outcome, run_metadata, db_session)

    assert ejecucion.id is not None
    assert ejecucion.iniciada_en is not None
    assert ejecucion.finalizada_en is not None
    assert ejecucion.commit_git  # repo git real -- no vacio
    assert ejecucion.hash_archivo_entrada is not None
    assert len(ejecucion.hash_archivo_entrada) == 64
    assert ejecucion.registros_leidos == 10
    assert ejecucion.registros_validos == 6
    assert ejecucion.registros_rechazados == 4
    assert ejecucion.registros_almacenados == len(dataset_persistencia_df)
    assert ejecucion.errores == ["fila 3: valor fuera de rango"]
    assert ejecucion.advertencias == ["fila 5: unidad duplicada"]


def test_hash_archivo_entrada_es_reproducible_entre_corridas(
    db_session, dataset_persistencia_df, tmp_path
):
    run_metadata = _run_metadata(tmp_path, contenido="contenido identico")
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=[])

    ejecucion_1 = persist(outcome, run_metadata, db_session)
    ejecucion_2 = persist(outcome, run_metadata, db_session)

    assert ejecucion_1.hash_archivo_entrada == ejecucion_2.hash_archivo_entrada


# --- Grupo 6: Bitacora de transformaciones (RN-AUD-02) ----------------------


def test_bitacora_persistida_conserva_todos_los_campos_y_orden(
    db_session, dataset_persistencia_df, tmp_path
):
    operaciones = [
        OperacionTransformacion(
            tipo="normalizacion_nombre",
            columna="ambiente",
            registros_afectados=6,
            muestra_antes=["AMBIENTE"],
            muestra_despues=["ambiente"],
        ),
        OperacionTransformacion(
            tipo="conversion_unidad",
            columna="valor",
            registros_afectados=6,
            muestra_antes=[1.0],
            muestra_despues=[1000.0],
        ),
    ]
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=operaciones)
    run_metadata = _run_metadata(tmp_path)

    ejecucion = persist(outcome, run_metadata, db_session)

    filas = (
        db_session.execute(
            select(BitacoraTransformacion)
            .where(BitacoraTransformacion.ejecucion_id == ejecucion.id)
            .order_by(BitacoraTransformacion.orden)
        )
        .scalars()
        .all()
    )

    assert len(filas) == 2
    assert [f.orden for f in filas] == [0, 1]
    assert filas[0].tipo == "normalizacion_nombre"
    assert filas[0].columna == "ambiente"
    assert filas[0].registros_afectados == 6
    assert filas[0].muestra_antes == ["AMBIENTE"]
    assert filas[0].muestra_despues == ["ambiente"]
    assert filas[1].tipo == "conversion_unidad"
    assert all(f.ejecucion_id == ejecucion.id for f in filas)


def test_bitacora_permite_reconstruir_la_secuencia_aplicada(
    db_session, dataset_persistencia_df, tmp_path
):
    operaciones = [
        OperacionTransformacion(
            tipo="normalizacion_nombre", columna="ambiente", registros_afectados=6,
            muestra_antes=["A"], muestra_despues=["a"],
        ),
        OperacionTransformacion(
            tipo="estandarizacion_categorica", columna="tratamiento", registros_afectados=2,
            muestra_antes=["TESTIGO"], muestra_despues=["Testigo"],
        ),
        OperacionTransformacion(
            tipo="conversion_unidad", columna="valor", registros_afectados=6,
            muestra_antes=[1.0], muestra_despues=[1000.0],
        ),
    ]
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=operaciones)
    run_metadata = _run_metadata(tmp_path)

    ejecucion = persist(outcome, run_metadata, db_session)

    filas = (
        db_session.execute(
            select(BitacoraTransformacion)
            .where(BitacoraTransformacion.ejecucion_id == ejecucion.id)
            .order_by(BitacoraTransformacion.orden)
        )
        .scalars()
        .all()
    )
    secuencia_reconstruida = [(f.tipo, f.columna) for f in filas]
    secuencia_original = [(op.tipo, op.columna) for op in operaciones]

    assert secuencia_reconstruida == secuencia_original


# --- Grupo 7: persist() -- dataset transformado + transaccion atomica ------


def test_persist_dataset_tidy_como_observaciones_ligadas(
    db_session, dataset_persistencia_df, tmp_path
):
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=[])
    run_metadata = _run_metadata(tmp_path)

    ejecucion = persist(outcome, run_metadata, db_session)

    observaciones = (
        db_session.execute(select(Observacion).where(Observacion.ejecucion_id == ejecucion.id))
        .scalars()
        .all()
    )
    assert len(observaciones) == len(dataset_persistencia_df)

    ensayo = db_session.execute(select(Ensayo).where(Ensayo.codigo == "E-SINT-01")).scalar_one()
    ambientes = db_session.execute(select(Ambiente).where(Ambiente.ensayo_id == ensayo.id)).scalars().all()
    assert {a.descripcion for a in ambientes} == {"Campo Norte", "Campo Sur"}

    for obs in observaciones:
        assert obs.unidad_experimental_id is not None
        unidad = db_session.get(UnidadExperimental, obs.unidad_experimental_id)
        assert unidad.ambiente.ensayo_id == ensayo.id


def test_persist_revierte_toda_la_corrida_si_falla_a_mitad(db_session, tmp_path):
    df_tidy = pd.DataFrame(
        {
            "codigo_ensayo": ["E-ATOM-01", "E-ATOM-01"],
            "ambiente": ["Campo A", "Campo A"],
            "tratamiento": ["Testigo", "Testigo"],
            "id_unidad": ["U1", None],  # None -> viola NOT NULL de UnidadExperimental
            "variable": ["rendimiento", "rendimiento"],
            "valor": [100.0, 110.0],
        }
    )
    outcome = TransformationOutcome(df_tidy=df_tidy, operaciones=[])
    run_metadata = _run_metadata(tmp_path, registros_leidos=2, registros_validos=2)

    with pytest.raises(IntegrityError):
        persist(outcome, run_metadata, db_session)

    assert db_session.execute(select(func.count()).select_from(Ejecucion)).scalar() == 0
    assert db_session.execute(select(func.count()).select_from(BitacoraTransformacion)).scalar() == 0
    assert db_session.execute(select(func.count()).select_from(Observacion)).scalar() == 0
    assert db_session.execute(select(func.count()).select_from(Ensayo)).scalar() == 0
    assert db_session.execute(select(func.count()).select_from(UnidadExperimental)).scalar() == 0


def test_persist_dos_veces_no_duplica_entidades_de_dominio(
    db_session, dataset_persistencia_df, tmp_path
):
    outcome = TransformationOutcome(df_tidy=dataset_persistencia_df, operaciones=[])
    run_metadata = _run_metadata(tmp_path)

    ejecucion_1 = persist(outcome, run_metadata, db_session)
    ejecucion_2 = persist(outcome, run_metadata, db_session)

    assert ejecucion_1.id != ejecucion_2.id
    assert db_session.execute(select(func.count()).select_from(Ensayo)).scalar() == 1
    assert db_session.execute(select(func.count()).select_from(Ambiente)).scalar() == 2
    assert db_session.execute(select(func.count()).select_from(Tratamiento)).scalar() == 2
    assert db_session.execute(select(func.count()).select_from(UnidadExperimental)).scalar() == 6
    assert db_session.execute(select(func.count()).select_from(Observacion)).scalar() == 12
    assert db_session.execute(select(func.count()).select_from(Ejecucion)).scalar() == 2


# --- CLI fino por archivos (D-1/D-2/D-3/D-4, change n8n-orchestration-workflows) --


class TestCLI:
    def _preparar_corrida(self, tmp_path, dataset_persistencia_df, ruta_archivo_entrada=None):
        """Arma un directorio de corrida completo (tidy.pkl + operaciones.json
        + manifest.json) tal como lo dejarian transformation/validation antes
        de invocar persistence (D-3, contrato de corrida)."""
        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir(exist_ok=True)
        dataset_persistencia_df.to_pickle(corrida_dir / "tidy.pkl")

        operacion = OperacionTransformacion(
            tipo="normalizacion_nombre",
            columna="ambiente",
            registros_afectados=6,
            muestra_antes=["campo norte"],
            muestra_despues=["Campo Norte"],
        )
        (corrida_dir / "operaciones.json").write_text(
            json.dumps([operacion.to_dict()]), encoding="utf-8"
        )

        archivo_entrada = ruta_archivo_entrada or (tmp_path / "entrada_original.csv")
        if not Path(archivo_entrada).exists():
            Path(archivo_entrada).write_text("contenido de referencia", encoding="utf-8")

        (corrida_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "ruta_archivo_entrada": str(archivo_entrada),
                    "registros_leidos": 6,
                    "registros_validos": 6,
                    "registros_rechazados": 0,
                }
            ),
            encoding="utf-8",
        )
        return corrida_dir

    def test_cli_persiste_desde_corrida_y_emite_ids_por_stdout(
        self, tmp_path, monkeypatch, capsys, dataset_persistencia_df
    ):
        """5.1/5.2: `main` lee tidy.pkl + operaciones.json + manifest.json de
        un directorio de corrida, persiste (delegando en `persist`, logica
        intacta) y emite `{ejecucion_id, ensayo_id, registros_almacenados}`
        por stdout Y en `resultado_persistencia.json` (D-3: n8n encadena por
        rutas/exit codes, no por datos de negocio en expresiones)."""
        from pipeline.db import build_engine
        from pipeline.models import Base
        from pipeline.persistence import main

        db_path = tmp_path / "cli_test.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        engine = build_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        corrida_dir = self._preparar_corrida(tmp_path, dataset_persistencia_df)

        exit_code = main([str(corrida_dir)])

        assert exit_code == 0
        salida = json.loads(capsys.readouterr().out)
        assert salida["ejecucion_id"]
        assert salida["ensayo_id"]
        assert salida["registros_almacenados"] == 6

        resultado_archivo = json.loads(
            (corrida_dir / "resultado_persistencia.json").read_text(encoding="utf-8")
        )
        assert resultado_archivo == salida

    def test_cli_manifiesto_incompleto_sale_exit_code_1(
        self, tmp_path, monkeypatch, dataset_persistencia_df
    ):
        """5.3 TRIANGULATE: un `manifest.json` al que le faltan campos
        requeridos (`registros_validos`/`registros_rechazados`) es un error
        de dominio/configuracion determinista -- exit 1, no se reintenta
        (D-4): reintentar un manifiesto incompleto nunca lo completa."""
        from pipeline.db import build_engine
        from pipeline.models import Base
        from pipeline.persistence import main

        db_path = tmp_path / "cli_test_incompleto.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        engine = build_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        corrida_dir = tmp_path / "corrida"
        corrida_dir.mkdir()
        dataset_persistencia_df.to_pickle(corrida_dir / "tidy.pkl")
        (corrida_dir / "operaciones.json").write_text("[]", encoding="utf-8")
        (corrida_dir / "manifest.json").write_text(
            json.dumps({"ruta_archivo_entrada": str(tmp_path / "no_importa.csv"), "registros_leidos": 6}),
            encoding="utf-8",
        )

        exit_code = main([str(corrida_dir)])

        assert exit_code == 1

    def test_cli_base_inaccesible_exit_2_y_reinvocacion_persiste_una_sola_vez(
        self, tmp_path, monkeypatch, dataset_persistencia_df
    ):
        """5.3 TRIANGULATE: `DATABASE_URL` apuntando a un directorio
        inexistente (SQLite nunca lo crea) es un fallo REAL de
        infraestructura -- exit 2 -- distinto del exit 1 de arriba. La
        re-invocacion del MISMO comando con la base ya accesible persiste
        UNA sola vez (re-invocabilidad segura de la etapa, D-9): sin filas
        parciales del intento fallido (persist() ya es atomico, Decision 5
        de C-06 -- este test verifica que el CLI no lo rompe)."""
        from pipeline.db import build_engine, build_session_factory
        from pipeline.models import Base, Ejecucion
        from pipeline.persistence import main

        corrida_dir = self._preparar_corrida(tmp_path, dataset_persistencia_df)

        ruta_inaccesible = tmp_path / "directorio_inexistente" / "cli_test_infra.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta_inaccesible}")

        exit_code_1 = main([str(corrida_dir)])
        assert exit_code_1 == 2
        assert not (corrida_dir / "resultado_persistencia.json").exists()

        db_path = tmp_path / "cli_test_retry.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        engine = build_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)

        exit_code_2 = main([str(corrida_dir)])
        assert exit_code_2 == 0

        session = build_session_factory(engine)()
        try:
            total_ejecuciones = session.execute(select(func.count()).select_from(Ejecucion)).scalar_one()
        finally:
            session.close()
        engine.dispose()

        assert total_ejecuciones == 1
