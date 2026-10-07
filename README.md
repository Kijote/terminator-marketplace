# terminator-marketplace

Marketplace de plugins para [Terminator](https://github.com/gnome-terminator/terminator).
Agrega al menú del clic derecho un submenú **Plugins** para activar y desactivar
en caliente los plugins del catálogo, y para actualizarlo con `git pull`.

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

## Agregar un plugin

1. Poné el archivo en `plugins/`. Es un plugin normal de Terminator: define
   `AVAILABLE` y clases que heredan de `terminatorlib.plugin.Plugin`.
2. Si arranca timers o conecta señales, implementá `unload()` para limpiarlos,
   así se puede desactivar sin reiniciar.
3. Agregalo a `catalog.json`:
   ```json
   {
     "id": "mi_plugin",
     "name": "Mi plugin",
     "description": "Qué hace (se muestra como tooltip).",
     "file": "plugins/mi_plugin.py",
     "classes": ["MiPlugin"]
   }
   ```

Los plugins se instalan como symlinks a este repo, así que un **Actualizar
catálogo** baja el código nuevo. Los cambios de código de un plugin ya activo
aplican al reiniciar Terminator.
