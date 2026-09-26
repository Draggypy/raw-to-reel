"""Muletillas y repeticiones, detectadas de forma conservadora por reglas
-- sin depender de ningún servicio externo (punto 17 de la spec: nada de
sistemas de IA innecesarios para esto). La arquitectura permite cambiar a
un analista más inteligente más adelante (por ejemplo, algo como lo que
hacía el sistema anterior con `claude -p`) sin tocar cut_manager.py: sólo
haría falta otra función acá que devuelva la misma lista de Corte.

Regla central, igual que en todo el resto del proyecto: ante la duda, no
cortar. Una muletilla inequívoca ("eh", "emm") se corta siempre; una que
también es palabra real ("este", "tipo") sólo si tiene una pausa real
pegada, medida sobre el audio -- señal de duda, no de frase fluida. Una
repetición sólo se corta si son 2 o más palabras exactas repetidas poco
después -- una sola palabra repetida es demasiado común en el habla
normal como para ser señal confiable de un arranque en falso.
"""

import re
import unicodedata
from typing import List, Sequence

import config
from cut_manager import Corte
from silence_detector import Silencio
from transcription import Palabra


def _normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", texto)


def _fin_seguro(palabras: List[Palabra], indice_ultima: int) -> float:
    """Whisper marca el `fin` de una palabra justo donde arranca la
    siguiente: cortar hasta ahí pisaba el primer fonema de la palabra que
    sigue si su inicio venía apenas tarde. Se deja una guarda antes."""
    fin = palabras[indice_ultima].fin
    if indice_ultima + 1 < len(palabras):
        fin = min(fin, palabras[indice_ultima + 1].inicio - config.GUARDA_ONSET_SEG)
    return fin


def _hay_pausa_pegada(inicio: float, fin: float, silencios: Sequence[Silencio]) -> bool:
    tol = config.TOLERANCIA_MULETILLA_SILENCIO_SEG
    return any(s.fin >= inicio - tol and s.inicio <= fin + tol for s in silencios)


def detectar_muletillas(
    palabras: List[Palabra], silencios: Sequence[Silencio] = ()
) -> List[Corte]:
    """Busca la muletilla (de una o más palabras, p. ej. "o sea") más
    larga que coincida en cada posición.

    Las inequívocas se cortan SIEMPRE que aparecen. Las de
    MULETILLAS_AMBIGUAS ("este", "tipo"...) son también palabras reales
    ("en este video", "tipo de cosa"): cortarlas siempre metía un salto
    en medio de una frase fluida. Sólo se cortan si el detector de
    silencios encontró una pausa real pegada (antes o después).

    La pausa se mide contra los silencios detectados por volumen y NO
    contra los huecos entre timestamps de Whisper: Whisper estira el fin
    de cada palabra hasta la siguiente, así que entre sus palabras nunca
    hay hueco aunque la pausa exista (medido con un video real: 393
    palabras, 0 muletillas "aisladas" por timestamps). Si la muletilla
    va seguida de una pausa, el silencio cae DENTRO del intervalo
    estirado de la palabra, y por eso se busca solapamiento y no
    adyacencia exacta."""
    normalizadas = [_normalizar(p.texto) for p in palabras]
    n = len(palabras)
    max_palabras_muletilla = max(len(m.split()) for m in config.MULETILLAS)
    cortes = []
    i = 0

    while i < n:
        tam_match = None
        for tam in range(max_palabras_muletilla, 0, -1):
            if i + tam > n:
                continue
            frase = " ".join(normalizadas[i:i + tam])
            if frase in config.MULETILLAS:
                tam_match = tam
                break

        if tam_match:
            inicio = palabras[i].inicio
            fin = _fin_seguro(palabras, i + tam_match - 1)
            es_ambigua = frase in config.MULETILLAS_AMBIGUAS
            if fin > inicio and (not es_ambigua or _hay_pausa_pegada(inicio, fin, silencios)):
                cortes.append(Corte(inicio=inicio, fin=fin))
            i += tam_match
        else:
            i += 1

    return cortes


def detectar_repeticiones(palabras: List[Palabra]) -> List[Corte]:
    """Detecta un arranque en falso: el hablante empieza una frase, se
    traba, y la vuelve a empezar igual ("yo creo que... yo creo que esto
    es genial"). Se corta la PRIMERA aparición y se conserva desde la
    segunda.

    CLAVE: la segunda aparición tiene que venir CASI PEGADA a la primera
    (a lo sumo REPETICION_MAX_PALABRAS_INTERMEDIAS palabras en el medio y
    dentro de VENTANA_REPETICION_SEG). Sin esa condición, esto borraba
    frases enteras de habla normal: con "yo quiero mostrarte lo que
    hicimos este mes con el equipo y lo que viene", el "lo que" repetido
    naturalmente hacía que se borrara todo lo del medio y quedara "yo
    quiero mostrarte lo que viene". Repetir una expresión común más
    adelante en la frase NO es trabarse."""
    normalizadas = [_normalizar(p.texto) for p in palabras]
    n = len(palabras)
    cortes = []
    i = 0

    while i < n:
        encontrado = None

        for tam in range(config.NGRAMA_MAX, config.NGRAMA_MIN - 1, -1):
            if i + tam > n:
                continue
            ngrama = normalizadas[i:i + tam]
            if "" in ngrama:
                continue

            primer_j = i + tam
            ultimo_j = primer_j + config.REPETICION_MAX_PALABRAS_INTERMEDIAS
            for j in range(primer_j, min(ultimo_j, n - tam) + 1):
                if palabras[j].inicio - palabras[i + tam - 1].fin > config.VENTANA_REPETICION_SEG:
                    break
                if normalizadas[j:j + tam] == ngrama:
                    encontrado = (tam, j)
                    break

            if encontrado:
                break

        if encontrado:
            _, j = encontrado
            fin = palabras[j].inicio - config.GUARDA_ONSET_SEG
            if fin > palabras[i].inicio:
                cortes.append(Corte(inicio=palabras[i].inicio, fin=fin))
            i = j
        else:
            i += 1

    return cortes
