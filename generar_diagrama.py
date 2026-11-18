import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Polygon
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(16, 22))
ax.set_xlim(0, 16)
ax.set_ylim(0, 22)
ax.axis('off')
ax.set_title('SIGEC - Diagrama de Flujo del Sistema de Inventario y Gestión de Equipos de Cómputo', 
             fontsize=16, fontweight='bold', pad=20)

# Colors
start_end = '#4CAF50'
process = '#2196F3'
decision = '#FF9800'
data = '#9C27B0'
exception = '#F44336'

def draw_box(ax, x, y, w, h, text, color, shape='box'):
    if shape == 'box':
        box = FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.1", 
                             facecolor=color, edgecolor='black', linewidth=1.5, alpha=0.9)
    elif shape == 'diamond':
        points = np.array([[x, y+h/2], [x+w/2, y], [x, y-h/2], [x-w/2, y]])
        box = Polygon(points, facecolor=color, edgecolor='black', linewidth=1.5, alpha=0.9)
    elif shape == 'ellipse':
        box = mpatches.Ellipse((x, y), w, h, facecolor=color, edgecolor='black', linewidth=1.5, alpha=0.9)
    ax.add_patch(box)
    ax.text(x, y, text, ha='center', va='center', fontsize=7.5, wrap=True, 
            fontweight='bold' if shape=='ellipse' else 'normal')
    return box

def draw_arrow(ax, x1, y1, x2, y2, label=''):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))
    if label:
        mid_x, mid_y = (x1+x2)/2, (y1+y2)/2
        ax.text(mid_x, mid_y, label, fontsize=6, ha='center', color='darkred', 
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

# Start
draw_box(ax, 8, 21, 2.5, 0.8, 'INICIO', start_end, 'ellipse')

# Main process
draw_box(ax, 8, 19.5, 3.5, 0.9, 'Registrar Equipo\n(Tipo, Serie, Estado inicial)', process)
draw_arrow(ax, 8, 20.6, 8, 20.0)

draw_box(ax, 8, 18, 3, 0.8, '¿Serie única?', decision, 'diamond')
draw_arrow(ax, 8, 19.0, 8, 18.4)

draw_box(ax, 12, 18, 2.5, 0.7, 'Rechazar\n(Duplicado)', exception)
draw_arrow(ax, 9.5, 18, 10.7, 18, 'No')

draw_box(ax, 8, 16.5, 3.2, 0.8, 'Gestionar Empleados\n(Activos/Inactivos)', process)
draw_arrow(ax, 8, 17.6, 8, 16.9)
draw_arrow(ax, 6.5, 18, 6.5, 17, '')  # from yes path conceptually

# Decision for assignment
draw_box(ax, 8, 15, 3.2, 0.8, '¿Asignar equipo?', decision, 'diamond')
draw_arrow(ax, 8, 16.1, 8, 15.4)

draw_box(ax, 12.5, 15, 2.8, 0.7, 'Consultar / Reportes', process)
draw_arrow(ax, 9.6, 15, 11.1, 15, 'No')

# Assignment flow
draw_box(ax, 8, 13.5, 3.5, 0.9, 'Seleccionar Equipo\nDisponible + Empleado Activo', process)
draw_arrow(ax, 8, 14.6, 8, 14.0)

draw_box(ax, 8, 12, 3, 0.8, '¿Equipo disponible\ny Empleado activo?', decision, 'diamond')
draw_arrow(ax, 8, 13.05, 8, 12.4)

draw_box(ax, 12.5, 12, 2.8, 0.7, 'Rechazar asignación\n(Mensaje claro)', exception)
draw_arrow(ax, 9.5, 12, 11.1, 12, 'No')

draw_box(ax, 8, 10.5, 3.5, 0.9, 'Crear Asignación\nCambiar estado a "Asignado"\nGenerar Acta Pendiente', process)
draw_arrow(ax, 8, 11.6, 8, 11.0)

draw_box(ax, 8, 9, 3, 0.8, 'Registrar Firma del Acta', process)
draw_arrow(ax, 8, 10.05, 8, 9.4)

draw_box(ax, 8, 7.5, 3.2, 0.8, '¿Firma registrada?', decision, 'diamond')
draw_arrow(ax, 8, 8.6, 8, 7.9)

draw_box(ax, 12, 7.5, 2.5, 0.7, 'Acta pendiente\n(Seguimiento)', exception)
draw_arrow(ax, 9.5, 7.5, 10.7, 7.5, 'No')

# Changes and close
draw_box(ax, 8, 6, 3.5, 0.9, 'Cambios de Estado\n(Reparación, Devolución, Baja)', process)
draw_arrow(ax, 8, 7.1, 8, 6.5)

draw_box(ax, 8, 4.5, 3, 0.8, 'Registrar en Historial\n(Auditoría)', data)
draw_arrow(ax, 8, 5.55, 8, 4.9)

draw_box(ax, 8, 3, 3.2, 0.8, 'Consultas de Trazabilidad\n(Equipo ↔ Empleado)', process)
draw_arrow(ax, 8, 4.1, 8, 3.4)

draw_box(ax, 8, 1.5, 2.5, 0.8, 'FIN / Continuar', start_end, 'ellipse')
draw_arrow(ax, 8, 2.6, 8, 1.9)

# Legend
legend_elements = [
    mpatches.Patch(color=start_end, label='Inicio / Fin'),
    mpatches.Patch(color=process, label='Proceso'),
    mpatches.Patch(color=decision, label='Decisión / Validación'),
    mpatches.Patch(color=exception, label='Excepción / Alternativa'),
    mpatches.Patch(color=data, label='Registro / Historial'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=8, framealpha=0.9)

# Side notes
ax.text(1, 19, 'Validaciones:\n• Serie única (RN-08)\n• Solo equipos disponibles (RN-01)\n• Empleado activo (RN-05)', 
        fontsize=7, va='top', bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
ax.text(1, 10, 'Situaciones no ideales:\n• Acta sin firmar\n• Equipo no disponible\n• Empleado inactivo\n• Duplicado de serie', 
        fontsize=7, va='top', bbox=dict(boxstyle='round', facecolor='#ffebee', alpha=0.8))

plt.tight_layout()
plt.savefig('/workspace/artifacts/sigec_proyecto/diagrama_flujo_sigec.png', dpi=150, bbox_inches='tight', 
            facecolor='white', edgecolor='none')
plt.close()
print("Diagrama de flujo generado: diagrama_flujo_sigec.png")
