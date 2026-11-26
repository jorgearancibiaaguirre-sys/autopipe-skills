# Avisos del .CHK de AutoPIPE

## Contenido
- Avisos que cambian los resultados
- Avisos informativos
- Errores de ejecucion tipicos

## Avisos que cambian los resultados
| Codigo | Significado | Accion |
|---|---|---|
| W2164-93 | Fluid Density Factor en 0 en los sets listados: el contenido no pesa | Poner el factor en 1,0 en el set lleno y reanalizar |
| W2143-76 | Friction Scale Factor en 0: se ignora la friccion de todos los soportes | Poner el factor en 1,0 si la friccion debe contar |
| W726-9 | Guide o Line Stop en un punto con quiebre | Mover el soporte a un punto cercano |
| W726-7 | Cambio de diametro sin reductor | Revisar el modelo |
| W726-8 | Quiebre en un tramo recto | Informativo si es el trazado real |

## Avisos informativos
| Codigo | Significado |
|---|---|
| W2164-78 | D/t < 20: la ecuacion de esfuerzo circunferencial puede no aplicar (HDPE gruesos); usar el factor Y del codigo |
| W726-93 | Brida de peso cero |
| W801-123 | Despegue de una guia bajo la carga de operacion |
| W726-2 | Orientacion de gap cambiada para una guia |

Los avisos de una lista de puntos (W726-*) traen los nombres de punto en las lineas siguientes del `.CHK`.

## Errores de ejecucion tipicos
- "Unstable system, need support at node X Dir Z": falta un soporte o anclaje en esa direccion; un extremo libre de un tramo suele necesitar un anclaje rigido.
