"""Logging simple: una línea con timestamp por evento a un archivo de texto
en Logs/, más un estado.json liviano para ver el progreso en vivo sin
necesitar cargar dependencias pesadas para mirarlo.
"""

import json
import time
from typing import Optional

import config

ARCHIVO_LOG = config.LOGS / "editor_gianni.log"
ARCHIVO_ESTADO = config.LOGS / "estado.json"


def log(mensaje: str) -> None:
    config.LOGS.mkdir(parents=True, exist_ok=True)
    linea = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}\n"
    with ARCHIVO_LOG.open("a", encoding="utf-8") as f:
        f.write(linea)
    print(linea, end="")


def actualizar_estado(video: Optional[str], etapa: str) -> None:
    """Escritura atómica (escribe a un temporal y renombra) para que un
    lector externo nunca encuentre el archivo a medio escribir."""
    config.LOGS.mkdir(parents=True, exist_ok=True)
    datos = {
        "video": video,
        "etapa": etapa,
        "actualizado": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    temporal = ARCHIVO_ESTADO.with_suffix(".tmp")
    temporal.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporal.replace(ARCHIVO_ESTADO)
