"""Pruebas unitarias y de compatibilidad multiplataforma (Linux / Windows) para RawToReel.
Corre con unittest estándar de Python (sin dependencias adicionales requeridas).
"""

import os
import sys
import unittest
import tempfile
import subprocess
from pathlib import Path

# Agregar src al sys.path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import numpy as np

import config
import cut_manager
from cut_manager import Corte, Tramo
import repetition_detector
import silence_detector
from silence_detector import Silencio
from transcription import Palabra
import subtitle_generator
from subtitle_generator import Caption
import transcription
import video_processor

MARGEN = config.MARGEN_SILENCIO_MS / 1000
MARGEN_FRASE = config.MARGEN_DENTRO_DE_FRASE_MS / 1000
PAUSA_FRASE = config.PAUSA_MINIMA_DENTRO_DE_FRASE_MS / 1000
CORTE_MINIMO = config.CORTE_MINIMO_MS / 1000


class TestCutManager(unittest.TestCase):

    def test_cortes_desde_silencios(self):
        silencios = [
            Silencio(inicio=1.0, fin=3.0),
            Silencio(inicio=5.0, fin=5.1), # Muy corto para margen
        ]
        cortes = cut_manager.cortes_desde_silencios(silencios)
        self.assertEqual(len(cortes), 1)
        # El corte debe respetar el margen de seguridad
        self.assertAlmostEqual(cortes[0].inicio, 1.0 + MARGEN)
        self.assertAlmostEqual(cortes[0].fin, 3.0 - MARGEN)

    def test_micro_corte_se_descarta(self):
        # Pausa apenas por encima del silencio mínimo: tras los dos márgenes
        # quedaría un corte de ~20ms -- un salto visual a cambio de nada.
        justo_por_debajo = 2 * MARGEN + CORTE_MINIMO - 0.02
        justo_por_encima = 2 * MARGEN + CORTE_MINIMO + 0.02
        silencios = [
            Silencio(inicio=1.0, fin=1.0 + justo_por_debajo),
            Silencio(inicio=5.0, fin=5.0 + justo_por_encima),
        ]
        cortes = cut_manager.cortes_desde_silencios(silencios)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 5.0 + MARGEN)

    def test_corte_no_pisa_inicio_de_palabra(self):
        # Volumen dice silencio de 1.0 a 3.0, pero Whisper oyó una palabra
        # que arranca en 2.0: es voz baja, el corte termina un margen antes.
        silencios = [Silencio(inicio=1.0, fin=3.0)]
        palabras = [Palabra("bajito", 2.0, 2.4)]
        cortes = cut_manager.cortes_desde_silencios(silencios, palabras)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 1.0 + MARGEN)
        self.assertAlmostEqual(cortes[0].fin, 2.0 - MARGEN)

    def test_corte_con_palabra_al_inicio_se_descarta(self):
        # Una palabra que arranca casi al principio del silencio no deja
        # nada útil para cortar.
        silencios = [Silencio(inicio=1.0, fin=3.0)]
        palabras = [Palabra("si", 1.1, 1.3)]
        self.assertEqual(cut_manager.cortes_desde_silencios(silencios, palabras), [])

    def test_palabra_fuera_del_silencio_no_afecta(self):
        silencios = [Silencio(inicio=1.0, fin=3.0)]
        palabras = [Palabra("antes.", 0.2, 0.9), Palabra("Despues", 3.0, 3.5)]
        cortes = cut_manager.cortes_desde_silencios(silencios, palabras)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].fin, 3.0 - MARGEN)

    def test_pausa_corta_dentro_de_frase_no_se_corta(self):
        # "estamos hablando [0.8s] de un tema": respiración en medio de la
        # frase, ritmo del habla -- no se toca aunque supere el mínimo general.
        palabras = [Palabra("estamos", 0.0, 0.5), Palabra("hablando", 0.5, 1.0), Palabra("de", 1.8, 2.0)]
        silencios = [Silencio(inicio=1.0, fin=1.0 + PAUSA_FRASE - 0.2)]
        self.assertEqual(cut_manager.cortes_desde_silencios(silencios, palabras), [])

    def test_pausa_larga_dentro_de_frase_se_corta_dejando_mas_aire(self):
        palabras = [Palabra("estamos", 0.0, 0.5), Palabra("hablando", 0.5, 1.0), Palabra("de", 2.6, 2.8)]
        silencios = [Silencio(inicio=1.0, fin=2.6)]
        cortes = cut_manager.cortes_desde_silencios(silencios, palabras)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 1.0 + MARGEN_FRASE)
        self.assertAlmostEqual(cortes[0].fin, 2.6 - MARGEN_FRASE)

    def test_pausa_entre_frases_se_corta_con_margen_normal(self):
        palabras = [Palabra("tema.", 0.5, 1.0), Palabra("Ahora", 1.6, 1.9)]
        silencios = [Silencio(inicio=1.0, fin=1.6)]
        cortes = cut_manager.cortes_desde_silencios(silencios, palabras)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 1.0 + MARGEN)
        self.assertAlmostEqual(cortes[0].fin, 1.6 - MARGEN)

    def test_coma_y_puntos_suspensivos(self):
        silencios = [Silencio(inicio=1.0, fin=1.8)]
        con_coma = [Palabra("tema,", 0.5, 1.0)]
        self.assertEqual(cut_manager.cortes_desde_silencios(silencios, con_coma), [])
        con_suspensivos = [Palabra("tema...", 0.5, 1.0)]
        self.assertEqual(len(cut_manager.cortes_desde_silencios(silencios, con_suspensivos)), 1)

    def test_remapear_intervalo(self):
        # Video de 10s cortado: conserva [0, 2] y [4, 7]
        tramos = [Tramo(inicio=0.0, fin=2.0), Tramo(inicio=4.0, fin=7.0)]
        
        # Una palabra en [0.5, 1.5] en el tramo 1
        remapeado = cut_manager.remapear_intervalo(0.5, 1.5, tramos)
        self.assertIsNotNone(remapeado)
        self.assertAlmostEqual(remapeado[0], 0.5)
        self.assertAlmostEqual(remapeado[1], 1.5)

        # Una palabra en [4.5, 5.5] en el tramo 2 (tiempo nuevo = 2 + (4.5 - 4) = 2.5)
        remapeado2 = cut_manager.remapear_intervalo(4.5, 5.5, tramos)
        self.assertIsNotNone(remapeado2)
        self.assertAlmostEqual(remapeado2[0], 2.5)
        self.assertAlmostEqual(remapeado2[1], 3.5)

        # Una palabra en [2.5, 3.5] (zona eliminada)
        remapeado_vacio = cut_manager.remapear_intervalo(2.5, 3.5, tramos)
        self.assertIsNone(remapeado_vacio)


def _db_sintetico(*tramos):
    """Curva de dB en ventanas de VENTANA_SILENCIO_MS: (duracion_seg, nivel_db)."""
    ventana = config.VENTANA_SILENCIO_MS / 1000
    partes = [np.full(round(dur / ventana), nivel, dtype=float) for dur, nivel in tramos]
    return np.concatenate(partes)


class TestSilenceDetector(unittest.TestCase):

    def test_pausa_clara_se_detecta(self):
        db = _db_sintetico((2.0, -25.0), (1.0, -50.0), (2.0, -25.0))
        silencios = silence_detector._silencios_desde_db(db)
        self.assertEqual(len(silencios), 1)
        self.assertAlmostEqual(silencios[0].inicio, 2.0, delta=0.06)
        self.assertAlmostEqual(silencios[0].fin, 3.0, delta=0.06)

    def test_voz_baja_no_es_silencio(self):
        # Voz floja a -30dB (dentro del rango medido de voz) en un video con
        # piso alto: antes el umbral podía subir hasta -28 y cortarla.
        db = _db_sintetico((2.0, -22.0), (1.0, -30.0), (2.0, -22.0))
        self.assertEqual(silence_detector._silencios_desde_db(db), [])

    def test_oscilacion_alrededor_del_umbral_no_fragmenta(self):
        # Voz que roza el umbral, alternando cada 10ms +-2dB alrededor de un
        # umbral de ~-38dB: sin suavizado ni histéresis esto daba decenas de
        # cortes de una ventana. Debe dar cero silencios.
        piso = _db_sintetico((1.0, -55.0))
        voz = _db_sintetico((2.0, -25.0))
        oscilante = np.tile([-36.0, -40.0], 50)  # 1s alternando
        db = np.concatenate([piso, voz, oscilante, voz])
        silencios = silence_detector._silencios_desde_db(db)
        # el único silencio es el piso inicial; la zona oscilante (3s-4s) no
        self.assertEqual(len(silencios), 1)
        self.assertLessEqual(silencios[0].fin, 1.06)

    def test_histeresis_cierra_silencio_ante_voz(self):
        # Silencio real seguido de una palabra apenas por encima del umbral:
        # el silencio tiene que cerrarse ahí, no comerse la palabra.
        db = _db_sintetico((1.0, -55.0), (1.0, -25.0), (1.0, -55.0), (0.5, -37.0), (1.0, -25.0))
        silencios = silence_detector._silencios_desde_db(db)
        self.assertEqual(len(silencios), 2)
        self.assertAlmostEqual(silencios[1].fin, 3.0, delta=0.06)


class TestMuletillas(unittest.TestCase):

    def _palabras(self, *textos, paso=0.3):
        # Whisper estira el fin de cada palabra hasta el inicio de la siguiente
        return [Palabra(t, i * paso, (i + 1) * paso) for i, t in enumerate(textos)]

    def test_muletilla_inequivoca_se_corta_siempre(self):
        palabras = self._palabras("yo", "eh", "creo")
        cortes = repetition_detector.detectar_muletillas(palabras)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 0.3)
        # guarda antes del inicio de "creo"
        self.assertAlmostEqual(cortes[0].fin, 0.6 - config.GUARDA_ONSET_SEG)

    def test_este_en_frase_fluida_no_se_corta(self):
        palabras = self._palabras("en", "este", "video", "vamos")
        self.assertEqual(repetition_detector.detectar_muletillas(palabras, []), [])

    def test_este_con_pausa_pegada_se_corta(self):
        # "este" dubitativo: Whisper lo estira sobre la pausa que le sigue
        palabras = [
            Palabra("y", 0.0, 0.3),
            Palabra("este", 0.3, 1.5),
            Palabra("bueno", 1.5, 1.9),
        ]
        silencios = [Silencio(inicio=0.7, fin=1.45)]
        cortes = repetition_detector.detectar_muletillas(palabras, silencios)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 0.3)

    def test_o_sea_multipalabra_con_pausa(self):
        palabras = self._palabras("o", "sea", "vamos")
        silencios = [Silencio(inicio=-0.5, fin=0.05)]
        cortes = repetition_detector.detectar_muletillas(palabras, silencios)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 0.0)

    def test_repeticion_con_pausa_en_el_medio_se_corta(self):
        # "yo creo... [pausa] yo creo que sí": traba real
        palabras = self._palabras("yo", "creo", "yo", "creo", "que", "si")
        silencios = [Silencio(inicio=0.45, fin=0.6)]
        cortes = repetition_detector.detectar_repeticiones(palabras, silencios)
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 0.0)
        self.assertAlmostEqual(cortes[0].fin, 0.6 - config.GUARDA_ONSET_SEG)

    def test_repeticion_por_enfasis_no_se_corta(self):
        # "y pulas y pulas y pulas", "al hablar al hablar": de corrido, sin pausa
        palabras = self._palabras("y", "pulas", "y", "pulas", "y", "pulas", "eso")
        self.assertEqual(repetition_detector.detectar_repeticiones(palabras, []), [])

    def test_repeticion_con_muletilla_en_el_medio_se_corta(self):
        palabras = self._palabras("yo", "creo", "eh", "yo", "creo", "que")
        cortes = repetition_detector.detectar_repeticiones(palabras, [])
        self.assertEqual(len(cortes), 1)
        self.assertAlmostEqual(cortes[0].inicio, 0.0)
        self.assertAlmostEqual(cortes[0].fin, 0.9 - config.GUARDA_ONSET_SEG)


class TestSubtitleGenerator(unittest.TestCase):

    def test_formatear_tiempo_ass(self):
        self.assertEqual(subtitle_generator._formatear_tiempo_ass(0.0), "0:00:00.00")
        self.assertEqual(subtitle_generator._formatear_tiempo_ass(65.5), "0:01:05.50")
        self.assertEqual(subtitle_generator._formatear_tiempo_ass(3661.12), "1:01:01.12")

    def test_agrupar_en_captions(self):
        palabras = [
            Palabra(texto="Hola", inicio=0.1, fin=0.4),
            Palabra(texto="mundo", inicio=0.5, fin=0.9),
            Palabra(texto="este", inicio=2.0, fin=2.3),
            Palabra(texto="es", inicio=2.4, fin=2.6),
            Palabra(texto="un", inicio=2.7, fin=2.9),
            Palabra(texto="test", inicio=3.0, fin=3.4),
        ]
        captions = subtitle_generator.agrupar_en_captions(palabras)
        self.assertGreater(len(captions), 0)
        # Cada caption debe tener texto y rango de tiempo
        for cap in captions:
            self.assertTrue(len(cap.texto) > 0)
            self.assertGreater(cap.fin, cap.inicio)


class TestRutaFiltroWindowsCompat(unittest.TestCase):

    def test_escapar_ruta_posix(self):
        p = Path("/tmp/subtitulos.ass")
        escapada = video_processor._escapar_ruta_para_filtro(p)
        self.assertTrue(escapada.startswith("'") and escapada.endswith("'"))
        self.assertIn("/tmp/subtitulos.ass", escapada)

    def test_escapar_ruta_formato_windows(self):
        # Simula una ruta con dos puntos y barras de Windows
        class FakeWindowsPath:
            def __str__(self):
                return "C:\\Users\\runneradmin\\AppData\\Local\\Temp\\video.ass"
        
        texto_escapado = video_processor._escapar_ruta_para_filtro(FakeWindowsPath())
        # En FFmpeg el ':' debe estar escapado con '\:' para que el filtro ass= no falle
        self.assertIn("C\\:", texto_escapado)


class TestFFmpegPipelineReal(unittest.TestCase):

    def test_corte_y_subtitulado_sintetico(self):
        """Genera un video sintético de 2 segundos, corta y quema un subtítulo .ass de prueba."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            video_origen = tmppath / "origen.mp4"
            video_destino = tmppath / "destino.mp4"
            ass_path = tmppath / "prueba.ass"

            # 1. Crear video sintético con ffmpeg (2 segundos con audio)
            cmd_gen = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
                "-c:v", "libx264", "-c:a", "aac",
                str(video_origen)
            ]
            res_gen = subprocess.run(cmd_gen, capture_output=True, text=True)
            self.assertEqual(res_gen.returncode, 0, f"Error generando video sintético: {res_gen.stderr}")

            # 2. Generar archivo .ass básico
            captions = [
                Caption(texto="Prueba de subtítulo", inicio=0.2, fin=1.2)
            ]
            subtitle_generator.generar_ass(captions, 320, 240, ass_path)
            self.assertTrue(ass_path.exists())

            # 3. Cortar tramo [0.0 - 1.5] y quemar subtítulo
            tramos = [Tramo(inicio=0.0, fin=1.5)]
            video_processor.cortar_y_subtitular(video_origen, tramos, ass_path, video_destino)

            self.assertTrue(video_destino.exists(), "El video de salida no fue creado")
            self.assertGreater(video_destino.stat().st_size, 1000, "El video de salida está vacío o corrupto")


class TestAudioUtilizable(unittest.TestCase):

    def _video_sintetico(self, tmppath, con_audio):
        destino = tmppath / ("con_audio.mp4" if con_audio else "sin_audio.mp4")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=25"]
        if con_audio:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", str(destino)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return destino

    def test_video_sin_pista_de_audio_falla_con_mensaje_claro(self):
        # Caso real: un celular grabó video pero ninguna muestra de audio.
        # Antes ffmpeg fallaba con "Output file does not contain any stream".
        with tempfile.TemporaryDirectory() as tmpdir:
            video = self._video_sintetico(Path(tmpdir), con_audio=False)
            with self.assertRaises(RuntimeError) as ctx:
                transcription.extraer_audio(video)
            self.assertIn("audio", str(ctx.exception).lower())
            self.assertNotIn("does not contain any stream", str(ctx.exception))

    def test_video_con_audio_pasa_la_verificacion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            video = self._video_sintetico(Path(tmpdir), con_audio=True)
            transcription.verificar_audio_utilizable(video)  # no debe lanzar


class TestWhisperEngine(unittest.TestCase):

    def test_faster_whisper_carga_modelo_cpu(self):
        """Verifica que faster-whisper y el runtime ctranslate2 inicialicen correctamente."""
        from faster_whisper import WhisperModel
        # Usamos modelo 'tiny' para test rápido y liviano (~39MB)
        modelo = WhisperModel("tiny", device="cpu", compute_type="int8")
        self.assertIsNotNone(modelo)
        del modelo


if __name__ == "__main__":
    unittest.main()
