"""Editor Gianni -- punto de entrada.

Loop: buscar un video estable en Crudos/, procesarlo por completo, repetir.
Un video a la vez, siempre. Sin vigilante separado: este mismo programa
hace de escaneo + procesamiento.

Pipeline real (Fases 3-11, todas ya integradas acá): transcribir ->
detectar silencios + muletillas/repeticiones -> consolidar cortes
(sin pisar inicios de palabra) -> generar subtítulos remapeados -> cortar + quemar
subtítulos con ffmpeg -> validar. Sólo si todo eso sale bien se llama a
file_manager.finalizar(), que recién ahí mueve el resultado a Listos/ y
borra el original de Crudos/.
"""

import signal
import time
from pathlib import Path

import config
import cut_manager
import file_manager
import logger
import repetition_detector
import scanner
import silence_detector
import subtitle_generator
import transcription
import validator
import video_processor

_seguir_corriendo = True


def _pedido_de_parar(signum, frame):
    global _seguir_corriendo
    logger.log(f"Señal {signum} recibida, terminando después del video actual (si hay uno)")
    _seguir_corriendo = False


def procesar_video(video: Path) -> bool:
    logger.log(f"Procesando: {video.name}")

    try:
        resultado = transcription.transcribir_video(video)

        if not resultado.palabras:
            logger.log("ADVERTENCIA: la transcripción no devolvió ninguna palabra, no hay nada que conservar")
            return False

        logger.actualizar_estado(video.name, "detectando silencios")
        silencios = silence_detector.detectar_silencios(resultado.audio_path)
        logger.log(f"Silencios detectados: {len(silencios)}")

        ancho, alto = subtitle_generator.obtener_dimensiones(video)
        duracion_total = video_processor.obtener_duracion_total(video)

        try:
            resultado.audio_path.unlink()
        except OSError:
            pass  # no crítico, es solo el WAV intermedio

        logger.actualizar_estado(video.name, "buscando muletillas y repeticiones")
        cortes_muletillas = repetition_detector.detectar_muletillas(resultado.palabras, silencios)
        cortes_repeticiones = repetition_detector.detectar_repeticiones(resultado.palabras, silencios)
        logger.log(
            f"Muletillas: {len(cortes_muletillas)}, repeticiones: {len(cortes_repeticiones)}"
        )

        logger.actualizar_estado(video.name, "consolidando cortes")
        cortes = (
            cut_manager.cortes_desde_silencios(silencios, resultado.palabras)
            + cortes_muletillas
            + cortes_repeticiones
        )
        tramos = cut_manager.consolidar(cortes, duracion_total, resultado.palabras)
        logger.log(f"Tramos a conservar: {len(tramos)} (de {duracion_total:.1f}s originales)")

        if not tramos:
            logger.log("ERROR: no quedó ningún tramo para conservar")
            return False

        logger.actualizar_estado(video.name, "generando subtítulos")
        palabras_remapeadas = subtitle_generator.remapear_palabras(resultado.palabras, tramos)
        captions = subtitle_generator.agrupar_en_captions(palabras_remapeadas)

        config.TEMP.mkdir(parents=True, exist_ok=True)
        ass_path = config.TEMP / f"{video.stem}.ass"
        subtitle_generator.generar_ass(captions, ancho, alto, ass_path)

        logger.actualizar_estado(video.name, "cortando y renderizando")
        temp_path = config.TEMP / video.name
        video_processor.cortar_y_subtitular(video, tramos, ass_path, temp_path)

        try:
            ass_path.unlink()
        except OSError:
            pass

        logger.actualizar_estado(video.name, "validando")
        resultado_validacion = validator.validar(temp_path, tramos)
        if not resultado_validacion.ok:
            logger.log(f"ERROR de validación: {resultado_validacion.motivo}")
            return False

    except Exception as e:
        logger.log(f"ERROR procesando video: {e}")
        return False

    logger.actualizar_estado(video.name, "moviendo a Listos")
    ok = file_manager.finalizar(temp_path, video)
    logger.log(f"Listo: {video.name}" if ok else f"Falló: {video.name}")
    return ok


def main() -> None:
    signal.signal(signal.SIGINT, _pedido_de_parar)
    signal.signal(signal.SIGTERM, _pedido_de_parar)

    logger.log("Editor Gianni arrancando")

    while _seguir_corriendo:
        video = scanner.siguiente_video()

        if video is None:
            logger.actualizar_estado(None, "esperando")
            time.sleep(config.INTERVALO_ESCANEO_SEG)
            continue

        exito = procesar_video(video)
        if not exito:
            file_manager.marcar_fallido(video)

    logger.log("Editor Gianni terminando")
    logger.actualizar_estado(None, "detenido")


if __name__ == "__main__":
    main()
