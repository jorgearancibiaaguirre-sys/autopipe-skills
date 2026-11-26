---
name: auditing-autopipe-model
description: Audita sin modificarlo un modelo de Bentley AutoPIPE leyendo el .DB (SQLite del ultimo analisis), el .CHK y los logs L00n.LOG; detecta Fluid Density Factor o Friction Scale Factor en cero, contenido que no pesa, incoherencias de presion/temperatura por pipe id, soportes y codos, desfases entre archivos y compara contra una especificacion en JSON, con peso analitico de tuberia y contenido. Usar cuando el usuario guarda un modelo editado en la GUI, pide revisar o comparar configuraciones, pregunta por que dos analysis sets dan cargas de gravedad iguales, un tramo parece no analizado, o la DataAPI no abre el .dat (error E0).
---

# Auditoria de modelos AutoPIPE (solo lectura)

## Fuentes, en este orden
1. `<modelo>.DB`: SQLite con el listado de entrada del ULTIMO analisis (soportes, anclajes, pipe properties, P/T por punto, analysis sets, codos, toberas, sismo). Tablas y columnas: [reference/tablas_db.md](reference/tablas_db.md).
2. `<modelo>.CHK`: avisos de consistencia. Significado de cada codigo: [reference/avisos.md](reference/avisos.md).
3. `<modelo>.L001.LOG`, `.L002.LOG`: reacciones de los soportes no lineales por set.
4. El `.dat` con la DataAPI **solo si abre**; un `.dat` guardado por la GUI puede dar E0 (causa no determinada). Nunca modificarlo.

El `.DB` refleja el ultimo analisis, no necesariamente lo que hay hoy en el `.dat`: siempre comparar fechas y avisar del desfase.

## Flujo
```
- [ ] 1. Confirmar con el usuario que archivos son (modelo y fecha de su ultimo analisis) y que no se modifica nada
- [ ] 2. python scripts/audit_db.py --db M.DB --chk M.CHK --logs L001.LOG L002.LOG [--dat M.dat] [--spec spec.json] --out informe.md
- [ ] 3. Leer HALLAZGOS y secciones 1-10 del informe; contrastar cada hallazgo con su evidencia (tabla, valor, aviso)
- [ ] 4. Responder al usuario con causa probable, evidencia, lo no verificado y pasos; sin tocar el modelo
```
El script imprime ademas el sha256 de cada entrada antes y despues: citarlo como prueba de que nada cambio.

## Criterio (con libertad)
- **Gravedad igual entre sets:** mirar primero `Fluid_Density_Fact_Contents` y el flag de contenido en `Static_Analysis`, el aviso W2164-93 y las sumas GR de los logs frente al peso analitico (seccion 9). Un set lleno cuya suma GR se acerca al peso del tubo solo no esta pesando el contenido. En la API `pipe_contents=False` significa contenido incluido: no declarar "invertido" sin leer `Contents_Weight_Included`.
- **Tramo "no analizado":** buscar incoherencias de P/T por pipe id (seccion 5); un modulo de acero en puntos de una tuberia HDPE es una causa tipica.
- **Comparar contra una especificacion:** cada item sale como cumple, NO CUMPLE o no verificable; no convertir un "no verificable" en cumple.
- Un hallazgo es una pista, no una conclusion: decir que se verifico y que no (reportes de la GUI, resultados fuera de los logs).
- Los logs recortados dan sumas parciales; informarlo si el numero de soportes es menor que el del `.DB`.

## Cuando detenerse y preguntar
- El `.DB` es mas antiguo que el `.CHK` o el `.dat` y la conclusion depende de un valor que pudo cambiar (pedir reanalizar).
- Una diferencia parece una decision de diseno (cambio de patron de apoyo, clase de tuberia): se registra, no se corrige.
- El usuario pide corregir el modelo: eso lo hace `building-autopipe-model-api` o el usuario en la GUI, con su confirmacion.
- Unidades del `.DB` que no son SI: no estimar pesos.

## Reglas
- Solo lectura sobre todo archivo del usuario. Salidas en una carpeta aparte.
- No afirmar que algo "cumple" si no se leyo el valor.
- Los registros de cambios del usuario respecto del generador van a un archivo de diferencias; no se aplican en silencio.
