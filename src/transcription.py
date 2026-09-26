"""Extracción de audio + transcripción con faster-whisper.

Devuelve palabras con timestamps -- esa es la única salida que le importa
al resto del programa (subtítulos, detección de silencios/repeticiones
trabajan todos sobre esta lista de palabras, no sobre el video).
"""

import gc
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

import config
import logger


@dataclass
class Palabra:
    texto: str
    inicio: float  # segundos, línea de tiempo ORIGINAL del video
    fin: float


@dataclass
class ResultadoTranscripcion:
    audio_path: Path
    palabras: List[Palabra]


def verificar_audio_utilizable(video: Path) -> None:
    """Falla con un mensaje claro si el video no tiene una pista de audio
    con la que se pueda trabajar. Sin esto, ffmpeg fallaba con "Output
    file does not contain any stream" -- críptico, y el usuario no sabía
    por qué el video terminaba en fallidos/.

    Caso real (2026-09-26, VID_20260926_033221.mp4 de un Xiaomi): el
    archivo tenía la pista de audio creada pero VACÍA -- 0 muestras, sin
    códec (codec_tag 0x0000), caja stbl de 8 bytes. El celular grabó 30s
    de video y nada de audio; pasa cuando otra app tiene tomado el
    micrófono al empezar a grabar, o con el micrófono silenciado."""
    comando = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-of", "csv=p=0", str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffprobe no pudo leer el video: {resultado.stderr.strip()}")

    pistas = [l for l in resultado.stdout.strip().splitlines() if l.strip()]
    if not pistas:
        raise RuntimeError(
            "El video no tiene pista de audio. Sin audio no hay nada que "
            "transcribir ni silencios que cortar."
        )

    for pista in pistas:
        campos = [c.strip() for c in pista.rstrip(",").split(",")]
        codec = campos[0] if campos else ""
        try:
            sample_rate = int(campos[1]) if len(campos) > 1 and campos[1] else 0
        except ValueError:
            sample_rate = 0
        if codec and codec not in ("unknown", "none") and sample_rate > 0:
            return

    raise RuntimeError(
        "La pista de audio del video está vacía (sin códec ni muestras): el "
        "celular grabó video pero no audio. Suele pasar cuando otra app "
        "tenía tomado el micrófono al empezar a grabar, o si el micrófono "
        "estaba silenciado. Revisá que el video tenga sonido al reproducirlo."
    )


def extraer_audio(video: Path) -> Path:
    """Extrae el audio del video a un WAV mono 16kHz en Temp/ -- el formato
    que whisper espera nativamente, y suficiente para el análisis de
    silencios de la Fase 5 más adelante."""
    verificar_audio_utilizable(video)
    config.TEMP.mkdir(parents=True, exist_ok=True)
    destino = config.TEMP / f"{video.stem}.wav"

    comando = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló extrayendo audio: {resultado.stderr.strip()}")

    return destino


def transcribir(audio_path: Path) -> List[Palabra]:
    """Carga el modelo, transcribe, libera el modelo. Nunca deja el modelo
    cargado entre llamadas -- cada video paga el costo de carga de nuevo,
    a cambio de nunca acumular memoria de un video al siguiente."""
    from faster_whisper import WhisperModel

    modelo = WhisperModel(
        config.MODELO_WHISPER,
        device=config.DEVICE_WHISPER,
        compute_type=config.COMPUTE_TYPE_WHISPER,
    )
    try:
        segmentos, _info = modelo.transcribe(
            str(audio_path),
            language=config.IDIOMA_WHISPER,
            word_timestamps=True,
        )
        palabras = [
            Palabra(texto=p.word.strip(), inicio=p.start, fin=p.end)
            for segmento in segmentos
            for p in segmento.words
        ]
    finally:
        del modelo
        gc.collect()

    return palabras


def transcribir_video(video: Path) -> ResultadoTranscripcion:
    logger.actualizar_estado(video.name, "extrayendo audio")
    audio_path = extraer_audio(video)

    logger.actualizar_estado(video.name, "transcribiendo")
    palabras = transcribir(audio_path)
    logger.log(f"Transcripción: {len(palabras)} palabra(s)")

    return ResultadoTranscripcion(audio_path=audio_path, palabras=palabras)
