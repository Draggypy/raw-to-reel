"""Muletillas y repeticiones, detectadas de forma conservadora por reglas
-- sin depender de ningún servicio externo (punto 17 de la spec: nada de
sistemas de IA innecesarios para esto). La arquitectura permite cambiar a
un analista más inteligente más adelante (por ejemplo, algo como lo que
hacía el sistema anterior con `claude -p`) sin tocar cut_manager.py: sólo
haría falta otra función acá que devuelva la misma lista de Corte.

Regla central, igual que en todo el resto del proyecto: ante la duda, no
cortar. Una muletilla sólo se corta si está aislada (pausa real antes o
después -- señal de duda real, no parte de una frase fluida). Una
repetición sólo se corta si son 2 o más palabras exactas repetidas poco
después -- una sola palabra repetida es demasiado común en el habla
normal como para ser señal confiable de un arranque en falso.
"""

import re
import unicodedata
from typing import List

import config
from cut_manager import Corte
from transcription import Palabra


def _normalizar(texto: str) -> str:
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", texto)


def detectar_muletillas(palabras: List[Palabra]) -> List[Corte]:
    """Busca la muletilla (de una o más palabras, p. ej. "o sea") más
    larga que coincida en cada posición, y la corta SIEMPRE que aparezca
    en la lista -- sin pedir una pausa aislada alrededor.

    Antes exigía una pausa real (150ms) antes o después para considerarla
    "aislada", pero Whisper casi nunca deja timestamps con esa separación
    limpia aunque la muletilla exista de verdad -- en la práctica esa
    condición casi nunca se cumplía y no cortaba nada (medido con un video
    real: 393 palabras, 0 muletillas detectadas). Sacada por feedback
    directo del usuario tras ver el resultado (2026-08-24): prioriza cero
    huecos por encima de un posible falso positivo. Ojo: "este" y "tipo"
    también son palabras reales (pronombre / "tipo de cosa"), así que
    ocasionalmente se puede cortar un uso legítimo, no sólo la duda."""
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
            cortes.append(Corte(inicio=palabras[i].inicio, fin=palabras[i + tam_match - 1].fin))
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
            cortes.append(Corte(inicio=palabras[i].inicio, fin=palabras[j].inicio))
            i = j
        else:
            i += 1

    return cortes
