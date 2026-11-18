# Reglas del proyecto SIGEC

Este archivo lo lee Claude (Claude Code / Cowork) al abrir el proyecto. Las reglas son obligatorias.

## REGLA 1 — El manual siempre al día (pedida por el dueño del proyecto)

**Cada vez que se haga CUALQUIER cambio en SIGEC** (código, pantallas, reglas de negocio, roles, configuración,
base de datos, instalación), en esa misma tarea y antes de entregar se debe:

1. Actualizar `docs/manual.md` (es la fuente del manual **y** del conocimiento del asistente de IA).
   - Mantener la estructura `## Capítulo` / `### Sección` (el asistente busca por esos títulos).
   - Si cambió algo visual, recapturar las pantallas: `python docs/capturar_pantallas.py <url> <usuario> <clave>`
     (requiere la app corriendo con datos de ejemplo, `pip install playwright` y Chrome).
2. Regenerar el PDF: `python docs/generar_manual.py` → `docs/Manual_SIGEC.pdf`.
3. Subir la versión (`VERSION` en `app.py`, la línea «Versión X.Y» del encabezado y la sección
   «Historial de versiones» de `docs/manual.md`) y agregar la entrada en `CHANGELOG.md`.
4. **Volver a empaquetar el .zip del proyecto incluyendo el manual actualizado** (sin `.env` si se va a compartir).
5. Decirle al usuario, en la respuesta final, qué cambió en el manual.

Un cambio sin manual actualizado se considera inconcluso.

## REGLA 1-B — La ficha del cliente siempre en sincronía (pedida por el dueño del proyecto)

Todo el proyecto nace de `docs/Ficha_Documentacion_SIGEC.docx` (Ficha de Documentación y Levantamiento entregada al
cliente: el profesor de la universidad). **Si un cambio en el sistema no coincide con lo que dice la ficha, hay que
ajustar la ficha en la misma tarea** (y, si la ficha pide algo que el sistema no hace, se implementa o se registra
como decisión). Al hacerlo:

1. Editar el `.docx` en su propio formato (no rehacerlo): requerimientos (RF/RNF), reglas (RN), controles, excepciones,
   criterios de aceptación (CA), tecnologías, riesgos, y las secciones afectadas.
2. Agregar la decisión en la sección 21 y una fila en la sección 22 (control de revisión) con versión y fecha.
3. Actualizar el encabezado (fecha y versión) y la sección 1; la versión de la ficha avanza junto con la del sistema.
4. Actualizar `docs/Trazabilidad_Ficha_vs_Sistema.md`.
5. Incluir la ficha actualizada en el .zip y decirle al usuario qué cambió en ella.

## REGLA 2 — Estilo visual

El diseño de referencia es: panel inicial (`body.layout-home`, imagen 1) y demás paneles (`body.layout-inner`, imagen 2).
No cambiar colores/medidas de `static/style.css` sin necesidad; conservar la paleta azul marino (#0a1c44 → #12254b),
azul de acción (#1a6cff) y tipografía Roboto (incluida localmente en `static/vendor/fonts`).

## REGLA 3 — Seguridad

- Las claves (`DATABASE_URL`, `SECRET_KEY`) viven solo en `.env`. Nunca en el código ni en el manual.
- Toda ruta POST lleva token CSRF; toda ruta está protegida por sesión y rol (`@requiere(...)`).
- El usuario `Admin` (contraseña inicial definida en `db.ADMIN_PASS` y escrita solo en la ficha Word, no en el manual) es el administrador principal: no se elimina ni se desactiva.

## Mapa rápido

| Archivo | Para qué sirve |
|---|---|
| `app.py` | Rutas, permisos, lógica de negocio |
| `db.py` | Conexión a Neon, creación idempotente de tablas, usuario Admin |
| `asistente.py` | Asistente: Claude (opcional, `ia.py`, herramientas de solo lectura por rol) → Ollama → motor interno sobre `docs/manual.md`. La clave `ANTHROPIC_API_KEY` solo en variables de entorno |
| `informes.py` | Exportación a Excel y PDF |
| `templates/`, `static/` | Interfaz |
| `docs/` | Manual (md + PDF), capturas y scripts para regenerarlo |
