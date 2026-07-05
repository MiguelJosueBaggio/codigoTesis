"""E2E de la CLI interna del motor de sesiones (`pipeline.session_cli`) --
change `telegram-interaction-layer` (C-13), grupo 3 del tasks.md, D-9 capa 2.

Mismo criterio que `tests/test_cli_chain.py` (C-08): ejecuta el CLI real por
`subprocess` (nunca una llamada de funcion en memoria -- eso no probaria que
n8n pueda invocarlo por CLI, DD-05) contra SQLite real (nunca mock, regla
dura del proyecto), verificando el contrato JSON stdin/stdout con exit code
SIEMPRE 0 (D-2).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.db import build_engine, build_session_factory
from pipeline.models import Base, Sesion, UsuarioTelegram
from pipeline.session_seed import sembrar_setup_ensayo

PYTHON_BIN = sys.executable
REPO_ROOT = Path(__file__).parent.parent


def _correr_cli(subcomando: str, payload: dict, database_url: str, env_extra: dict = None) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    if env_extra:
        env.update(env_extra)
    resultado = subprocess.run(
        [PYTHON_BIN, "-m", "pipeline.session_cli", subcomando],
        input=json.dumps(payload),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, (
        f"session_cli DEBE salir siempre 0 (salio {resultado.returncode}): {resultado.stderr}"
    )
    assert "TELEGRAM_BOT_TOKEN" not in resultado.stdout
    return json.loads(resultado.stdout)


def _crear_base(tmp_path) -> str:
    db_path = tmp_path / "session_cli_e2e.db"
    database_url = f"sqlite:///{db_path}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return database_url


def _sesion_directa(database_url):
    engine = build_engine(database_url)
    factory = build_session_factory(engine)
    return factory(), engine


def _crear_usuario(database_url, telegram_user_id, rol, ensayo_id=None):
    session, engine = _sesion_directa(database_url)
    ahora = datetime.now(timezone.utc)
    try:
        session.add(
            UsuarioTelegram(
                telegram_user_id=telegram_user_id,
                rol=rol,
                ensayo_id=ensayo_id,
                created_at=ahora,
                updated_at=ahora,
            )
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()


def _sembrar_setup_ensayo(database_url):
    session, engine = _sesion_directa(database_url)
    try:
        sembrar_setup_ensayo(session)
    finally:
        session.close()
        engine.dispose()


class TestResolver:
    def test_resolver_devuelve_prompt_del_paso_actual(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-ing-cli-001", "ingeniero")
        _sembrar_setup_ensayo(database_url)

        respuesta = _correr_cli("resolver", {"telegram_user_id": "tg-ing-cli-001"}, database_url)

        assert respuesta["autorizado"] is True
        assert respuesta["tipo_sesion"] == "setup_ensayo"
        assert respuesta["paso_actual"] == 0
        assert respuesta["prompt"]
        assert respuesta["tipo_respuesta"] == "texto"

    def test_resolver_usuario_no_mapeado_es_rechazado(self, tmp_path):
        database_url = _crear_base(tmp_path)

        respuesta = _correr_cli("resolver", {"telegram_user_id": "tg-fantasma"}, database_url)

        assert respuesta["autorizado"] is False
        assert respuesta["mensaje"]


class TestAvanzar:
    def test_respuesta_invalida_no_avanza_y_pide_reintento(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-ing-cli-002", "ingeniero")
        _sembrar_setup_ensayo(database_url)
        _correr_cli("resolver", {"telegram_user_id": "tg-ing-cli-002"}, database_url)

        # paso 0 exige texto_libre obligatorio -- null viola "no nulo".
        respuesta = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-ing-cli-002", "respuesta": None}, database_url
        )

        assert respuesta["valido"] is False
        assert respuesta["mensaje_reintento"]
        assert respuesta["completada"] is False

    def test_respuesta_valida_avanza_al_paso_siguiente(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-ing-cli-003", "ingeniero")
        _sembrar_setup_ensayo(database_url)
        _correr_cli("resolver", {"telegram_user_id": "tg-ing-cli-003"}, database_url)

        respuesta = _correr_cli(
            "avanzar",
            {"telegram_user_id": "tg-ing-cli-003", "respuesta": "ENSAYO-CLI-001"},
            database_url,
        )

        assert respuesta["valido"] is True
        assert respuesta["completada"] is False
        assert respuesta["prompt"]

    def test_usuario_no_autorizado_en_avanzar_da_json_de_rechazo_exit_0(self, tmp_path):
        database_url = _crear_base(tmp_path)

        respuesta = _correr_cli(
            "avanzar",
            {"telegram_user_id": "tg-fantasma-2", "respuesta": "x"},
            database_url,
        )

        assert respuesta["autorizado"] is False
        assert respuesta["mensaje"]


class TestExpirar:
    def test_expira_sesiones_vencidas_y_respeta_las_vigentes(self, tmp_path):
        database_url = _crear_base(tmp_path)
        session, engine = _sesion_directa(database_url)
        try:
            hace_25h = datetime.now(timezone.utc) - timedelta(hours=25)
            vigente = datetime.now(timezone.utc)
            session.add(
                Sesion(
                    telegram_user_id="tg-vencida",
                    tipo_sesion="carga_dato",
                    paso_actual=0,
                    respuestas_acumuladas={},
                    estado="abierta",
                    created_at=hace_25h,
                    updated_at=hace_25h,
                )
            )
            session.add(
                Sesion(
                    telegram_user_id="tg-vigente",
                    tipo_sesion="carga_dato",
                    paso_actual=0,
                    respuestas_acumuladas={},
                    estado="abierta",
                    created_at=vigente,
                    updated_at=vigente,
                )
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()

        respuesta = _correr_cli("expirar", {}, database_url)

        assert respuesta["expiradas"] == 1


class TestFinalizarSetup:
    def test_finalizar_setup_respeta_override_de_rutas_por_env(self, tmp_path):
        """El subcomando `finalizar_setup` NUNCA debe tocar los archivos
        reales de config/ durante un test -- las variables de entorno
        `SESSION_CLI_DATA_DICTIONARY_PATH`/`SESSION_CLI_ANALYSIS_CONFIG_PATH`
        son el unico mecanismo para redirigirlo en la suite e2e (D-9)."""
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-ing-finalizar", "ingeniero")
        _sembrar_setup_ensayo(database_url)
        _correr_cli("resolver", {"telegram_user_id": "tg-ing-finalizar"}, database_url)
        _correr_cli(
            "avanzar", {"telegram_user_id": "tg-ing-finalizar", "respuesta": "ENSAYO-E2E"}, database_url
        )
        variables = (
            '[{"nombre_canonico": "altura", "descripcion": "Altura", '
            '"tipo_dato": "real", "obligatorio": true}]'
        )
        _correr_cli(
            "avanzar", {"telegram_user_id": "tg-ing-finalizar", "respuesta": variables}, database_url
        )
        analisis = '{"formula": "altura ~ C(tratamiento)"}'
        respuesta_avance = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-ing-finalizar", "respuesta": analisis}, database_url
        )
        assert respuesta_avance["completada"] is True

        ruta_dict = tmp_path / "override_dict.json"
        ruta_yaml = tmp_path / "override_analysis.yaml"
        respuesta = _correr_cli(
            "finalizar_setup",
            {"session_id": respuesta_avance["session_id"]},
            database_url,
            env_extra={
                "SESSION_CLI_DATA_DICTIONARY_PATH": str(ruta_dict),
                "SESSION_CLI_ANALYSIS_CONFIG_PATH": str(ruta_yaml),
            },
        )

        assert respuesta["ok"] is True
        assert ruta_dict.exists()
        assert ruta_yaml.exists()


class TestTipoSesionSinPasos:
    def test_tipo_sesion_sin_pasos_es_fail_closed_heredado_del_motor(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-ing-sin-pasos", "ingeniero")
        # Deliberadamente NO se siembra config_paso_sesion.

        respuesta = _correr_cli("resolver", {"telegram_user_id": "tg-ing-sin-pasos"}, database_url)

        assert respuesta["autorizado"] is True
        assert respuesta["error"]
