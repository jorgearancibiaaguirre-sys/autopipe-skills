# Entradas de building-autopipe-model-api

## Contenido
- trazado_general.csv
- tabla_tramos.csv
- config_proyecto.json
- Reglas de coherencia

Separador `;`, decimal con punto o coma, UTF-8 con o sin BOM. Los dos CSV los produce `compiling-piping-input-data`.

## trazado_general.csv
Columnas: `punto;tipo_nodo;rama;X_m;Y_m;Z_eje_m;progresiva_m`.
- `Z_eje_m` es la cota del EJE de la tuberia (no del fondo ni del terreno).
- `tipo_nodo`: `extremo`, `soporte`, `vertice_trazado` (cambio de direccion: se modela como codo), `punto`.
- `rama`: solo `PRINCIPAL`.
- `progresiva_m` crece a lo largo de la linea y se usa para ubicar los cambios de clase entre nodos.

## tabla_tramos.csv
Columnas: `tramo;desde_m;hasta_m;material;DN_mm;PN;fuente;estado`.
- Los tramos empalman (`hasta` de uno = `desde` del siguiente) y cubren toda la linea.
- `estado` debe ser `vigente`. `DISCREPANCIA abierta` detiene la construccion.
- La clase de un tramo es la clave `material|DN_mm|PN`, por ejemplo `HDPE PE100|315|PN16`.

## config_proyecto.json
| Campo | Obligatorio | Descripcion |
|---|---|---|
| `proyecto` | no | Id del proyecto (se escribe en el modelo) |
| `ruta_dataapi` | no | Carpeta de la DataAPI; por defecto la instalacion estandar de AutoPIPE 2025 |
| `codigo.edicion`, `codigo.libreria_materiales` | si | Edicion de ASME B31.4 y libreria de materiales (p. ej. `2019`, `B314-19`) |
| `temperatura_montaje_C` | si | Temperatura de montaje |
| `clases` | si | Una entrada por clave de clase: `id` (maximo 8 caracteres), `presion_operacion_MPa`. HDPE: `od_mm` y `espesor_mm` obligatorios, `sdr` (opcional). Otro material: ademas `material_id` y `schedule` (obligatorios) y opcionales `od_mm`, `espesor_mm` (ver abajo), `nps_in` (si el DN no esta en la correspondencia estandar), `propiedades`, `radio_codo_en_diametros`, `sin_soporte_suelo` |
| `material_hdpe` | si hay clases HDPE | `densidad_kg_m3`, `modulo_caliente_MPa`, `fluencia_MPa`, `poisson`; opcionales `coef_expansion_1e6_por_C`, `modulo_frio_MPa` (si faltan: FALTANTE, quedan en 0) |
| `fluido.densidad_kg_m3` | si | Para el peso del contenido |
| `reductor_largo_mm` | si | Largo del reductor insertado en un cambio de DN |
| `discretizacion_m` | no | Paso maximo entre puntos en tramos rectos (`null` = solo nodos del trazado) |
| `codo.radio_en_diametros` | si | Radio del codo en multiplos del OD (el criterio del proyecto: ver el codigo aplicable) |
| `casos[]` | si | `nombre`, `T_C`, `presion` (`"clase"` = presion de operacion de cada clase, o un numero en MPa), `contenido` (true = lleno) |
| `sismo_estatico_g` | no | `E1_X`, `E2_Y`, `E3_Z` en g |
| `soportes.suelo` | si | `roce`, `gap_lateral_mm`, `gap_arriba_mm`, `gap_abajo_mm`, `aplicar_en_tipos_nodo`, `en_intermedios` |
| `soportes.anclajes_rigidos_en` | no | `"extremos"` o lista de nombres de punto |
| `analisis` | no | `friction_scale_factor`, `fluid_density_factor_lleno`, `no_lineal`, `iteraciones` |

## Clases que no son HDPE
- La clave de la clase es el `material` de la tabla de tramos (cualquier texto que no empiece con `HDPE`), por ejemplo `ACERO A53-B|150|CL150`.
- `material_id`: id del material en la libreria de AutoPIPE (p. ej. `A53-B`); `schedule`: p. ej. `STD`, `40`. AutoPIPE carga de su libreria modulo, densidad y expansion segun ambos; la skill no las sobrescribe ni las verifica (se avisa). La API **no valida** que el material o el schedule existan: revisarlo en Pipe Properties.
- `od_mm` y `espesor_mm` son **opcionales** (ambos o ninguno). Sin ellos la skill escribe solo NPS + material + schedule y AutoPIPE asigna OD y espesor desde su base; la API los lee como 0, asi que no se verifican. Con ellos se escriben y se verifican. El contenido no depende de esto: la skill escribe solo la densidad del fluido (`fluido.densidad_kg_m3`) y AutoPIPE calcula el peso por longitud.
- El radio del codo de estas clases es `radio_en_diametros` x diametro NOMINAL (NPS x 25,4 mm); en HDPE, x OD.
- NPS: `nps_in` si se indica; si no, la correspondencia estandar DN->NPS (DN150 = 6", DN450 = 18"); un DN fuera de la tabla detiene el proceso.
- `material_id` = `NS` (no estandar) exige `propiedades` con `densidad_kg_m3`, `modulo_caliente_MPa`, `fluencia_MPa`, `poisson` (opcionales `coef_expansion_1e6_por_C`, `modulo_frio_MPa`); con `propiedades` la skill las sobrescribe y las verifica como en HDPE.
- Ejemplo mixto acero + HDPE: `assets/config_proyecto_mixto.example.json`.
- El reductor se inserta cuando cambia el DN entre tramos, no cuando cambia el OD.

Los valores del ejemplo son de un proyecto de demostracion; nunca los reutilice sin confirmarlos con el usuario.

## Reglas de coherencia
Las comprueba `scripts/preflight.py`: columnas, continuidad de tramos, cobertura del trazado, clases presentes en `clases`, ids unicos de hasta 8 caracteres, campos obligatorios, nombres de punto unicos.
