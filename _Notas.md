# Gianni Edit — Notas

Procesador de video talking-head: corta silencios, corta muletillas/repeticiones conservador, quema subtítulos. Corre como servicio systemd (`gianni-edit.service`) — vigila `Crudos/` solo, no hace falta lanzarlo a mano.

## ⚠️ Incidente corregido 2026-09-14: el servicio corría "en el aire"

La carpeta real se había movido a `Escritorio/System/Gianni Edit/` en algún momento anterior, pero el servicio de systemd seguía con la ruta vieja (`Escritorio/Gianni Edit/`) en memoria — seguía "activo" según `systemctl status`, pero escribía su estado en una carpeta casi vacía y nunca veía los videos que caían en el `Crudos/` real. Quedaba como zombi: parecía andar, no hacía nada.

**Arreglado al mover todo a `~/Vault/`:** se paró el servicio, se consolidó todo en `~/Vault/Gianni Edit/` (la copia real, con `venv/`, `src/`, `Crudos/`, `Logs/` con historial real), se actualizó `ExecStart` en `~/.config/systemd/user/gianni-edit.service` a la ruta nueva, y se reinició. Verificado con `/proc/<pid>/cwd` y timestamps de `Logs/estado.json` que ahora escribe donde corresponde.

**Lección para la próxima vez que se mueva esta carpeta:** después de mover, hay que actualizar `ExecStart` en el `.service` y correr `systemctl --user daemon-reload && systemctl --user restart gianni-edit.service` — si no, se repite el mismo bug silencioso.

## Parámetros clave (`src/config.py`)

- `DURACION_MINIMA_SILENCIO_MS = 300` — piso de cuánto silencio hace falta para cortar (subido de 250 el 2026-09-13).
- `MARGEN_SILENCIO_MS = 50` — buffer en cada borde de un corte para no comerse una palabra.
- `TRAMO_MINIMO_SEG = 0.3` — evita flashes de escena de una fracción de segundo.

## Pendiente

Revisión humana de calidad (subtítulos, sensación del corte) — la validación mecánica pasa, pero nadie escuchó/miró el resultado con atención todavía.
