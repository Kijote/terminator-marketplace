# Contribuir

¡Gracias por querer sumar un plugin! El flujo es el de siempre en GitHub:
fork, rama, cambios y pull request.

## 1. Prepará tu entorno

```bash
git clone https://github.com/<tu-usuario>/terminator-marketplace.git
cd terminator-marketplace
./install.sh
```

`install.sh` corrido desde el clon usa ese clon, así que vas a probar tu
versión. Cerrá Terminator del todo y abrilo de nuevo para que cargue el
marketplace.

## 2. Escribí el plugin

Un plugin es un archivo de Python en `plugins/` que Terminator carga al
arrancar. Lo mínimo:

```python
import terminatorlib.plugin as plugin

AVAILABLE = ['MiPlugin']


class MiPlugin(plugin.MenuItem):
    capabilities = ['terminal_menu']

    def callback(self, menuitems, menu, terminal):
        ...
```

- **`AVAILABLE`** tiene que ser una lista literal con los nombres de las clases
  que expone el archivo.
- **Las clases** heredan de `terminatorlib.plugin.Plugin` o de una de sus
  subclases (`MenuItem` para agregar cosas al menú del clic derecho,
  `URLHandler` para reconocer URLs). Mirá los plugins que trae Terminator en
  `/usr/lib/python3/dist-packages/terminatorlib/plugins/` como ejemplo.
- **`unload()`**: si tu plugin arranca timers (`GLib.timeout_add…`) o conecta
  señales, implementá `unload()` y limpialos ahí. El marketplace activa,
  desactiva y recarga plugins sin reiniciar Terminator, y sin `unload()` la
  versión vieja sigue corriendo junto a la nueva.
- **Nombres únicos**: el nombre del archivo no puede coincidir con un módulo de
  Python ni con un plugin que trae Terminator (`logger.py`, `json.py`…), y las
  clases no pueden repetirse con las de otro plugin. El validador lo revisa.
- **Configuración**: si tu plugin es configurable, guardala en un archivo
  propio en `~/.config/terminator/` y no en el `config` de Terminator. Una
  instancia abierta de Terminator pisa ese archivo cuando guarda.
- **Sin sorpresas**: nada de pedidos de red, comandos destructivos ni lectura
  del contenido de las terminales sin que la descripción del plugin lo diga.

## 3. Agregalo al catálogo

Sumá una entrada a `catalog.json`:

```json
{
  "id": "mi_plugin",
  "name": "Mi plugin",
  "description": "Qué hace, en una línea (se muestra como tooltip en el menú).",
  "file": "plugins/mi_plugin.py",
  "classes": ["MiPlugin"]
}
```

Y una fila en la tabla de **Plugins** del README.

## 4. Probalo

```bash
python3 scripts/validate_catalog.py
```

Después reiniciá Terminator y desde clic derecho → **Plugins**:

1. Activalo y verificá que funcione.
2. Desactivalo y verificá que deje de hacer lo que hacía.
3. Volvé a activarlo, sin reiniciar.

Mientras el plugin está activo, cada vez que guardás el archivo el marketplace
lo recarga solo y te avisa con una notificación. Si el código nuevo tiene un
error, la notificación lo dice y sigue corriendo la versión anterior. Si algo
falla, corré Terminator con `terminator -d` desde otra terminal para
ver los errores.

## 5. Abrí el pull request

El template del PR te pide qué hace el plugin y qué toca (archivos, comandos,
red). En cada PR corre una validación automática del catálogo; si falla,
revisá el log del check.

Los plugins corren con los permisos del usuario dentro de Terminator, así que
cada PR se revisa con cuidado antes de mergear. Una vez mergeado, le aparece a
todos con **Actualizar catálogo**.
