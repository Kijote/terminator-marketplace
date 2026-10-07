# terminator-marketplace

A plugin marketplace for [Terminator](https://github.com/gnome-terminator/terminator).
It adds a **Plugins** submenu to the right-click menu where you can enable and
disable the catalog's plugins on the fly, and update the catalog with
`git pull`. When the code of an active plugin changes (after an update or
because you edited it), it reloads automatically, without restarting Terminator.

> The plugins' menus and messages are currently in Spanish.

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/Kijote/terminator-marketplace/main/install.sh | bash
```

This clones the repo into `~/.local/share/terminator-marketplace` (or into
`$TERMINATOR_MARKETPLACE_DIR`) and enables the marketplace. If it was already
installed, it updates it. You can also clone the repo yourself and run
`./install.sh` from your clone.

Then quit Terminator completely and open it again: right-click → **Plugins**.

## Plugins

| Plugin | What it does |
|---|---|
| Session autosave (*Autosave de sesión*) | Saves windows, splits, working directories and running commands (`npm run dev:ws`, `claude --resume <session>`, monitors like `htop`/`watch`, and `tail -f`) every 15 seconds and restores them when Terminator opens. The programs to relaunch are configured in `~/.config/terminator/autosave.conf` (one rule per line, e.g. `htop` or `tail -f`) or from right-click → **Autosave**. |

## Blocking a plugin (security patch)

To disable a plugin on every installation, add `"blocked"` with the reason to
its entry in `catalog.json` and push it to `main`:

```json
{
  "id": "my_plugin",
  ...
  "blocked": "Vulnerability in version 1.2, fixed in the next release"
}
```

- The marketplace checks the catalog on GitHub at startup and every 30
  minutes, **only to read the blocks**: it never downloads or changes code
  unless you ask it to.
- A blocked plugin is disabled immediately, its symlink is deleted and it is
  removed from the config, so it won't load again. In the menu it shows up as
  **(bloqueado)** ("blocked"), with the reason in the tooltip, and it can't be
  enabled.
- To lift the block, remove the `"blocked"` field. Users who had it enabled can
  enable it again from the menu.
- If the block is published while Terminator is closed and the guard (see
  below) isn't installed, the plugin may still load at startup, because
  Terminator loads plugins in no fixed order. It is disabled as soon as the
  marketplace reads the block, within the first few seconds.

Removing a plugin from the catalog also disables it, but only once each
installation updates its catalog. For an urgent patch, use `"blocked"`.

### Security guard

To make sure a blocked plugin never runs, not even at startup, install the
guard:

```bash
~/.local/share/terminator-marketplace/install.sh --guard   # or from your clone
# with the one-liner:
curl -fsSL https://raw.githubusercontent.com/Kijote/terminator-marketplace/main/install.sh | bash -s -- --guard
```

It is installed with `sudo` (or `pkexec` when there is no terminal) into
Terminator's system plugin folder, which loads before yours. When Terminator
starts, the guard checks GitHub for blocks (with a 2-second timeout; without
network access it uses the last known blocks) and removes blocked plugins
before they load.

The **Plugins** menu shows whether the guard is active or outdated. When it
changes, update it with the same command. To remove it:
`install.sh --remove-guard`.

## Contributing

Want to add a plugin? See [CONTRIBUTING.md](CONTRIBUTING.md) for how to write
it, add it to the catalog, test it and open a pull request. Every PR goes
through an automatic check (`scripts/validate_catalog.py`).
