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
- Nueva contraseña inicial del Admin (se indica solo en la Ficha de Documentación).
- Catálogos de **ubicación** y **cargo** (listas desplegables en equipos y empleados, con los valores existentes importados) y filtro de ubicación en el inventario como lista.
- **Correo obligatorio** en empleados (con validación de formato); las fichas antiguas sin correo reciben uno provisional asociado a su nombre.
- Mayúsculas automáticas: nombres y apellidos («Julian Venegas») y catálogos con primera letra en mayúscula (siglas de 3 letras o menos y abreviaturas con puntos se respetan); los datos existentes se corrigen al arrancar.
- **Asignación de varios equipos en una sola entrega**, con una sola acta que los lista y una sola firma; cada equipo conserva su asignación y se puede devolver por separado.
- Filtros dinámicos: Equipos, Empleados y Reportes se actualizan solos al cambiar un filtro (sin pulsar el botón).
- Textos guía en el inicio de sesión («Digite su usuario» / «Digite su contraseña»).
- Contraseña olvidada: el Administrador genera una clave temporal aleatoria (se muestra una vez) y la persona debe cambiarla al ingresar; recuperación del Admin con la variable `ADMIN_RESET_PASSWORD`.
- Aviso de contraseña inicial del Admin, cabeceras de seguridad y corrección al eliminar usuarios con mantenimientos asignados.
- Listo para Railway: gunicorn, ruta de salud `/health`, volumen persistente (`DATA_DIR`) y guía `RAILWAY.md`.
