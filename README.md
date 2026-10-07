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

## Bloquear un plugin (parche de seguridad)

Para desactivar un plugin en todas las instalaciones, agregale `"blocked"` con
el motivo en `catalog.json` y subilo a `main`:

```json
{
  "id": "mi_plugin",
  ...
  "blocked": "Vulnerabilidad en la versión 1.2, se corrige en la próxima"
}
```

- El marketplace consulta el catálogo de GitHub al arrancar y cada 30 minutos,
  **solo para leer los bloqueos**: no baja ni cambia código sin que lo pidas.
- Un plugin bloqueado se desactiva al instante, se borra su symlink y sale de
  la config, así que no vuelve a cargar. En el menú aparece como
  **(bloqueado)**, con el motivo en el tooltip, y no se puede activar.
- Para levantar el bloqueo, sacá el campo `"blocked"`. Los que lo tenían
  activo lo vuelven a activar desde el menú.
- Si el bloqueo se publica con Terminator cerrado, sin el guardián (ver abajo)
  el plugin puede llegar a cargarse al arrancar, porque Terminator carga los
  plugins sin un orden fijo, y se desactiva apenas el marketplace lee el
  bloqueo, en los primeros segundos.

Sacar un plugin del catálogo también lo desactiva, pero solo cuando cada
instalación actualiza el catálogo. Para un parche urgente usá `"blocked"`.

### Guardián de seguridad

Para que un plugin bloqueado no llegue a ejecutarse nunca, ni siquiera al
arrancar, instalá el guardián:

```bash
~/.local/share/terminator-marketplace/install.sh --guard   # o desde tu clon
# con el one-liner:
curl -fsSL https://raw.githubusercontent.com/Kijote/terminator-marketplace/main/install.sh | bash -s -- --guard
```

Se instala con `sudo` en la carpeta de plugins del sistema de Terminator, que
se carga antes que la tuya. Al arrancar Terminator consulta los bloqueos en
GitHub (con un timeout de 2 segundos; sin red usa los últimos que conoce) y
saca los plugins bloqueados antes de que se carguen.

En el menú **Plugins** se ve si está activo o desactualizado. Cuando cambia,
actualizalo con el mismo comando. Para sacarlo: `install.sh --remove-guard`.

## Contribuir

¿Querés sumar un plugin? Mirá [CONTRIBUTING.md](CONTRIBUTING.md): cómo
escribirlo, agregarlo al catálogo, probarlo y abrir el pull request. Cada PR
pasa por una validación automática (`scripts/validate_catalog.py`).
