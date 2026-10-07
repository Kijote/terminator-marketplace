## What it adds or changes

<!-- What the plugin does and what it's for. If it changes an existing plugin, what changes. -->

## What it touches

<!-- Check what applies. It helps review the PR faster. -->

- [ ] Reads or writes files (which ones?)
- [ ] Runs commands or processes (which ones?)
- [ ] Makes network requests (to where?)
- [ ] Reads the terminals' contents
- [ ] None of the above

## Checklist

- [ ] The plugin is in `plugins/` and has its entry in `catalog.json`
- [ ] `python3 scripts/validate_catalog.py` passes without errors
- [ ] I installed it with `./install.sh`, restarted Terminator and enabled it from right-click → **Plugins**
- [ ] I disabled and re-enabled it from the menu without restarting, and it works (or I implemented `unload()` if it uses timers or signals)
- [ ] If it adds configuration, it's documented in the README
