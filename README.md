# SIGEC — Sistema de Inventario y Gestión de Equipos de Cómputo (v1.0)

Flask + PostgreSQL (Neon). Incluye inicio de sesión con roles, inventario, empleados, asignaciones con acta,
devoluciones, mantenimientos, reportes (PDF/Excel), configuración y un asistente de ayuda con IA local.

## Ejecutar
1. Instala Python 3.10+ (con «Add Python to PATH»).
2. Revisa que `.env` tenga tu `DATABASE_URL` de Neon (ver `.env.example`).
3. Doble clic en `ejecutar_sigec.bat` (o `pip install -r requirements.txt` y `python app.py`).
4. Abre http://localhost:5000 — usuario **Admin**, contraseña inicial indicada en la Ficha de Documentación (cámbiala al entrar).

Las tablas se crean/actualizan solas al arrancar (no hay que correr `sigec_postgresql.sql`; se conserva como referencia).

## Documentación
- **Manual de ayuda y uso:** `docs/Manual_SIGEC.pdf` (fuente: `docs/manual.md`). También se abre desde el menú de usuario → «Manual de uso».
- **Historial de cambios:** `CHANGELOG.md`.
- **Reglas del proyecto** (el manual debe actualizarse con cada cambio): `CLAUDE.md`.
- Diagrama de flujo original: `diagrama_flujo_sigec.png`.

## Asistente de IA
Funciona sin instalar nada (motor interno sobre el manual, local). Para respuestas con un modelo de lenguaje local:
instala [Ollama](https://ollama.com) y ejecuta `ollama pull llama3.2:3b`. SIGEC lo detecta solo.
Opcional: define la variable de entorno `ANTHROPIC_API_KEY` (nunca en el código) para que el asistente use Claude,
entienda cualquier formulación y consulte el inventario con herramientas de solo lectura según el rol. El Administrador
puede apagarlo en Configuración → General; si falla, el asistente vuelve al motor local.

## Estructura
`app.py` rutas y reglas · `db.py` base de datos · `asistente.py` + `ia.py` asistente de IA · `informes.py` PDF/Excel · `templates/` y `static/` interfaz · `docs/` manual.


## Documentación
- `docs/Manual_SIGEC.pdf`: manual de ayuda y uso.
- `docs/Ficha_Documentacion_SIGEC.docx`: ficha entregada al cliente (se mantiene sincronizada con el sistema).
- `docs/Trazabilidad_Ficha_vs_Sistema.md`: qué requisito de la ficha cubre cada parte del sistema.

- `RAILWAY.md`: cómo publicar SIGEC en Railway (variables, volumen y dominio).
