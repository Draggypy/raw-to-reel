"""Coreografía segura de entregar un video terminado en Listos/ y sólo
entonces borrar el original de Crudos/. El original nunca se toca hasta
que la copia final ya fue verificada de forma independiente.
"""

import shutil
from pathlib import Path

import config
import logger


def _copia_valida(temp_path: Path, destino: Path) -> bool:
    """Chequeo barato de que la copia a Listos/ llegó completa."""
    return destino.exists() and destino.stat().st_size == temp_path.stat().st_size


def finalizar(temp_path: Path, original: Path) -> bool:
    """Copia temp_path -> Listos/, verifica la copia, y sólo entonces borra
    el original de Crudos/ y el temporal. Si algo falla en el camino, el
    original queda intacto."""
    config.LISTOS.mkdir(parents=True, exist_ok=True)
    destino = config.LISTOS / original.name

    try:
        shutil.copy2(temp_path, destino)
    except OSError as e:
        logger.log(f"ERROR copiando a Listos/: {e}")
        return False

    if not _copia_valida(temp_path, destino):
        logger.log("ERROR: la copia en Listos/ no coincide con el temporal, no se borra el original")
        destino.unlink(missing_ok=True)
        return False

    try:
        original.unlink()
    except OSError as e:
        logger.log(f"ERROR borrando original de Crudos/ (la copia en Listos/ ya está OK): {e}")
        return False

    try:
        temp_path.unlink()
    except OSError:
        pass  # no crítico: el temporal se puede limpiar en la próxima corrida

    return True


def marcar_fallido(original: Path) -> None:
    """Mueve un original que falló el procesamiento a Crudos/fallidos/, para
    no reintentarlo solo en el próximo escaneo."""
    config.FALLIDOS.mkdir(parents=True, exist_ok=True)
    destino = config.FALLIDOS / original.name
    try:
        shutil.move(str(original), str(destino))
        logger.log(f"Movido a fallidos/: {original.name}")
    except OSError as e:
        logger.log(f"ERROR moviendo a fallidos/: {e}")
