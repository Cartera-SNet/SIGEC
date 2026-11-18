```mermaid
flowchart TD
    A[Inicio] --> B[Registrar Equipo<br/>Tipo, Serie, Estado inicial]
    B --> C{¿Número de serie<br/>único?}
    C -->|No| D[Rechazar registro<br/>Mensaje de duplicado]
    C -->|Sí| E[Guardar equipo<br/>en inventario]
    E --> F[Gestionar / Consultar<br/>Empleados]
    F --> G{¿Se requiere<br/>asignar equipo?}
    G -->|No| H[Consultas, Reportes<br/>e Indicadores]
    G -->|Sí| I[Seleccionar equipo<br/>Disponible + Empleado Activo]
    I --> J{¿Equipo disponible<br/>y Empleado activo?}
    J -->|No| K[Rechazar asignación<br/>Mensaje claro]
    J -->|Sí| L[Crear Asignación<br/>Estado → Asignado<br/>Generar Acta Pendiente]
    L --> M[Registrar Firma<br/>del Acta]
    M --> N{¿Firma<br/>confirmada?}
    N -->|No| O[Acta queda pendiente<br/>para seguimiento]
    N -->|Sí| P[Acta Firmada<br/>Custodia formalizada]
    P --> Q[Cambios de Estado<br/>Reparación / Devolución / Baja]
    Q --> R[Registrar evento<br/>en Historial]
    R --> S[Consultas de Trazabilidad<br/>Equipo ↔ Empleado]
    S --> T[Fin / Continuar operación]
    
    style A fill:#4CAF50,color:#fff
    style T fill:#4CAF50,color:#fff
    style C fill:#FF9800
    style G fill:#FF9800
    style J fill:#FF9800
    style N fill:#FF9800
    style D fill:#F44336,color:#fff
    style K fill:#F44336,color:#fff
    style O fill:#F44336,color:#fff
```

**Leyenda de relación con la ficha:**
- Validaciones alineadas con RN-01, RN-05, RN-08
- Procesos principales según sección 8
- Situaciones no ideales según sección 15
- Trazabilidad bidireccional (RF-09, RF-10)
