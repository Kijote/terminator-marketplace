#!/usr/bin/env bash
# Instala el marketplace en Terminator. Se puede correr desde un clon del repo
# o directo con:
#   curl -fsSL https://raw.githubusercontent.com/Kijote/terminator-marketplace/main/install.sh | bash
# En ese caso clona el repo en $TERMINATOR_MARKETPLACE_DIR (por defecto
# ~/.local/share/terminator-marketplace), o lo actualiza si ya esta.
#
# Opciones:
#   --guard          instala o actualiza el guardian de seguridad (pide sudo)
#   --remove-guard   lo desinstala (pide sudo)
# Con el one-liner: curl ... | bash -s -- --guard
set -euo pipefail

GUARD=""
for arg in "$@"; do
    case "$arg" in
        --guard) GUARD=install ;;
        --remove-guard) GUARD=remove ;;
        *) echo "Opción desconocida: $arg" >&2; exit 1 ;;
    esac
done

REPO_URL="https://github.com/Kijote/terminator-marketplace.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/marketplace.py" ]; then
    REPO="$SCRIPT_DIR"
else
    command -v git >/dev/null || { echo "Falta git: sudo apt install git" >&2; exit 1; }
    REPO="${TERMINATOR_MARKETPLACE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/terminator-marketplace}"
    if [ -d "$REPO/.git" ]; then
        git -C "$REPO" pull --ff-only -q
    else
        git clone -q "$REPO_URL" "$REPO"
    fi
fi

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

if [ -n "$GUARD" ]; then
    SYSTEM_PLUGINS="$(python3 -c 'import os, terminatorlib; print(os.path.join(os.path.dirname(terminatorlib.__file__), "plugins"))')"
    if [ "$GUARD" = install ]; then
        echo "Instalando el guardián de seguridad en $SYSTEM_PLUGINS (pide sudo)..."
        sudo install -m 644 "$REPO/guard/marketplace_guard.py" "$SYSTEM_PLUGINS/marketplace_guard.py"
        echo "Guardián instalado: los plugins bloqueados se sacan antes de que Terminator los cargue."
    else
        echo "Desinstalando el guardián de seguridad (pide sudo)..."
        sudo rm -f "$SYSTEM_PLUGINS/marketplace_guard.py"
        echo "Guardián desinstalado."
    fi
fi

echo "Marketplace instalado en $REPO."
if pgrep -f /usr/bin/terminator >/dev/null; then
    echo "Cerrá Terminator del todo y abrilo de nuevo: la instancia abierta no ve el cambio y podría pisarlo."
fi
echo "Después: clic derecho → Plugins."
