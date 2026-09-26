"""Aplica los cortes al video con ffmpeg.

Corta con trim/atrim, rebasando PTS por tramo (PTS-STARTPTS), NUNCA con
select+setpts asumiendo un frame rate constante -- ese approach ya causó
hasta 4.9s de desincronización audio/video en el sistema anterior, porque
el celular graba a frame rate variable.

IMPORTANTE (encontrado y medido el 2026-08-24, después de un cuelgue real
de la máquina): un solo filtro gigante que referencia [0:v]/[0:a] una vez
por cada tramo (con un concat de N vías) hace que ffmpeg use MUCHA más
memoria de la esperada -- medido: 161MB para un transcode simple, pero
más de 1GB con sólo 3 tramos en un único filtro, y 1.4GB con 30. Cortar
cada tramo a su propio archivo con un filtro simple (un solo trim, sin
compartir el input con nadie más) cuesta ~165MB por tramo sin importar
cuántos tramos haya en total -- y unirlos después con el demuxer de
concat (stream copy, sin recodificar) es prácticamente gratis. Por eso
el corte acá NUNCA arma un filter_complex con más de un trim adentro.
"""

import subprocess
from pathlib import Path
from typing import List, Tuple

import config
from cut_manager import Tramo


def _cortar_un_tramo(video: Path, tramo: Tramo, destino: Path) -> None:
    """Corta UN solo tramo a su propio archivo.

    El `-ss` va ANTES del `-i`: así ffmpeg salta directo al punto del
    corte en vez de decodificar el video desde el segundo 0 cada vez.
    Antes esto usaba un filtro `trim`, que obliga a decodificar todo lo
    anterior: con 18 tramos el video se decodificaba 18 veces enteras.
    Medido sobre un video real 1080p HEVC, cortando el mismo tramo de 2s
    que arranca en el segundo 30: 31.6s con el filtro trim contra 6.6s
    con `-ss` adelante, y la diferencia crece cuanto más adentro del
    video esté el tramo. Sigue siendo exacto porque se re-codifica: con
    `-ss` antes del `-i` ffmpeg busca el keyframe previo y descarta los
    frames sobrantes hasta el timestamp pedido."""
    comando = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{tramo.inicio:.3f}",
        "-i", str(video),
        "-t", f"{tramo.duracion:.3f}",
        "-c:v", "libx264", "-preset", config.PRESET_SEGMENTO, "-crf", str(config.CRF_SEGMENTO),
        "-c:a", "aac", "-b:a", "128k",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló cortando un tramo: {resultado.stderr.strip()}")


def _concatenar(segmentos: List[Path], destino: Path) -> None:
    """Une los archivos ya cortados con el demuxer de concat -- stream
    copy, sin recodificar, prácticamente gratis en tiempo y memoria."""
    lista_path = destino.with_suffix(".txt")
    contenido = "\n".join(f"file '{s.resolve()}'" for s in segmentos)
    lista_path.write_text(contenido, encoding="utf-8")

    comando = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(lista_path),
        "-c", "copy",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    lista_path.unlink(missing_ok=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló concatenando: {resultado.stderr.strip()}")


def _escapar_ruta_para_filtro(ruta: Path) -> str:
    """El filtro ass= de ffmpeg usa ':' y ''' como caracteres especiales
    en su propio mini-lenguaje -- hay que escaparlos antes de envolver la
    ruta entre comillas simples.
    
    En Windows, usar barras '/' (formato posix) es el estándar soportado por
    ffmpeg para evitar colisiones de escape con barras invertidas."""
    if hasattr(ruta, "as_posix"):
        texto = ruta.as_posix()
    else:
        texto = str(ruta).replace("\\", "/")
    texto = texto.replace(":", "\\:").replace("'", "\\'")
    return f"'{texto}'"


def _quemar_subtitulos(video: Path, ass_path: Path, destino: Path) -> None:
    """Único paso que recodifica el video final -- el audio se copia tal
    cual, los subtítulos no lo tocan."""
    ruta_ass = _escapar_ruta_para_filtro(ass_path)
    comando = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video),
        "-vf", f"ass={ruta_ass}",
        "-c:v", "libx264", "-preset", config.PRESET_FINAL, "-crf", str(config.CRF_FINAL),
        "-c:a", "copy",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló quemando subtítulos: {resultado.stderr.strip()}")


def cortar_video(video: Path, tramos: List[Tramo], destino: Path) -> None:
    """Escribe en destino el video con sólo los tramos conservados,
    concatenados en orden, sin quemar subtítulos (ver cortar_y_subtitular
    para el paso real del pipeline)."""
    if not tramos:
        raise ValueError("No hay tramos para conservar -- no se puede generar un video vacío")

    destino.parent.mkdir(parents=True, exist_ok=True)
    segmentos = [destino.parent / f"{destino.stem}_seg{i}.mp4" for i in range(len(tramos))]

    try:
        for tramo, seg_path in zip(tramos, segmentos):
            _cortar_un_tramo(video, tramo, seg_path)
        _concatenar(segmentos, destino)
    finally:
        for seg in segmentos:
            seg.unlink(missing_ok=True)


def cortar_y_subtitular(video: Path, tramos: List[Tramo], ass_path: Path, destino: Path) -> None:
    """Corta a los tramos conservados y quema los subtítulos ya
    remapeados. Cada tramo se corta a su propio archivo, se concatenan
    sin recodificar, y recién ahí se queman los subtítulos en un único
    paso final -- tres pasos simples en vez de un filtro gigante."""
    if not tramos:
        raise ValueError("No hay tramos para conservar -- no se puede generar un video vacío")

    destino.parent.mkdir(parents=True, exist_ok=True)
    segmentos = [destino.parent / f"{destino.stem}_seg{i}.mp4" for i in range(len(tramos))]
    concatenado = destino.parent / f"{destino.stem}_concat.mp4"

    try:
        for tramo, seg_path in zip(tramos, segmentos):
            _cortar_un_tramo(video, tramo, seg_path)
        _concatenar(segmentos, concatenado)
        _quemar_subtitulos(concatenado, ass_path, destino)
    finally:
        for seg in segmentos:
            seg.unlink(missing_ok=True)
        concatenado.unlink(missing_ok=True)


def obtener_duracion_total(video: Path) -> float:
    comando = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError(f"ffprobe falló obteniendo duración: {resultado.stderr.strip()}")
    return float(resultado.stdout.strip())


def duraciones_de_streams(video: Path) -> Tuple[float, float]:
    """Duración del stream de video y de audio por separado -- reportados
    distinto es exactamente la señal del bug de desincronización que ya
    pasó antes."""
    def _duracion(select_stream: str) -> float:
        comando = [
            "ffprobe", "-v", "error", "-select_streams", select_stream,
            "-show_entries", "stream=duration", "-of", "csv=p=0",
            str(video),
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0 or not resultado.stdout.strip():
            raise RuntimeError(f"ffprobe falló obteniendo duración ({select_stream}): {resultado.stderr.strip()}")
        # el stream de video puede traer una coma final de más si tiene
        # SIDE_DATA (metadata de rotación, común en HEVC de celular)
        return float(resultado.stdout.strip().rstrip(","))

    return _duracion("v:0"), _duracion("a:0")
