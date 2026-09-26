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

import cut_manager
from cut_manager import Corte, Tramo
from silence_detector import Silencio
from transcription import Palabra
import subtitle_generator
from subtitle_generator import Caption
import video_processor


class TestCutManager(unittest.TestCase):

    def test_cortes_desde_silencios(self):
        silencios = [
            Silencio(inicio=1.0, fin=3.0),
            Silencio(inicio=5.0, fin=5.1), # Muy corto para margen
        ]
        cortes = cut_manager.cortes_desde_silencios(silencios)
        self.assertGreater(len(cortes), 0)
        # El corte debe respetar el margen de seguridad
        self.assertGreater(cortes[0].inicio, 1.0)
        self.assertLess(cortes[0].fin, 3.0)

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
