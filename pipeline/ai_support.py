"""Componente de apoyo IA: sugerencias de estandarizacion y anomalias --
change `ai-support-standardization` (C-09), Epica 6 (US-006).

Tres capas con dependencias en un solo sentido (D-1 del design):

1. **Generacion (pura, sin efectos):** `sugerir_estandarizacion` (fuzzy
   determinista, `rapidfuzz`, D-2) y `detectar_anomalias` (estadistica,
   `scipy`/IQR-zscore, D-3). Ninguna muta el DataFrame ni toca la base.
2. **Provider (opcional):** `SugerenciaProvider` (D-4) -- `MockProvider`
   determinista (default) y `OllamaProvider` de referencia, que degrada
   honestamente si Ollama no esta corriendo.
3. **Aplicacion (gate RN-IA-01/02/03, D-7):** `aprobar_sugerencia`/
   `rechazar_sugerencia`/`aplicar_sugerencia` operan SOLO sobre una
   `SugerenciaIA` ya decidida por un humano; `aplicar_sugerencia` construye
   `TransformationRules.correspondencias` e invoca `pipeline.transformation
   .transform` (unica via) + `pipeline.persistence.persist` (C-06).

Ademas, este modulo es el **productor** del `tipo_sesion = "confirmacion_ia"`
que `pipeline.session_engine` (C-12) dejo cableado sin productor (D-6):
`crear_confirmacion_ia` inserta la `Sesion` directamente (iniciada por el
sistema, NO por rol -- no pasa por `resolver_sesion`) y
`resolver_confirmacion_ia` deriva la sesion completada a
`aplicar_sugerencia`/`rechazar_sugerencia`. Enganche, NO disparo automatico:
ningun llamador de este modulo dispara una corrida del pipeline por si solo
(D-6, Non-Goals del design); el cableado n8n de C-13 ya es generico para
cualquier paso `choice` y NO se toca aca.

Matiz DD-04 (D-2/D-3 del design): esto es analisis/sugerencia, NUNCA
validacion -- este modulo NO importa `great_expectations` ni escribe
`if`/`else` de validacion. `sugerir_estandarizacion`/`detectar_anomalias`
son advisory: nunca levantan excepcion ni descartan datos; el humano decide.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional, Protocol

import pandas as pd
from rapidfuzz import fuzz, process, utils as rapidfuzz_utils
from scipy import stats as scipy_stats
from sqlalchemy.orm import Session

from pipeline.data_dictionary import DataDictionary
from pipeline.models import Sesion, SugerenciaIA
from pipeline.persistence import RunMetadata, persist
from pipeline.transformation import TransformationRules, transform

# --- Capa 1: generacion pura (D-1/D-2/D-3) ----------------------------------

TIPO_LEXICA = "lexica"
TIPO_ANOMALIA = "anomalia"

ORIGEN_FUZZY = "fuzzy"
ORIGEN_ESTADISTICA = "estadistica"
ORIGEN_LLM = "llm"

# Umbral fuzzy por defecto (D-2, rango 0-100 de rapidfuzz): calibracion fina
# diferida al caso de estudio real (Open Question 3 del design); 85 es el
# valor propuesto y aprobado en el gate humano (task 0.1).
UMBRAL_FUZZY_DEFAULT = 85.0

METODO_IQR = "iqr"
METODO_ZSCORE = "zscore"
_METODOS_ANOMALIA_VALIDOS = (METODO_IQR, METODO_ZSCORE)

# Factor de Tukey para el rango intercuartilico (D-3) y umbral de z-score
# (|z| >= umbral se marca) -- valores convencionales de la literatura
# estadistica, configurables por parametro.
IQR_FACTOR_DEFAULT = 1.5
ZSCORE_UMBRAL_DEFAULT = 3.0

# Cantidad minima de observaciones numericas para que un metodo estadistico
# tenga sentido (D-3, Scenario "variable sin datos numericos suficientes"):
# menos de esto no produce anomalias, nunca un error.
_MINIMO_OBSERVACIONES_ANOMALIA = 4

_TIPOS_DATO_NUMERICOS = ("entero", "real")


@dataclass(frozen=True)
class Sugerencia:
    """Una sugerencia de apoyo (lexica o de anomalia), D-1/D-2/D-3.

    Attributes:
        columna: nombre canonico de la variable afectada.
        valor_original: el valor observado (o sospechoso, para anomalias).
        valor_sugerido: la forma canonica propuesta; `None` para anomalias
            (D-3: una anomalia marca para revision, no propone reemplazo).
        score: similitud fuzzy (0-100) o distancia estadistica.
        tipo: `"lexica"` | `"anomalia"`.
        origen: quien la propuso -- `"fuzzy"` | `"estadistica"` | `"llm"`.
    """

    columna: str
    valor_original: Any
    valor_sugerido: Optional[Any]
    score: float
    tipo: str
    origen: str = ORIGEN_FUZZY


def sugerir_estandarizacion(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    umbral: float = UMBRAL_FUZZY_DEFAULT,
) -> List[Sugerencia]:
    """Sugiere estandarizaciones lexicas por *fuzzy matching* determinista
    (D-2, `rapidfuzz`) contra `valores_admisibles` de cada variable categorica
    del diccionario (C-02). NO muta `df`; una columna sin `valores_admisibles`
    o ausente en `df` se ignora sin error.

    Vectorizado sobre los valores DISTINTOS de cada columna (no fila-a-fila):
    el costo es proporcional a la cardinalidad de la columna, no al numero de
    filas.

    Usa `rapidfuzz.utils.default_process` (lowercase + colapso de espacios/
    puntuacion) como `processor` de `process.extractOne`: sin el, WRatio
    puntua muy bajo variantes de solo-capitalizacion (p. ej. `"TESTIGO"` vs
    `"Testigo"` da ~14 sin normalizar, ~100 normalizado) -- el processor es
    lo que hace que el umbral por defecto (85) tenga sentido para variantes
    tipicas de tipeo/capitalizacion.
    """
    sugerencias: List[Sugerencia] = []

    for variable in diccionario:
        admisibles = variable.valores_admisibles
        if not admisibles or variable.nombre_canonico not in df.columns:
            continue

        valores_distintos = df[variable.nombre_canonico].dropna().unique()
        admisibles_set = set(admisibles)

        for valor in valores_distintos:
            if valor in admisibles_set:
                continue

            # `admisibles` ya se garantizo no vacio arriba (`if not admisibles`),
            # asi que `extractOne` contra una lista de choices no vacia
            # siempre devuelve un resultado (nunca `None`).
            candidato, score, _ = process.extractOne(
                str(valor),
                admisibles,
                scorer=fuzz.WRatio,
                processor=rapidfuzz_utils.default_process,
            )
            if score >= umbral:
                sugerencias.append(
                    Sugerencia(
                        columna=variable.nombre_canonico,
                        valor_original=valor,
                        valor_sugerido=candidato,
                        score=float(score),
                        tipo=TIPO_LEXICA,
                        origen=ORIGEN_FUZZY,
                    )
                )

    return sugerencias


def _limites_iqr(serie: pd.Series, factor: float) -> "tuple[float, float]":
    q1 = serie.quantile(0.25)
    q3 = serie.quantile(0.75)
    iqr = q3 - q1
    return q1 - factor * iqr, q3 + factor * iqr


def _anomalias_iqr(columna: str, serie: pd.Series) -> List[Sugerencia]:
    limite_inf, limite_sup = _limites_iqr(serie, IQR_FACTOR_DEFAULT)
    iqr = limite_sup - limite_inf

    sugerencias: List[Sugerencia] = []
    for valor in serie[(serie < limite_inf) | (serie > limite_sup)]:
        distancia_fuera = (limite_inf - valor) if valor < limite_inf else (valor - limite_sup)
        score = float(distancia_fuera / iqr) if iqr else float(abs(distancia_fuera))
        sugerencias.append(
            Sugerencia(
                columna=columna,
                valor_original=valor,
                valor_sugerido=None,
                score=score,
                tipo=TIPO_ANOMALIA,
                origen=ORIGEN_ESTADISTICA,
            )
        )
    return sugerencias


def _anomalias_zscore(columna: str, serie: pd.Series, umbral: float) -> List[Sugerencia]:
    if serie.std(ddof=0) == 0:
        return []

    z_scores = scipy_stats.zscore(serie.to_numpy())
    sugerencias: List[Sugerencia] = []
    for valor, z in zip(serie, z_scores):
        if abs(z) >= umbral:
            sugerencias.append(
                Sugerencia(
                    columna=columna,
                    valor_original=valor,
                    valor_sugerido=None,
                    score=float(abs(z)),
                    tipo=TIPO_ANOMALIA,
                    origen=ORIGEN_ESTADISTICA,
                )
            )
    return sugerencias


def detectar_anomalias(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    metodo: str = METODO_IQR,
    umbral_zscore: float = ZSCORE_UMBRAL_DEFAULT,
) -> List[Sugerencia]:
    """Marca valores numericos sospechosos por IQR de Tukey o z-score (D-3),
    100% estadistico (`scipy`), sin LLM. Advisory: NUNCA levanta excepcion ni
    descarta datos -- `valor_sugerido=None` (marca para revision, no
    reemplazo automatico). Una variable sin suficientes datos numericos
    (< `_MINIMO_OBSERVACIONES_ANOMALIA`) produce 0 anomalias, no error.

    Args:
        metodo: `"iqr"` (default, Tukey) o `"zscore"`.
    """
    if metodo not in _METODOS_ANOMALIA_VALIDOS:
        raise ValueError(
            f"metodo de anomalia desconocido: '{metodo}' (validos: {_METODOS_ANOMALIA_VALIDOS})"
        )

    sugerencias: List[Sugerencia] = []
    for variable in diccionario:
        if variable.tipo_dato not in _TIPOS_DATO_NUMERICOS:
            continue
        if variable.nombre_canonico not in df.columns:
            continue

        serie = pd.to_numeric(df[variable.nombre_canonico], errors="coerce").dropna()
        if len(serie) < _MINIMO_OBSERVACIONES_ANOMALIA:
            continue

        if metodo == METODO_IQR:
            sugerencias.extend(_anomalias_iqr(variable.nombre_canonico, serie))
        else:
            sugerencias.extend(_anomalias_zscore(variable.nombre_canonico, serie, umbral_zscore))

    return sugerencias


# --- Capa 2: provider opcional (D-4) -----------------------------------------


@dataclass(frozen=True)
class ContextoSugerencia:
    """Contexto que recibe un `SugerenciaProvider` para proponer sugerencias
    adicionales (D-1): el dataset, el diccionario vigente y las sugerencias
    ya generadas por las capas fuzzy/estadistica (para no duplicar)."""

    df: pd.DataFrame
    diccionario: DataDictionary
    sugerencias_previas: List[Sugerencia] = field(default_factory=list)


class SugerenciaProvider(Protocol):
    """Interfaz de la capa LLM opcional (D-4). El LLM SOLO propone: toda
    sugerencia que devuelva pasa por el MISMO gate humano (RN-IA-02) que las
    sugerencias fuzzy/estadisticas -- nunca se aplica directo."""

    def esta_disponible(self) -> bool: ...

    def sugerir(self, contexto: ContextoSugerencia) -> List[Sugerencia]: ...


class MockProvider:
    """Default determinista (D-4): sin red, `esta_disponible()` siempre
    `True`, `sugerir()` devuelve el conjunto fijo inyectado (o `[]`). Usado en
    tests/CI para garantizar que el componente corre solo-fuzzy/estadistico
    sin invocar ningun LLM."""

    def __init__(self, sugerencias: Optional[List[Sugerencia]] = None) -> None:
        self._sugerencias = list(sugerencias) if sugerencias else []

    def esta_disponible(self) -> bool:
        return True

    def sugerir(self, contexto: ContextoSugerencia) -> List[Sugerencia]:
        return list(self._sugerencias)


# --- OllamaProvider de referencia (D-4) --------------------------------------

OLLAMA_BASE_URL_DEFAULT = "http://localhost:11434"
OLLAMA_MODEL_DEFAULT = "llama3.2"
OLLAMA_PING_TIMEOUT_SEGUNDOS = 2.0
OLLAMA_GENERATE_TIMEOUT_SEGUNDOS = 30.0

# Errores de red/infraestructura que degradan honestamente a "sin sugerencias"
# (D-4): nunca una excepcion no capturada rompe el componente solo por un
# servicio externo OPCIONAL caido/ausente/lento.
_ERRORES_DEGRADACION_OLLAMA = (urllib.error.URLError, OSError, TimeoutError, ValueError)


def _construir_prompt_ollama(contexto: ContextoSugerencia) -> str:
    columnas_categoricas = [
        variable.nombre_canonico for variable in contexto.diccionario if variable.valores_admisibles
    ]
    return (
        "Sos un asistente que revisa datos de un ensayo agricola y propone "
        "estandarizaciones lexicas ADICIONALES para columnas categoricas "
        "(nunca inventes columnas fuera de esta lista). Respondé "
        "EXCLUSIVAMENTE con un JSON: una lista de objetos "
        '{"columna": str, "valor_original": str, "valor_sugerido": str, '
        '"score": float}. Si no proponés nada, respondé con una lista vacia []. '
        f"Columnas categoricas disponibles: {columnas_categoricas}."
    )


def _parsear_sugerencias_ollama(respuesta_texto: str) -> List[Sugerencia]:
    try:
        datos = json.loads(respuesta_texto)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(datos, list):
        return []

    sugerencias: List[Sugerencia] = []
    for item in datos:
        try:
            sugerencias.append(
                Sugerencia(
                    columna=item["columna"],
                    valor_original=item["valor_original"],
                    valor_sugerido=item.get("valor_sugerido"),
                    score=float(item.get("score", 0.0)),
                    tipo=TIPO_LEXICA,
                    origen=ORIGEN_LLM,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sugerencias


class OllamaProvider:
    """Implementacion de referencia de `SugerenciaProvider` contra un Ollama
    LOCAL (D-4, confidencialidad DD-09 -- el dato del ensayo nunca sale de la
    maquina). Degrada honestamente: si Ollama no responde,
    `esta_disponible()` -> `False` y `sugerir()` -> `[]` SIN levantar
    excepcion; el componente sigue funcionando solo con fuzzy/estadistica.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        modelo: Optional[str] = None,
        ping_timeout: float = OLLAMA_PING_TIMEOUT_SEGUNDOS,
        generate_timeout: float = OLLAMA_GENERATE_TIMEOUT_SEGUNDOS,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL") or OLLAMA_BASE_URL_DEFAULT
        ).rstrip("/")
        self.modelo = modelo or os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL_DEFAULT)
        self._ping_timeout = ping_timeout
        self._generate_timeout = generate_timeout

    def esta_disponible(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=self._ping_timeout):
                return True
        except _ERRORES_DEGRADACION_OLLAMA:
            return False

    def _generar(self, contexto: ContextoSugerencia) -> str:
        payload = {
            "model": self.modelo,
            "prompt": _construir_prompt_ollama(contexto),
            "stream": False,
            "format": "json",
        }
        peticion = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(peticion, timeout=self._generate_timeout) as respuesta:
            cuerpo = json.loads(respuesta.read().decode("utf-8"))
        return cuerpo.get("response", "[]")

    def sugerir(self, contexto: ContextoSugerencia) -> List[Sugerencia]:
        if not self.esta_disponible():
            return []
        try:
            respuesta_texto = self._generar(contexto)
        except _ERRORES_DEGRADACION_OLLAMA:
            return []
        return _parsear_sugerencias_ollama(respuesta_texto)


def generar_sugerencias(
    df: pd.DataFrame,
    diccionario: DataDictionary,
    umbral_fuzzy: float = UMBRAL_FUZZY_DEFAULT,
    metodo_anomalia: str = METODO_IQR,
    provider: Optional[SugerenciaProvider] = None,
) -> List[Sugerencia]:
    """Orquesta las tres fuentes de sugerencias (D-1): fuzzy + estadistica
    (siempre) y, si el provider esta disponible, sus sugerencias adicionales.
    Sin `provider`, usa `MockProvider()` -- el componente corre 100%
    solo-fuzzy/estadistico por defecto (D-4)."""
    provider_efectivo = provider if provider is not None else MockProvider()

    sugerencias = sugerir_estandarizacion(df, diccionario, umbral=umbral_fuzzy)
    sugerencias += detectar_anomalias(df, diccionario, metodo=metodo_anomalia)

    if provider_efectivo.esta_disponible():
        contexto = ContextoSugerencia(
            df=df, diccionario=diccionario, sugerencias_previas=list(sugerencias)
        )
        sugerencias += provider_efectivo.sugerir(contexto)

    return sugerencias


# --- Capa 3: aplicacion con gate humano (D-7, RN-IA-01/02/03) ----------------


class SugerenciaNoAprobadaError(Exception):
    """Se intento aplicar una `SugerenciaIA` que no esta en estado
    `"aprobada"` (RN-IA-01/02: ningun cambio se aplica sin aprobacion humana
    explicita). Fail-closed: primera linea de `aplicar_sugerencia`, el
    dataset NUNCA se modifica en este camino."""


def aprobar_sugerencia(sugerencia: SugerenciaIA, justificacion: str, session: Session) -> SugerenciaIA:
    """Aprueba una `SugerenciaIA` con su justificacion (RN-IA-02/03): SOLO
    cambia el estado de la sugerencia, no toca el dataset. `aplicar_sugerencia`
    exige este estado antes de aplicar el cambio."""
    try:
        sugerencia.estado = "aprobada"
        sugerencia.justificacion = justificacion
        session.commit()
    except Exception:
        session.rollback()
        raise
    return sugerencia


def rechazar_sugerencia(sugerencia: SugerenciaIA, justificacion: str, session: Session) -> SugerenciaIA:
    """Rechaza una `SugerenciaIA` con su justificacion (RN-IA-03): el dataset
    NO se modifica; el estado y la justificacion quedan persistidos para
    auditoria."""
    try:
        sugerencia.estado = "rechazada"
        sugerencia.justificacion = justificacion
        session.commit()
    except Exception:
        session.rollback()
        raise
    return sugerencia


def aplicar_sugerencia(
    sugerencia: SugerenciaIA,
    df: pd.DataFrame,
    diccionario: DataDictionary,
    run_metadata: RunMetadata,
    session: Session,
):
    """Aplica una `SugerenciaIA` YA aprobada (D-7): fail-closed si no lo esta
    (primera linea, RN-IA-01/02). Construye
    `TransformationRules.correspondencias` y aplica el cambio EXCLUSIVAMENTE
    via `pipeline.transformation.transform` (unica via, nunca escribe el
    DataFrame a mano); persiste el resultado via `pipeline.persistence
    .persist` (C-06) y liga la sugerencia a la `Ejecucion` resultante.

    Nota de atomicidad: `persist()` ya es atomico en si mismo (Decision 5 de
    C-06) y administra su propia transaccion (`with session.begin():`);
    SQLAlchemy no permite anidar otra transaccion explicita alrededor de esa
    llamada (`InvalidRequestError`). El estado de la sugerencia se actualiza
    en un segundo commit inmediatamente despues -- ligado al MISMO `ejecucion
    .id` ya persistido -- en vez de en la transaccion interna de `persist`,
    unico punto donde el reuso estricto del modulo de C-06 (regla dura: no
    reescribir `persistence.py`) es compatible con la API de `Session`.

    Returns:
        La `Ejecucion` persistida (mismo tipo que devuelve `persist`).
    """
    if sugerencia.estado != "aprobada":
        raise SugerenciaNoAprobadaError(
            f"La sugerencia {sugerencia.id} esta en estado '{sugerencia.estado}'; "
            "solo una sugerencia 'aprobada' puede aplicarse (RN-IA-01/02)."
        )

    reglas = TransformationRules(
        correspondencias={sugerencia.columna: {sugerencia.valor_original: sugerencia.valor_sugerido}}
    )
    outcome = transform(df, diccionario, reglas=reglas)

    ejecucion = persist(outcome, run_metadata, session)

    try:
        sugerencia.estado = "aplicada"
        sugerencia.ejecucion_id = ejecucion.id
        session.commit()
    except Exception:
        session.rollback()
        raise

    return ejecucion


# --- Productor de confirmacion_ia (D-6) --------------------------------------
# `confirmacion_ia` es un tipo_sesion iniciado por el SISTEMA, no por rol
# (a diferencia de setup_ensayo/carga_dato): NO pasa por
# `pipeline.session_engine.resolver_sesion`. La secuencia de pasos vive como
# DATA en `config_paso_sesion` (RN-SES-03), sembrada en la migracion 0005 --
# el motor de C-12 la avanza sin ninguna rama por tipo_sesion.
#
# Enganche, NO disparo automatico (D-6, Non-Goals del design): NADA en este
# modulo dispara una corrida del pipeline por si solo; el cableado n8n
# GENERICO de C-13 (`interaccion_telegram.json`) ya cubre cualquier paso
# `choice`, incluido `confirmacion_ia`, y NO se toca aca.

TIPO_SESION_CONFIRMACION_IA = "confirmacion_ia"

_PASO_CHOICE_APROBAR_RECHAZAR = 0
_PASO_TEXTO_JUSTIFICACION = 1

_CLAVE_SUGERENCIA_ID = "sugerencia_id"


def crear_confirmacion_ia(
    session: Session,
    sugerencia: SugerenciaIA,
    telegram_user_id: str,
    ahora: Optional[datetime] = None,
) -> Sesion:
    """Crea la `Sesion(tipo_sesion="confirmacion_ia")` que presenta
    `sugerencia` al humano (D-6): iniciada por el SISTEMA (no resuelve rol),
    ligada a la sugerencia via `respuestas_acumuladas={"sugerencia_id": id}`
    (Open Question 1 resuelta: sin FK dedicada en v1, para no tocar el
    esquema de `sesion` de C-12). El motor generico de C-12 la avanza con las
    filas `config_paso_sesion` sembradas para este `tipo_sesion`."""
    momento = ahora or datetime.now(timezone.utc)
    sesion = Sesion(
        telegram_user_id=telegram_user_id,
        tipo_sesion=TIPO_SESION_CONFIRMACION_IA,
        paso_actual=0,
        respuestas_acumuladas={_CLAVE_SUGERENCIA_ID: sugerencia.id},
        estado="abierta",
        created_at=momento,
        updated_at=momento,
    )
    session.add(sesion)
    session.commit()
    return sesion


def resolver_confirmacion_ia(
    session: Session,
    sesion: Sesion,
    df: pd.DataFrame,
    diccionario: DataDictionary,
    run_metadata: RunMetadata,
) -> SugerenciaIA:
    """Consumidor de una sesion `confirmacion_ia` YA `completada` (D-6, task
    8.4): lee la respuesta `choice` (paso 0, aprobar/rechazar) y la
    justificacion (paso 1) de `sesion.respuestas_acumuladas`, y deriva a
    `aplicar_sugerencia`/`rechazar_sugerencia` segun corresponda. El
    `evento_sesion` de auditoria (RN-SES-06) ya quedo escrito por
    `pipeline.session_engine.avanzar` al completar cada paso -- este
    consumidor solo actua sobre la `SugerenciaIA` ligada.
    """
    sugerencia_id = sesion.respuestas_acumuladas[_CLAVE_SUGERENCIA_ID]
    sugerencia = session.get(SugerenciaIA, sugerencia_id)

    decision = sesion.respuestas_acumuladas[str(_PASO_CHOICE_APROBAR_RECHAZAR)]
    justificacion = sesion.respuestas_acumuladas[str(_PASO_TEXTO_JUSTIFICACION)]

    if decision == "aprobar":
        aprobar_sugerencia(sugerencia, justificacion, session)
        aplicar_sugerencia(sugerencia, df, diccionario, run_metadata, session)
    else:
        rechazar_sugerencia(sugerencia, justificacion, session)

    return sugerencia
