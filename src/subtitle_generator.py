"""Genera subtítulos .ass a partir de las palabras de Whisper.

Puede trabajar sobre la línea de tiempo original o sobre una ya remapeada
a un video cortado (ver remapear_palabras) -- no necesita saber cuál es
cuál, sólo recibe una lista de Palabra con los timestamps que sean.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import config
import cut_manager
from transcription import Palabra


def remapear_palabras(palabras: List[Palabra], tramos: List["cut_manager.Tramo"]) -> List[Palabra]:
    """Traduce cada palabra a la línea de tiempo de salida contra los
    tramos ya cortados (ver cut_manager.remapear_intervalo). Una palabra
    que no solapa NINGÚN tramo conservado se descarta -- no tiene sentido
    mostrar un subtítulo de algo que ya no está en el video final. Si
    solapa parcialmente (borde de Whisper impreciso), se recorta al tramo
    en vez de descartarse entera."""
    remapeadas = []
    for p in palabras:
        intervalo = cut_manager.remapear_intervalo(p.inicio, p.fin, tramos)
        if intervalo is None:
            continue
        nuevo_inicio, nuevo_fin = intervalo
        remapeadas.append(Palabra(texto=p.texto, inicio=nuevo_inicio, fin=nuevo_fin))
    return remapeadas


@dataclass
class Caption:
    texto: str
    inicio: float
    fin: float


def agrupar_en_captions(palabras: List[Palabra]) -> List[Caption]:
    """Agrupa palabras consecutivas en captions cortos (estilo CapCut/Reels):
    máximo N palabras, y siempre arranca un caption nuevo si hay una pausa
    real entre una palabra y la siguiente."""
    if not palabras:
        return []

    captions = []
    grupo = [palabras[0]]

    for palabra in palabras[1:]:
        pausa = palabra.inicio - grupo[-1].fin
        si_pausa_larga = pausa >= config.PAUSA_CORTE_CAPTION_SEG
        si_grupo_lleno = len(grupo) >= config.MAX_PALABRAS_POR_CAPTION
        if si_pausa_larga or si_grupo_lleno:
            captions.append(_cerrar_grupo(grupo))
            grupo = [palabra]
        else:
            grupo.append(palabra)

    captions.append(_cerrar_grupo(grupo))
    return captions


def _cerrar_grupo(grupo: List[Palabra]) -> Caption:
    texto = " ".join(p.texto for p in grupo)
    return Caption(texto=texto, inicio=grupo[0].inicio, fin=grupo[-1].fin)


def obtener_dimensiones(video: Path) -> Tuple[int, int]:
    comando = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffprobe falló obteniendo dimensiones: {resultado.stderr.strip()}")

    # ffprobe agrega una coma final de más cuando el stream de video trae
    # SIDE_DATA (p. ej. metadata de rotación, muy común en HEVC de celular)
    # -- se toman sólo los primeros dos valores, se ignora cualquier resto.
    valores = resultado.stdout.strip().split(",")
    return int(valores[0]), int(valores[1])


def _formatear_tiempo_ass(segundos: float) -> str:
    """Convierte a centésimas como entero primero para no arrastrar errores
    de redondeo de punto flotante al formatear H:MM:SS.CC."""
    total_centesimas = round(segundos * 100)
    centesimas = total_centesimas % 100
    total_segundos = total_centesimas // 100
    segs = total_segundos % 60
    total_minutos = total_segundos // 60
    minutos = total_minutos % 60
    horas = total_minutos // 60
    return f"{horas}:{minutos:02d}:{segs:02d}.{centesimas:02d}"


def generar_ass(captions: List[Caption], ancho: int, alto: int, destino: Path) -> None:
    tamano_fuente = round(alto * config.FRACCION_TAMANO_FUENTE)
    contorno = round(alto * config.FRACCION_CONTORNO)
    margen_inferior = round(alto * config.FRACCION_MARGEN_INFERIOR)

    encabezado = (
        "[Script Info]\n"
        "Title: Editor Gianni\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {ancho}\n"
        f"PlayResY: {alto}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{config.FUENTE_SUBTITULOS},{tamano_fuente},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H00000000,0,0,0,0,100,{config.ESCALA_VERTICAL_SUBTITULOS},0,0,1,{contorno},0,2,20,20,{margen_inferior},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # El tracking negativo se aplica acá, no en el campo Spacing del Style:
    # se probó y libass lo ignora cuando es negativo (queda igual que en 0),
    # pero sí respeta el override \fsp puesto en cada línea de diálogo.
    prefijo_tracking = f"{{\\fsp{config.TRACKING_SUBTITULOS}}}" if config.TRACKING_SUBTITULOS else ""

    lineas = []
    for cap in captions:
        inicio = _formatear_tiempo_ass(cap.inicio)
        fin = _formatear_tiempo_ass(cap.fin)
        texto = cap.texto.replace("\n", " ").strip()
        if texto:
            lineas.append(f"Dialogue: 0,{inicio},{fin},Default,,0,0,0,,{prefijo_tracking}{texto}")

    destino.write_text(encabezado + "\n".join(lineas) + "\n", encoding="utf-8")
