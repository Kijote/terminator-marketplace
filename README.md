# terminator-marketplace

Marketplace de plugins para [Terminator](https://github.com/gnome-terminator/terminator).
Agrega al menú del clic derecho un submenú **Plugins** para activar y desactivar
en caliente los plugins del catálogo, y para actualizarlo con `git pull`. Cuando
cambia el código de un plugin activo (al actualizar o al editarlo), se recarga
solo, sin reiniciar Terminator.

## Instalación

```bash
curl -fsSL https://raw.githubusercontent.com/Kijote/terminator-marketplace/main/install.sh | bash
```

Clona el repo en `~/.local/share/terminator-marketplace` (o en
`$TERMINATOR_MARKETPLACE_DIR`) y activa el marketplace. Si ya estaba instalado,
lo actualiza. También se puede clonar a mano y correr `./install.sh` desde el clon.

Después cerrá Terminator del todo y abrilo de nuevo: clic derecho → **Plugins**.

## Plugins

| Plugin | Qué hace |
|---|---|
| Autosave de sesión | Guarda ventanas, splits, directorios y comandos (`npm run dev:ws`, `claude --resume <sesión>`, monitores como `htop`/`watch` y `tail -f`) cada 15s y los restaura al abrir Terminator. Qué programas se relanzan se configura en `~/.config/terminator/autosave.conf` (una regla por línea, ej. `htop` o `tail -f`) o con clic derecho → **Autosave**. |

## Contribuir

¿Querés sumar un plugin? Mirá [CONTRIBUTING.md](CONTRIBUTING.md): cómo
escribirlo, agregarlo al catálogo, probarlo y abrir el pull request. Cada PR
pasa por una validación automática (`scripts/validate_catalog.py`).
