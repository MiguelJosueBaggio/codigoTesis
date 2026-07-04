"""Tests del motor de sesiones (`pipeline/session_engine.py`) -- change
session-engine (C-12).

SQLite real via `db_session` (fixture de `conftest.py`, prohibido mockear la
base -- regla dura del proyecto). Ningun test toca Telegram ni n8n (fuera de
alcance de C-12, ver design.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from pipeline.models import ConfigPasoSesion, Sesion


def _sembrar_pasos_setup_ensayo(db_session) -> None:
    """Secuencia sintetica de 3 pasos (0..2) para `tipo_sesion=setup_ensayo`
    (Non-Goal del design: el catalogo real de pasos lo define C-13; aca solo
    se siembran fixtures de test)."""
    db_session.add_all(
        [
            ConfigPasoSesion(
                tipo_sesion="setup_ensayo",
                paso=0,
                prompt="Codigo del ensayo?",
                tipo_respuesta="texto",
                regla_validacion={"tipo_dato": "texto_libre", "obligatorio": True},
            ),
            ConfigPasoSesion(
                tipo_sesion="setup_ensayo",
                paso=1,
                prompt="Temperatura registrada (C)?",
                tipo_respuesta="numero",
                regla_validacion={
                    "tipo_dato": "real",
                    "obligatorio": True,
                    "rango": {"min": -10, "max": 50},
                },
            ),
            ConfigPasoSesion(
                tipo_sesion="setup_ensayo",
                paso=2,
                prompt="Foto de la parcela",
                tipo_respuesta="foto",
                regla_validacion=None,
            ),
        ]
    )
    db_session.commit()


class TestConfiguracionDePasosComoDatos:
    """RN-SES-03: la secuencia de pasos es DATA, sin ramas por `tipo_sesion`."""

    def test_el_motor_lee_la_secuencia_desde_la_configuracion(self, db_session):
        from pipeline.session_engine import _obtener_secuencia_pasos

        _sembrar_pasos_setup_ensayo(db_session)

        secuencia = _obtener_secuencia_pasos(db_session, "setup_ensayo")

        assert [paso.paso for paso in secuencia] == [0, 1, 2]
        assert secuencia[0].prompt == "Codigo del ensayo?"
        assert secuencia[0].tipo_respuesta == "texto"
        assert secuencia[1].regla_validacion == {
            "tipo_dato": "real",
            "obligatorio": True,
            "rango": {"min": -10, "max": 50},
        }

    def test_agregar_un_paso_es_agregar_una_fila(self, db_session):
        from pipeline.session_engine import _obtener_secuencia_pasos

        _sembrar_pasos_setup_ensayo(db_session)
        db_session.add(
            ConfigPasoSesion(
                tipo_sesion="setup_ensayo",
                paso=3,
                prompt="Observaciones adicionales?",
                tipo_respuesta="texto",
                regla_validacion={"tipo_dato": "texto_libre", "obligatorio": False},
            )
        )
        db_session.commit()

        secuencia = _obtener_secuencia_pasos(db_session, "setup_ensayo")

        assert [paso.paso for paso in secuencia] == [0, 1, 2, 3]

    def test_tipo_sesion_sin_filas_falla_explicito(self, db_session):
        from pipeline.session_engine import TipoSesionSinPasosError, _obtener_secuencia_pasos

        with pytest.raises(TipoSesionSinPasosError):
            _obtener_secuencia_pasos(db_session, "tipo_inexistente")


def _sembrar_pasos_carga_dato(db_session) -> None:
    db_session.add(
        ConfigPasoSesion(
            tipo_sesion="carga_dato",
            paso=0,
            prompt="Valor observado?",
            tipo_respuesta="numero",
            regla_validacion={"tipo_dato": "real", "obligatorio": True},
        )
    )
    db_session.commit()


class TestResolverReanudarVsNueva:
    """RN-SES-04: reanudar sesion abierta existente, o crear una nueva por rol."""

    def test_crea_sesion_nueva_en_paso_0_para_rol_ingeniero(self, db_session):
        from pipeline.session_engine import resolver_sesion

        _sembrar_pasos_setup_ensayo(db_session)
        ahora = datetime.now(timezone.utc)

        sesion = resolver_sesion(db_session, telegram_user_id="tg-100", rol="ingeniero", ahora=ahora)

        assert sesion.id is not None
        assert sesion.telegram_user_id == "tg-100"
        assert sesion.tipo_sesion == "setup_ensayo"
        assert sesion.paso_actual == 0
        assert sesion.estado == "abierta"
        assert sesion.respuestas_acumuladas == {}

    def test_reanuda_sesion_abierta_existente_sin_crear_otra(self, db_session):
        from pipeline.session_engine import resolver_sesion

        _sembrar_pasos_setup_ensayo(db_session)
        ahora = datetime.now(timezone.utc)
        existente = Sesion(
            telegram_user_id="tg-101",
            tipo_sesion="setup_ensayo",
            paso_actual=2,
            respuestas_acumuladas={"0": "E-001", "1": 22.5},
            estado="abierta",
            created_at=ahora,
            updated_at=ahora,
        )
        db_session.add(existente)
        db_session.commit()
        existente_id = existente.id

        resuelta = resolver_sesion(db_session, telegram_user_id="tg-101", rol="ingeniero", ahora=ahora)

        assert resuelta.id == existente_id
        assert resuelta.paso_actual == 2

        total_sesiones = db_session.execute(
            select(Sesion).where(Sesion.telegram_user_id == "tg-101")
        ).scalars().all()
        assert len(total_sesiones) == 1

    def test_rol_ayudante_crea_sesion_carga_dato(self, db_session):
        from pipeline.session_engine import resolver_sesion

        _sembrar_pasos_carga_dato(db_session)
        ahora = datetime.now(timezone.utc)

        sesion = resolver_sesion(db_session, telegram_user_id="tg-102", rol="ayudante", ahora=ahora)

        assert sesion.tipo_sesion == "carga_dato"
        assert sesion.paso_actual == 0


def _crear_sesion_en_paso(db_session, paso_actual: int, ahora: datetime, telegram_user_id: str = "tg-200") -> Sesion:
    sesion = Sesion(
        telegram_user_id=telegram_user_id,
        tipo_sesion="setup_ensayo",
        paso_actual=paso_actual,
        respuestas_acumuladas={},
        estado="abierta",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sesion)
    db_session.commit()
    return sesion


class TestAvanceConValidacionPorPaso:
    """RN-SES-05: valida contra la regla_validacion del paso ANTES de avanzar."""

    def test_avance_con_respuesta_valida_almacena_y_avanza(self, db_session):
        from pipeline.session_engine import avanzar

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=0, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        resultado = avanzar(db_session, sesion, respuesta="E-100", ahora=ahora)

        assert resultado.valido is True
        assert resultado.sesion.paso_actual == 1
        assert resultado.sesion.respuestas_acumuladas == {"0": "E-100"}
        assert resultado.sesion.updated_at == ahora

    @pytest.mark.parametrize(
        "respuesta",
        ["no-es-un-numero", 999.0],
        ids=["tipo_erroneo", "fuera_de_rango"],
    )
    def test_rechazo_de_respuesta_invalida_no_avanza(self, db_session, respuesta):
        from pipeline.session_engine import avanzar

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=1, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        resultado = avanzar(db_session, sesion, respuesta=respuesta, ahora=ahora)

        assert resultado.valido is False
        assert resultado.sesion.paso_actual == 1
        assert resultado.sesion.respuestas_acumuladas == {}
        assert resultado.mensaje is not None


class TestFinalizacionAlUltimoPaso:
    def test_respuesta_valida_en_ultimo_paso_completa_la_sesion(self, db_session):
        from pipeline.session_engine import avanzar

        _sembrar_pasos_setup_ensayo(db_session)  # ultimo paso configurado = 2 (foto)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=2, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        resultado = avanzar(db_session, sesion, respuesta="foto_ref_123", ahora=ahora)

        assert resultado.valido is True
        assert resultado.sesion.estado == "completada"
        assert resultado.sesion.paso_actual == 2  # no avanza a un paso inexistente
        assert resultado.sesion.respuestas_acumuladas == {"2": "foto_ref_123"}

    def test_resolver_crea_sesion_nueva_tras_completada_no_reanuda(self, db_session):
        from pipeline.session_engine import avanzar, resolver_sesion

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(
            db_session, paso_actual=2, ahora=creacion, telegram_user_id="tg-300"
        )
        ahora = datetime.now(timezone.utc)
        resultado = avanzar(db_session, sesion, respuesta="foto_ref_999", ahora=ahora)
        assert resultado.sesion.estado == "completada"

        nueva = resolver_sesion(db_session, telegram_user_id="tg-300", rol="ingeniero", ahora=ahora)

        assert nueva.id != sesion.id
        assert nueva.estado == "abierta"
        assert nueva.paso_actual == 0


class TestAuditoriaDeEventosDeSesion:
    """RN-SES-06: cada avance valido deja un `evento_sesion` en la MISMA
    transaccion (cadena de custodia de RN-AUD)."""

    def test_cada_avance_valido_persiste_un_evento_sesion(self, db_session):
        from pipeline.session_engine import avanzar
        from pipeline.models import EventoSesion

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=0, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        avanzar(db_session, sesion, respuesta="E-777", ahora=ahora)

        eventos = db_session.execute(
            select(EventoSesion).where(EventoSesion.session_id == sesion.id)
        ).scalars().all()
        assert len(eventos) == 1
        assert eventos[0].paso == 0
        assert eventos[0].respuesta == "E-777"
        # SQLite no preserva tzinfo en el roundtrip de DateTime(timezone=True)
        # (limitacion conocida del dialecto -- Riesgo TZ, DD-03); se compara
        # en UTC reconstruyendo el tzinfo perdido.
        assert eventos[0].timestamp.replace(tzinfo=timezone.utc) == ahora

    def test_rechazo_no_deja_evento_de_avance(self, db_session):
        from pipeline.session_engine import avanzar
        from pipeline.models import EventoSesion

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=1, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        resultado = avanzar(db_session, sesion, respuesta="no-es-numero", ahora=ahora)
        assert resultado.valido is False

        eventos = db_session.execute(
            select(EventoSesion).where(EventoSesion.session_id == sesion.id)
        ).scalars().all()
        assert eventos == []

    def test_rollback_de_la_transaccion_no_deja_evento_huerfano(self, db_session, monkeypatch):
        import pipeline.session_engine as engine_mod
        from pipeline.models import EventoSesion

        _sembrar_pasos_setup_ensayo(db_session)
        creacion = datetime.now(timezone.utc) - timedelta(minutes=5)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=0, ahora=creacion)
        ahora = datetime.now(timezone.utc)

        def _commit_que_falla():
            db_session.rollback()
            raise RuntimeError("fallo simulado de infraestructura")

        monkeypatch.setattr(db_session, "commit", _commit_que_falla)

        with pytest.raises(RuntimeError):
            engine_mod.avanzar(db_session, sesion, respuesta="E-888", ahora=ahora)

        monkeypatch.undo()
        eventos = db_session.execute(
            select(EventoSesion).where(EventoSesion.session_id == sesion.id)
        ).scalars().all()
        assert eventos == []
        recargada = db_session.get(Sesion, sesion.id)
        assert recargada.paso_actual == 0
        assert recargada.respuestas_acumuladas == {}


class TestTimeoutYExpiracion:
    """RN-SES-07 / DD-10: umbral de 24h uniforme, `ahora` inyectado
    (determinista, sin mock de reloj)."""

    def test_sesion_vencida_transiciona_a_expirada(self, db_session):
        from pipeline.session_engine import expirar_sesiones_vencidas

        ahora = datetime.now(timezone.utc)
        vencida = _crear_sesion_en_paso(
            db_session,
            paso_actual=0,
            ahora=ahora - timedelta(hours=25),
            telegram_user_id="tg-400",
        )

        expirar_sesiones_vencidas(db_session, ahora=ahora)

        recargada = db_session.get(Sesion, vencida.id)
        assert recargada.estado == "expirada"

    def test_sesion_dentro_del_umbral_permanece_abierta(self, db_session):
        from pipeline.session_engine import expirar_sesiones_vencidas

        ahora = datetime.now(timezone.utc)
        reciente = _crear_sesion_en_paso(
            db_session,
            paso_actual=0,
            ahora=ahora - timedelta(hours=1),
            telegram_user_id="tg-401",
        )

        expirar_sesiones_vencidas(db_session, ahora=ahora)

        recargada = db_session.get(Sesion, reciente.id)
        assert recargada.estado == "abierta"

    def test_sesion_completada_no_se_re_transiciona(self, db_session):
        from pipeline.session_engine import expirar_sesiones_vencidas

        ahora = datetime.now(timezone.utc)
        completada = _crear_sesion_en_paso(
            db_session,
            paso_actual=0,
            ahora=ahora - timedelta(hours=25),
            telegram_user_id="tg-402",
        )
        completada.estado = "completada"
        db_session.commit()

        expirar_sesiones_vencidas(db_session, ahora=ahora)

        recargada = db_session.get(Sesion, completada.id)
        assert recargada.estado == "completada"

    def test_sesion_expirada_no_es_candidata_a_reanudacion(self, db_session):
        from pipeline.session_engine import expirar_sesiones_vencidas, resolver_sesion

        _sembrar_pasos_setup_ensayo(db_session)
        ahora = datetime.now(timezone.utc)
        vencida = _crear_sesion_en_paso(
            db_session,
            paso_actual=1,
            ahora=ahora - timedelta(hours=25),
            telegram_user_id="tg-403",
        )
        expirar_sesiones_vencidas(db_session, ahora=ahora)

        nueva = resolver_sesion(db_session, telegram_user_id="tg-403", rol="ingeniero", ahora=ahora)

        assert nueva.id != vencida.id
        assert nueva.estado == "abierta"
        assert nueva.paso_actual == 0


class TestFailClosedDelMotor:
    """Cobertura de los caminos fail-closed que no exige ningun scenario del
    spec por si solo, pero que la disciplina fail-closed del proyecto exige
    ejercitar (patron de `pipeline.db.DatabaseUrlNotConfiguredError`)."""

    def test_resolver_con_rol_desconocido_falla_explicito(self, db_session):
        from pipeline.session_engine import RolNoReconocidoError, resolver_sesion

        with pytest.raises(RolNoReconocidoError):
            resolver_sesion(
                db_session, telegram_user_id="tg-500", rol="rol_inexistente", ahora=datetime.now(timezone.utc)
            )

    def test_avanzar_con_paso_actual_sin_configuracion_falla_explicito(self, db_session):
        from pipeline.session_engine import PasoSesionNoConfiguradoError, avanzar

        _sembrar_pasos_setup_ensayo(db_session)  # solo tiene pasos 0, 1, 2
        ahora = datetime.now(timezone.utc)
        sesion = _crear_sesion_en_paso(db_session, paso_actual=99, ahora=ahora)

        with pytest.raises(PasoSesionNoConfiguradoError):
            avanzar(db_session, sesion, respuesta="cualquiera", ahora=ahora)
