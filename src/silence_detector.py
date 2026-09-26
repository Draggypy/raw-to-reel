"""Detección conservadora de silencios reales sobre el audio ya extraído.

Usa un umbral ADAPTATIVO (piso de ruido propio de este video + margen), no
un número fijo -- un video grabado en una habitación con algo de ruido de
fondo no debería tratarse igual que uno grabado en silencio casi total.
Ante la duda, no se marca como silencio: mejor dejar un resto de silencio
que arriesgarse a cortar dentro de una palabra.
"""

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

import config
import logger


@dataclass
class Silencio:
    inicio: float  # segundos, línea de tiempo del audio analizado
    fin: float


def _cargar_audio_mono16(audio_path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(audio_path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(
                "Se esperaba WAV mono de 16 bits (el que genera transcription.extraer_audio)"
            )
        frecuencia = wav.getframerate()
        crudo = wav.readframes(wav.getnframes())

    muestras = np.frombuffer(crudo, dtype=np.int16).astype(np.float64)
    return muestras, frecuencia


def _volumen_db_por_ventana(muestras: np.ndarray, frecuencia: int) -> np.ndarray:
    tam_ventana = max(1, round(frecuencia * config.VENTANA_SILENCIO_MS / 1000))
    n_ventanas = len(muestras) // tam_ventana
    if n_ventanas == 0:
        return np.array([])

    recortado = muestras[: n_ventanas * tam_ventana]
    ventanas = recortado.reshape(n_ventanas, tam_ventana)
    rms = np.sqrt(np.mean(ventanas ** 2, axis=1))
    rms = np.maximum(rms, 1.0)  # evita log(0) en tramos de silencio digital puro
    return 20 * np.log10(rms / 32768.0)


def _suavizar(db_por_ventana: np.ndarray) -> np.ndarray:
    n = max(1, round(config.SUAVIZADO_SILENCIO_MS / config.VENTANA_SILENCIO_MS))
    if n <= 1 or len(db_por_ventana) < n:
        return db_por_ventana
    # Promedio móvil con bordes rellenados (edge), para no arrastrar ceros
    # (= 0dB, volumen máximo) hacia adentro en el arranque y el final.
    relleno = n // 2
    extendido = np.pad(db_por_ventana, (relleno, n - 1 - relleno), mode="edge")
    return np.convolve(extendido, np.ones(n) / n, mode="valid")


def _marcar_silencio_con_histeresis(db_por_ventana: np.ndarray, umbral: float) -> np.ndarray:
    """Devuelve un booleano por ventana. Entrar en silencio exige caer
    HISTERESIS_DB por debajo del umbral; salir alcanza con volver a
    tocarlo. Así una voz floja que roza el umbral no abre un silencio, y
    cualquier asomo de voz lo cierra."""
    umbral_entrar = umbral - config.HISTERESIS_DB
    es_silencio = np.zeros(len(db_por_ventana), dtype=bool)
    en_silencio = False
    for i, db in enumerate(db_por_ventana):
        if en_silencio:
            en_silencio = db < umbral
        else:
            en_silencio = db < umbral_entrar
        es_silencio[i] = en_silencio
    return es_silencio


def detectar_silencios(audio_path: Path) -> List[Silencio]:
    muestras, frecuencia = _cargar_audio_mono16(audio_path)
    db_por_ventana = _volumen_db_por_ventana(muestras, frecuencia)
    if len(db_por_ventana) == 0:
        return []
    return _silencios_desde_db(db_por_ventana)


def _silencios_desde_db(db_por_ventana: np.ndarray) -> List[Silencio]:
    db_por_ventana = _suavizar(db_por_ventana)

    piso_de_ruido_crudo = float(np.percentile(db_por_ventana, 10))
    # Si el percentil 10 ya cae dentro de rango de voz (poca pausa real en
    # este video en particular), no confiar en él tal cual -- lo baja al
    # techo real documentado de "silencio" antes de sumarle el margen.
    piso_de_ruido = min(piso_de_ruido_crudo, config.PISO_RUIDO_MAX_DB)
    umbral = piso_de_ruido + config.MARGEN_DB_SOBRE_PISO
    umbral = max(config.UMBRAL_DB_MIN, min(config.UMBRAL_DB_MAX, umbral))
    logger.log(
        f"Umbral de silencio: piso crudo {piso_de_ruido_crudo:.1f}dB "
        f"(usado {piso_de_ruido:.1f}dB) -> umbral {umbral:.1f}dB"
    )

    tam_ventana_seg = config.VENTANA_SILENCIO_MS / 1000
    es_silencio = _marcar_silencio_con_histeresis(db_por_ventana, umbral)

    tramos_crudos = []
    inicio_actual = None
    for i, silencioso in enumerate(es_silencio):
        if silencioso and inicio_actual is None:
            inicio_actual = i
        elif not silencioso and inicio_actual is not None:
            tramos_crudos.append((inicio_actual, i))
            inicio_actual = None
    if inicio_actual is not None:
        tramos_crudos.append((inicio_actual, len(es_silencio)))

    resultado = []
    for ini_ventana, fin_ventana in tramos_crudos:
        duracion_ms = (fin_ventana - ini_ventana) * tam_ventana_seg * 1000
        if duracion_ms >= config.DURACION_MINIMA_SILENCIO_MS:
            resultado.append(
                Silencio(
                    inicio=ini_ventana * tam_ventana_seg,
                    fin=fin_ventana * tam_ventana_seg,
                )
            )

    return resultado
