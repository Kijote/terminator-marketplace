"""Guardian de seguridad del marketplace de plugins de Terminator.

Se instala (con sudo) en la carpeta de plugins del sistema de Terminator, que
se carga antes que ~/.config/terminator/plugins/. Al importarse, antes de que
cargue cualquier plugin del usuario:

1. Consulta el catalogo del remote para leer los bloqueos, con un timeout
   corto (GUARD_TIMEOUT) para no demorar el arranque. Sin red usa los ultimos
   bloqueos conocidos.
2. Saca los plugins bloqueados: borra su symlink y los quita de
   enabled_plugins, asi Terminator no los carga.

No expone clases (AVAILABLE vacio): todo pasa al importarse. Es un archivo
autocontenido porque se copia fuera del repo. Instalar o actualizar:
    install.sh --guard
"""
import json
import os
import subprocess

from terminatorlib.config import Config
from terminatorlib.util import dbg, err, get_config_dir

AVAILABLE = []

GUARD_TIMEOUT = 2
CONFIG_DIR = get_config_dir()
PLUGINS_DIR = os.path.join(CONFIG_DIR, 'plugins')
INSTALLED_FILE = os.path.join(CONFIG_DIR, 'marketplace-installed.json')
REMOTE_BLOCKED_FILE = os.path.join(CONFIG_DIR, 'marketplace-blocked.json')


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _git(repo, args, timeout):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
               GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=%d' % timeout)
    return subprocess.run(['git', '-C', repo] + args, env=env, timeout=timeout,
                          capture_output=True, text=True, check=True).stdout


def _fetch_remote_blocked(repo):
    """Actualiza los bloqueos del remote; si no hay red se queda con los guardados."""
    try:
        _git(repo, ['fetch', '-q'], GUARD_TIMEOUT)
        remote = json.loads(_git(repo, ['show', '@{upstream}:catalog.json'], GUARD_TIMEOUT))
    except (OSError, subprocess.SubprocessError, ValueError) as ex:
        dbg('marketplace_guard: sin catalogo remoto, uso los bloqueos guardados: %s' % ex)
        return
    if isinstance(remote, list):
        blocked = {e['id']: e['blocked'] for e in remote
                   if isinstance(e, dict) and e.get('id') and e.get('blocked')}
        if blocked != _read_json(REMOTE_BLOCKED_FILE, {}):
            _write_json(REMOTE_BLOCKED_FILE, blocked)


def _guard():
    marketplace = os.path.join(PLUGINS_DIR, 'marketplace.py')
    if not os.path.islink(marketplace):
        return
    repo = os.path.dirname(os.path.realpath(marketplace))
    _fetch_remote_blocked(repo)

    catalog = _read_json(os.path.join(repo, 'catalog.json'), [])
    catalog = [e for e in catalog if isinstance(e, dict) and e.get('id')] \
        if isinstance(catalog, list) else []
    blocked = dict(_read_json(REMOTE_BLOCKED_FILE, {}))
    blocked.update({e['id']: e['blocked'] for e in catalog if e.get('blocked')})
    if not blocked:
        return

    # Instalados segun el marketplace, mas los symlinks de entradas del catalogo
    # (por si el registro de instalados no existe todavia)
    installed = _read_json(INSTALLED_FILE, {})
    for entry in catalog:
        link = os.path.join(PLUGINS_DIR, os.path.basename(entry.get('file', '')))
        if entry['id'] not in installed and os.path.islink(link):
            installed[entry['id']] = {k: entry.get(k) for k in ('name', 'file', 'classes')}

    config = Config()
    removed = []
    for plugin_id, record in list(installed.items()):
        if plugin_id not in blocked:
            continue
        classes = record.get('classes') or []
        config['enabled_plugins'] = [c for c in config['enabled_plugins'] if c not in classes]
        link = os.path.join(PLUGINS_DIR, os.path.basename(record.get('file') or ''))
        if os.path.islink(link):
            os.remove(link)
        del installed[plugin_id]
        removed.append('%s (%s)' % (record.get('name') or plugin_id, blocked[plugin_id]))

    if removed:
        config.save()
        _write_json(INSTALLED_FILE, installed)
        message = 'Plugins bloqueados, no se cargaron: ' + ', '.join(removed)
        err('marketplace_guard: ' + message)
        try:
            subprocess.Popen(['notify-send', 'Terminator', message])
        except OSError:
            pass


try:
    _guard()
except Exception as ex:
    # El guardian nunca puede impedir que Terminator arranque
    err('marketplace_guard: %s' % ex)
