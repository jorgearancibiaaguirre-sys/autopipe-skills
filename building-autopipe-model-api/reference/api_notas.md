# Notas de la DataAPI de AutoPIPE (verificadas en la version 25.00.01.213)

## Contenido
- Errores frecuentes
- Semanticas que enganan
- Escritura de valores
- Limitaciones sin sustituto
- Sin verificar

## Errores frecuentes
| Codigo | Causa | Accion |
|---|---|---|
| E4 License not found | Sesion de Bentley sin licencia activa | Pedir iniciar sesion en Bentley Connect |
| E0 internal error al abrir | `.dat` guardado por la GUI; causa no determinada (en el proyecto de origen ocurrio con un modelo de 6,5 MB guardado por la GUI de la misma version, y la documentacion de la API dice que solo abre modelos de su misma version) | No modificar el archivo; leer el `.DB` |
| E19007 | Soporte que no admite holguras (V-stop) | Usar Guide con gap arriba y abajo |
| E19008 | Linestop con roce | Linestop sin roce; el roce va en la Guide |
| E1009 | Soporte en el vertice de un codo | Poner el soporte en near/far del codo |
| E6000 componente desconectado | Un componente creado y no conectado al segmento | No dejar `add_nozzle` ni runs sueltos; quitarlos antes de guardar |
| E15001, E15005 | Tobera: largo, L1/L2 o ubicacion de recipiente no admitidos por el metodo | Completar esos datos en la GUI |

## Semanticas que enganan
- `LoadSet.pipe_contents`: **False = el set incluye el peso del contenido** (se confirmo comparando con el `.DB` de AutoPIPE: Contents_Weight_Included = Yes). El set lleno se escribe con False. Un modelo con el flag al reves da el mismo peso gravitacional en los dos sets.
- `LoadSet.fluid_density_factor` y `friction_factor` valen 0 si no se asignan (avisos W2164-93 y W2143-76 del `.CHK`): asignarlos despues de `add_load_set`.
- `PipeProperty.content_weight` es la **densidad del fluido en lb/ft3** (1000 kg/m3 = 62,43), no un peso por longitud: AutoPIPE calcula el peso por longitud con el diametro interior (6,195 lb/in en un DN450 PN16 con agua, contrastado con el modelo de origen). No necesita OD ni espesor para escribirse.
- `Support.connected` nunca es `None`: un soporte sin conexion devuelve un Handle invalido (E2006 al pedir `.name`). Para saber si una guia esta conectada a una viga, leer `s.connected.name` dentro de un `try`.
- Derivaciones: `tee.branch.segment = m.add_segment()`; el primer elemento de la derivacion se agrega con `offset` respecto de la tee (no `position`); el cierre de un lazo es `ultimo.link(tee.branch)`. `Tee` y `TeeBranch` tienen `pt_loads` (presion y temperatura por caso). La API acepta el `link` sin comprobar la geometria: la conexion se confirma en la GUI.
- Vigas: `add_section` necesita los campos de material (densidad, dilatacion, fluencia, rotura, nombre, tipo) o el `.dat` guardado no se reabre; `add_frame_node` x2, `add_beam(i=pie, j=tope, section, beta_angle)`, `pie.add_anchor()` y `soporte.connected = tope`.
- `pipe_id` se corta a 8 caracteres.
- Renombrar un componente (`component.name`) no es renombrar su punto: son entidades distintas.
- El nombre de un codo es su punto de interseccion de tangentes (`bend.tangent`); los puntos `near`, `mid`, `far` se nombran solos (`X N`, `X F`).

## Escritura de valores
- Unidades internas: pulgadas, lb, psi, F, lb/in3; expansion en in/100 ft (= deformacion unitaria x 1200).
- Modulo caliente y fluencia por caso: `pt_loads[k].override_hot_modulus = True` antes de `hot_modulus`; `override_yield_stress = True` antes de `yield_stress`.
- Con una sola etapa (todo antes del primer `save`) el yield del caso 1 se leyo correctamente en las pruebas de la skill. En el proyecto de origen, aplicar las cargas despues de reabrir un modelo guardado dejo el yield del caso 1 en 0 y se corrigio con un parche binario del `.dat`; `verify_model.py` lo detecta y no se debe usar el parche sin confirmar el valor en la GUI.
- `add_pipe_property(...)` acepta `dimension_ratio`, `is_hdpe_material`; la lectura posterior puede no devolver `is_hdpe_material` ni el SDR (campos que la GUI recalcula).
- `add_pipe_property` con `material_id` y `schedule` (p. ej. `A53-B`, `STD`) no calcula OD ni espesor (leidos 0 si no se pasan, tambien tras guardar y reabrir con la API; el usuario indica que la GUI los asigna desde su base segun NPS y schedule, sin confirmar aqui) y no valida que el material ni el schedule existan (`XXXX` y `999` se aceptan): OD, espesor y la existencia del material se confirman en la GUI. Las propiedades de libreria no se leen por API (modulo y densidad salen 0 al leer). Un tubo HDPE `NS` devuelve schedule vacio al releer.
- La API guarda siempre un archivo nuevo (`<nombre>_API_<n>.dat`); no sobrescribe.

## Limitaciones sin sustituto
- Direccion de las Guide/Linestop (quedan por defecto) y orientacion de vigas: revisar en la GUI.
- Toberas (`add_nozzle`): largo, L1/L2 y ubicacion de recipiente no se pueden escribir con Bijlaard ni WRC 297.
- Analisis y lectura de resultados: no se hacen por la API en esta skill.

## Sin verificar
- Que los avisos W2164-93 y W2143-76 desaparezcan al reanalizar un modelo generado con estos scripts.
- Que el yield del caso 1 coincida con el que muestra la GUI en Pipe Properties (la lectura por API coincide).
- Otras versiones de AutoPIPE.
