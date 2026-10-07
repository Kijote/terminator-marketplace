"""Marketplace de plugins para Terminator.

Agrega al menu del clic derecho un submenu "Plugins" con los plugins de
catalog.json: cada uno se activa/desactiva en caliente. Instalar un plugin es
crear un symlink en ~/.config/terminator/plugins/ hacia este repo, asi un
"Actualizar catalogo" (git pull) actualiza su codigo.
"""
import importlib.util
import json
import os
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.util import err, get_config_dir

AVAILABLE = ['Marketplace']

REPO = os.path.dirname(os.path.realpath(__file__))
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


def _notify(message):
    subprocess.Popen(['notify-send', 'Terminator', message])


class Marketplace(plugin.MenuItem):
    capabilities = ['terminal_menu']

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

        missing = [c for c in entry['classes'] if c not in registry.available_plugins]
        if missing:
            spec = importlib.util.spec_from_file_location(entry['id'], link)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for name in missing:
                registry.available_plugins[name] = getattr(module, name)

        for name in entry['classes']:
            if not registry.is_enabled(name):
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
             ' && notify-send Terminator "Catálogo actualizado (los cambios de código aplican al reiniciar)"'
             ' || notify-send Terminator "No se pudo actualizar el catálogo"',
             'update', REPO])
