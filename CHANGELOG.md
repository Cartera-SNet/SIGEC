# Historial de cambios de SIGEC

## 1.0 — 18/11/2026
Primera versión completa del sistema, alineada con la Ficha de Documentación entregada al cliente.
- Diseño visual nuevo (panel inicial y paneles internos), logo, inicio de sesión con usuario Admin, roles y permisos, usuarios con foto de perfil propia.
- Equipos, empleados, asignaciones, mantenimientos, cambio de estado con motivo, firma de actas con evidencia, catálogos, reportes (PDF y Excel), configuración y respaldo automático diario.
- Asistente de IA (local por defecto; opcionalmente con Claude y herramientas de solo lectura por rol, con interruptor del Administrador y tope de uso), manual de ayuda en PDF y diseño responsive para celulares y tabletas.
- Rol **Mantenimiento** (solo ve y completa los mantenimientos que se le asignan) y responsable en cada mantenimiento.
- Catálogos de **marca** y **área** con listas desplegables en los formularios de equipos y empleados.
- Reportes con filtro por **usuario** o **equipo**, tabla y hoja de **movimientos**, y responsable en mantenimientos.
- Diseño más compacto en escritorio.
- Contraseña olvidada: el Administrador genera una clave temporal aleatoria (se muestra una vez) y la persona debe cambiarla al ingresar; recuperación del Admin con la variable `ADMIN_RESET_PASSWORD`.
- Aviso de contraseña inicial del Admin, cabeceras de seguridad y corrección al eliminar usuarios con mantenimientos asignados.
- Listo para Railway: gunicorn, ruta de salud `/health`, volumen persistente (`DATA_DIR`) y guía `RAILWAY.md`.
