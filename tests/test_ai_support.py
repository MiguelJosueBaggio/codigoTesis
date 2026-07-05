"""Tests de `pipeline/ai_support.py` -- change `ai-support-standardization`
(C-09), Epica 6 (US-006).

Cubre las tres capas del componente (D-1 del design): generacion pura
(fuzzy/estadistica), provider opcional (mock/Ollama) y aplicacion con gate
humano (RN-IA-01/02/03) + el productor de `confirmacion_ia` (D-6). SQLite
REAL via los fixtures `db_session`/`db_engine` de `conftest.py` para los
tests de persistencia/aplicacion (regla dura del proyecto, DD-03).
"""

from __future__ import annotations

import socket

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pipeline.ai_support import (
    METODO_ZSCORE,
    ContextoSugerencia,
    MockProvider,
    OllamaProvider,
    Sugerencia,
    SugerenciaNoAprobadaError,
    TIPO_ANOMALIA,
    TIPO_LEXICA,
    TIPO_SESION_CONFIRMACION_IA,
    _construir_prompt_ollama,
    _parsear_sugerencias_ollama,
    aplicar_sugerencia,
    aprobar_sugerencia,
    crear_confirmacion_ia,
    detectar_anomalias,
    generar_sugerencias,
    rechazar_sugerencia,
    resolver_confirmacion_ia,
    sugerir_estandarizacion,
)
from pipeline.models import ConfigPasoSesion, Sesion, SugerenciaIA
from pipeline.persistence import RunMetadata
from pipeline.session_engine import avanzar
from pipeline.transformation import transform


# --- Grupo 2: estandarizacion lexica por fuzzy matching (D-2) ---------------


def test_variante_lexica_bajo_el_umbral_se_sugiere_como_canonica(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    sugerencias = sugerir_estandarizacion(dataset_ai_support_categorico_df, diccionario_ai_support)

    por_original = {s.valor_original: s for s in sugerencias if s.columna == "tratamiento"}
    # Valor esperado tomado del diccionario (C-02), no computado por el codigo bajo prueba.
    assert por_original["testigo "].valor_sugerido == "Testigo"
    assert por_original["testigo "].tipo == TIPO_LEXICA
    assert por_original["testigo "].score >= 85.0


def test_sugerir_estandarizacion_no_muta_el_dataframe(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    original = dataset_ai_support_categorico_df.copy(deep=True)

    sugerir_estandarizacion(dataset_ai_support_categorico_df, diccionario_ai_support)

    pd.testing.assert_frame_equal(dataset_ai_support_categorico_df, original)


def test_valor_ya_canonico_no_genera_sugerencia(diccionario_ai_support):
    df = pd.DataFrame({"tratamiento": ["Testigo", "Fertilizado"]})

    sugerencias = sugerir_estandarizacion(df, diccionario_ai_support)

    assert sugerencias == []


def test_valor_demasiado_distinto_no_se_sugiere(diccionario_ai_support):
    df = pd.DataFrame({"tratamiento": ["Trigo"]})  # score fuzzy ~67, bajo el umbral 85

    sugerencias = sugerir_estandarizacion(df, diccionario_ai_support)

    assert sugerencias == []


def test_columna_sin_valores_admisibles_se_ignora(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    sugerencias = sugerir_estandarizacion(dataset_ai_support_categorico_df, diccionario_ai_support)

    assert all(s.columna != "id_unidad" for s in sugerencias)


def test_umbral_configurable_cambia_el_resultado(diccionario_ai_support):
    df = pd.DataFrame({"tratamiento": ["Tstg"]})  # score fuzzy ~73

    sin_sugerencia = sugerir_estandarizacion(df, diccionario_ai_support, umbral=85.0)
    con_sugerencia = sugerir_estandarizacion(df, diccionario_ai_support, umbral=70.0)

    assert sin_sugerencia == []
    assert len(con_sugerencia) == 1
    assert con_sugerencia[0].valor_sugerido == "Testigo"


# --- Grupo 3: deteccion de anomalias estadisticas (D-3) ---------------------


def test_outlier_iqr_se_marca_para_revision(dataset_ai_support_numerico_df, diccionario_ai_support):
    serie = dataset_ai_support_numerico_df["valor"]
    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    iqr = q3 - q1
    limite_superior_esperado = q3 + 1.5 * iqr  # referencia calculada a mano, no via el codigo bajo prueba
    assert 500.0 > limite_superior_esperado  # confirma que el fixture SI es outlier

    sugerencias = detectar_anomalias(dataset_ai_support_numerico_df, diccionario_ai_support)

    assert len(sugerencias) == 1
    anomalia = sugerencias[0]
    assert anomalia.columna == "valor"
    assert anomalia.valor_original == 500.0
    assert anomalia.valor_sugerido is None
    assert anomalia.tipo == TIPO_ANOMALIA
    assert anomalia.score > 0


def test_valores_dentro_de_rango_no_generan_anomalias(diccionario_ai_support):
    df = pd.DataFrame({"valor": [100.0, 101.0, 99.0, 100.5, 99.5, 100.2]})

    sugerencias = detectar_anomalias(df, diccionario_ai_support)

    assert sugerencias == []


def test_metodo_zscore_como_alternativa(diccionario_ai_support):
    # n=13 con baja dispersion salvo un outlier -- con muestras chicas el
    # z-score maximo teorico es sqrt(n-1); hace falta suficiente n para que
    # el outlier supere el umbral default (3.0) sin ser un valor extremo.
    df = pd.DataFrame(
        {
            "valor": [
                100.0, 101.0, 99.0, 100.5, 99.5, 100.2, 99.8,
                100.1, 99.9, 100.3, 99.7, 100.0, 180.0,
            ]
        }
    )

    sugerencias = detectar_anomalias(df, diccionario_ai_support, metodo=METODO_ZSCORE)

    assert len(sugerencias) == 1
    assert sugerencias[0].valor_original == 180.0


def test_detectar_anomalias_maneja_nan_sin_propagar(diccionario_ai_support):
    df = pd.DataFrame({"valor": [100.0, 101.0, 99.0, None, 100.5, None, 99.5, 500.0]})

    sugerencias = detectar_anomalias(df, diccionario_ai_support)

    # No debe levantar excepcion ni incluir NaN como "anomalia"; el outlier real se detecta igual.
    assert all(s.valor_original == 500.0 for s in sugerencias)
    assert len(sugerencias) == 1


def test_variable_sin_datos_numericos_suficientes_no_genera_error(diccionario_ai_support):
    df = pd.DataFrame({"valor": [100.0, None, None]})  # 1 dato numerico real

    sugerencias = detectar_anomalias(df, diccionario_ai_support)

    assert sugerencias == []


def test_columna_categorica_se_ignora_en_deteccion_de_anomalias(diccionario_ai_support):
    df = pd.DataFrame({"tratamiento": ["Testigo", "Fertilizado", "Testigo", "Fertilizado"]})

    sugerencias = detectar_anomalias(df, diccionario_ai_support)

    assert sugerencias == []


def test_metodo_de_anomalia_desconocido_levanta_value_error(
    dataset_ai_support_numerico_df, diccionario_ai_support
):
    with pytest.raises(ValueError):
        detectar_anomalias(dataset_ai_support_numerico_df, diccionario_ai_support, metodo="no-existe")


def test_zscore_con_desviacion_estandar_cero_no_genera_error_ni_anomalias(diccionario_ai_support):
    df = pd.DataFrame({"valor": [100.0, 100.0, 100.0, 100.0, 100.0]})

    sugerencias = detectar_anomalias(df, diccionario_ai_support, metodo=METODO_ZSCORE)

    assert sugerencias == []


# --- Grupo 4: SugerenciaProvider + MockProvider (D-4) -----------------------


def test_mock_provider_esta_siempre_disponible_y_es_deterministico():
    inyectadas = [
        Sugerencia(columna="x", valor_original="a", valor_sugerido="b", score=99.0, tipo=TIPO_LEXICA)
    ]
    provider = MockProvider(inyectadas)

    assert provider.esta_disponible() is True
    assert provider.sugerir(contexto=None) == inyectadas
    # Determinista: invocarlo de nuevo (sin red) devuelve exactamente lo mismo.
    assert provider.sugerir(contexto=None) == inyectadas


def test_componente_corre_solo_fuzzy_con_mock_por_defecto(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    sugerencias = generar_sugerencias(dataset_ai_support_categorico_df, diccionario_ai_support)

    assert all(s.origen in ("fuzzy", "estadistica") for s in sugerencias)


def test_generar_sugerencias_combina_provider_sin_duplicar(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    extra = Sugerencia(
        columna="tratamiento", valor_original="Testigoo", valor_sugerido="Testigo", score=93.0, tipo=TIPO_LEXICA, origen="llm"
    )
    provider = MockProvider([extra])

    sugerencias = generar_sugerencias(
        dataset_ai_support_categorico_df, diccionario_ai_support, provider=provider
    )

    fuzzy_solo = sugerir_estandarizacion(dataset_ai_support_categorico_df, diccionario_ai_support)
    assert len(sugerencias) == len(fuzzy_solo) + 1
    assert extra in sugerencias


def test_provider_que_devuelve_vacio_no_cambia_resultado_fuzzy(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    provider_vacio = MockProvider([])

    con_provider = generar_sugerencias(
        dataset_ai_support_categorico_df, diccionario_ai_support, provider=provider_vacio
    )
    sin_provider = generar_sugerencias(dataset_ai_support_categorico_df, diccionario_ai_support)

    assert con_provider == sin_provider


# --- Grupo 5: OllamaProvider de referencia (D-4) -----------------------------


def _puerto_cerrado() -> int:
    """Encuentra un puerto TCP local que NO tiene ningun servidor escuchando
    (para probar degradacion honesta con una URL real, sin mockear
    disponibilidad -- obs #224 / D-4)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def test_ollama_provider_degrada_honestamente_sin_servidor():
    puerto_cerrado = _puerto_cerrado()
    provider = OllamaProvider(base_url=f"http://127.0.0.1:{puerto_cerrado}", ping_timeout=0.5)

    assert provider.esta_disponible() is False
    assert provider.sugerir(contexto=None) == []


def test_construir_prompt_ollama_incluye_solo_columnas_categoricas(diccionario_ai_support):
    contexto = ContextoSugerencia(df=pd.DataFrame(), diccionario=diccionario_ai_support)

    prompt = _construir_prompt_ollama(contexto)

    assert "tratamiento" in prompt
    assert "ambiente" in prompt
    assert "id_unidad" not in prompt  # texto_libre, sin valores_admisibles


def test_parsear_sugerencias_ollama_respuesta_valida():
    respuesta = (
        '[{"columna": "tratamiento", "valor_original": "Testigoo", '
        '"valor_sugerido": "Testigo", "score": 93.0}]'
    )

    sugerencias = _parsear_sugerencias_ollama(respuesta)

    assert len(sugerencias) == 1
    assert sugerencias[0].columna == "tratamiento"
    assert sugerencias[0].valor_sugerido == "Testigo"
    assert sugerencias[0].origen == "llm"


def test_parsear_sugerencias_ollama_json_invalido_devuelve_vacio():
    assert _parsear_sugerencias_ollama("esto no es json") == []


def test_parsear_sugerencias_ollama_no_lista_devuelve_vacio():
    assert _parsear_sugerencias_ollama('{"no": "es una lista"}') == []


def test_parsear_sugerencias_ollama_item_incompleto_se_descarta():
    respuesta = '[{"columna": "tratamiento"}]'  # falta valor_original

    assert _parsear_sugerencias_ollama(respuesta) == []


@pytest.mark.skipif(
    True,
    reason=(
        "Requiere un Ollama real corriendo en OLLAMA_BASE_URL; se activa "
        "manualmente en una maquina con Ollama instalado (D-4, obs #224: "
        "NUNCA mockear disponibilidad)."
    ),
)
def test_ollama_provider_real_produce_sugerencias_que_entran_al_gate(
    dataset_ai_support_categorico_df, diccionario_ai_support
):
    from pipeline.ai_support import ContextoSugerencia

    provider = OllamaProvider()
    assert provider.esta_disponible() is True

    contexto = ContextoSugerencia(df=dataset_ai_support_categorico_df, diccionario=diccionario_ai_support)
    sugerencias = provider.sugerir(contexto)

    assert all(s.tipo == TIPO_LEXICA for s in sugerencias)


# --- Grupo 6: persistencia de SugerenciaIA (SQLite real) --------------------


def test_persistir_y_recuperar_sugerencia_ia_con_todos_sus_campos(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="tratamiento",
        valor_original="testigo ",
        valor_sugerido="Testigo",
        tipo="lexica",
        score=92.3,
        origen="fuzzy",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    db_session.commit()

    recuperada = db_session.execute(
        select(SugerenciaIA).where(SugerenciaIA.id == sugerencia.id)
    ).scalar_one()

    assert recuperada.columna == "tratamiento"
    assert recuperada.valor_original == "testigo "
    assert recuperada.valor_sugerido == "Testigo"
    assert recuperada.tipo == "lexica"
    assert recuperada.origen == "fuzzy"
    assert recuperada.estado == "generada"
    assert recuperada.ejecucion_id is None
    assert recuperada.justificacion is None


def test_check_constraint_tipo_invalido_es_rechazado(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="x",
        valor_original="a",
        valor_sugerido="b",
        tipo="no-valido",
        score=1.0,
        origen="fuzzy",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_check_constraint_estado_invalido_es_rechazado(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="x",
        valor_original="a",
        valor_sugerido="b",
        tipo="lexica",
        score=1.0,
        origen="fuzzy",
        estado="no-valido",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_check_constraint_origen_invalido_es_rechazado(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="x",
        valor_original="a",
        valor_sugerido="b",
        tipo="lexica",
        score=1.0,
        origen="no-valido",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_valor_sugerido_null_admitido_para_anomalia(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="valor",
        valor_original=500.0,
        valor_sugerido=None,
        tipo="anomalia",
        score=3.5,
        origen="estadistica",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    db_session.commit()

    recuperada = db_session.execute(
        select(SugerenciaIA).where(SugerenciaIA.id == sugerencia.id)
    ).scalar_one()
    assert recuperada.valor_sugerido is None


def test_ejecucion_id_null_hasta_aplicar(db_session):
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    sugerencia = SugerenciaIA(
        columna="tratamiento",
        valor_original="testigo ",
        valor_sugerido="Testigo",
        tipo="lexica",
        score=92.3,
        origen="fuzzy",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sugerencia)
    db_session.commit()

    assert sugerencia.ejecucion_id is None


# --- Grupo 7: ciclo de aprobacion (aplicar/rechazar, RN-IA-01/02/03) --------


def _sugerencia_pendiente(session, **overrides) -> SugerenciaIA:
    import datetime as dt

    ahora = dt.datetime.now(dt.timezone.utc)
    defaults = dict(
        columna="tratamiento",
        valor_original="testigo ",
        valor_sugerido="Testigo",
        tipo="lexica",
        score=92.3,
        origen="fuzzy",
        estado="generada",
        created_at=ahora,
        updated_at=ahora,
    )
    defaults.update(overrides)
    sugerencia = SugerenciaIA(**defaults)
    session.add(sugerencia)
    session.commit()
    return sugerencia


def _dataset_con_variante(dataset_persistencia_df: pd.DataFrame) -> pd.DataFrame:
    df = dataset_persistencia_df.copy()
    df.loc[df["tratamiento"] == "Testigo", "tratamiento"] = "testigo "
    return df


def test_aplicar_sugerencia_no_aprobada_falla_explicito_y_no_modifica_dataset(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    df = _dataset_con_variante(dataset_persistencia_df)
    original = df.copy(deep=True)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    run_metadata = _run_metadata(tmp_path)

    with pytest.raises(SugerenciaNoAprobadaError):
        aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)

    pd.testing.assert_frame_equal(df, original)


def test_aplicar_sugerencia_rechazada_falla_explicito(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    df = _dataset_con_variante(dataset_persistencia_df)
    sugerencia = _sugerencia_pendiente(db_session, estado="rechazada")
    run_metadata = _run_metadata(tmp_path)

    with pytest.raises(SugerenciaNoAprobadaError):
        aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)


def test_sugerencia_aprobada_se_refleja_en_dataset_y_en_bitacora(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    from pipeline.models import BitacoraTransformacion, Observacion

    df = _dataset_con_variante(dataset_persistencia_df)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    aprobar_sugerencia(sugerencia, "Confirmado por el ingeniero de campo", db_session)
    run_metadata = _run_metadata(tmp_path)

    ejecucion = aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)

    assert sugerencia.estado == "aplicada"
    assert sugerencia.ejecucion_id == ejecucion.id

    bitacora = db_session.execute(
        select(BitacoraTransformacion).where(BitacoraTransformacion.ejecucion_id == ejecucion.id)
    ).scalars().all()
    assert any(b.tipo == "estandarizacion_categorica" for b in bitacora)

    observaciones = db_session.execute(
        select(Observacion).where(Observacion.ejecucion_id == ejecucion.id)
    ).scalars().all()
    assert len(observaciones) == len(df)


def test_rechazar_sugerencia_no_modifica_el_dataset(
    db_session, dataset_persistencia_df, diccionario_ai_support
):
    df = _dataset_con_variante(dataset_persistencia_df)
    original = df.copy(deep=True)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")

    resultado = rechazar_sugerencia(sugerencia, "No corresponde, es un tratamiento nuevo", db_session)

    assert resultado.estado == "rechazada"
    assert resultado.justificacion == "No corresponde, es un tratamiento nuevo"
    pd.testing.assert_frame_equal(df, original)


def test_anomalia_con_valor_corregido_por_el_humano_se_aplica_como_lexica(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    df = dataset_persistencia_df.copy()
    valor_original_anomalo = df["valor"].iloc[0]
    sugerencia = _sugerencia_pendiente(
        db_session,
        columna="valor",
        valor_original=valor_original_anomalo,
        valor_sugerido=3100.0,  # el humano aporta el valor corregido
        tipo="anomalia",
        origen="estadistica",
        estado="generada",
    )
    aprobar_sugerencia(sugerencia, "Error de tipeo confirmado por el ingeniero", db_session)
    run_metadata = _run_metadata(tmp_path)

    ejecucion = aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)

    assert sugerencia.estado == "aplicada"
    assert sugerencia.ejecucion_id == ejecucion.id


def test_aprobar_sugerencia_rollback_no_deja_estado_a_medias(db_session, monkeypatch):
    """Mismo patron que `test_session_engine.test_rollback_de_la_transaccion_no_deja_evento_huerfano`
    (C-12): simula un fallo de infraestructura en el commit para verificar
    que `aprobar_sugerencia` revierte y no deja el estado a medio escribir."""
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")

    def _commit_que_falla():
        db_session.rollback()
        raise RuntimeError("fallo simulado de infraestructura")

    monkeypatch.setattr(db_session, "commit", _commit_que_falla)

    with pytest.raises(RuntimeError):
        aprobar_sugerencia(sugerencia, "justificacion", db_session)

    monkeypatch.undo()
    recargada = db_session.get(SugerenciaIA, sugerencia.id)
    assert recargada.estado == "generada"
    assert recargada.justificacion is None


def test_rechazar_sugerencia_rollback_no_deja_estado_a_medias(db_session, monkeypatch):
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")

    def _commit_que_falla():
        db_session.rollback()
        raise RuntimeError("fallo simulado de infraestructura")

    monkeypatch.setattr(db_session, "commit", _commit_que_falla)

    with pytest.raises(RuntimeError):
        rechazar_sugerencia(sugerencia, "justificacion", db_session)

    monkeypatch.undo()
    recargada = db_session.get(SugerenciaIA, sugerencia.id)
    assert recargada.estado == "generada"


def test_aplicar_sugerencia_rollback_del_commit_final_no_deja_estado_a_medias(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path, monkeypatch
):
    """`persist()` de C-06 administra su PROPIA transaccion (`with session
    .begin():`), que NO pasa por el atributo `session.commit` (confirmado
    empiricamente: parchear `db_session.commit` no intercepta el commit
    interno de `persist`) -- asi que el UNICO llamado a `session.commit()` en
    todo `aplicar_sugerencia` es el commit final que fija `estado`/
    `ejecucion_id` de la sugerencia. Si ese commit falla, `aplicar_sugerencia`
    propaga la excepcion y revierte (documentado en la nota de atomicidad del
    docstring): el dataset y la `Ejecucion` de `persist()` ya quedaron
    persistidos (limitacion conocida de reusar `persist` sin reescribirlo),
    pero la `SugerenciaIA` NO queda marcada `aplicada` a medias."""
    df = _dataset_con_variante(dataset_persistencia_df)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    aprobar_sugerencia(sugerencia, "justificacion", db_session)
    run_metadata = _run_metadata(tmp_path)

    def _commit_que_falla():
        db_session.rollback()
        raise RuntimeError("fallo simulado de infraestructura")

    monkeypatch.setattr(db_session, "commit", _commit_que_falla)

    with pytest.raises(RuntimeError):
        aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)

    monkeypatch.undo()
    recargada = db_session.get(SugerenciaIA, sugerencia.id)
    assert recargada.estado == "aprobada"
    assert recargada.ejecucion_id is None


def test_decision_humana_queda_persistida_con_justificacion_y_recuperable(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    df = _dataset_con_variante(dataset_persistencia_df)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    aprobar_sugerencia(sugerencia, "Justificacion de prueba", db_session)
    run_metadata = _run_metadata(tmp_path)
    aplicar_sugerencia(sugerencia, df, diccionario_ai_support, run_metadata, db_session)

    recuperada = db_session.execute(
        select(SugerenciaIA).where(SugerenciaIA.id == sugerencia.id)
    ).scalar_one()
    assert recuperada.estado == "aplicada"
    assert recuperada.justificacion == "Justificacion de prueba"
    assert recuperada.ejecucion_id is not None


def _run_metadata(tmp_path, contenido="contenido de referencia ai_support") -> RunMetadata:
    archivo = tmp_path / "entrada_ai_support.csv"
    archivo.write_text(contenido, encoding="utf-8")
    return RunMetadata(
        ruta_archivo_entrada=archivo,
        registros_leidos=6,
        registros_validos=6,
        registros_rechazados=0,
    )


# --- Grupo 8: productor de confirmacion_ia (enganche con C-12) --------------


def _sembrar_confirmacion_ia(session) -> None:
    """Replica el seed de la migracion 0005 para tests que no corren Alembic
    (usan `Base.metadata.create_all`, patron de `conftest.db_engine`)."""
    session.add_all(
        [
            ConfigPasoSesion(
                tipo_sesion=TIPO_SESION_CONFIRMACION_IA,
                paso=0,
                prompt="Se sugiere un cambio. Respondé 'aprobar' o 'rechazar'.",
                tipo_respuesta="choice",
                regla_validacion={
                    "tipo_dato": "categorico",
                    "obligatorio": True,
                    "valores_admisibles": ["aprobar", "rechazar"],
                },
            ),
            ConfigPasoSesion(
                tipo_sesion=TIPO_SESION_CONFIRMACION_IA,
                paso=1,
                prompt="Justificacion.",
                tipo_respuesta="texto",
                regla_validacion={"tipo_dato": "texto_libre", "obligatorio": True},
            ),
        ]
    )
    session.commit()


def test_crear_confirmacion_ia_crea_sesion_ligada_a_la_sugerencia(db_session):
    sugerencia = _sugerencia_pendiente(db_session)
    _sembrar_confirmacion_ia(db_session)

    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")

    assert sesion.tipo_sesion == TIPO_SESION_CONFIRMACION_IA
    assert sesion.paso_actual == 0
    assert sesion.estado == "abierta"
    assert sesion.respuestas_acumuladas["sugerencia_id"] == sugerencia.id


def test_motor_c12_avanza_la_sesion_confirmacion_ia_con_los_pasos_sembrados(db_session):
    import datetime as dt

    sugerencia = _sugerencia_pendiente(db_session)
    _sembrar_confirmacion_ia(db_session)
    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")
    ahora = dt.datetime.now(dt.timezone.utc)

    resultado_paso0 = avanzar(db_session, sesion, "aprobar", ahora)
    assert resultado_paso0.valido is True
    assert resultado_paso0.sesion.paso_actual == 1

    resultado_paso1 = avanzar(db_session, resultado_paso0.sesion, "Confirmado", ahora)
    assert resultado_paso1.valido is True
    assert resultado_paso1.sesion.estado == "completada"


def test_respuesta_choice_invalida_no_avanza_el_paso(db_session):
    import datetime as dt

    sugerencia = _sugerencia_pendiente(db_session)
    _sembrar_confirmacion_ia(db_session)
    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")
    ahora = dt.datetime.now(dt.timezone.utc)

    resultado = avanzar(db_session, sesion, "no-es-una-opcion-valida", ahora)

    assert resultado.valido is False
    assert resultado.sesion.paso_actual == 0


def test_resolver_confirmacion_ia_aprobada_deriva_a_aplicar_sugerencia(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    import datetime as dt

    df = _dataset_con_variante(dataset_persistencia_df)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    _sembrar_confirmacion_ia(db_session)
    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")
    ahora = dt.datetime.now(dt.timezone.utc)

    resultado_paso0 = avanzar(db_session, sesion, "aprobar", ahora)
    resultado_paso1 = avanzar(db_session, resultado_paso0.sesion, "Confirmado por ingeniero", ahora)
    assert resultado_paso1.sesion.estado == "completada"

    run_metadata = _run_metadata(tmp_path)
    sugerencia_resuelta = resolver_confirmacion_ia(
        db_session, resultado_paso1.sesion, df, diccionario_ai_support, run_metadata
    )

    assert sugerencia_resuelta.estado == "aplicada"
    assert sugerencia_resuelta.ejecucion_id is not None
    assert sugerencia_resuelta.justificacion == "Confirmado por ingeniero"


def test_resolver_confirmacion_ia_rechazada_no_toca_el_dataset(
    db_session, dataset_persistencia_df, diccionario_ai_support, tmp_path
):
    import datetime as dt

    df = _dataset_con_variante(dataset_persistencia_df)
    original = df.copy(deep=True)
    sugerencia = _sugerencia_pendiente(db_session, estado="generada")
    _sembrar_confirmacion_ia(db_session)
    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")
    ahora = dt.datetime.now(dt.timezone.utc)

    resultado_paso0 = avanzar(db_session, sesion, "rechazar", ahora)
    resultado_paso1 = avanzar(db_session, resultado_paso0.sesion, "No corresponde", ahora)
    assert resultado_paso1.sesion.estado == "completada"

    run_metadata = _run_metadata(tmp_path)
    sugerencia_resuelta = resolver_confirmacion_ia(
        db_session, resultado_paso1.sesion, df, diccionario_ai_support, run_metadata
    )

    assert sugerencia_resuelta.estado == "rechazada"
    assert sugerencia_resuelta.justificacion == "No corresponde"
    pd.testing.assert_frame_equal(df, original)


def test_evento_sesion_de_confirmacion_ia_queda_auditado(db_session):
    import datetime as dt

    from pipeline.models import EventoSesion

    sugerencia = _sugerencia_pendiente(db_session)
    _sembrar_confirmacion_ia(db_session)
    sesion = crear_confirmacion_ia(db_session, sugerencia, telegram_user_id="tg-123")
    ahora = dt.datetime.now(dt.timezone.utc)

    avanzar(db_session, sesion, "aprobar", ahora)

    eventos = db_session.execute(
        select(EventoSesion).where(EventoSesion.session_id == sesion.id)
    ).scalars().all()
    assert len(eventos) == 1
    assert eventos[0].respuesta == "aprobar"
