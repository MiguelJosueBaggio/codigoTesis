"""E2E sobre el fixture sintetico de C-02 (D-9 capa 2) -- change
`telegram-interaction-layer` (C-13), grupo 7 del tasks.md.

Simula eventos de Telegram (mensajes/respuestas de un usuario) invocando el
CLI real `pipeline.session_cli` por `subprocess` (nunca una llamada de
funcion en memoria -- DD-05/D-9), contra SQLite real (regla dura del
proyecto, C-06). La deteccion de "es foto" y el ruteo por tipo_respuesta
viven en el grafo de n8n (`interaccion_telegram.json`, testeado como DATOS
en `tests/test_n8n_workflows.py`); aca se ejercita el lado Python/CLI de
cada flujo, honestamente, sin fingir un runtime n8n (D-9 heredado de C-08).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline.data_dictionary import load_data_dictionary
from pipeline.db import build_engine, build_session_factory
from pipeline.models import Base, ConfigPasoSesion, EventoSesion, Sesion, UsuarioTelegram
from pipeline.session_seed import sembrar_carga_dato, sembrar_setup_ensayo

PYTHON_BIN = sys.executable
REPO_ROOT = Path(__file__).parent.parent
RUTA_ESCALAMIENTO = REPO_ROOT / "n8n_workflows" / "escalamiento_notificacion.json"
DICCIONARIO_REAL_PATH = REPO_ROOT / "config" / "data_dictionary.json"


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
    return json.loads(resultado.stdout)


def _crear_base(tmp_path) -> str:
    db_path = tmp_path / "telegram_e2e.db"
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


def _sembrar_carga_dato(database_url):
    session, engine = _sesion_directa(database_url)
    try:
        diccionario = load_data_dictionary(DICCIONARIO_REAL_PATH)
        sembrar_carga_dato(session, diccionario)
    finally:
        session.close()
        engine.dispose()


class TestSetupGuiadoCompleto:
    """7.1: setup guiado completo simulando eventos de Telegram contra la
    CLI -> genera data_dictionary.json + analysis_config.yaml validos;
    sesion completada."""

    def test_setup_completo_genera_configs_y_completa_la_sesion(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-ingeniero", "ingeniero")
        _sembrar_setup_ensayo(database_url)

        resuelto = _correr_cli("resolver", {"telegram_user_id": "tg-e2e-ingeniero"}, database_url)
        assert resuelto["autorizado"] is True
        assert resuelto["paso_actual"] == 0

        avance_0 = _correr_cli(
            "avanzar",
            {"telegram_user_id": "tg-e2e-ingeniero", "respuesta": "ENSAYO-E2E-SETUP"},
            database_url,
        )
        assert avance_0["valido"] is True
        assert avance_0["completada"] is False

        variables = json.dumps(
            [
                {
                    "nombre_canonico": "rendimiento_kg_ha",
                    "descripcion": "Rendimiento",
                    "tipo_dato": "real",
                    "obligatorio": True,
                    "rango": {"min": 0, "max": 10000},
                }
            ]
        )
        avance_1 = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-e2e-ingeniero", "respuesta": variables}, database_url
        )
        assert avance_1["valido"] is True

        analisis = json.dumps(
            {
                "formula": "rendimiento_kg_ha ~ C(tratamiento)",
                "tipo": "anova",
                "alpha": 0.05,
                "metodo_comparacion": "tukey",
                "factor": "tratamiento",
            }
        )
        avance_2 = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-e2e-ingeniero", "respuesta": analisis}, database_url
        )
        assert avance_2["valido"] is True
        assert avance_2["completada"] is True

        ruta_dict = tmp_path / "data_dictionary_e2e.json"
        ruta_yaml = tmp_path / "analysis_config_e2e.yaml"
        resultado_finalizar = _correr_cli(
            "finalizar_setup",
            {"session_id": avance_2["session_id"]},
            database_url,
            env_extra={
                "SESSION_CLI_DATA_DICTIONARY_PATH": str(ruta_dict),
                "SESSION_CLI_ANALYSIS_CONFIG_PATH": str(ruta_yaml),
            },
        )

        assert resultado_finalizar["ok"] is True
        assert ruta_dict.exists()
        assert ruta_yaml.exists()

        # El diccionario ensamblado es realmente valido contra el contrato
        # central del pipeline (C-02) -- no solo "parece JSON".
        diccionario = load_data_dictionary(ruta_dict)
        assert "rendimiento_kg_ha" in diccionario

        session, engine = _sesion_directa(database_url)
        try:
            sesion = session.get(Sesion, avance_2["session_id"])
            assert sesion.estado == "completada"
        finally:
            session.close()
            engine.dispose()


class TestCargaPorTextoDeAyudanteAutorizado:
    """7.2: carga por texto de un ayudante autorizado -> valida, almacena,
    converge al pipeline; SQLite real."""

    def test_ayudante_autorizado_carga_dato_por_texto_y_persiste_en_evento_sesion(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-ayudante", "ayudante")
        _sembrar_carga_dato(database_url)

        resuelto = _correr_cli("resolver", {"telegram_user_id": "tg-e2e-ayudante"}, database_url)
        assert resuelto["autorizado"] is True
        assert resuelto["tipo_sesion"] == "carga_dato"

        diccionario = load_data_dictionary(DICCIONARIO_REAL_PATH)
        variables_en_orden = list(diccionario)
        session_id = resuelto["session_id"]

        # Valores validos por variable (segun config/data_dictionary.json),
        # en el MISMO orden en que fueron sembrados como pasos (session_seed).
        valores_validos = {
            "codigo_ensayo": "ENSAYO-E2E-CARGA",
            "ambiente": "Campo Norte",
            "tratamiento": "Testigo",
            "id_unidad": "U-001",
            "variable": "rendimiento_kg_ha",
            "valor": 1234.5,
        }

        ultimo_avance = None
        for variable in variables_en_orden:
            respuesta = valores_validos[variable.nombre_canonico]
            ultimo_avance = _correr_cli(
                "avanzar", {"telegram_user_id": "tg-e2e-ayudante", "respuesta": respuesta}, database_url
            )
            assert ultimo_avance["valido"] is True, ultimo_avance

        assert ultimo_avance["completada"] is True

        # "Converge al pipeline existente": las respuestas acumuladas, una
        # vez ensambladas en una fila, vuelven a validar limpio contra el
        # MISMO motor de validacion que usa el pipeline de ingesta (C-04) --
        # prueba de que el dato entregado por Telegram es compatible.
        import pandas as pd

        from pipeline.validation import validate as validar

        session, engine = _sesion_directa(database_url)
        try:
            sesion = session.get(Sesion, session_id)
            fila = {
                variables_en_orden[int(paso)].nombre_canonico: valor
                for paso, valor in sesion.respuestas_acumuladas.items()
            }
        finally:
            session.close()
            engine.dispose()

        df_fila = pd.DataFrame([fila])
        clave_primaria = ["codigo_ensayo", "ambiente", "tratamiento", "id_unidad", "variable"]
        resultado_validacion = validar(df_fila, diccionario, clave_primaria=clave_primaria)
        assert resultado_validacion.df_validos.shape[0] == 1
        assert resultado_validacion.df_rechazados.shape[0] == 0


class TestFotoSinC11Degrada:
    """7.3: foto sin C-11 -> degrada honestamente a solo-texto, la sesion
    no se rompe. La deteccion 'es_foto' vive en el grafo de n8n (Normalizar
    Evento de Telegram / ¿Es Foto?, testeado como DATOS en
    tests/test_n8n_workflows.py, D-6); este test verifica la propiedad que
    hace segura esa degradacion desde el lado del motor/CLI: NO invocar
    `avanzar` para una foto dejar la sesion exactamente donde estaba
    (idempotente) -- no rompe nada, permite reintentar por texto."""

    def test_no_invocar_avanzar_ante_foto_deja_la_sesion_intacta(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-foto", "ayudante")
        _sembrar_carga_dato(database_url)

        primero = _correr_cli("resolver", {"telegram_user_id": "tg-e2e-foto"}, database_url)
        # Simula: el usuario envia una FOTO -- el workflow real (D-6) la
        # detecta ANTES de construir el payload de la CLI y jamas llama a
        # `avanzar`; aca solo confirmamos que un segundo `resolver` (sin
        # ningun avanzar de por medio) reporta EXACTAMENTE el mismo paso.
        segundo = _correr_cli("resolver", {"telegram_user_id": "tg-e2e-foto"}, database_url)

        assert segundo["session_id"] == primero["session_id"]
        assert segundo["paso_actual"] == primero["paso_actual"]
        assert segundo["prompt"] == primero["prompt"]

        session, engine = _sesion_directa(database_url)
        try:
            sesion = session.get(Sesion, primero["session_id"])
            assert sesion.estado == "abierta"
        finally:
            session.close()
            engine.dispose()


class TestConfirmacionBajoUmbralReanudaYAuditaEnBitacora:
    """7.4: confirmacion bajo umbral -> boton/callback reanuda y registra
    original vs. confirmado en bitacora (RN-OCR-04/RN-AUD-02). El
    `valor_sugerido` viaja en `regla_validacion` del paso (asi lo dejaria un
    futuro C-11/C-09); el valor CONFIRMADO es la `respuesta` que el clic del
    boton entrega a `avanzar` -- session_engine (C-12) ya audita cada
    avance valido en `evento_sesion` (RN-SES-06), sin tocar su contrato."""

    def test_boton_confirmar_registra_original_vs_confirmado(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-confirma", "ingeniero")

        session, engine = _sesion_directa(database_url)
        try:
            session.add(
                ConfigPasoSesion(
                    tipo_sesion="confirmacion_ocr",
                    paso=0,
                    prompt="Leimos 45.2 kg/ha por OCR. ¿Confirmas?",
                    tipo_respuesta="choice",
                    regla_validacion={
                        "tipo_dato": "real",
                        "obligatorio": True,
                        "valor_sugerido": 45.2,
                    },
                )
            )
            session.commit()

            ahora = datetime.now(timezone.utc)
            sesion = Sesion(
                telegram_user_id="tg-e2e-confirma",
                tipo_sesion="confirmacion_ocr",
                paso_actual=0,
                respuestas_acumuladas={},
                estado="abierta",
                created_at=ahora,
                updated_at=ahora,
            )
            session.add(sesion)
            session.commit()
            session_id = sesion.id
        finally:
            session.close()
            engine.dispose()

        # El "clic" en Confirmar reenvia el valor sugerido como confirmado.
        avance = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-e2e-confirma", "respuesta": 45.2}, database_url
        )
        assert avance["valido"] is True

        session, engine = _sesion_directa(database_url)
        try:
            config_paso = (
                session.query(ConfigPasoSesion)
                .filter_by(tipo_sesion="confirmacion_ocr", paso=0)
                .one()
            )
            evento = session.query(EventoSesion).filter_by(session_id=session_id, paso=0).one()

            original = config_paso.regla_validacion["valor_sugerido"]
            confirmado = evento.respuesta

            assert original == 45.2
            assert confirmado == 45.2
            assert original == confirmado  # confirmar: sin correccion
        finally:
            session.close()
            engine.dispose()

    def test_boton_corregir_registra_un_confirmado_distinto_del_original(self, tmp_path):
        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-corrige", "ingeniero")

        session, engine = _sesion_directa(database_url)
        try:
            session.add(
                ConfigPasoSesion(
                    tipo_sesion="confirmacion_ocr",
                    paso=0,
                    prompt="Leimos 45.2 kg/ha por OCR. ¿Confirmas?",
                    tipo_respuesta="choice",
                    regla_validacion={
                        "tipo_dato": "real",
                        "obligatorio": True,
                        "valor_sugerido": 45.2,
                    },
                )
            )
            session.commit()
            ahora = datetime.now(timezone.utc)
            sesion = Sesion(
                telegram_user_id="tg-e2e-corrige",
                tipo_sesion="confirmacion_ocr",
                paso_actual=0,
                respuestas_acumuladas={},
                estado="abierta",
                created_at=ahora,
                updated_at=ahora,
            )
            session.add(sesion)
            session.commit()
            session_id = sesion.id
        finally:
            session.close()
            engine.dispose()

        # El usuario corrige: el valor real leido a mano era distinto.
        avance = _correr_cli(
            "avanzar", {"telegram_user_id": "tg-e2e-corrige", "respuesta": 52.0}, database_url
        )
        assert avance["valido"] is True

        session, engine = _sesion_directa(database_url)
        try:
            config_paso = (
                session.query(ConfigPasoSesion)
                .filter_by(tipo_sesion="confirmacion_ocr", paso=0)
                .one()
            )
            evento = session.query(EventoSesion).filter_by(session_id=session_id, paso=0).one()

            assert config_paso.regla_validacion["valor_sugerido"] == 45.2
            assert evento.respuesta == 52.0
            assert config_paso.regla_validacion["valor_sugerido"] != evento.respuesta
        finally:
            session.close()
            engine.dispose()


class TestRbacRechazaAyudanteEnSetup:
    """7.5: RBAC rechaza a un ayudante intentando `setup_ensayo`
    (fail-closed) y registra el rechazo -- defensa en profundidad a nivel
    e2e: aun si una sesion `setup_ensayo` abierta quedara asociada (por
    inconsistencia de datos) a un `telegram_user_id` mapeado como ayudante,
    `resolver` la rechaza sin crear ni avanzar nada."""

    def test_ayudante_con_sesion_setup_abierta_es_rechazado_y_auditado(self, tmp_path):
        from pipeline.models import RechazoAutorizacion

        database_url = _crear_base(tmp_path)
        _crear_usuario(database_url, "tg-e2e-ayudante-setup", "ayudante")
        _sembrar_setup_ensayo(database_url)

        session, engine = _sesion_directa(database_url)
        try:
            ahora = datetime.now(timezone.utc)
            session.add(
                Sesion(
                    telegram_user_id="tg-e2e-ayudante-setup",
                    tipo_sesion="setup_ensayo",
                    paso_actual=0,
                    respuestas_acumuladas={},
                    estado="abierta",
                    created_at=ahora,
                    updated_at=ahora,
                )
            )
            session.commit()
        finally:
            session.close()
            engine.dispose()

        respuesta = _correr_cli(
            "resolver", {"telegram_user_id": "tg-e2e-ayudante-setup"}, database_url
        )

        assert respuesta["autorizado"] is False
        assert respuesta["mensaje"]

        session, engine = _sesion_directa(database_url)
        try:
            rechazos = (
                session.query(RechazoAutorizacion)
                .filter_by(telegram_user_id="tg-e2e-ayudante-setup", accion="setup_ensayo")
                .all()
            )
            assert len(rechazos) == 1
            assert rechazos[0].motivo == "rol_sin_permiso"
        finally:
            session.close()
            engine.dispose()


class TestEscalamientoProduceElPayloadDeTelegram:
    """7.6: fallo persistente produce el payload de escalamiento de
    Telegram -- verificacion honesta (D-9): sin runtime n8n, se comprueba
    que el TEMPLATE del mensaje habilitado (grupo 6) referencia exactamente
    los campos que 'Registrar Payload de Escalamiento' arma a partir del
    Error Trigger (etapa/run_id/mensaje_error/workflow_fallido, D-6/D-7 de
    n8n-orchestration-workflows), sustituyendo esas expresiones por un
    payload sintetico igual al que produciria un fallo persistente real."""

    def test_template_del_mensaje_renderiza_con_el_payload_de_escalamiento(self):
        workflow = json.loads(RUTA_ESCALAMIENTO.read_text(encoding="utf-8"))
        nodo_telegram = next(
            n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.telegram"
        )
        assert nodo_telegram.get("disabled") is not True

        payload_sintetico = {
            "workflow_fallido": "Pipeline Principal - Flujo 1",
            "run_id": "20260704T000000Z_deadbeef",
            "mensaje_error": "Fallo persistente en 'persistence' tras agotar reintentos",
        }

        texto = nodo_telegram["parameters"]["text"]
        for campo, valor in payload_sintetico.items():
            texto = texto.replace("{{$json." + campo + "}}", valor)

        assert "{{" not in texto  # todas las expresiones se pudieron resolver
        for valor in payload_sintetico.values():
            assert valor in texto
