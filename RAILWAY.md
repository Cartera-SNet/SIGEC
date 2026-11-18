# Despliegue de SIGEC en Railway

El proyecto ya trae todo lo necesario: `railway.json`, `Procfile`, `wsgi.py` (gunicorn), `requirements.txt`,
ruta de salud `/health` y soporte de volumen persistente. **No incluye el archivo `.env`**: las claves van en las
variables de Railway.

## Pasos
1. Sube esta carpeta a un repositorio de GitHub (el `.gitignore` ya excluye `.env`, `fotos/`, `evidencias/`, `respaldos/`).
2. En Railway: **New Project → Deploy from GitHub repo** y elige el repositorio. Railway detecta Python y usa `railway.json`.
3. En el servicio, pestaña **Variables → Raw Editor**, pega el contenido de `RAILWAY_VARIABLES.env` (te lo entregué aparte).
4. **Volumen para fotos, evidencias y respaldos** (el disco del contenedor se borra en cada despliegue):
   servicio → **Settings → Volumes → New Volume**, ruta de montaje `/data`. La variable `DATA_DIR=/data` ya lo usa.
5. **Settings → Networking → Generate Domain** para obtener la URL pública (HTTPS).
6. Abre la URL e ingresa con `Admin` / `@dm1n2026`. **Cambia esa contraseña de inmediato** (Configuración → Seguridad).

## Variables
| Variable | Valor | Para qué |
|---|---|---|
| `DATABASE_URL` | cadena de Neon (con `?sslmode=require`) | Base de datos PostgreSQL. Las tablas se crean solas al arrancar |
| `SECRET_KEY` | clave larga aleatoria | Firma de sesiones. No la cambies después o se cerrarán todas las sesiones |
| `DATA_DIR` | `/data` | Carpeta persistente (volumen) para fotos, evidencias de actas y respaldos |
| `PORT` | la pone Railway | No la definas |
| `ANTHROPIC_API_KEY` | clave de la API de Anthropic | Activa el asistente con Claude (opcional). Sin ella, usa su motor interno basado en el manual |
| `ANTHROPIC_MODEL` | opcional (`claude-sonnet-5-5` por defecto) | Modelo de Claude que responde |
| `OLLAMA_URL`, `OLLAMA_MODEL` | opcionales | El modelo local no existe en Railway; sin Claude el asistente usa su motor interno |
| `COOKIE_SECURE`, `TRUST_PROXY` | automáticas | Se activan solas en Railway (cookies seguras y detrás del proxy HTTPS) |

## Notas
- Un solo proceso (`--workers 1`): el bloqueo por intentos fallidos y el respaldo diario viven en memoria del proceso.
- El respaldo automático diario se guarda en `/data/respaldos/` (últimos 14). Puedes descargar uno manual en Configuración → Respaldos.
- Salud: `https://TU-DOMINIO/health` (y `/health?db=1` prueba la conexión a Neon).
- Si Neon estaba en reposo, el primer arranque reintenta la conexión unos segundos; es normal.
- Rota la contraseña de Neon y la clave de Anthropic si el archivo de variables (o la clave) se compartió por un medio inseguro. Con Claude activo, las preguntas viajan a Anthropic; se apaga en Configuración → General.
