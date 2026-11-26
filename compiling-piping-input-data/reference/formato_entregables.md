# Formato de los entregables

## Contenido
- trazado_general.csv
- tabla_tramos.csv
- resumen_antecedentes.md
- CLAUDE.md del proyecto

CSV con separador `;`, UTF-8 con BOM, una cabecera. Se admiten columnas adicionales al final.

## trazado_general.csv
Columnas obligatorias: `punto;tipo_nodo;rama;X_m;Y_m;Z_eje_m;progresiva_m`
- `punto`: nombre unico del nodo.
- `tipo_nodo`: `extremo`, `soporte`, `vertice_trazado`, `punto`, `tee`, `soporte_viga` (otros tipos, como `valvula` o `brida`, se admiten pero `building-autopipe-model-api` hoy los rechaza).
- `rama`: `PRINCIPAL` o el nombre de la rama. Una derivacion repite como primer nodo la tee de la rama de la que nace (mismo `punto` y coordenadas, tipo `tee`); si vuelve a otra tee (lazo), su ultimo nodo la repite.
- Tipos que `building-autopipe-model-api` construye: `extremo`, `soporte`, `vertice_trazado`, `punto`, `tee` y `soporte_viga` (guia sobre viga vertical).
- `X_m`, `Y_m`: coordenadas en metros en el sistema acordado (local o del datum).
- `Z_eje_m`: cota del EJE de la tuberia (cota del fondo mas medio diametro exterior). Sin OD conocido: `FALTANTE`, y la cota del fondo va en la columna opcional `z_bop_m`.
- `progresiva_m`: metros desde el origen, creciente a lo largo de la linea.
Columnas utiles opcionales: `z_terreno_m`, `comentario`.

## tabla_tramos.csv
Columnas obligatorias: `tramo;desde_m;hasta_m;material;DN_mm;PN;fuente;estado`
- Los tramos empalman y cubren desde la primera hasta la ultima progresiva.
- `material`: por ejemplo `HDPE PE100`; `DN_mm`: numero.
- `PN`: por ejemplo `PN16`.
- `fuente`: de donde sale cada dato (`trazado`, `memoria p.12`, `plano capa X`, `usuario 2026-11-26`).
- `estado`: `vigente` o `DISCREPANCIA abierta`.
- Si un dato falta: la palabra `FALTANTE` en esa celda.
Columnas opcionales: `rama` (vacia = PRINCIPAL; una fila por tramo de cada rama, con la progresiva propia de la rama), `clase_plano_ref` (la clase que indica el plano cuando difiere), `observacion`.

## resumen_antecedentes.md
Seis secciones con estos titulos:
1. `## 1. Entendimiento del proyecto y del trazado`
2. `## 2. Tabla de tramos` (la de `tabla_tramos.csv`, con la fuente de cada dato)
3. `## 3. Discrepancias` (ambas versiones, progresivas y fuente; si no hay: "ninguna")
4. `## 4. Faltantes y preguntas` (cada FALTANTE con la pregunta concreta al usuario)
5. `## 5. Supuestos sin aplicar` (lo que habria que suponer; ninguno se aplica; si no hay: "ninguno")
6. `## 6. Datos generales de entrada` (fluido y densidad, presiones, temperaturas, material, normas; solo valores, con fuente)

## CLAUDE.md del proyecto
Resumen de cinco a diez lineas con: de que trata la linea, jerarquia de fuentes acordada, rutas relativas de los archivos anteriores, decisiones del usuario con fecha y la regla "no inventar datos; las discrepancias se registran". No copiar tablas completas.
