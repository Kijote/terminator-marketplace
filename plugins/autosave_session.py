"""Autosave de la sesion de Terminator (estilo tmux-continuum).

Cada INTERVAL segundos guarda la disposicion actual (ventanas, splits,
pestanas y directorio de cada terminal) como layout "default", que es el que
Terminator abre al arrancar. Si en una terminal esta corriendo un comando
permitido (ver _detect, MONITORS y FOLLOWERS), tambien se guarda para relanzarlo al restaurar.
"""
import glob
import json
import os
import re
import shlex

from gi.repository import GLib

import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.terminator import Terminator
from terminatorlib.util import dbg, err

AVAILABLE = ['AutosaveSession']

INTERVAL = 15
LAYOUT = 'default'
NVM_NODE = re.compile(r'/\.nvm/versions/node/(v[^/]+)/')

# Programas de solo lectura: se relanzan con los mismos argumentos
MONITORS = {'htop', 'btop', 'top', 'glances', 'nvtop', 'watch', 'nload', 'bmon'}
# Se relanzan solo si estaban siguiendo un log
FOLLOWERS = {'tail', 'journalctl'}
FOLLOW_FLAGS = {'-f', '-F', '--follow'}


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


def _detect(term):
    """Comando permitido que corre dentro de la terminal, o None."""
    if not term.pid:
        return None
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
        if name in MONITORS or (name in FOLLOWERS and FOLLOW_FLAGS & set(args)):
            return shlex.join([name] + args[1:])
        queue.extend(_children(pid))
    return None


class AutosaveSession(plugin.Plugin):
    capabilities = ['session']

    def __init__(self):
        self.last = None
        self.timer = GLib.timeout_add_seconds(INTERVAL, self.save)

    def unload(self):
        GLib.source_remove(self.timer)

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
