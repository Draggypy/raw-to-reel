#!/usr/bin/env python3
"""Ver Estado -- muestra en vivo qué está haciendo Editor Gianni.

Script independiente y liviano: no importa nada del pipeline (ni siquiera
config.py de src/), así que corre con el python3 del sistema, sin el
venv del proyecto, y es seguro dejarlo abierto en una terminal mientras
se edita el código -- nunca carga numpy/whisper/ffmpeg.

Uso: python3 ver_estado.py   (Ctrl+C para salir)
"""

import json
import time
from pathlib import Path

ARCHIVO_ESTADO = Path(__file__).resolve().parent / "Logs" / "estado.json"


def leer_estado():
    try:
        return json.loads(ARCHIVO_ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def main():
    print("Viendo el progreso de Editor Gianni (Ctrl+C para salir)...")
    anterior = None
    avisado_esperando = False

    while True:
        estado = leer_estado()

        if estado is None:
            if not avisado_esperando:
                print("Esperando a que Editor Gianni arranque...")
                avisado_esperando = True
        elif estado != anterior:
            video = estado.get("video") or "(ninguno)"
            etapa = estado.get("etapa", "?")
            hora = estado.get("actualizado", "")
            print(f"[{hora}] {video} -> {etapa}")
            anterior = estado
            avisado_esperando = False

        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nChau.")
