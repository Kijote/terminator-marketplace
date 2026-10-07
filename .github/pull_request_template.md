## Qué agrega o cambia

<!-- Qué hace el plugin y para qué sirve. Si es un cambio a uno existente, qué cambia. -->

## Qué toca

<!-- Marcá lo que corresponda. Sirve para revisar el PR más rápido. -->

- [ ] Lee o escribe archivos (¿cuáles?)
- [ ] Ejecuta comandos o procesos (¿cuáles?)
- [ ] Hace pedidos de red (¿a dónde?)
- [ ] Lee el contenido de las terminales
- [ ] Nada de lo anterior

## Checklist

- [ ] El plugin está en `plugins/` y tiene su entrada en `catalog.json`
- [ ] `python3 scripts/validate_catalog.py` pasa sin errores
- [ ] Lo instalé con `./install.sh`, reinicié Terminator y lo activé desde clic derecho → **Plugins**
- [ ] Lo desactivé y volví a activar desde el menú sin reiniciar, y funciona (o implementé `unload()` si usa timers o señales)
- [ ] Si agrega configuración, está documentada en el README
