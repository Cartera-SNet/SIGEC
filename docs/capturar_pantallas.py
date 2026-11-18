"""
Captura las pantallas de SIGEC para el manual (docs/capturas/*.jpg).

Uso (con SIGEC ya ejecutándose y datos de ejemplo cargados):
    python docs/capturar_pantallas.py http://127.0.0.1:5000 Admin "Admin2026"
Requiere:  pip install playwright   y un Chrome/Chromium instalado.
Variable opcional CHROME_PATH para indicar el ejecutable de Chrome.
Después de capturar, ejecuta:  python docs/generar_manual.py
"""
import os
import re
import sys
import time

from PIL import Image
from playwright.sync_api import sync_playwright

AQUI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(AQUI, "capturas")
base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
user = sys.argv[2] if len(sys.argv) > 2 else "Admin"
clave = sys.argv[3] if len(sys.argv) > 3 else "Admin2026"
os.makedirs(OUT, exist_ok=True)


def guardar(pg, nombre):
    tmp = os.path.join(OUT, nombre + ".png")
    pg.screenshot(path=tmp)
    im = Image.open(tmp).convert("RGB")
    im = im.resize((1200, int(im.height * 1200 / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, nombre + ".jpg"), quality=84, optimize=True)
    os.remove(tmp)
    print("  capturada", nombre)


with sync_playwright() as p:
    opts = {"args": ["--no-sandbox"]}
    if os.environ.get("CHROME_PATH"):
        opts["executable_path"] = os.environ["CHROME_PATH"]
    elif os.path.exists("/usr/bin/google-chrome"):
        opts["executable_path"] = "/usr/bin/google-chrome"
    else:
        opts["channel"] = "chrome"
    b = p.chromium.launch(**opts)
    pg = b.new_page(viewport={"width": 1536, "height": 1024})

    def ir(ruta, espera=.6):
        pg.goto(base + ruta); pg.wait_for_load_state("networkidle"); time.sleep(espera)

    ir("/login"); guardar(pg, "01_login")
    pg.fill("#username", user); pg.fill("#password", clave); pg.click("button[type=submit]"); pg.wait_for_load_state("networkidle")
    ir("/"); guardar(pg, "02_dashboard")
    ir("/equipos"); guardar(pg, "03_inventario")
    ir("/equipos/nuevo"); guardar(pg, "04_nuevo_equipo")
    ir("/asignar"); guardar(pg, "05_asignar")
    html = pg.content()
    ir("/actas"); html = pg.content()
    ids = re.findall(r"/actas/(\d+)/imprimir", html)
    if ids:
        ir("/entrega/" + ids[0]); guardar(pg, "06_entrega")
        ir("/actas"); guardar(pg, "07_actas")
        ir("/actas/%s/imprimir" % ids[0]); guardar(pg, "08_acta_imprimir")
    ir("/mantenimiento"); guardar(pg, "09_mantenimiento")
    ir("/reportes?desde=2026-01-01&hasta=2026-11-30&equipo=119"); guardar(pg, "10_reportes")
    ir("/usuarios"); guardar(pg, "11_usuarios")
    ir("/configuracion"); guardar(pg, "12_configuracion")
    ir("/empleados"); guardar(pg, "13_empleados")
    ir("/equipos"); m = re.search(r"/equipo/(\d+)", pg.content())
    if m: ir("/equipo/" + m.group(1)); guardar(pg, "15_detalle_equipo")
    ir("/actas?estado=pendiente"); m = re.search(r"/actas/(\d+)/firmar", pg.content())
    if m: ir("/actas/" + m.group(1) + "/firmar"); guardar(pg, "16_firmar_acta")
    ir("/empleados"); m = re.search(r"/empleados/(\d+)\"", pg.content())
    if m: ir("/empleados/" + m.group(1)); guardar(pg, "17_detalle_empleado")
    ir("/configuracion?tab=catalogos"); guardar(pg, "19_catalogos")
    if len(sys.argv) > 5:   # usuario con rol Empleado (opcional): python capturar_pantallas.py URL Admin CLAVE usuario_empleado clave_empleado
        pg2 = b.new_page(viewport={"width": 1536, "height": 1024})
        pg2.goto(base + "/login"); pg2.fill("#username", sys.argv[4]); pg2.fill("#password", sys.argv[5])
        pg2.click("button[type=submit]"); pg2.wait_for_load_state("networkidle"); time.sleep(.8)
        guardar(pg2, "18_mis_equipos")
    ir("/")
    pg.click("#ia-fab"); pg.click("#ia-sug button:nth-child(1)"); pg.wait_for_selector(".ia-m.bot small", timeout=20000); time.sleep(.5)
    guardar(pg, "14_asistente")
    b.close()
