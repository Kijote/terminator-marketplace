#!/usr/bin/env bash
# Instala el marketplace en Terminator. Correr con Terminator cerrado, o
# reiniciarlo despues: la instancia abierta no ve el cambio y podria pisarlo.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
PLUGINS="${XDG_CONFIG_HOME:-$HOME/.config}/terminator/plugins"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/terminator/config"

mkdir -p "$PLUGINS"
ln -sfn "$REPO/marketplace.py" "$PLUGINS/marketplace.py"

python3 - "$CONFIG" <<'EOF'
import os, sys
from configobj import ConfigObj

path = sys.argv[1]
config = ConfigObj(path if os.path.exists(path) else None, encoding='utf-8')
config.filename = path
config.indent_type = '  '
section = config.setdefault('global_config', {})
enabled = section.get('enabled_plugins', ['LaunchpadBugURLHandler', 'LaunchpadCodeURLHandler', 'APTURLHandler'])
if isinstance(enabled, str):
    enabled = [enabled]
if 'Marketplace' not in enabled:
    section['enabled_plugins'] = enabled + ['Marketplace']
config.write()
EOF

echo "Marketplace instalado. Reiniciá Terminator: clic derecho → Plugins."
