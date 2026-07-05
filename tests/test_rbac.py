"""Tests de `pipeline.rbac.resolver_rol_y_autorizar` -- change
`telegram-interaction-layer` (C-13), grupo 2 del tasks.md.

Fail-closed (KB 03 §RBAC): SQLite real via `db_session` (nunca mock --
regla dura C-06). La resolucion de rol y la autorizacion ocurren en Python,
nunca en el grafo de n8n (Decision 1 del design).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pipeline.models import Ensayo, RechazoAutorizacion, UsuarioTelegram
from pipeline.rbac import resolver_rol_y_autorizar


def _crear_usuario(db_session, telegram_user_id, rol, ensayo_id=None):
    ahora = datetime.now(timezone.utc)
    usuario = UsuarioTelegram(
        telegram_user_id=telegram_user_id,
        rol=rol,
        ensayo_id=ensayo_id,
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_usuario_no_mapeado_es_rechazado_sin_filtrar_existencia(db_session):
    ahora = datetime.now(timezone.utc)

    resultado = resolver_rol_y_autorizar(db_session, "tg-desconocido", "carga_dato", ahora)

    assert resultado.autorizado is False
    assert resultado.mensaje == "Usuario no autorizado."
    assert resultado.rol is None


def test_ayudante_intenta_setup_ensayo_es_rechazado(db_session):
    ahora = datetime.now(timezone.utc)
    _crear_usuario(db_session, "tg-ayu-001", "ayudante")

    resultado = resolver_rol_y_autorizar(db_session, "tg-ayu-001", "setup_ensayo", ahora)

    assert resultado.autorizado is False
    assert resultado.mensaje == "Usuario no autorizado."


def test_ingeniero_autorizado_para_setup_ensayo(db_session):
    ahora = datetime.now(timezone.utc)
    _crear_usuario(db_session, "tg-ing-001", "ingeniero")

    resultado = resolver_rol_y_autorizar(db_session, "tg-ing-001", "setup_ensayo", ahora)

    assert resultado.autorizado is True
    assert resultado.rol == "ingeniero"


def test_ayudante_autorizado_para_carga_dato(db_session):
    ahora = datetime.now(timezone.utc)
    _crear_usuario(db_session, "tg-ayu-002", "ayudante")

    resultado = resolver_rol_y_autorizar(db_session, "tg-ayu-002", "carga_dato", ahora)

    assert resultado.autorizado is True
    assert resultado.rol == "ayudante"


class TestRechazoQuedaAuditado:
    def test_rechazo_por_usuario_no_mapeado_deja_evento_auditable(self, db_session):
        ahora = datetime.now(timezone.utc)

        resolver_rol_y_autorizar(db_session, "tg-sin-mapear", "carga_dato", ahora)

        eventos = db_session.query(RechazoAutorizacion).all()
        assert len(eventos) == 1
        assert eventos[0].telegram_user_id == "tg-sin-mapear"
        assert eventos[0].accion == "carga_dato"
        assert eventos[0].motivo == "usuario_no_mapeado"

    def test_rechazo_por_rol_sin_permiso_deja_evento_auditable(self, db_session):
        ahora = datetime.now(timezone.utc)
        _crear_usuario(db_session, "tg-ayu-003", "ayudante")

        resolver_rol_y_autorizar(db_session, "tg-ayu-003", "setup_ensayo", ahora)

        eventos = db_session.query(RechazoAutorizacion).all()
        assert len(eventos) == 1
        assert eventos[0].motivo == "rol_sin_permiso"


class TestTriangulacionCasosLimite:
    def test_ayudante_acotado_por_ensayo_id_distinto_es_rechazado(self, db_session):
        ahora = datetime.now(timezone.utc)
        ensayo_propio = Ensayo(codigo="ENSAYO-RBAC-A", created_at=ahora)
        ensayo_otro = Ensayo(codigo="ENSAYO-RBAC-B", created_at=ahora)
        db_session.add_all([ensayo_propio, ensayo_otro])
        db_session.flush()
        _crear_usuario(db_session, "tg-ayu-004", "ayudante", ensayo_id=ensayo_propio.id)

        resultado = resolver_rol_y_autorizar(
            db_session, "tg-ayu-004", "carga_dato", ahora, ensayo_id=ensayo_otro.id
        )

        assert resultado.autorizado is False
        eventos = db_session.query(RechazoAutorizacion).all()
        assert eventos[-1].motivo == "ensayo_no_autorizado"

    def test_ayudante_acotado_por_su_propio_ensayo_es_autorizado(self, db_session):
        ahora = datetime.now(timezone.utc)
        ensayo_propio = Ensayo(codigo="ENSAYO-RBAC-C", created_at=ahora)
        db_session.add(ensayo_propio)
        db_session.flush()
        _crear_usuario(db_session, "tg-ayu-005", "ayudante", ensayo_id=ensayo_propio.id)

        resultado = resolver_rol_y_autorizar(
            db_session, "tg-ayu-005", "carga_dato", ahora, ensayo_id=ensayo_propio.id
        )

        assert resultado.autorizado is True

    def test_accion_desconocida_es_fail_closed_para_rol_valido(self, db_session):
        ahora = datetime.now(timezone.utc)
        _crear_usuario(db_session, "tg-ing-002", "ingeniero")

        resultado = resolver_rol_y_autorizar(db_session, "tg-ing-002", "borrar_todo", ahora)

        assert resultado.autorizado is False
        eventos = db_session.query(RechazoAutorizacion).all()
        assert eventos[-1].motivo == "accion_desconocida"
