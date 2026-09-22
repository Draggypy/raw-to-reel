"""Elige el próximo video a procesar de Crudos/ y confirma que esté estable
(no a medio copiar, p. ej. desde USB) antes de entregarlo.
"""

import time
from pathlib import Path
from typing import Optional

import config


def listar_videos_pendientes() -> list[Path]:
    """Videos en Crudos/ (no en subcarpetas como fallidos/), del más
    antiguo al más nuevo por fecha de modificación."""
    if not config.CRUDOS.is_dir():
        return []
    videos = [
        p for p in config.CRUDOS.iterdir()
        if p.is_file() and p.suffix.lower() in config.EXTENSIONES_VIDEO
    ]
    videos.sort(key=lambda p: p.stat().st_mtime)
    return videos


def esta_estable(video: Path) -> bool:
    """Confirma que el tamaño del archivo no cambia entre chequeos sucesivos,
    para no agarrar un archivo a medio copiar."""
    try:
        tamano_previo = video.stat().st_size
    except FileNotFoundError:
        return False

    for _ in range(config.CHEQUEOS_ESTABILIDAD):
        time.sleep(config.ESPERA_ESTABILIDAD_SEG)
        try:
            tamano_actual = video.stat().st_size
        except FileNotFoundError:
            return False
        if tamano_actual != tamano_previo:
            return False
        tamano_previo = tamano_actual

    return True


def siguiente_video() -> Optional[Path]:
    """Próximo video listo para procesar, o None si no hay ninguno estable
    todavía."""
    for video in listar_videos_pendientes():
        if esta_estable(video):
            return video
    return None
