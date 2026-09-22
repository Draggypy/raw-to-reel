"""Consolida los cortes candidatos (silencios, muletillas y repeticiones)
en la lista final de tramos a CONSERVAR del video.

Dos cortes demasiado cercanos se fusionan, para no dejar entre ellos un
tramo conservado tan corto que se vea como un flash de escena -- pero
nunca si en el medio hay una palabra, porque fusionar borra lo que queda
adentro.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import config
from silence_detector import Silencio
from transcription import Palabra


@dataclass
class Corte:
    inicio: float
    fin: float


@dataclass
class Tramo:
    inicio: float
    fin: float

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


def cortes_desde_silencios(silencios: List[Silencio]) -> List[Corte]:
    """El corte real es más angosto que el silencio detectado: deja
    MARGEN_SILENCIO_MS de buffer en cada borde para no comerse el final
    o el comienzo de una palabra.

    Ese margen es la ÚNICA protección que necesitan estos cortes, y es
    deliberado. Antes había además un paso que "protegía palabras" usando
    los timestamps de Whisper, y resultó ser un desastre: Whisper estira
    el `fin` de cada palabra hasta donde arranca la siguiente, así que se
    traga la pausa del medio. Un silencio REAL de 1.6s medido por el audio
    caía "dentro" de una palabra según Whisper y el corte se descartaba
    entero. Medido en un video real: de 20 silencios detectados casi
    ninguno se cortaba, y quedaban 9.4s de silencio en 35s de video.
    El detector de silencios mide volumen real: si dice que ahí no hay
    sonido, no hay ninguna palabra que proteger."""
    margen = config.MARGEN_SILENCIO_MS / 1000
    cortes = []
    for s in silencios:
        inicio = s.inicio + margen
        fin = s.fin - margen
        if fin > inicio:  # la Fase 5 ya lo garantiza, pero por las dudas
            cortes.append(Corte(inicio=inicio, fin=fin))
    return cortes


def _fusionar_cercanos(cortes: List[Corte], palabras: List[Palabra]) -> List[Corte]:
    """Fusiona dos cortes muy pegados para no dejar entre ellos un tramo
    conservado tan corto que se vea como un flash de escena.

    OJO: fusionar BORRA lo que quedaba en el medio. Por eso sólo se fusiona
    si en ese hueco no arranca ninguna palabra -- si ahí hay una palabra
    real (aunque sea corta, "sí", "no", "y"), se prefiere el tramo corto
    antes que borrar algo que el usuario dijo. Se mira el inicio de la
    palabra y no su fin porque Whisper estira los finales (ver
    cortes_desde_silencios)."""
    if not cortes:
        return []

    ordenados = sorted(cortes, key=lambda c: c.inicio)
    fusionados = [Corte(ordenados[0].inicio, ordenados[0].fin)]

    for actual in ordenados[1:]:
        anterior = fusionados[-1]
        hueco = actual.inicio - anterior.fin
        hay_palabra_en_el_hueco = any(
            anterior.fin <= p.inicio < actual.inicio for p in palabras
        )
        if hueco < config.TRAMO_MINIMO_SEG and not hay_palabra_en_el_hueco:
            anterior.fin = max(anterior.fin, actual.fin)
        else:
            fusionados.append(Corte(actual.inicio, actual.fin))

    return fusionados


def _tramos_conservados(cortes: List[Corte], duracion_total: float) -> List[Tramo]:
    tramos = []
    cursor = 0.0

    for corte in cortes:
        if corte.inicio > cursor:
            tramos.append(Tramo(inicio=cursor, fin=corte.inicio))
        cursor = max(cursor, corte.fin)

    if cursor < duracion_total:
        tramos.append(Tramo(inicio=cursor, fin=duracion_total))

    return [t for t in tramos if t.duracion > 0]


def _asegurar_tramo_minimo(
    tramos: List[Tramo], palabras: List[Palabra], duracion_total: float
) -> List[Tramo]:
    """Elimina las "escenas instantáneas": tramos conservados tan cortos
    que se ven como un flash (se midió uno de 50 ms = un frame y medio).

    Dos casos distintos:
    - El tramo no tiene ninguna palabra: era puro relleno de márgenes (el
      caso típico es el arranque del video, donde el margen del primer
      silencio deja 50 ms sueltos antes del corte). Se descarta.
    - El tramo sí tiene una palabra: no se puede tirar sin perder lo que
      dijo, así que se ENSANCHA hacia los costados robándole tiempo al
      silencio de al lado hasta llegar al mínimo. O sea: se le devuelve un
      poco de silencio al video justo ahí, que es exactamente lo que hace
      falta para que el corte no se sienta como un salto raro."""
    minimo = config.TRAMO_MINIMO_SEG
    resultado: List[Tramo] = []

    for i, t in enumerate(tramos):
        if t.duracion >= minimo:
            resultado.append(t)
            continue

        if not any(t.inicio <= p.inicio < t.fin for p in palabras):
            continue

        falta = minimo - t.duracion
        # el borde izquierdo no puede pisar al tramo anterior YA ensanchado
        limite_izq = resultado[-1].fin if resultado else 0.0
        limite_der = tramos[i + 1].inicio if i + 1 < len(tramos) else duracion_total
        espacio_izq = max(0.0, t.inicio - limite_izq)
        espacio_der = max(0.0, limite_der - t.fin)

        toma_der = min(falta / 2, espacio_der)
        toma_izq = min(falta - toma_der, espacio_izq)
        toma_der = min(falta - toma_izq, espacio_der)  # rebalanceo si un lado no daba

        resultado.append(Tramo(inicio=t.inicio - toma_izq, fin=t.fin + toma_der))

    return resultado


def consolidar(cortes: List[Corte], duracion_total: float, palabras: List[Palabra]) -> List[Tramo]:
    """Fuente-agnóstico: recibe cortes ya calculados (de silencios,
    muletillas y repeticiones), fusiona los que quedarían demasiado cerca
    -- sin borrar palabras al hacerlo -- y devuelve los tramos finales a
    conservar."""
    cortes = _fusionar_cercanos(cortes, palabras)
    tramos = _tramos_conservados(cortes, duracion_total)
    return _asegurar_tramo_minimo(tramos, palabras, duracion_total)


def remapear_intervalo(
    inicio: float, fin: float, tramos: List[Tramo]
) -> Optional[Tuple[float, float]]:
    """Traduce un intervalo [inicio, fin) de la línea de tiempo ORIGINAL
    (p. ej. una palabra de Whisper) a la línea de tiempo ya cortada.

    A propósito NO exige que los dos bordes caigan exactos dentro del mismo
    tramo conservado: los timestamps de palabra de Whisper no son
    perfectos, y remapear cada borde por separado (como hacía la versión
    anterior de esto) descartaba palabras enteras -- audibles en el video
    final -- sólo porque un borde según Whisper rozaba el límite de un
    corte por unos milisegundos. Acá se busca el tramo con más solapamiento
    con el intervalo y se recorta a ese tramo. Sólo devuelve None si el
    intervalo no solapa NINGÚN tramo conservado -- ahí sí no hay nada que
    mostrar."""
    acumulado = 0.0
    mejor: Optional[Tuple[float, Tramo, float]] = None
    for t in tramos:
        solapa_inicio = max(inicio, t.inicio)
        solapa_fin = min(fin, t.fin)
        solapamiento = solapa_fin - solapa_inicio
        if solapamiento > 0 and (mejor is None or solapamiento > mejor[0]):
            mejor = (solapamiento, t, acumulado)
        acumulado += t.duracion

    if mejor is None:
        return None

    _, tramo, offset = mejor
    inicio_recortado = max(inicio, tramo.inicio)
    fin_recortado = min(fin, tramo.fin)
    return (
        offset + (inicio_recortado - tramo.inicio),
        offset + (fin_recortado - tramo.inicio),
    )
