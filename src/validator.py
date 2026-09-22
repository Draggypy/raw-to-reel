"""Validación completa del archivo generado, antes de aprobarlo para
Listos/. Los chequeos van de más barato a más caro y se detienen en el
primer fallo. Si falla cualquiera, el video NO se aprueba y el original
en Crudos/ no se toca -- ver file_manager.py.

Nota: que ffmpeg haya terminado con código de salida 0 ya lo garantiza
video_processor.cortar_video() (lanza una excepción si no) -- si eso
falla, nunca se llega a llamar a validar() con un archivo para revisar.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import config
from cut_manager import Tramo


@dataclass
class ResultadoValidacion:
    ok: bool
    motivo: Optional[str] = None


def _existe_y_pesa_algo(video: Path) -> ResultadoValidacion:
    if not video.exists():
        return ResultadoValidacion(False, "el archivo no existe")
    if video.stat().st_size < config.TAMANO_MINIMO_BYTES:
        return ResultadoValidacion(False, f"pesa sólo {video.stat().st_size} bytes, sospechosamente poco")
    return ResultadoValidacion(True)


def _ffprobe_abre_con_streams(video: Path) -> ResultadoValidacion:
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        return ResultadoValidacion(False, f"ffprobe no pudo abrir el archivo: {resultado.stderr.strip()}")

    # ffprobe agrega una coma final de más en la línea de un stream con
    # SIDE_DATA (p. ej. metadata de rotación, muy común en HEVC de celular)
    # -- se saca antes de comparar, si no un video real cualquiera con esa
    # metadata falla acá por error, no porque le falte el stream de video.
    tipos = [linea.rstrip(",") for linea in resultado.stdout.strip().splitlines()]
    if "video" not in tipos:
        return ResultadoValidacion(False, "no tiene stream de video")
    if "audio" not in tipos:
        return ResultadoValidacion(False, "no tiene stream de audio")
    return ResultadoValidacion(True)


def _duracion_esperada(video: Path, tramos: List[Tramo]) -> ResultadoValidacion:
    duracion_esperada = sum(t.duracion for t in tramos)
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or not resultado.stdout.strip():
        return ResultadoValidacion(False, "no se pudo leer la duración de salida")

    duracion_real = float(resultado.stdout.strip())
    diferencia = abs(duracion_real - duracion_esperada)
    tolerancia = (
        config.TOLERANCIA_DURACION_BASE_SEG
        + len(tramos) * config.TOLERANCIA_DURACION_POR_TRAMO_SEG
    )
    if diferencia > tolerancia:
        return ResultadoValidacion(
            False,
            f"duración esperada {duracion_esperada:.2f}s, la real es {duracion_real:.2f}s "
            f"(diferencia {diferencia:.2f}s, tolerancia {tolerancia:.2f}s para {len(tramos)} tramos)",
        )
    return ResultadoValidacion(True)


def _decodifica_sin_errores(video: Path) -> ResultadoValidacion:
    comando = ["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or resultado.stderr.strip():
        return ResultadoValidacion(False, f"errores decodificando: {resultado.stderr.strip()[:500]}")
    return ResultadoValidacion(True)


def validar(video: Path, tramos: List[Tramo]) -> ResultadoValidacion:
    """Corre todos los chequeos, del más barato al más caro, y se detiene
    en el primero que falla. Sólo si todos pasan se puede mover a
    Listos/."""
    chequeos = [
        lambda: _existe_y_pesa_algo(video),
        lambda: _ffprobe_abre_con_streams(video),
        lambda: _duracion_esperada(video, tramos),
        lambda: _decodifica_sin_errores(video),
    ]
    for chequeo in chequeos:
        resultado = chequeo()
        if not resultado.ok:
            return resultado
    return ResultadoValidacion(True)
