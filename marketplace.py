"""Marketplace de plugins para Terminator.

Agrega al menu del clic derecho un submenu "Plugins" con los plugins de
catalog.json: cada uno se activa/desactiva en caliente. Instalar un plugin es
crear un symlink en ~/.config/terminator/plugins/ hacia este repo.

El marketplace vigila los archivos del repo: cuando cambia el codigo de un
plugin activo (por "Actualizar catalogo", que hace git pull, o porque se
edito el archivo) lo recarga en caliente, sin reiniciar Terminator. Si el
codigo nuevo falla al cargar, sigue corriendo la version anterior.
"""
import json
import os
import subprocess
import types

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk

import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.util import err, get_config_dir

AVAILABLE = ['Marketplace']

REPO = os.path.dirname(os.path.realpath(__file__))
SELF = {'id': 'marketplace', 'name': 'Marketplace', 'file': 'marketplace.py',
        'classes': ['Marketplace']}
# Los editores y git guardan en rafagas de eventos: se espera a que se calmen
RELOAD_DELAY_MS = 500
PLUGINS_DIR = os.path.join(get_config_dir(), 'plugins')


def _catalog():
    try:
        with open(os.path.join(REPO, 'catalog.json')) as f:
            return json.load(f)
    except (OSError, ValueError) as ex:
        err('Marketplace: no se pudo leer catalog.json: %s' % ex)
        return []


def _link(entry):
    return os.path.join(PLUGINS_DIR, os.path.basename(entry['file']))


def _set_enabled(classes, enabled):
    config = Config()
    current = [c for c in config['enabled_plugins'] if c not in classes]
    config['enabled_plugins'] = current + (classes if enabled else [])
    config.save()


def _load(entry):
    """Importa de cero el archivo del plugin (sin pasar por la cache de modulos)."""
    # Se compila el fuente directo: la cache de __pycache__ compara mtime en
    # segundos y tamano, y un cambio rapido del mismo largo cargaria lo viejo
    path = os.path.join(REPO, entry['file'])
    with open(path, encoding='utf-8') as f:
        source = f.read()
    module = types.ModuleType('marketplace_' + entry['id'])
    module.__file__ = path
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


def _entry_for(path):
    real = os.path.realpath(path)
    for entry in _catalog() + [SELF]:
        if os.path.realpath(os.path.join(REPO, entry['file'])) == real:
            return entry
    return None


def _notify(message):
    subprocess.Popen(['notify-send', 'Terminator', message])


class Marketplace(plugin.MenuItem):
    capabilities = ['terminal_menu']

    def __init__(self):
        plugin.MenuItem.__init__(self)
        self.pending = {}
        self.monitors = []
        for path in (REPO, os.path.join(REPO, 'plugins')):
            monitor = Gio.File.new_for_path(path).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None)
            monitor.connect('changed', self.on_file_changed)
            self.monitors.append(monitor)

    def unload(self):
        for monitor in self.monitors:
            monitor.cancel()
        for source in self.pending.values():
            GLib.source_remove(source)
        self.pending = {}

    def callback(self, menuitems, menu, terminal):
        registry = plugin.PluginRegistry()
        submenu = Gtk.Menu()

        for entry in _catalog():
            item = Gtk.CheckMenuItem.new_with_label(entry['name'])
            item.set_tooltip_text(entry.get('description', ''))
            item.set_active(all(registry.is_enabled(c) for c in entry['classes']))
            item.connect('toggled', self.on_toggled, entry)
            submenu.append(item)

        submenu.append(Gtk.SeparatorMenuItem())
        update = Gtk.MenuItem.new_with_label('Actualizar catálogo')
        update.connect('activate', self.on_update)
        submenu.append(update)

        root = Gtk.MenuItem.new_with_label('Plugins')
        root.set_submenu(submenu)
        menuitems.append(root)

    def on_toggled(self, item, entry):
        try:
            if item.get_active():
                self.install(entry)
            else:
                self.uninstall(entry)
        except Exception as ex:
            err('Marketplace: %s' % ex)
            _notify('Error con %s: %s' % (entry['name'], ex))

    def install(self, entry):
        registry = plugin.PluginRegistry()
        link = _link(entry)
        if not os.path.lexists(link):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
            os.symlink(os.path.join(REPO, entry['file']), link)

        module = _load(entry)
        for name in entry['classes']:
            if not registry.is_enabled(name):
                registry.available_plugins[name] = getattr(module, name)
                registry.enable(name)
        _set_enabled(entry['classes'], True)
        _notify('%s activado' % entry['name'])

    def uninstall(self, entry):
        registry = plugin.PluginRegistry()
        for name in entry['classes']:
            if registry.is_enabled(name):
                registry.disable(name)
        _set_enabled(entry['classes'], False)
        link = _link(entry)
        if os.path.islink(link):
            os.remove(link)
        _notify('%s desactivado' % entry['name'])

    def on_update(self, _item):
        subprocess.Popen(
            ['bash', '-c',
             'git -C "$1" pull --ff-only'
             ' && notify-send Terminator "Catálogo actualizado"'
             ' || notify-send Terminator "No se pudo actualizar el catálogo"',
             'update', REPO])

    def on_file_changed(self, _monitor, file, other, event):
        if event == Gio.FileMonitorEvent.RENAMED:
            # Guardado atomico (vim, git): se escribe un temporal y se renombra
            file = other
        elif event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                           Gio.FileMonitorEvent.CREATED,
                           Gio.FileMonitorEvent.MOVED_IN):
            return
        path = file.get_path() if file else None
        if not path or not path.endswith('.py'):
            return
        if path in self.pending:
            GLib.source_remove(self.pending[path])
        self.pending[path] = GLib.timeout_add(RELOAD_DELAY_MS, self.on_reload_due, path)

    def on_reload_due(self, path):
        self.pending.pop(path, None)
        entry = _entry_for(path)
        if entry:
            self.reload(entry)
        return False

    def reload(self, entry):
        """Recarga en caliente las clases activas del plugin."""
        registry = plugin.PluginRegistry()
        active = [c for c in entry['classes'] if registry.is_enabled(c)]
        if not active:
            return
        try:
            module = _load(entry)
            classes = {name: getattr(module, name) for name in active}
        except Exception as ex:
            err('Marketplace: no se pudo recargar %s: %s' % (entry['name'], ex))
            _notify('%s no se recargó, sigue la versión anterior: %s' % (entry['name'], ex))
            return
        for name, cls in classes.items():
            old = registry.available_plugins[name]
            registry.disable(name)
            registry.available_plugins[name] = cls
            try:
                registry.enable(name)
            except Exception as ex:
                err('Marketplace: no se pudo recargar %s: %s' % (name, ex))
                registry.available_plugins[name] = old
                registry.enable(name)
                _notify('%s no se recargó, sigue la versión anterior: %s' % (entry['name'], ex))
                return
        _notify('%s recargado' % entry['name'])
