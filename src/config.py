"""Configuración central de Editor Gianni.

Cada fase de implementación agrega acá sus propias constantes ajustables,
a medida que se van necesitando -- no se completa todo de entrada.
"""

from pathlib import Path

# --- Rutas del proyecto ---
RAIZ = Path(__file__).resolve().parent.parent
CRUDOS = RAIZ / "Crudos"
FALLIDOS = CRUDOS / "fallidos"
LISTOS = RAIZ / "Listos"
TEMP = RAIZ / "Temp"
LOGS = RAIZ / "Logs"

# --- Formatos de video aceptados ---
EXTENSIONES_VIDEO = {".mp4", ".mov", ".mkv", ".avi"}

# --- Escaneo de Crudos/ ---
INTERVALO_ESCANEO_SEG = 5   # cada cuánto revisar si no hay nada para procesar
CHEQUEOS_ESTABILIDAD = 2    # cuántas confirmaciones de tamaño estable se piden
ESPERA_ESTABILIDAD_SEG = 2  # segundos de espera entre chequeos de estabilidad

# --- Whisper (transcripción) ---
MODELO_WHISPER = "small"     # "base" como fallback si hay que bajar consumo de RAM
DEVICE_WHISPER = "cpu"
COMPUTE_TYPE_WHISPER = "int8"  # cuantizado, mucho más liviano en CPU
IDIOMA_WHISPER = "es"

# --- Detección de silencios ---
# Umbral ADAPTATIVO (piso de ruido propio del video + margen), no un número
# fijo -- valores heredados y ya validados del sistema anterior.
VENTANA_SILENCIO_MS = 10        # tamaño de ventana de análisis de volumen
# Medido sobre audio real del usuario (2026-08-24): la voz vive entre -30 y
# -17 dB y el silencio entre -55 y -45 dB. Con margen 10 el umbral daba
# -44.8 dB, pegado al piso de ruido: todo lo que estaba entre -44 y -38 dB
# (silencio perfectamente audible como pausa) contaba como voz y no se
# cortaba. Con 17 el umbral queda en ~-38 dB, que es donde la curva de
# "cuánto silencio detecto" se aplana -- más allá de ahí empieza a comerse
# voz baja en vez de sumar pausas reales.
MARGEN_DB_SOBRE_PISO = 17
UMBRAL_DB_MIN = -40.0           # el umbral nunca es más estricto que esto...
UMBRAL_DB_MAX = -28.0           # ...ni más permisivo que esto
# Techo del PISO DE RUIDO en sí (no del umbral final) -- agregado 2026-09-20,
# feedback: "hay videos que no te dejan ni hablar, corta todo el tiempo".
# Medido en logs reales: la densidad de cortes variaba de 0.15/seg (natural)
# a 0.83/seg (casi un corte por segundo) según el video. El percentil 10 de
# volumen ASUME que al menos un 10% del clip es silencio real -- si un video
# tiene poca pausa real (el usuario habla casi sin parar en esa toma), ese
# percentil 10 termina cayendo dentro de voz baja/consonantes suaves, no
# silencio, y el umbral calculado (piso + 17dB) se cuela para arriba y
# empieza a tratar voz normal como silencio. El propio -45dB ya documentado
# arriba como techo real de "silencio" (rango medido: -55 a -45dB) es el
# límite correcto para el piso mismo, antes de sumarle el margen.
PISO_RUIDO_MAX_DB = -45.0

# Cuánto buffer dejar en cada borde de un silencio antes de cortar, para no
# comerse el final/comienzo de una palabra. Bajado de 200ms a 50ms (2026-08-24,
# feedback tras probar con un video real): con 200ms, ninguna pausa de menos
# de ~600ms llegaba a cortarse -- el video quedaba con muchos huecos que el
# usuario no quiere para nada ("si o si se cortan, solo alguien hablando").
# 50ms es el valor que el sistema anterior ya tenía tuneado para lo mismo.
# Subido de 50 a 150 (2026-09-20, feedback tras primera revisión humana real
# del resultado): con 50ms, un silencio de 300ms+ quedaba en ~100ms totales
# después del corte (2x50) -- prácticamente nada, el usuario lo sintió como
# que "corta apenas dejo de hablar" y "no se escucha nada de silencio". No es
# lo mismo que DURACION_MINIMA_SILENCIO_MS (que decide qué pausas se cortan);
# esto decide cuánto silencio queda audible DESPUÉS de cortar. Con 150,
# 2x150=300ms de silencio quedan tras cada corte -- el número que el usuario
# pidió textualmente. Sigue cortando cualquier silencio real de 300ms+, solo
# que ahora deja un resto natural en vez de un salto seco.
MARGEN_SILENCIO_MS = 150

# Un silencio más corto que esto no se corta -- directamente no alcanza el
# margen. Tiene que ser mayor al doble de MARGEN_SILENCIO_MS, si no un
# silencio "justo" en ese límite quedaría sin nada útil en el medio después
# de aplicarle el margen en los dos bordes.
# Subido de 150 a 250 (2026-08-27, feedback tras uso real): 150ms cortaba
# pausas de respiración normales dentro de una frase hablada -- el usuario
# lo describió como cortes "exagerados", sobre todo al arranque del video
# (una entrada de voz más floja al empezar a hablar cae más fácil bajo el
# umbral de dB, y con sólo 150ms de piso cualquier micro-pausa ahí se
# cortaba). 250ms deja pasar esas pausas cortas y sigue cortando silencios
# reales.
# Subido de 250 a 300 (2026-09-12, Tareas a realizar.md: "el corte ya es
# muy agresivo... por el minimo silencio que existe corta"). Mismo ajuste
# que el de 2026-08-27, un paso mas: seguia cortando pausas cortas dentro
# del habla.
DURACION_MINIMA_SILENCIO_MS = 300

# --- Consolidación de cortes ---
# Un tramo conservado más corto que esto, atrapado entre dos cortes, se
# fusiona con ellos en vez de quedar como un flash de escena de una
# fracción de segundo (el "problema crítico" que ya pasó en el sistema
# anterior). Con MARGEN_SILENCIO_MS=50 (2x50=100ms garantizados entre dos
# silencios distintos) este valor SÍ puede activarse con cortes de
# silencio solos, a diferencia de cuando el margen era 200ms.
TRAMO_MINIMO_SEG = 0.3

# --- Muletillas y repeticiones (Fase 11) ---
# Detección por reglas, sin depender de ningún servicio externo (punto 17
# de la spec: nada de sistemas de IA innecesarios acá). Las muletillas se
# cortan siempre que aparecen en la lista (sin pedir pausa aislada -- ver
# repetition_detector.py, cambiado 2026-08-24 por feedback real). Las
# repeticiones sí siguen exigiendo 2+ palabras exactas -- una sola palabra
# repetida es demasiado común en el habla normal como para ser confiable.
MULETILLAS = {"eh", "emm", "mmm", "este", "o sea", "tipo", "digamos"}
NGRAMA_MIN = 2             # mínimo de palabras exactas repetidas para contar como autocorrección
NGRAMA_MAX = 6
# La repetición tiene que venir casi pegada para ser un arranque en falso.
# Con valores laxos (6s de ventana, cualquier distancia en palabras) esto
# borraba frases enteras de habla normal -- ver repetition_detector.py.
VENTANA_REPETICION_SEG = 1.5      # desde el fin de la 1ra aparición al inicio de la 2da
REPETICION_MAX_PALABRAS_INTERMEDIAS = 1  # deja pasar una muletilla en el medio, nada más

# --- Codificación (velocidad del render) ---
# El render hace DOS codificaciones: primero cada tramo por separado, y
# después una pasada final para quemar los subtítulos. En esta máquina
# (2 núcleos, sin GPU) las dos en "medium" tardaban 21 min para un video
# de 47s en 1080p. Los tramos son archivos intermedios que se borran, así
# que se codifican en "ultrafast" con CRF más fino (no se nota la pérdida
# y evita arrastrarla a la pasada final); sólo la pasada final define la
# calidad real del video que se publica.
PRESET_SEGMENTO = "ultrafast"
CRF_SEGMENTO = 18
PRESET_FINAL = "veryfast"
CRF_FINAL = 21

# --- Validación ---
TAMANO_MINIMO_BYTES = 10_000     # por debajo de esto, se descarta como vacío/truncado
# El redondeo a nivel de frame de cada corte (-ss + re-encode, ver video_processor)
# se acumula con la cantidad de tramos: medido en un video real de 36 tramos, ~14ms
# de exceso por tramo. Una tolerancia fija fallaba por muy poco (0.51s vs 0.5s) en
# videos con muchos cortes sin que el video tuviera nada mal -- por eso escala con
# la cantidad de tramos en vez de ser un número fijo.
TOLERANCIA_DURACION_BASE_SEG = 0.15       # margen base, videos con pocos tramos
TOLERANCIA_DURACION_POR_TRAMO_SEG = 0.02  # margen extra por cada tramo (generoso: ~14ms medidos)

# --- Subtítulos ---
# Tiempos Headline (Klim Type Foundry), peso Regular -- confirmado 2026-08-25
# tras varias rondas de comparación real contra el propio contenido de
# Instagram del usuario. El nombre de familia real ("Tiempos Headline") NO
# sirve acá: el archivo es un build de evaluación/web-embed y libass resuelve
# el nombre LEGACY de la tabla `name` del ttf, no el typographic name --
# "Copyright Klim Type Foundry" es ese nombre legacy (confirmado con
# fontTools). Sólo el peso Regular está instalado en
# ~/.local/share/fonts/TiemposHeadline-Regular.ttf para evitar ambigüedad
# con otros pesos que compartan el mismo nombre interno.
#
# OJO LICENCIA: este archivo es un build de evaluación ("Not Licensed for
# Desktop Use" es literalmente su nombre de estilo interno) -- no hay
# licencia de escritorio comprada. El usuario decidió usarla igual para su
# propio contenido de Instagram con ese conocimiento. Si esto se usara para
# entregar video a un tercero (no el caso de este proyecto), habría que
# comprar la licencia real en klim.co.nz antes.
FUENTE_SUBTITULOS = "Copyright Klim Type Foundry"
# Una palabra por caption (2026-08-25, feedback tras comparar con el propio
# contenido de Instagram del usuario: ahí los subtítulos van de a una
# palabra, no de a dos -- pasan más rápido).
MAX_PALABRAS_POR_CAPTION = 1
PAUSA_CORTE_CAPTION_SEG = 0.4    # una pausa mayor a esto arranca un caption nuevo
# Subido de 0.062 a 0.085 y despues bajado a 0.075 (2026-08-25): 0.085 fue
# "el más grande" de la primera comparación, pero un poco después el usuario
# pidió achicarlo "un poquito nomás" -- 0.075 fue el punto confirmado como
# definitivo tras comparar 0.070/0.075/0.080/0.085 lado a lado.
FRACCION_TAMANO_FUENTE = 0.075
# Bajado de 0.028 a 0.004 y despues a 0.0025 (2026-08-25): con 0.028 el
# contorno (54px sobre una fuente de 119px, ~45% del alto de la letra) era
# tan grueso que los trazos se fusionaban en un blob negro sólido detrás del
# texto -- se notaba sobre todo en tildes y letras juntas. 0.0025 (~5px con
# el tamaño de fuente actual) da un trazo fino que define la letra sin
# engordarla, confirmado como el punto justo tras comparar 3/5/7px.
FRACCION_CONTORNO = 0.0025
# Estira las letras verticalmente sin ensanchar los costados (ScaleX se
# mantiene en 100) -- confirmado 2026-08-25 tras comparar 115/125/135:
# 125 da el aire más "condensado y alto" sin deformarse.
ESCALA_VERTICAL_SUBTITULOS = 125
# Tracking negativo (junta las letras). Confirmado -8 tras varias rondas de
# comparación a distintos tamaños de fuente -- ver nota en subtitle_generator
# sobre por qué esto se aplica como override \fsp y no en el campo Spacing
# del Style (libass ignora Spacing negativo).
TRACKING_SUBTITULOS = -8
FRACCION_MARGEN_INFERIOR = 0.20  # zona segura para no chocar con la UI de Instagram
