"""Autosave de la sesion de Terminator (estilo tmux-continuum).

Cada INTERVAL segundos guarda la disposicion de todas las ventanas abiertas
(splits, pestanas y directorio de cada terminal) como layout "autosave". Si en
una terminal esta corriendo un comando permitido (ver _detect), tambien se
guarda para relanzarlo al restaurar.

La sesion se restaura solo cuando Terminator arranca: la ventana inicial se
reemplaza por las ventanas guardadas. El layout "default" queda como una sola
terminal, asi las ventanas que se abren despues (que Terminator crea con ese
layout) arrancan vacias.

Los programas que se relanzan se configuran en ~/.config/terminator/autosave.conf
(se crea con DEFAULT_RULES si no existe), o desde el menu del clic derecho
(Autosave). Una regla por linea: el primer token es el programa y el resto son
argumentos que tiene que tener para relanzarse ("tail -f" solo relanza tail si
estaba con -f). Se relanza con los mismos argumentos con los que corria.
"""
import glob
import json
import os
import re
import shlex
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk

import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.terminator import Terminator
from terminatorlib.util import dbg, err, get_config_dir

AVAILABLE = ['AutosaveSession']

INTERVAL = 15
LAYOUT = 'autosave'
# Solo se restaura si el plugin carga en los primeros segundos del proceso:
# activarlo despues desde el marketplace no tiene que abrir la sesion
STARTUP_WINDOW = 30
EMPTY_LAYOUT = {
    'window0': {'type': 'Window', 'parent': ''},
    'child1': {'type': 'Terminal', 'parent': 'window0'},
}
NVM_NODE = re.compile(r'/\.nvm/versions/node/(v[^/]+)/')

RULES_FILE = os.path.join(get_config_dir(), 'autosave.conf')
DEFAULT_RULES = """\
# Programas que el autosave de Terminator relanza al restaurar la sesion.
# Una regla por linea: programa y, opcionalmente, argumentos que tiene que
# tener para relanzarse. Se relanza con los mismos argumentos que tenia.
# claude se relanza con --resume de la conversacion que tenia abierta.

claude
npm run dev:ws
htop
btop
top
glances
nvtop
watch
nload
bmon
tail -f
tail -F
journalctl -f
"""


def _read_rules():
    """Reglas como listas de tokens; crea el archivo por defecto si no existe."""
    if not os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'w') as f:
            f.write(DEFAULT_RULES)
    rules = []
    with open(RULES_FILE) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if line:
                rules.append(shlex.split(line))
    return rules


def _write_rules(add=None, remove=None):
    """Agrega una regla o saca las de un programa, conservando comentarios."""
    _read_rules()
    with open(RULES_FILE) as f:
        lines = f.readlines()
    if remove:
        lines = [l for l in lines
                 if l.split('#', 1)[0].split()[:1] != [remove]]
    if add:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.append(add + '\n')
    with open(RULES_FILE, 'w') as f:
        f.writelines(lines)


def _match(rules, args):
    name = os.path.basename(args[0]) if args else ''
    return any(rule[0] == name and set(rule[1:]) <= set(args[1:]) for rule in rules)


def _process_age():
    """Segundos desde que arranco este proceso de Terminator."""
    try:
        with open('/proc/self/stat') as f:
            # El campo 22 (starttime) va despues del nombre, que puede tener espacios
            start = int(f.read().rsplit(')', 1)[1].split()[19])
        with open('/proc/uptime') as f:
            uptime = float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return uptime - start / os.sysconf('SC_CLK_TCK')


def _migrate_layouts(config):
    """Pasa una sesion guardada en "default" (versiones anteriores) a LAYOUT
    y deja "default" como una sola terminal."""
    layouts = config.list_layouts()
    default = config.layout_get_config('default') if 'default' in layouts else {}
    terminals = [e for e in default.values() if e.get('type') == 'Terminal']
    if LAYOUT not in layouts and (len(terminals) > 1 or any(t.get('command') for t in terminals)):
        config.add_layout(LAYOUT, default)
    if len(terminals) != 1 or terminals[0].get('command') or terminals[0].get('directory'):
        if not config.replace_layout('default', EMPTY_LAYOUT):
            config.add_layout('default', EMPTY_LAYOUT)
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


def _detect(term, rules):
    """Comando permitido que corre dentro de la terminal, o None."""
    if not term.pid:
        return None
    queue = _children(term.pid)
    while queue:
        pid = queue.pop(0)
        args = _args(pid)
        if _match(rules, args):
            name = os.path.basename(args[0])
            if name == 'claude':
                return _claude_command(pid)
            version = _node_version(pid)
            nvm = 'nvm use %s >/dev/null; ' % version if version else ''
            return nvm + shlex.join([name] + args[1:])
        queue.extend(_children(pid))
    return None


class AutosaveSession(plugin.Plugin):
    capabilities = ['session', 'terminal_menu']

    def __init__(self):
        self.last = None
        # Ultimo "claude --resume" visto por terminal: al cerrar Terminator,
        # claude borra su archivo de sesion antes de terminar y un guardado en
        # ese momento perderia el resume
        self.resumes = {}
        self.timer = GLib.timeout_add_seconds(INTERVAL, self.save)
        try:
            _migrate_layouts(Config())
        except Exception as ex:
            err('AutosaveSession: %s' % ex)
        # La marca vive en Terminator (compartido por todo el proceso), asi un
        # reload del plugin no vuelve a restaurar
        terminator = Terminator()
        if not getattr(terminator, 'autosave_started', False):
            terminator.autosave_started = True
            age = _process_age()
            if age is not None and age < STARTUP_WINDOW:
                GLib.idle_add(self.restore)

    def unload(self):
        GLib.source_remove(self.timer)

    def restore(self):
        """Reemplaza la ventana vacia del arranque por la sesion guardada."""
        try:
            terminator = Terminator()
            options = terminator.config.options_get()
            if options and options.layout not in (None, 'default'):
                return False  # se pidio otro layout con -l
            if len(terminator.windows) != 1 or len(terminator.terminals) != 1:
                return False
            if LAYOUT not in terminator.config.list_layouts():
                return False
            initial = terminator.windows[0]
            terminator.create_layout(LAYOUT)
            terminator.layout_done()
            # Recien ahora se cierra la inicial: sin ventanas, Terminator se cerraria
            if len(terminator.windows) > 1:
                initial.on_destroy_event(initial)
        except Exception as ex:
            err('AutosaveSession: no se pudo restaurar la sesion: %s' % ex)
        return False

    def callback(self, menuitems, menu, terminal):
        submenu = Gtk.Menu()
        name = _foreground(terminal)
        rules = _read_rules()

        # El programa de esta terminal solo se ofrece si todavia no esta en la
        # lista; para sacarlo esta la lista de abajo
        if name and not any(rule[0] == name for rule in rules):
            add = Gtk.MenuItem.new_with_label('Agregar «%s» a la lista' % name)
            add.connect('activate', self.on_add, name)
            submenu.append(add)
            submenu.append(Gtk.SeparatorMenuItem())

        if rules:
            saved = Gtk.Menu()
            for rule in rules:
                item = Gtk.CheckMenuItem.new_with_label(shlex.join(rule))
                item.set_active(True)
                item.connect('toggled', self.on_toggled, rule[0])
                saved.append(item)
            saved_item = Gtk.MenuItem.new_with_label('Programas que se relanzan')
            saved_item.set_submenu(saved)
            submenu.append(saved_item)

        edit = Gtk.MenuItem.new_with_label('Editar lista…')
        edit.connect('activate', lambda _item: Gtk.show_uri_on_window(
            None, GLib.filename_to_uri(RULES_FILE), Gtk.get_current_event_time()))
        submenu.append(edit)

        root = Gtk.MenuItem.new_with_label('Autosave')
        root.set_submenu(submenu)
        menuitems.append(root)

    def on_add(self, _item, name):
        try:
            _write_rules(add=name)
        except OSError as ex:
            err('AutosaveSession: %s' % ex)
        self.last = None

    def on_toggled(self, item, name):
        try:
            if item.get_active():
                _write_rules(add=name)
            else:
                _write_rules(remove=name)
        except OSError as ex:
            err('AutosaveSession: %s' % ex)
        self.last = None

    def save(self):
        try:
            terminator = Terminator()
            if not terminator.terminals:
                return True
            rules = _read_rules()
            layout = terminator.describe_layout(save_cwd=True)
            # describe_layout guarda el objeto uuid de cada terminal: se busca
            # por identidad porque dos terminales pueden tener el mismo valor
            # (ej. un layout restaurado dos veces)
            by_uuid = {id(t.uuid): t for t in terminator.terminals}
            alive = set()
            for entry in layout.values():
                if entry.get('type') != 'Terminal':
                    continue
                term = by_uuid.get(id(entry.get('uuid')))
                command = term and _detect(term, rules)
                key = id(term)
                alive.add(key)
                if command == 'claude' and key in self.resumes:
                    command = self.resumes[key]
                elif command and command.startswith('claude --resume '):
                    self.resumes[key] = command
                else:
                    self.resumes.pop(key, None)
                if command:
                    # bash -i para que cargue nvm/PATH del .bashrc; al cortar
                    # el comando queda un shell abierto en la terminal
                    entry['command'] = 'bash -ic %s; exec bash' % shlex.quote(command)
            self.resumes = {k: v for k, v in self.resumes.items() if k in alive}
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
