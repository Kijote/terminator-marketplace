# terminator-marketplace

Marketplace de plugins para [Terminator](https://github.com/gnome-terminator/terminator).
Agrega al menú del clic derecho un submenú **Plugins** para activar y desactivar
en caliente los plugins del catálogo, y para actualizarlo con `git pull`.

## Instalación

```bash
git clone <este repo> ~/dev/terminator-marketplace
~/dev/terminator-marketplace/install.sh
```

Después reiniciá Terminator (cerralo del todo y abrilo de nuevo).

## Plugins

| Plugin | Qué hace |
|---|---|
| Autosave de sesión | Guarda ventanas, splits, directorios y comandos (`npm run dev:ws`, `claude --resume <sesión>`) cada 15s y los restaura al abrir Terminator. |

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
