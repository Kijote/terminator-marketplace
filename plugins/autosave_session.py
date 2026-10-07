"""Autosave de la sesion de Terminator (estilo tmux-continuum).

Cada INTERVAL segundos guarda la disposicion actual (ventanas, splits,
pestanas y directorio de cada terminal) como layout "default", que es el que
Terminator abre al arrancar. Si en una terminal esta corriendo un comando
permitido (ver _detect), tambien se guarda para relanzarlo al restaurar.

Los programas que se relanzan son configurables desde el menu del clic derecho
(Autosave) o en el config de Terminator:

    [plugins]
      [[AutosaveSession]]
        relaunch = htop, watch, lazydocker
        relaunch_following = tail, journalctl
"""
import glob
import json
import os
import re
import shlex

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.terminator import Terminator
from terminatorlib.util import dbg, err

AVAILABLE = ['AutosaveSession']

INTERVAL = 15
LAYOUT = 'default'
NVM_NODE = re.compile(r'/\.nvm/versions/node/(v[^/]+)/')

# Valores por defecto de la config. relaunch: se relanzan con los mismos
# argumentos. relaunch_following: solo si estaban siguiendo un log (-f).
DEFAULTS = {
    'relaunch': ['htop', 'btop', 'top', 'glances', 'nvtop', 'watch', 'nload', 'bmon'],
    'relaunch_following': ['tail', 'journalctl'],
}
FOLLOW_FLAGS = {'-f', '-F', '--follow'}
BUILTIN = {'claude', 'npm'}


def _setting(key):
    value = Config().plugin_get(AVAILABLE[0], key, DEFAULTS[key])
    if isinstance(value, str):
        value = [value] if value else []
    return [v for v in value if v]


def _set_setting(key, value):
    config = Config()
    config.plugin_set(AVAILABLE[0], key, value)
    config.save()


def _children(pid):
    try:
        with open('/proc/%d/task/%d/children' % (pid, pid)) as f:
            return [int(p) for p in f.read().split()]
    except OSError:
        return []


def _args(pid):
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            return f.read().replace(b'\0', b' ').decode(errors='replace').split()
    except OSError:
        return []


def _node_version(pid):
    try:
        match = NVM_NODE.search(os.readlink('/proc/%d/exe' % pid))
    except OSError:
        return None
    return match.group(1) if match else None


def _claude_command(pid):
    """claude --resume <sessionId> de la conversacion abierta en ese proceso."""
    home = os.path.expanduser('~/.claude')
    try:
        with open(os.path.join(home, 'sessions', '%d.json' % pid)) as f:
            session = json.load(f).get('sessionId')
    except (OSError, ValueError):
        session = None
    # Una sesion sin mensajes todavia no tiene transcript y no se puede retomar
    if session and glob.glob(os.path.join(home, 'projects', '*', session + '.jsonl')):
        return 'claude --resume %s' % session
    return 'claude'


def _foreground(term):
    """Nombre del programa en primer plano de la terminal, o None si esta el shell."""
    try:
        pid = os.tcgetpgrp(term.vte.get_pty().get_fd())
    except (AttributeError, OSError):
        return None
    if pid == term.pid:
        return None
    args = _args(pid)
    return os.path.basename(args[0]) if args else None


def _detect(term):
    """Comando permitido que corre dentro de la terminal, o None."""
    if not term.pid:
        return None
    relaunch = set(_setting('relaunch'))
    following = set(_setting('relaunch_following'))
    queue = _children(term.pid)
    while queue:
        pid = queue.pop(0)
        args = _args(pid)
        if args[:3] == ['npm', 'run', 'dev:ws']:
            version = _node_version(pid)
            nvm = 'nvm use %s >/dev/null; ' % version if version else ''
            return nvm + 'npm run dev:ws'
        if args and os.path.basename(args[0]) == 'claude':
            return _claude_command(pid)
        name = os.path.basename(args[0]) if args else ''
        if name in relaunch or (name in following and FOLLOW_FLAGS & set(args)):
            return shlex.join([name] + args[1:])
        queue.extend(_children(pid))
    return None


class AutosaveSession(plugin.Plugin):
    capabilities = ['session', 'terminal_menu']

    def __init__(self):
        self.last = None
        self.timer = GLib.timeout_add_seconds(INTERVAL, self.save)

    def unload(self):
        GLib.source_remove(self.timer)

    def callback(self, menuitems, menu, terminal):
        submenu = Gtk.Menu()
        name = _foreground(terminal)
        relaunch = _setting('relaunch')
        following = _setting('relaunch_following')

        if not name:
            current = Gtk.MenuItem.new_with_label('No hay ningún programa corriendo')
            current.set_sensitive(False)
        elif name in BUILTIN:
            current = Gtk.MenuItem.new_with_label('«%s» se relanza siempre' % name)
            current.set_sensitive(False)
        else:
            key = 'relaunch_following' if name in following else 'relaunch'
            label = 'Relanzar «%s» al restaurar' % name
            if key == 'relaunch_following':
                label += ' (solo con -f)'
            current = Gtk.CheckMenuItem.new_with_label(label)
            current.set_active(name in relaunch or name in following)
            current.connect('toggled', self.on_toggled, key, name)
        submenu.append(current)

        if relaunch or following:
            submenu.append(Gtk.SeparatorMenuItem())
            saved = Gtk.Menu()
            for key, names in (('relaunch', relaunch), ('relaunch_following', following)):
                for other in names:
                    item = Gtk.CheckMenuItem.new_with_label(
                        other + (' (solo con -f)' if key == 'relaunch_following' else ''))
                    item.set_active(True)
                    item.connect('toggled', self.on_toggled, key, other)
                    saved.append(item)
            saved_item = Gtk.MenuItem.new_with_label('Programas que se relanzan')
            saved_item.set_submenu(saved)
            submenu.append(saved_item)

        root = Gtk.MenuItem.new_with_label('Autosave')
        root.set_submenu(submenu)
        menuitems.append(root)

    def on_toggled(self, item, key, name):
        names = [n for n in _setting(key) if n != name]
        if item.get_active():
            names.append(name)
        _set_setting(key, names)
        self.last = None

    def save(self):
        try:
            terminator = Terminator()
            if not terminator.terminals:
                return True
            layout = terminator.describe_layout(save_cwd=True)
            by_uuid = {str(t.uuid): t for t in terminator.terminals}
            for entry in layout.values():
                if entry.get('type') != 'Terminal':
                    continue
                term = by_uuid.get(str(entry.get('uuid')))
                command = term and _detect(term)
                if command:
                    # bash -i para que cargue nvm/PATH del .bashrc; al cortar
                    # el comando queda un shell abierto en la terminal
                    entry['command'] = 'bash -ic %s; exec bash' % shlex.quote(command)
            if repr(layout) == self.last:
                return True
            config = Config()
            if not config.replace_layout(LAYOUT, layout):
                config.add_layout(LAYOUT, layout)
            config.save()
            self.last = repr(layout)
            dbg('AutosaveSession: layout guardado')
        except Exception as ex:
            err('AutosaveSession: %s' % ex)
        return True
