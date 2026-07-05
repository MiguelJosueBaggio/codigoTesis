"""Tests de `pipeline.setup_ensayo.finalizar_setup` -- change
`telegram-interaction-layer` (C-13), grupo 4 del tasks.md (D-4).

SQLite real via `db_session` (nunca mock, regla dura C-06). Escritura
atomica de `config/data_dictionary.json` + `config/analysis_config.yaml`
sobre rutas de `tmp_path` (NUNCA los archivos reales del repo).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pipeline.models import Sesion
from pipeline.setup_ensayo import finalizar_setup

_VARIABLES_VALIDAS = json.dumps(
    [
        {
            "nombre_canonico": "altura_planta",
            "descripcion": "Altura de la planta",
            "tipo_dato": "real",
            "obligatorio": True,
            "unidad": "cm",
            "rango": {"min": 0, "max": 500},
        }
    ]
)
_ANALISIS_VALIDO = json.dumps(
    {
        "formula": "altura_planta ~ C(tratamiento)",
        "tipo": "anova",
        "alpha": 0.05,
        "metodo_comparacion": "tukey",
        "factor": "tratamiento",
    }
)


def _crear_sesion_completada(db_session, respuestas: dict) -> Sesion:
    ahora = datetime.now(timezone.utc)
    sesion = Sesion(
        telegram_user_id="tg-setup-001",
        tipo_sesion="setup_ensayo",
        paso_actual=2,
        respuestas_acumuladas=respuestas,
        estado="completada",
        created_at=ahora,
        updated_at=ahora,
    )
    db_session.add(sesion)
    db_session.commit()
    return sesion


class TestSetupCompletoGeneraConfigsValidos:
    def test_construye_data_dictionary_y_analysis_config(self, db_session, tmp_path):
        respuestas = {"0": "ENSAYO-SETUP-001", "1": _VARIABLES_VALIDAS, "2": _ANALISIS_VALIDO}
        sesion = _crear_sesion_completada(db_session, respuestas)

        ruta_dict = tmp_path / "data_dictionary.json"
        ruta_yaml = tmp_path / "analysis_config.yaml"
        ahora = datetime.now(timezone.utc)

        resultado = finalizar_setup(
            db_session, sesion.id, ahora, dictionary_path=ruta_dict, analysis_config_path=ruta_yaml
        )

        assert resultado.ok is True
        assert ruta_dict.exists()
        assert ruta_yaml.exists()

        contenido = json.loads(ruta_dict.read_text(encoding="utf-8"))
        assert contenido["variables"][0]["nombre_canonico"] == "altura_planta"

        persistida = db_session.get(Sesion, sesion.id)
        assert persistida.estado == "completada"


class TestDiccionarioInvalidoNoCompletaLaSesion:
    def test_diccionario_invalido_no_reemplaza_destino_ni_completa_sesion(self, db_session, tmp_path):
        variables_invalidas = json.dumps(
            [
                {
                    "nombre_canonico": "Altura Planta",  # viola el patron snake_case
                    "descripcion": "Altura",
                    "tipo_dato": "real",
                    "obligatorio": True,
                }
            ]
        )
        respuestas = {"0": "ENSAYO-SETUP-002", "1": variables_invalidas, "2": _ANALISIS_VALIDO}
        sesion = _crear_sesion_completada(db_session, respuestas)

        ruta_dict = tmp_path / "data_dictionary.json"
        ruta_yaml = tmp_path / "analysis_config.yaml"
        ruta_dict.write_text('{"contenido": "previo"}', encoding="utf-8")
        ahora = datetime.now(timezone.utc)

        resultado = finalizar_setup(
            db_session, sesion.id, ahora, dictionary_path=ruta_dict, analysis_config_path=ruta_yaml
        )

        assert resultado.ok is False
        assert resultado.error
        # El destino NO fue reemplazado (rename atomico, D-4).
        assert ruta_dict.read_text(encoding="utf-8") == '{"contenido": "previo"}'
        assert not ruta_yaml.exists()

        persistida = db_session.get(Sesion, sesion.id)
        assert persistida.estado == "abierta"

    def test_no_deja_archivos_temporales_huerfanos_tras_fallo(self, db_session, tmp_path):
        respuestas = {"0": "ENSAYO-SETUP-003", "1": "no es json valido", "2": _ANALISIS_VALIDO}
        sesion = _crear_sesion_completada(db_session, respuestas)

        ruta_dict = tmp_path / "data_dictionary.json"
        ruta_yaml = tmp_path / "analysis_config.yaml"
        ahora = datetime.now(timezone.utc)

        resultado = finalizar_setup(
            db_session, sesion.id, ahora, dictionary_path=ruta_dict, analysis_config_path=ruta_yaml
        )

        assert resultado.ok is False
        archivos_temporales = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
        assert archivos_temporales == []


class TestTriangulacionCasosLimite:
    def test_sesion_no_setup_ensayo_es_rechazada(self, db_session, tmp_path):
        ahora = datetime.now(timezone.utc)
        sesion = Sesion(
            telegram_user_id="tg-otro-tipo",
            tipo_sesion="carga_dato",
            paso_actual=0,
            respuestas_acumuladas={},
            estado="completada",
            created_at=ahora,
            updated_at=ahora,
        )
        db_session.add(sesion)
        db_session.commit()

        resultado = finalizar_setup(
            db_session,
            sesion.id,
            ahora,
            dictionary_path=tmp_path / "d.json",
            analysis_config_path=tmp_path / "a.yaml",
        )

        assert resultado.ok is False

    def test_sesion_no_completada_es_rechazada(self, db_session, tmp_path):
        ahora = datetime.now(timezone.utc)
        sesion = Sesion(
            telegram_user_id="tg-en-progreso",
            tipo_sesion="setup_ensayo",
            paso_actual=1,
            respuestas_acumuladas={"0": "ENSAYO-X"},
            estado="abierta",
            created_at=ahora,
            updated_at=ahora,
        )
        db_session.add(sesion)
        db_session.commit()

        resultado = finalizar_setup(
            db_session,
            sesion.id,
            ahora,
            dictionary_path=tmp_path / "d.json",
            analysis_config_path=tmp_path / "a.yaml",
        )

        assert resultado.ok is False
