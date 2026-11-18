# Trazabilidad: Ficha de Documentación ↔ Sistema (v1.0 del sistema / v1.0 de la ficha)

Referencia: `docs/Ficha_Documentacion_SIGEC.docx`. Cuando cambie el sistema o la ficha, actualizar este cuadro (Regla 1-B de `CLAUDE.md`).

| Ficha | Dónde está en el sistema | Estado |
|---|---|---|
| RF-01, RF-02 | Equipos: `/equipos/nuevo`, `/equipos/<id>/editar`, `/equipo/<id>` | Cumple |
| RF-03, RN-12, RN-18, CA-18 | Configuración → Catálogos (tipos, estados, marcas y áreas: `/configuracion/catalogos/*`); estados base protegidos; marca y área como listas desplegables | Cumple |
| RF-04, RF-09, CA-05, RN-10 | Empleados, ficha `/empleados/<id>` (solo asignaciones activas + histórico) | Cumple |
| RF-05, RF-06, RF-15, RN-01..03, RN-11, RN-16 | `/asignar` (acta automática, bloqueo de fila, fecha no futura) | Cumple |
| RF-07, RN-04, CA-04 | `/actas/<id>/firmar` (asignación activa, evidencia PNG/JPG/PDF ≤ 5 MB, historial) | Cumple |
| RF-08, RN-06, RN-15, CA-07 | `/equipos/<id>/estado` (motivo obligatorio, cierra asignación, crea/cierra mantenimiento) | Cumple |
| RF-10, RF-11, CA-06 | Detalle de equipo con historial | Cumple |
| RF-12 | Filtros: texto, estado, tipo, ubicación, rango de ingreso | Cumple |
| RF-13, RF-17, CA-09, CA-12, sec. 17 | Reportes + PDF/Excel: tasa de mantenimiento, actas pendientes, cerradas, sin movimiento (umbral configurable), asignados por área | Cumple |
| RF-23, CA-17 | Reportes filtrados por usuario (empleado) o equipo, con tabla y hoja «Movimientos» (`/reportes?equipo=&empleado=`) | Cumple |
| RF-14, RNF-02, CA-08 | Roles Administrador, Operador, Auditor, Jefe, Mantenimiento, Empleado (`PERMISOS`, `EMPLEADO_OK`, `MANT_OK`) | Cumple (Jefe sin filtro por área: decisión registrada) |
| RF-16, RN-13, CA-11 | `/mantenimiento` (con responsable por mantenimiento) | Cumple |
| RF-24, RN-17, CA-16 | Rol Mantenimiento: solo `/mantenimiento`; ve y completa únicamente los suyos | Cumple |
| RF-18 | `/usuarios` (rol + vínculo a empleado; el rol Empleado crea su ficha al darse de alta) | Cumple |
| RF-22 | Foto de perfil por usuario (`/cuenta/foto`, menú del usuario) | Cumple |
| RF-19, RNF-06 | Configuración, respaldo manual y automático diario (`respaldos/`) | Cumple |
| RF-18, RN-19, CA-19 | Restablecer clave con contraseña temporal y cambio obligatorio (`restablecer_clave`, `clave_obligatoria`); recuperación del Admin con `ADMIN_RESET_PASSWORD` | Cumple |
| RF-20, RNF-11, CA-15 | Asistente de IA (`asistente.py`: motor interno/Ollama locales + Claude opcional en `ia.py`, solo lectura por rol, interruptor del Admin) + manual PDF | Cumple |
| RF-21, CA-13 | `/mis-equipos`, «Mis actas» | Cumple |
| RN-05, CA-10 | Solo empleados activos en `/asignar` | Cumple |
| RN-07 | Destino al devolver: Disponible / En recepción / En Mantenimiento | Cumple |
| RN-08 | Serie y placa únicas | Cumple |
| RN-14 | Baja definitiva, solo Administrador, con motivo | Cumple |
| RNF-01, RNF-10, CA-14 | Sesión 60 min, bloqueo 5 intentos/5 min, hash, CSRF | Cumple |
| RNF-09 | Responsive verificado de 320 a 1180 px (sin desborde horizontal en las pantallas principales) | Cumple |
| RNF-04, RNF-05, RNF-07 | Rendimiento, disponibilidad y compatibilidad: no medidos automáticamente | Pendiente de verificación manual |
| RNF-08 | Historial con usuario y fecha en operaciones críticas | Cumple |
| Sec. 18 | Flask, PostgreSQL (Neon), Jinja2, Chart.js, ReportLab, openpyxl | Ficha ajustada |

Pendiente conocido: filtro por área para el rol Jefe (ficha sec. 6, ahora como decisión de alcance).
