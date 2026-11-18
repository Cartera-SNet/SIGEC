"""Punto de entrada para producción (Railway): gunicorn wsgi:application"""
import app as sigec

try:
    sigec.arrancar()
except Exception as exc:  # la app arranca igual y muestra «Sin conexión a la base de datos» hasta que Neon responda
    print("[SIGEC] aviso al arrancar:", exc)

application = sigec.app
