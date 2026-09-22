# Gianni Edit

Procesador automático de video talking-head: corta silencios y muletillas/repeticiones, y quema subtítulos generados automáticamente — sin edición manual.

Corre como un servicio que vigila una carpeta: dejás un video crudo adentro y sale editado del otro lado.

## Qué hace

1. **Transcribe** el video con [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (local, sin API externa).
2. **Detecta** silencios, muletillas y repeticiones.
3. **Consolida los cortes**, protegiendo palabras completas (nunca corta a mitad de una).
4. **Genera subtítulos** remapeados a los tiempos ya cortados.
5. **Corta y quema los subtítulos** con `ffmpeg` en un solo paso.
6. **Valida** el resultado antes de darlo por bueno — si algo falla, el video se marca como fallido en vez de entregarse a medias.

## Cómo se usa

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Necesitás `ffmpeg` instalado en el sistema.

Ajustá `src/config.py` con las rutas de tus carpetas (`Crudos/`, `Listos/`, `Temp/`, `Logs/`) y corré:

```bash
python src/main.py
```

Dejá un video en `Crudos/` — cuando termina de procesarlo, aparece listo en `Listos/`. Un video a la vez, siempre.

## Parámetros principales (`src/config.py`)

- `DURACION_MINIMA_SILENCIO_MS` — cuánto silencio hace falta para que se considere corte.
- `MARGEN_SILENCIO_MS` — margen en cada borde del corte para no comerse una palabra.
- `TRAMO_MINIMO_SEG` — evita dejar tramos de una fracción de segundo.

## Estado del proyecto

Activo, en maduración. La validación automática pasa en todos los casos probados, pero todavía no hay una revisión humana exhaustiva de la sensación final de los cortes y subtítulos en un video real de punta a punta — tratalo como beta, no como producto terminado.

Se agradecen issues y PRs.

## Licencia

MIT — ver `LICENSE`.
