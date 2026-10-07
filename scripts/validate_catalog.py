#!/usr/bin/env python3
"""Valida catalog.json y los plugins del repo sin ejecutar su codigo.

Se corre en CI en cada PR y se puede correr a mano:
    python3 scripts/validate_catalog.py
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = {'id': str, 'name': str, 'description': str, 'file': str, 'classes': list}
# Opcionales: "blocked": "motivo" desactiva el plugin en todas las instalaciones
OPTIONAL = {'blocked': str}
# Terminator importa el plugin por el nombre del archivo: tiene que ser un
# nombre de modulo valido
FILE_NAME = re.compile(r'^plugins/[a-z][a-z0-9_]*\.py$')

# Terminator importa cada plugin por el nombre del archivo: si coincide con un
# modulo ya cargado (plugins que trae Terminator, la stdlib), se usa ese otro
BUILTIN_MODULES = {
    'activitywatch', 'command_notify', 'custom_commands', 'dir_open',
    'insert_term_name', 'logger', 'maven', 'run_cmd_on_match',
    'save_last_session_layout', 'terminalshot', 'testplugin', 'url_handlers',
    'marketplace',
}
BUILTIN_CLASSES = {
    'CustomCommandsMenu', 'CurrDirOpen', 'InsertTermName', 'Logger',
    'MavenPluginURLHandler', 'RunCmdOnMatchMenu', 'SaveLastSessionLayout',
    'TerminalShot', 'TestPlugin', 'LaunchpadBugURLHandler',
    'LaunchpadCodeURLHandler', 'APTURLHandler', 'ActivityWatch',
    'InactivityWatch', 'CommandNotify', 'Marketplace',
}

errors = []
warnings = []


def error(message):
    errors.append(message)


def warn(message):
    warnings.append(message)


def available(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'AVAILABLE' for t in node.targets):
            try:
                return list(ast.literal_eval(node.value))
            except ValueError:
                return None
    return None


def check_plugin(entry, where):
    path = os.path.join(ROOT, entry['file'])
    module = os.path.splitext(os.path.basename(entry['file']))[0]

    if not FILE_NAME.match(entry['file']):
        error('%s: "file" tiene que ser plugins/<nombre>.py, con el nombre en '
              'minúsculas, dígitos y _ y empezando con una letra' % where)
        return
    if not os.path.isfile(path):
        error('%s: no existe %s' % (where, entry['file']))
        return
    if module in BUILTIN_MODULES or module in sys.stdlib_module_names:
        error('%s: el archivo %s choca con un módulo existente (%s); renombralo'
              % (where, entry['file'], module))

    try:
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=entry['file'])
    except SyntaxError as ex:
        error('%s: error de sintaxis en %s:%s: %s' % (where, entry['file'], ex.lineno, ex.msg))
        return

    names = available(tree)
    if names is None:
        error('%s: %s no define AVAILABLE como una lista literal' % (where, entry['file']))
        return

    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    for name in entry['classes']:
        if name not in names:
            error('%s: la clase %s no está en AVAILABLE de %s' % (where, name, entry['file']))
        if name not in classes:
            error('%s: %s no define la clase %s' % (where, entry['file'], name))
            continue
        source = ast.unparse(classes[name])
        methods = {n.name for n in classes[name].body if isinstance(n, ast.FunctionDef)}
        if ('timeout_add' in source or '.connect(' in source) and 'unload' not in methods:
            warn('%s: %s usa timers o señales pero no implementa unload(); '
                 'desactivarlo sin reiniciar lo va a dejar corriendo' % (where, name))
    for name in names:
        if name not in entry['classes']:
            warn('%s: %s está en AVAILABLE pero no en "classes" del catálogo' % (where, name))


def main():
    try:
        with open(os.path.join(ROOT, 'catalog.json'), encoding='utf-8') as f:
            catalog = json.load(f)
    except (OSError, ValueError) as ex:
        print('ERROR: catalog.json inválido: %s' % ex)
        return 1
    if not isinstance(catalog, list):
        print('ERROR: catalog.json tiene que ser una lista')
        return 1

    seen = {'id': {}, 'file': {}, 'class': {}}
    for index, entry in enumerate(catalog):
        where = 'catalog.json[%d]' % index
        if not isinstance(entry, dict):
            error('%s: tiene que ser un objeto' % where)
            continue
        where = '%s (%s)' % (where, entry.get('id', '?'))
        missing = [k for k, kind in REQUIRED.items() if not isinstance(entry.get(k), kind)]
        if missing:
            error('%s: faltan o tienen tipo incorrecto: %s' % (where, ', '.join(missing)))
            continue
        wrong = [k for k, kind in OPTIONAL.items() if k in entry and not isinstance(entry[k], kind)]
        if wrong:
            error('%s: tipo incorrecto en: %s' % (where, ', '.join(wrong)))
        unknown = set(entry) - set(REQUIRED) - set(OPTIONAL)
        if unknown:
            warn('%s: campos desconocidos: %s' % (where, ', '.join(sorted(unknown))))
        if not entry['classes'] or not all(isinstance(c, str) for c in entry['classes']):
            error('%s: "classes" tiene que ser una lista no vacía de nombres' % where)
            continue

        basename = os.path.basename(entry['file'])
        for kind, values in (('id', [entry['id']]), ('file', [basename]), ('class', entry['classes'])):
            for value in values:
                if value in seen[kind]:
                    error('%s: %s "%s" repetido (también en %s)' % (where, kind, value, seen[kind][value]))
                seen[kind][value] = where
        for name in entry['classes']:
            if name in BUILTIN_CLASSES:
                error('%s: la clase %s choca con un plugin de Terminator; renombrala' % (where, name))

        check_plugin(entry, where)

    plugins_dir = os.path.join(ROOT, 'plugins')
    listed = {os.path.basename(e['file']) for e in catalog
              if isinstance(e, dict) and isinstance(e.get('file'), str)}
    for name in sorted(os.listdir(plugins_dir)):
        if name.endswith('.py') and name not in listed:
            error('plugins/%s no está en catalog.json' % name)

    for message in warnings:
        print('AVISO: ' + message)
    for message in errors:
        print('ERROR: ' + message)
    if errors:
        return 1
    print('OK: %d plugin(s) válidos' % len(catalog))
    return 0


if __name__ == '__main__':
    sys.exit(main())
