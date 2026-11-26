---
name: compiling-piping-input-data
description: Compila los antecedentes de una linea de tuberias para un analisis de flexibilidad (AutoPIPE u otro): convierte la memoria y los planos a Markdown, consolida el trazado en una tabla de tramos con progresivas, DN, material y PN, registra discrepancias entre fuentes y datos faltantes sin inventar valores, lista los supuestos sin aplicar y deja el contexto en un CLAUDE.md. Usar al iniciar un proyecto de analisis de flexibilidad, cuando el usuario pide levantar antecedentes, ordenar el trazado, armar la tabla de tramos o preparar las entradas de un modelo; produce los archivos trazado_general.csv y tabla_tramos.csv que consume building-autopipe-model-api.
---

# Compilacion de antecedentes de una linea de tuberias

## Alcance
Ordena datos de entrada; **no modela, no calcula y no juzga el diseno**. De la memoria interesan las caracteristicas del trazado y de la tuberia, no su metodologia ni sus resultados (esfuerzos, espesores calculados, verificaciones): se citan como referencia solo si el usuario lo pide, nunca como dato de entrada.

## Archivos que se entregan (nombres fijos, en `contexto/` salvo que la config diga otra cosa)
| Archivo | Contenido | Formato |
|---|---|---|
| `memoria_<codigo>.md` | Memoria convertida a Markdown, con tablas y numeracion; figuras con datos transcritas y marcadas | libre |
| `trazado_general.csv` | Nodos del trazado | [reference/formato_entregables.md](reference/formato_entregables.md) |
| `tabla_tramos.csv` | Clase de tuberia por rango de progresivas | idem |
| `resumen_antecedentes.md` | 6 secciones fijas | idem |
| `CLAUDE.md` | Resumen breve y rutas de lo anterior, mas las decisiones del usuario | idem |

## Flujo
```
- [ ] 1. Preguntar lo que la config (assets/config_antecedentes.example.json) no resuelva: jerarquia entre fuentes, datum, que datos se toman de la memoria
- [ ] 2. Convertir la memoria a Markdown (herramientas de conversion disponibles; marcar OCR y figuras transcritas)
- [ ] 3. Extraer del trazado: nodos, coordenadas, cotas, progresivas, singulares y capas relevantes
- [ ] 4. Construir tabla_tramos.csv cruzando fuentes; anotar la fuente de CADA dato
- [ ] 5. Registrar discrepancias (estado "DISCREPANCIA abierta") y faltantes (FALTANTE); no resolver ninguna
- [ ] 6. Redactar resumen_antecedentes.md y actualizar CLAUDE.md
- [ ] 7. python scripts/validar_entregables.py --carpeta contexto ; corregir y repetir hasta 0 errores
- [ ] 8. Mostrar el resumen corto: que se leyo, cuantos tramos, discrepancias, faltantes y que debe aclarar el usuario
```

## Reglas
- **Nunca inventar un valor.** Lo que ninguna fuente trae se marca `FALTANTE` (SDR o espesor, temperatura de montaje, propiedades del material, norma, apoyos). No deducir un SDR del PN.
- **Una discrepancia no se resuelve por cuenta propia.** Se registran ambas versiones, sus progresivas y su fuente, con `estado = DISCREPANCIA abierta`. Si el usuario ya fijo una jerarquia ("el trazado prima, de la memoria solo el PN"), se aplica, y la version descartada queda como columna de referencia y como discrepancia informada.
- **Fuente por dato**: trazado, memoria, plano o la indicacion del usuario, con pagina o capa cuando exista.
- **Resultados de la memoria fuera de las entradas.**
- **`Z_eje_m` = cota del fondo + OD/2 solo si el OD esta en una fuente.** Sin OD, dejar `Z_eje_m` como `FALTANTE`, conservar la cota del fondo en `z_bop_m` y preguntar; no suponer OD = DN.
- **Clase de un nodo que cae en el limite entre dos tramos:** usar la convencion de la config (`convencion_clase_en_nodo_limite`, por defecto `tramo_que_termina`: la clase del nodo es la del tramo que termina en el). Anotarla en `CLAUDE.md` como decision por confirmar; no abrir una discrepancia por esa diferencia.
- Los datos que dio el usuario en el chat valen mas que los documentos: anotarlos con fecha en `CLAUDE.md`.
- Rutas con `/`; decimales con punto en los CSV nuevos (se leen ambos).

## Cuando detenerse y preguntar
- Una fuente no se puede abrir o leer bien (antes de rellenar con suposiciones).
- Falta la jerarquia entre fuentes y hay datos que difieren.
- Cualquier discrepancia que afecte DN, PN, material o progresivas de un tramo.
- El datum o las unidades de las coordenadas no estan claros.
- El usuario pide modelar o calcular: eso queda fuera de esta skill.

## Lo que viene despues
`building-autopipe-model-api` exige `estado = vigente` en todos los tramos y una clase por tramo; por eso las discrepancias abiertas deben cerrarse antes de modelar.
