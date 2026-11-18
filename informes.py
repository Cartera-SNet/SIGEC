"""SIGEC - Exportación de reportes a Excel (.xlsx) y PDF."""
import io
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AZUL = "0B2A66"


def _f(v, fmt="%d/%m/%Y"):
    return v.strftime(fmt) if v else "-"


def _hoja(wb, titulo, cabeceras, filas, first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = titulo
    ws.append(cabeceras)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center")
    for f in filas:
        ws.append(f)
    for i, _ in enumerate(cabeceras, 1):
        ancho = max(len(str(ws.cell(row=r, column=i).value or "")) for r in range(1, ws.max_row + 1))
        ws.column_dimensions[get_column_letter(i)].width = min(max(ancho + 3, 12), 50)
    ws.freeze_panes = "A2"
    return ws


def excel(rep):
    wb = Workbook()
    r = rep["resumen"]
    ws = _hoja(wb, "Resumen", ["Indicador", "Valor"], [
        ["Empresa", rep["empresa"]],
        ["Rango del reporte", f"{_f(rep['desde'])} - {_f(rep['hasta'])}"],
        ["Filtro", rep.get("filtro") or "Sin filtro (todos los equipos y usuarios)"],
        ["Generado", _f(rep["generado"], "%d/%m/%Y %H:%M")],
        ["Equipos totales (sin bajas)", r["total"]],
        ["Disponibles", r["disponibles"]],
        ["Asignados", r["asignados"]],
        ["En mantenimiento", r["mantenimiento"]],
        ["Actas pendientes de firma", r["actas_pendientes"]],
        ["Tasa de mantenimiento en el rango (%)", rep["tasa_mantenimiento"]],
        ["Asignaciones cerradas en el rango", rep["asignaciones_cerradas"]],
        [f"Equipos sin movimiento (> {rep['umbral']} días)", len(rep["sin_movimiento"])],
    ], first=True)
    ws.append([])
    ws.append(["Equipos por estado", "Cantidad"])
    for x in rep["por_estado"]:
        ws.append([x["nombre"], x["c"]])
    ws.append([])
    ws.append(["Equipos por tipo", "Cantidad"])
    for x in rep["por_tipo"]:
        ws.append([x["nombre"], x["c"]])
    _hoja(wb, "Asignaciones", ["Fecha", "Código", "Equipo", "Empleado", "Estado", "Devolución"],
          [[_f(a["fecha_asignacion"]), a["codigo"], f"{a['tipo'] or ''} {a['marca'] or ''} {a['modelo'] or ''}".strip(),
            a["empleado"], a["estado"], _f(a["fecha_devolucion"])] for a in rep["asignaciones"]])
    _hoja(wb, "Mantenimientos", ["Fecha", "Código", "Equipo", "Tipo", "Responsable", "Estado", "Descripción", "Finalizado"],
          [[_f(m["fecha"]), m["codigo"], f"{m['tipo_equipo'] or ''} {m['marca'] or ''} {m['modelo'] or ''}".strip(),
            m["tipo"], m.get("responsable") or "", m["estado"], m["descripcion"] or "", _f(m["fecha_fin"])]
           for m in rep["mantenimientos"]])
    _hoja(wb, "Movimientos", ["Fecha", "Código", "Equipo", "Evento", "Detalle", "Estado anterior", "Estado nuevo", "Registrado por"],
          [[_f(h["fecha"], "%d/%m/%Y %H:%M"), h["codigo"], f"{h['tipo'] or ''} {h['marca'] or ''} {h['modelo'] or ''}".strip(),
            h["tipo_evento"], h["detalle"] or "", h["estado_anterior"] or "", h["estado_nuevo"] or "", h["usuario"] or ""]
           for h in rep["movimientos"]])
    _hoja(wb, "Equipos registrados", ["Fecha ingreso", "Código", "Tipo", "Marca", "Modelo", "Serie", "Estado"],
          [[_f(n["fecha_ingreso"]), n["codigo"], n["tipo"], n["marca"], n["modelo"], n["numero_serie"], n["estado"]]
           for n in rep["nuevos"]])
    _hoja(wb, "Actas pendientes", ["N.º", "Generada", "Código", "Empleado", "Días pendiente"],
          [[f"{a['id']:04d}", _f(a["fecha_generacion"]), a["codigo"], a["empleado"], a["dias"]] for a in rep["actas_pendientes"]])
    _hoja(wb, "Sin movimiento", ["Código", "Equipo", "Estado", "Último movimiento", "Días"],
          [[m["codigo"], f"{m['tipo'] or ''} {m['marca'] or ''} {m['modelo'] or ''}".strip(), m["estado"],
            _f(m["ultimo"]), m["dias"]] for m in rep["sin_movimiento"]])
    _hoja(wb, "Asignados por área", ["Área", "Equipos asignados"], [[a["area"], a["c"]] for a in rep["por_area"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def pdf(rep):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Title"], textColor=colors.HexColor("#" + AZUL), fontSize=18, alignment=0)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=colors.HexColor("#" + AZUL), fontSize=12, spaceBefore=10)
    small = ParagraphStyle("s", parent=st["Normal"], fontSize=8, leading=10)

    def tabla(cab, filas, widths=None):
        data = [cab] + (filas or [["Sin registros"] + [""] * (len(cab) - 1)])
        data = [[Paragraph(str(c), small) for c in row] for row in data]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEFB")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D6F2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FE")]),
        ]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.4 * cm, title="Reporte SIGEC")
    el = []
    logo = os.path.join(BASE_DIR, "static", "favicon.png")
    cab = [[Image(logo, 1.8 * cm, 1.8 * cm) if os.path.exists(logo) else "",
            Paragraph("Reporte de Inventario de Equipos de Cómputo", h1)]]
    t = Table(cab, colWidths=[2.2 * cm, 15 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el += [t, Paragraph(f"{rep['empresa']} — Rango: {_f(rep['desde'])} a {_f(rep['hasta'])} — "
                        f"Generado: {_f(rep['generado'], '%d/%m/%Y %H:%M')}", small)]
    if rep.get("filtro"):
        el.append(Paragraph(f"<b>Filtro:</b> {rep['filtro']}", small))
    el.append(Spacer(1, 8))
    r = rep["resumen"]
    el += [Paragraph("Resumen actual", h2), tabla(["Total", "Disponibles", "Asignados", "En mantenimiento", "Actas pendientes"],
                                                  [[r["total"], r["disponibles"], r["asignados"], r["mantenimiento"], r["actas_pendientes"]]])]
    el += [Paragraph("Indicadores del rango", h2),
           tabla(["Tasa de mantenimiento", "Asignaciones cerradas", "Actas pendientes", f"Sin movimiento (> {rep['umbral']} días)"],
                 [[f"{rep['tasa_mantenimiento']}%", rep["asignaciones_cerradas"], len(rep["actas_pendientes"]), len(rep["sin_movimiento"])]])]
    el += [Paragraph("Equipos asignados por área", h2), tabla(["Área", "Equipos"], [[a["area"], a["c"]] for a in rep["por_area"]])]
    el += [Paragraph("Equipos por estado", h2), tabla(["Estado", "Cantidad"], [[x["nombre"], x["c"]] for x in rep["por_estado"]])]
    el += [Paragraph("Equipos por tipo", h2), tabla(["Tipo", "Cantidad"], [[x["nombre"], x["c"]] for x in rep["por_tipo"]])]
    el += [Paragraph(f"Asignaciones en el rango ({len(rep['asignaciones'])})", h2),
           tabla(["Fecha", "Código", "Equipo", "Empleado", "Estado"],
                 [[_f(a["fecha_asignacion"]), a["codigo"], f"{a['tipo'] or ''} {a['marca'] or ''} {a['modelo'] or ''}".strip(),
                   a["empleado"], a["estado"]] for a in rep["asignaciones"]])]
    el += [Paragraph(f"Mantenimientos en el rango ({len(rep['mantenimientos'])})", h2),
           tabla(["Fecha", "Código", "Tipo", "Responsable", "Estado", "Descripción"],
                 [[_f(m["fecha"]), m["codigo"], m["tipo"], m.get("responsable") or "-", m["estado"], m["descripcion"] or ""]
                  for m in rep["mantenimientos"]])]
    el += [Paragraph(f"Movimientos de equipos ({len(rep['movimientos'])})", h2),
           tabla(["Fecha", "Código", "Evento", "Detalle", "Cambio de estado", "Registrado por"],
                 [[_f(h["fecha"], "%d/%m/%Y %H:%M"), h["codigo"], h["tipo_evento"], h["detalle"] or "",
                   f"{h['estado_anterior'] or '-'} > {h['estado_nuevo'] or '-'}", h["usuario"] or ""] for h in rep["movimientos"]])]
    el += [Paragraph(f"Equipos registrados en el rango ({len(rep['nuevos'])})", h2),
           tabla(["Fecha", "Código", "Tipo", "Marca / Modelo", "Serie", "Estado"],
                 [[_f(n["fecha_ingreso"]), n["codigo"], n["tipo"], f"{n['marca'] or ''} {n['modelo'] or ''}".strip(),
                   n["numero_serie"], n["estado"]] for n in rep["nuevos"]])]
    el += [Paragraph(f"Actas pendientes de firma ({len(rep['actas_pendientes'])})", h2),
           tabla(["N.º", "Generada", "Código", "Empleado", "Días"],
                 [[f"{a['id']:04d}", _f(a["fecha_generacion"]), a["codigo"], a["empleado"], a["dias"]] for a in rep["actas_pendientes"]])]
    el += [Paragraph(f"Equipos sin movimiento ({len(rep['sin_movimiento'])})", h2),
           tabla(["Código", "Equipo", "Estado", "Último movimiento", "Días"],
                 [[m["codigo"], f"{m['tipo'] or ''} {m['marca'] or ''} {m['modelo'] or ''}".strip(), m["estado"],
                   _f(m["ultimo"]), m["dias"]] for m in rep["sin_movimiento"]])]
    doc.build(el)
    return buf.getvalue()
