# Guia de usuario: skills de AutoPIPE

Tres skills encadenadas: antecedentes -> construccion del modelo -> auditoria.

## 1. Inputs que entrega el usuario

| Skill | Que entrega el usuario | Formato |
|---|---|---|
| **1. `compiling-piping-input-data`** | Memoria de calculo | `.docx` o `.pdf` (se convierte a Markdown) |
| | Planos y perfil del trazado | DWG o PDF, o el trazado ya extraido a CSV (nodos, coordenadas, cotas, progresivas) |
| | Decisiones: jerarquia entre fuentes, datum, que datos se toman de la memoria | Chat, o `config_antecedentes.json` opcional |
| **2. `building-autopipe-model-api`** | `trazado_general.csv` y `tabla_tramos.csv` | CSV con `;` y UTF-8 (los produce la skill 1) |
| | `config_proyecto.json` | JSON |
| | Modelo base vacio | `.dat` de la misma version de AutoPIPE |
| **3. `auditing-autopipe-model`** | Salidas del ultimo analisis del modelo | `.DB`, `.CHK` y `L00n.LOG` |
| | Especificacion a comparar (opcional) | JSON |

### Detalle de la skill 2
- **`trazado_general.csv`**: columnas `punto; tipo_nodo; rama; X_m; Y_m; Z_eje_m; progresiva_m`.
  - `Z_eje_m` es la cota del eje, no del fondo ni del terreno.
  - `tipo_nodo`: `extremo`, `soporte`, `vertice_trazado`, `punto`, `tee`, `soporte_viga`.
  - Una derivacion repite como primer nodo la tee de la que nace; si cierra un lazo, repite como ultimo nodo la tee de llegada.
- **`tabla_tramos.csv`**: columnas `tramo; desde_m; hasta_m; material; DN_mm; PN; fuente; estado`, mas `rama` si hay derivaciones.
  - Los tramos deben empalmar y cubrir la progresiva de su rama; `estado` debe ser `vigente`.
  - La clase de cada tramo es la clave `material|DN|PN`, por ejemplo `HDPE PE100|315|PN16`.
- **`config_proyecto.json`**:
  - Codigo y libreria de materiales (por ejemplo `2019` y `B314-19`); temperatura de montaje.
  - Clases: `id` (maximo 8 caracteres) y presion de operacion. HDPE: ademas OD y espesor. Acero u otro material: `material_id` y `schedule`; OD y espesor opcionales.
  - Propiedades del HDPE, densidad del fluido, largo del reductor, radio del codo.
  - Casos de carga, sismo estatico, soportes de suelo, anclajes, analisis.
  - Si hay vigas: seccion, material (obligatorio), alturas y guia.
  - Detalle campo por campo: `building-autopipe-model-api/reference/config_schema.md`; ejemplos en `assets/`.

## 2. Que entregan las skills

| Skill | Entregables |
|---|---|
| **1** | `trazado_general.csv`, `tabla_tramos.csv`, `resumen_antecedentes.md` (6 secciones), `CLAUDE.md` del proyecto y la memoria en Markdown. Discrepancias y `FALTANTE` quedan registrados, no resueltos. |
| **2** | El `.dat` nuevo y `<nombre>.informe.md` con supuestos, FALTANTES y avisos; verificacion por lectura del archivo guardado. |
| **3** | Informe de solo lectura: cumplido, no cumplido y no verificable, como lista de ajustes por categoria. |

## 3. Limitaciones

**General**
- No analizan ni calculan esfuerzos: el analisis lo corre el usuario en AutoPIPE.
- No juzgan el diseno ni toman decisiones por el usuario.
- Validadas solo con Sonnet; sin probar con Haiku ni Opus.

**Skill 1**
- Depende de las herramientas disponibles para abrir DWG o PDF; si no puede leer una fuente, se detiene.
- No resuelve discrepancias entre fuentes.
- Sin OD en las fuentes, `Z_eje_m` queda `FALTANTE`.

**Skill 2**
- Construye: HDPE, acero y otros materiales de la libreria, reductores, tees, derivaciones, lazos y guias sobre vigas.
- No construye: valvulas, bridas, toberas, la union entre materiales distintos ni reducciones propias del trazado.
- La API acepta cualquier material o schedule sin validar que existan.
- Clase de acero sin OD ni espesor: la API los lee como 0 y no se verifican.
- La conexion del lazo y la orientacion de la viga no se pueden comprobar por lectura de la API.
- Un `.dat` guardado por la GUI puede no abrirse con la API (error E0).

**Skill 3**
- El `.DB` refleja el ultimo analisis, no necesariamente el `.dat` actual.
- Los logs pueden estar truncados (en las pruebas cubrian 972 de 1.548 soportes); la skill lo avisa.

## 4. Precauciones del usuario

- **Licencia**: sesion de Bentley activa; sin ella la API da error E4.
- **Versiones**: Python 3.12 y la misma version de AutoPIPE y de la DataAPI que el modelo base.
- **Originales**: las skills nunca sobrescriben un archivo, pero conviene mantener copia de los `.dat` propios. Al editar un modelo existente, el archivo nuevo puede perder datos que la API no guarda.
- **Valores de ejemplo**: no reutilizar los de `assets/` sin confirmarlos; son de un proyecto demo.
- **Revisar en la GUI el `.dat` generado**: material y schedule en Pipe Properties, OD y espesor asignados, cierre de lazos, orientacion de las vigas (vista solida), direccion de las guias, y que desaparezcan los avisos W2164-93 y W2143-76 al reanalizar.
- **Antes de construir**: resolver las discrepancias y los `FALTANTE`; con una `DISCREPANCIA abierta` la skill 2 se detiene.
- **Pendientes**: leer los `FALTANTE` y avisos de `*.informe.md` (expansion termica y modulo en frio quedan en 0 si no se dan).
- **Nombres**: ids de pipe property de maximo 8 caracteres; nombres de punto distintos del prefijo de las vigas (`VG` por defecto).
