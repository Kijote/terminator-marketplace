"""Marketplace de plugins para Terminator.

Agrega al menu del clic derecho un submenu "Plugins" con los plugins de
catalog.json: cada uno se activa/desactiva en caliente. Instalar un plugin es
crear un symlink en ~/.config/terminator/plugins/ hacia este repo.

El marketplace vigila los archivos del repo: cuando cambia el codigo de un
plugin activo (por "Actualizar catalogo", que hace git pull, o porque se
edito el archivo) lo recarga en caliente, sin reiniciar Terminator. Si el
codigo nuevo falla al cargar, sigue corriendo la version anterior.

Bloqueos: un plugin con "blocked": "motivo" en el catalogo se desactiva y no
se puede activar. Al arrancar y cada CHECK_INTERVAL se consulta el catalogo
del remote solo para leer los bloqueos (sin bajar codigo), asi un bloqueo
publicado llega a todos sin que tengan que actualizar. Los plugins instalados
que desaparecen del catalogo local tambien se desactivan. Desactivar un plugin
borra su symlink y lo saca de enabled_plugins, asi no se vuelve a cargar.
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
PLUGINS_DIR = os.path.join(get_config_dir(), 'plugins')
# Plugins instalados desde el marketplace: {id: {name, file, classes}}
INSTALLED_FILE = os.path.join(get_config_dir(), 'marketplace-installed.json')
# Bloqueos leidos del catalogo del remote: {id: motivo}
REMOTE_BLOCKED_FILE = os.path.join(get_config_dir(), 'marketplace-blocked.json')
SELF = {'id': 'marketplace', 'name': 'Marketplace', 'file': 'marketplace.py',
        'classes': ['Marketplace']}
# Los editores y git guardan en rafagas de eventos: se espera a que se calmen
RELOAD_DELAY_MS = 500
CHECK_INTERVAL = 30 * 60
GUARD_SOURCE = os.path.join(REPO, 'guard', 'marketplace_guard.py')
GUARD_INSTALLED = os.path.join(os.path.dirname(plugin.__file__), 'plugins',
                               'marketplace_guard.py')


def _catalog():
    """Entradas del catalogo, o None si no se puede leer (ej. a medio editar)."""
    try:
        with open(os.path.join(REPO, 'catalog.json')) as f:
            catalog = json.load(f)
    except (OSError, ValueError) as ex:
        err('Marketplace: no se pudo leer catalog.json: %s' % ex)
        return None
    if not isinstance(catalog, list):
        return None
    return [e for e in catalog if isinstance(e, dict) and 'id' in e]


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _blocked(catalog):
    blocked = dict(_read_json(REMOTE_BLOCKED_FILE))
    blocked.update({e['id']: e['blocked'] for e in catalog or [] if e.get('blocked')})
    return blocked


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
    for entry in (_catalog() or []) + [SELF]:
        if os.path.realpath(os.path.join(REPO, entry['file'])) == real:
            return entry
    return None


def _remove(record):
    """Desactiva las clases del plugin y borra su symlink."""
    registry = plugin.PluginRegistry()
    for name in record['classes']:
        if registry.is_enabled(name):
            try:
                registry.disable(name)
            except Exception as ex:
                # Un unload() roto no puede impedir sacar el plugin
                err('Marketplace: unload de %s falló: %s' % (name, ex))
                registry.instances.pop(name, None)
    _set_enabled(record['classes'], False)
    link = _link(record)
    if os.path.islink(link):
        os.remove(link)


def _guard_status():
    """(texto para el menu, tooltip) del guardian de seguridad."""
    command = os.path.join(REPO, 'install.sh') + ' --guard'
    try:
        with open(GUARD_INSTALLED, 'rb') as f:
            installed = f.read()
    except OSError:
        return ('Guardián de seguridad: no instalado',
                'Saca los plugins bloqueados antes de que Terminator los cargue. '
                'Para instalarlo: ' + command)
    try:
        with open(GUARD_SOURCE, 'rb') as f:
            current = f.read() == installed
    except OSError:
        current = True
    if current:
        return ('Guardián de seguridad: activo',
                'Saca los plugins bloqueados antes de que Terminator los cargue.')
    return ('Guardián de seguridad: desactualizado',
            'Hay una versión nueva. Para actualizarlo: ' + command)


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
        # Terminator carga los plugins sin orden fijo: si un bloqueado ya cargo
        # se desactiva, y si todavia no, sacarlo de enabled_plugins evita que cargue
        self.enforce(_catalog())
        self.timers = [GLib.idle_add(self.check_remote_once),
                       GLib.timeout_add_seconds(CHECK_INTERVAL, self.check_remote)]

    def unload(self):
        for monitor in self.monitors:
            monitor.cancel()
        context = GLib.MainContext.default()
        for source in list(self.pending.values()) + self.timers:
            # El chequeo inicial ya pudo haber corrido y terminado
            if context.find_source_by_id(source):
                GLib.source_remove(source)
        self.pending = {}
        self.timers = []

    def callback(self, menuitems, menu, terminal):
        registry = plugin.PluginRegistry()
        catalog = _catalog() or []
        blocked = _blocked(catalog)
        submenu = Gtk.Menu()

        for entry in catalog:
            if entry['id'] in blocked:
                item = Gtk.MenuItem.new_with_label('%s (bloqueado)' % entry['name'])
                item.set_tooltip_text(blocked[entry['id']])
                item.set_sensitive(False)
            else:
                item = Gtk.CheckMenuItem.new_with_label(entry['name'])
                item.set_tooltip_text(entry.get('description', ''))
                item.set_active(all(registry.is_enabled(c) for c in entry['classes']))
                item.connect('toggled', self.on_toggled, entry)
            submenu.append(item)

        submenu.append(Gtk.SeparatorMenuItem())
        label, tooltip = _guard_status()
        guard = Gtk.MenuItem.new_with_label(label)
        guard.set_tooltip_text(tooltip)
        guard.set_sensitive(False)
        submenu.append(guard)
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
        reason = _blocked(_catalog()).get(entry['id'])
        if reason:
            _notify('%s está bloqueado: %s' % (entry['name'], reason))
            return
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
        installed = _read_json(INSTALLED_FILE)
        installed[entry['id']] = {k: entry[k] for k in ('name', 'file', 'classes')}
        _write_json(INSTALLED_FILE, installed)
        _notify('%s activado' % entry['name'])

    def uninstall(self, entry):
        _remove(entry)
        installed = _read_json(INSTALLED_FILE)
        installed.pop(entry['id'], None)
        _write_json(INSTALLED_FILE, installed)
        _notify('%s desactivado' % entry['name'])

    def enforce(self, catalog):
        """Saca los plugins instalados que estan bloqueados o ya no estan en el catalogo."""
        if catalog is None:
            return
        installed = _read_json(INSTALLED_FILE)
        changed = False
        # Instalados antes de que existiera el registro de instalados
        for entry in catalog:
            if entry['id'] not in installed and os.path.islink(_link(entry)):
                installed[entry['id']] = {k: entry[k] for k in ('name', 'file', 'classes')}
                changed = True

        blocked = _blocked(catalog)
        ids = {e['id'] for e in catalog}
        for plugin_id, record in list(installed.items()):
            reason = blocked.get(plugin_id)
            if not reason and plugin_id not in ids:
                reason = 'se quitó del catálogo'
            if not reason:
                continue
            try:
                _remove(record)
            except Exception as ex:
                err('Marketplace: no se pudo sacar %s: %s' % (record['name'], ex))
            del installed[plugin_id]
            changed = True
            _notify('%s desactivado: %s' % (record['name'], reason))
        if changed:
            _write_json(INSTALLED_FILE, installed)

    def check_remote_once(self):
        self.check_remote()
        return False

    def check_remote(self):
        """Lee los bloqueos del catalogo del remote, sin tocar el codigo local."""
        def on_fetched(ok, _out):
            if ok:
                self.run_git(['show', '@{upstream}:catalog.json'], on_catalog)

        def on_catalog(ok, out):
            if not ok:
                return
            try:
                remote = json.loads(out)
            except ValueError:
                return
            if not isinstance(remote, list):
                return
            blocked = {e['id']: e['blocked'] for e in remote
                       if isinstance(e, dict) and e.get('id') and e.get('blocked')}
            if blocked != _read_json(REMOTE_BLOCKED_FILE):
                _write_json(REMOTE_BLOCKED_FILE, blocked)
            self.enforce(_catalog())

        self.run_git(['fetch', '-q'], on_fetched)
        return True

    def run_git(self, args, done):
        def on_done(proc, result):
            try:
                _ok, out, _err = proc.communicate_utf8_finish(result)
            except GLib.Error as ex:
                err('Marketplace: git %s falló: %s' % (args[0], ex))
                return
            done(proc.get_successful(), out or '')

        try:
            proc = Gio.Subprocess.new(
                ['git', '-C', REPO] + args,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as ex:
            err('Marketplace: no se pudo correr git: %s' % ex)
            return
        proc.communicate_utf8_async(None, None, on_done)

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
        if not path or not (path.endswith('.py') or os.path.basename(path) == 'catalog.json'):
            return
        if path in self.pending:
            GLib.source_remove(self.pending[path])
        self.pending[path] = GLib.timeout_add(RELOAD_DELAY_MS, self.on_reload_due, path)

    def on_reload_due(self, path):
        self.pending.pop(path, None)
        if os.path.basename(path) == 'catalog.json':
            self.enforce(_catalog())
            return False
        entry = _entry_for(path)
        if entry and entry['id'] not in _blocked(_catalog()):
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
