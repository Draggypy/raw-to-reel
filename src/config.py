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
# La energía de la voz oscila mucho de una ventana de 10ms a la siguiente
# (oclusivas, fricativas, finales de palabra). Sin suavizar, una voz que
# habla cerca del umbral alterna silencio/voz varias veces por segundo y
# eso se traducía en "corta, y de la nada corta otra vez" (2026-09-26). Se
# promedia la curva de dB en una ventana de este tamaño antes de comparar.
SUAVIZADO_SILENCIO_MS = 50
# Histéresis: para ENTRAR en silencio la señal tiene que caer este margen
# por debajo del umbral; para SALIR alcanza con volver a tocarlo. Sesgado
# a favor de la voz: una sílaba floja que roza el umbral no abre un
# silencio, pero cualquier asomo de voz lo cierra.
HISTERESIS_DB = 3.0
# Medido sobre audio real del usuario (2026-08-24): la voz vive entre -30 y
# -17 dB y el silencio entre -55 y -45 dB. Con margen 10 el umbral daba
# -44.8 dB, pegado al piso de ruido: todo lo que estaba entre -44 y -38 dB
# (silencio perfectamente audible como pausa) contaba como voz y no se
# cortaba. Con 17 el umbral queda en ~-38 dB, que es donde la curva de
# "cuánto silencio detecto" se aplana -- más allá de ahí empieza a comerse
# voz baja en vez de sumar pausas reales.
MARGEN_DB_SOBRE_PISO = 17
UMBRAL_DB_MIN = -40.0           # el umbral nunca es más estricto que esto...
# Bajado de -28 a -35 (2026-09-26): la voz medida vive entre -30 y -17dB.
# Con el techo en -28, en un video con piso de ruido alto el umbral llegaba
# a -28dB y trataba la voz baja (finales de frase, consonantes suaves) como
# silencio -- cortaba en medio del habla. -35 queda 5dB por debajo de la
# voz más floja medida y 10dB por encima del techo de silencio (-45).
UMBRAL_DB_MAX = -35.0           # ...ni más permisivo que esto
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

# Cuánto tiene que AHORRAR un corte, ya descontados los dos márgenes, para
# valer el salto visual. Agregado 2026-09-26: con silencio mínimo 300 y
# margen 150, una pausa de 320ms generaba un corte de 20ms -- la cabeza
# salta, el audio hace "clic", y el video no se acorta nada. Esos
# micro-cortes eran gran parte del "de la nada te corta" en medio de una
# frase. Con 150, sólo se cortan pausas que dejan al menos 150ms afuera
# (o sea, pausas de 2*MARGEN_SILENCIO_MS + 150 = 450ms o más).
CORTE_MINIMO_MS = 150

# --- Pausas DENTRO de una frase vs. ENTRE frases (2026-09-26) ---
# Una pausa dentro de una frase (respirar, buscar la palabra, la pausa
# dramática antes de lo importante) es ritmo del habla, no aire muerto.
# Cortarla con la misma regla que una pausa entre frases era el "estoy
# hablando 10 segundos del mismo tema y de la nada te corta". Se
# distingue con la puntuación que Whisper ya devuelve en cada palabra: si
# la última palabra antes del silencio termina en . ? ! o puntos
# suspensivos, la pausa es entre frases y se corta como siempre. Si no
# (sin puntuación, o con coma), hace falta una pausa bastante más larga
# para tocarla, y se deja más resto de silencio para que el ritmo siga
# sonando natural. Si Whisper no puntúa un tramo (pasa a veces), todo cae
# en "dentro de frase" y se corta MENOS -- el lado seguro.
PAUSA_MINIMA_DENTRO_DE_FRASE_MS = 1000
MARGEN_DENTRO_DE_FRASE_MS = 250   # 2x250 = 500ms de pausa quedan audibles
PUNTUACION_FIN_DE_FRASE = ".?!…"

# Un corte nunca pisa el inicio de una palabra según Whisper: si Whisper
# transcribió una palabra que arranca dentro de un silencio detectado por
# volumen, eso es voz baja, no silencio. El corte se recorta para terminar
# este margen antes del inicio de esa palabra (se usa el mismo margen que
# en los bordes por volumen). Sólo se miran INICIOS de palabra: los
# finales de Whisper se estiran hasta la palabra siguiente y no sirven
# (ver cut_manager.cortes_desde_silencios).
# Guarda extra antes del inicio de la palabra que sigue a una muletilla o
# repetición cortada: Whisper marca el `fin` de una palabra justo donde
# arranca la siguiente, así que cortar "hasta el fin" pisaba el primer
# fonema de la palabra siguiente si el inicio venía apenas tarde.
GUARDA_ONSET_SEG = 0.05

# --- Consolidación de cortes ---
# Un tramo conservado más corto que esto, atrapado entre dos cortes, se
# fusiona con ellos en vez de quedar como un flash de escena de una
# fracción de segundo (el "problema crítico" que ya pasó en el sistema
# anterior). Si el tramo tiene una palabra adentro no se borra: se
# ensancha hasta este mínimo robándole silencio a los costados.
# Subido de 0.3 a 0.5 (2026-09-26): dos cortes a 300ms uno del otro se
# sienten como una ráfaga de saltos; medio segundo es lo mínimo para que
# una escena entre dos cortes se lea como escena y no como parpadeo.
TRAMO_MINIMO_SEG = 0.5

# --- Muletillas y repeticiones (Fase 11) ---
# Detección por reglas, sin depender de ningún servicio externo (punto 17
# de la spec: nada de sistemas de IA innecesarios acá). Las muletillas se
# cortan siempre que aparecen en la lista (sin pedir pausa aislada -- ver
# repetition_detector.py, cambiado 2026-08-24 por feedback real). Las
# repeticiones sí siguen exigiendo 2+ palabras exactas -- una sola palabra
# repetida es demasiado común en el habla normal como para ser confiable.
# Apagado 2026-09-26 por feedback directo: "hablamos por repeticiones
# porque queremos especificar" ("mirá qué pasa esto, pero podría pasar lo
# contrario, pero pasa esto"). Aun con la regla de exigir pausa o muletilla
# en el medio, cortar repeticiones metía saltos en discurso fluido. El
# editor se especializa en silencios y muletillas; el código queda para
# poder volver a probarlo cambiando esto a True.
CORTAR_REPETICIONES = False
MULETILLAS = {"eh", "emm", "mmm", "este", "o sea", "tipo", "digamos"}
# Estas también son palabras reales ("en ESTE video", "TIPO de cosa", "O SEA
# que..."). Cortarlas siempre metía un salto en medio de una frase fluida
# (2026-09-26). Sólo se cortan si el detector de silencios encontró una
# pausa real pegada a ellas (antes o después) -- señal de duda, no de
# frase. Las que no están acá ("eh", "emm", "mmm", "digamos") no tienen
# uso legítimo en una frase y se cortan siempre.
MULETILLAS_AMBIGUAS = {"este", "tipo", "o sea"}
# Cuán cerca (en segundos) tiene que estar un silencio detectado de la
# muletilla ambigua para considerarla "aislada". Se mide contra el audio
# real, no contra los timestamps de Whisper (que nunca dejan huecos).
TOLERANCIA_MULETILLA_SILENCIO_SEG = 0.2
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
# Fundido de entrada/salida del audio en cada tramo cortado. Aunque el
# corte caiga dentro de un silencio, el ruido de fondo no es cero y el
# salto de una muestra a otra se oye como un "clic" que delata el corte
# (2026-09-26). 12ms es inaudible como fundido y suficiente para que la
# unión suene continua.
FUNDIDO_AUDIO_SEG = 0.012

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
