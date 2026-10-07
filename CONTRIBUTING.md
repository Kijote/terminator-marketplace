# Contributing

Thanks for wanting to add a plugin! The flow is the usual one on GitHub:
fork, branch, changes and pull request.

## 1. Set up your environment

```bash
git clone https://github.com/<your-user>/terminator-marketplace.git
cd terminator-marketplace
./install.sh
```

When `install.sh` runs from a clone, it uses that clone, so you'll be testing
your own version. Quit Terminator completely and open it again so it loads the
marketplace.

## 2. Write the plugin

A plugin is a Python file in `plugins/` that Terminator loads at startup. The
minimum:

```python
import terminatorlib.plugin as plugin

AVAILABLE = ['MyPlugin']


class MyPlugin(plugin.MenuItem):
    capabilities = ['terminal_menu']

    def callback(self, menuitems, menu, terminal):
        ...
```

- **`AVAILABLE`** must be a literal list with the names of the classes the
  file exposes.
- **Classes** inherit from `terminatorlib.plugin.Plugin` or one of its
  subclasses (`MenuItem` to add items to the right-click menu, `URLHandler` to
  recognize URLs). The plugins bundled with Terminator, in
  `/usr/lib/python3/dist-packages/terminatorlib/plugins/`, are good examples.
- **`unload()`**: if your plugin starts timers (`GLib.timeout_add…`) or
  connects signals, implement `unload()` and clean them up there. The
  marketplace enables, disables and reloads plugins without restarting
  Terminator, and without `unload()` the old version keeps running alongside
  the new one.
- **Unique names**: the file name can't match a Python module or a plugin
  bundled with Terminator (`logger.py`, `json.py`…), and class names can't
  repeat another plugin's. The validator checks this.
- **Configuration**: if your plugin is configurable, store its settings in
  its own file in `~/.config/terminator/`, not in Terminator's `config`. A
  running Terminator instance overwrites that file when it saves.
- **No surprises**: no network requests, destructive commands or reading the
  terminals' contents unless the plugin's description says so.

## 3. Add it to the catalog

Add an entry to `catalog.json`:

```json
{
  "id": "my_plugin",
  "name": "My plugin",
  "description": "What it does, in one line (shown as a tooltip in the menu).",
  "file": "plugins/my_plugin.py",
  "classes": ["MyPlugin"]
}
```

And a row to the **Plugins** table in the README.

## 4. Test it

```bash
python3 scripts/validate_catalog.py
```

Then restart Terminator and, from right-click → **Plugins**:

1. Enable it and check that it works.
2. Disable it and check that it stops doing what it did.
3. Enable it again, without restarting.

While the plugin is active, every time you save the file the marketplace
reloads it and lets you know with a notification. If the new code has an
error, the notification says so and the previous version keeps running. If
something fails, run Terminator with `terminator -d` from another terminal to
see the errors.

## 5. Open the pull request

The PR template asks what the plugin does and what it touches (files,
commands, network). An automatic catalog check runs on every PR; if it fails,
look at the check's log.

Plugins run with the user's permissions inside Terminator, so every PR is
reviewed carefully before merging. Once merged, it shows up for everyone after
**Actualizar catálogo** ("Update catalog").
