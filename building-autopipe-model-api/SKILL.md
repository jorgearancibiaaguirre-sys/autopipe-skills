---
name: building-autopipe-model-api
description: Construye con la Python DataAPI de AutoPIPE un modelo .dat de una linea de tuberias HDPE o de acero (u otro material de la libreria, segun material y schedule que indica el usuario) a partir de trazado_general.csv, tabla_tramos.csv y un config_proyecto.json; asigna pipe properties por clase, inserta reductores en los cambios de DN, construye tees, derivaciones y lazos, define soportes de suelo, guias sobre vigas verticales, anclajes, casos presion/temperatura, sismo estatico y analysis sets, y verifica todo leyendo el archivo guardado. Usar cuando se pide generar o regenerar un modelo AutoPIPE por script, crear un .dat con la API, aplicar a un modelo cambios hechos en la GUI o verificar un .dat generado. Se detiene ante discrepancias abiertas, clases sin datos o ramas no soportadas.
---

# Construccion de modelos AutoPIPE por API

## Alcance (esta version)
- Nodos `extremo`, `soporte`, `vertice_trazado`, `punto`, `tee` y `soporte_viga`. Valvulas, bridas, toberas y reducciones propias del trazado **no estan implementados**: detenerse e informar; no improvisar.
- **Ramas:** la rama `PRINCIPAL` mas derivaciones (ramales y lazos tipo bypass) que nacen en un nodo `tee`; reglas en [reference/config_schema.md](reference/config_schema.md). Ejemplo: `assets/ejemplo_ramas_*.csv`.
- **Vigas de soporte:** un nodo `soporte_viga` lleva una guia conectada a una viga vertical anclada al suelo; seccion y material de la viga vienen de la config (obligatorios).
- Materiales por clase (`material|DN|PN` de la tabla de tramos):
  - **HDPE** (la clave empieza con `HDPE`): material `NS`, propiedades de `material_hdpe` en la config.
  - **Cualquier otro** (acero, etc.): el usuario indica `material_id` de AutoPIPE y `schedule` en la clase; AutoPIPE carga modulo, densidad y expansion de su libreria y la skill no las sobrescribe, salvo que la clase traiga `propiedades`. Si el usuario no da OD ni espesor, AutoPIPE los asigna desde su base segun NPS y schedule (la API los lee como 0: no se verifican); si los da, se escriben y se verifican.
  - La union entre materiales distintos (brida, electrofusion) no se modela: queda como aviso.
- Nunca analiza el modelo: el analisis lo corre el usuario en AutoPIPE.
- Entradas, de la skill `compiling-piping-input-data` y del usuario: ver [reference/config_schema.md](reference/config_schema.md). Ejemplo: `assets/config_proyecto.example.json`.

## Flujo
Copiar esta lista y marcarla:
```
- [ ] 1. Preflight: python scripts/preflight.py --config C --trazado T --tabla R --base BASE.dat
- [ ] 2. Si hay DETENERSE o API NO DISPONIBLE: mostrar los mensajes al usuario y esperar su respuesta
- [ ] 3. Construir: python scripts/build_model.py --config C --trazado T --tabla R --base BASE.dat --out SALIDA.dat
- [ ] 4. Revisar la verificacion (verify_model.py corre solo al final): corregir y repetir hasta 0 FAIL
- [ ] 5. Entregar: ruta del .dat, SALIDA.informe.md, FALTANTES y pendientes manuales
```
Cada script imprime que hizo; no re-explicar su logica. Rutas con `/`. Python 3.12 y AutoPIPE con la misma version que el modelo base.

## Reglas que no se negocian
1. **Nunca sobrescribir** un `.dat` (el script se niega) ni tocar el modelo base ni uno del usuario; se trabaja en copias.
2. **No inventar datos.** Lo que no esta en la config queda en 0 y se lista como FALTANTE (expansion termica, modulo en frio). Una clase sin datos o un tramo con `estado` distinto de `vigente` detiene el proceso.
3. **Todo valor se verifica por lectura** del `.dat` guardado, no por el script que lo escribio. Si `verify_model.py` da FAIL, no declarar el modelo correcto.
4. La API habla unidades internas (pulgadas, lb, psi, F): los scripts convierten; no mezclar con valores SI.
5. Un `.dat` guardado por la GUI puede dar E0 en la API (causa no determinada). No intentar modificarlo: usar la skill `auditing-autopipe-model` (lee el `.DB`) o pedir al usuario guardar con la version de la API.
6. Una licencia ausente da E4: pedir iniciar sesion en Bentley Connect; no seguir sin ella.

## Modificar un modelo existente (p. ej. agregar un soporte)
Los scripts construyen modelos nuevos; para editar uno del usuario:
1. Calcular el sha256 del original y trabajar en una copia con otro nombre; la API guarda `<copia>_API_<n>.dat`.
2. Releer el archivo nuevo: confirmar el cambio y comparar conteos (puntos, soportes, anclajes, pipe properties, load sets) contra el original.
3. **Avisar siempre**: el archivo nuevo puede pesar menos (la API no guarda datos que no soporta) y puede no abrir en otra version; pedir abrirlo en AutoPIPE y revisar antes de usarlo. Si el `.dat` original da E0, no editarlo.
4. Si el pedido no fija holguras, direccion ni gap setting, no copiar los de un vecino sin preguntar: informar que quedaron en los valores por defecto de la API.
5. Confirmar que el sha256 del original no cambio.

## Cuando detenerse y preguntar
- Cualquier linea `DETENERSE Y PREGUNTAR` del preflight o del build.
- Cambio de DN que cae justo en un nodo (no se sabe donde va el reductor).
- Una clase que no es HDPE sin `material_id` o `schedule`: preguntar al usuario; no suponer A53-B ni STD.
- Una derivacion cuyo primer nodo no es una tee ya definida, o una rama sin tramos en la tabla; falta el material o la seccion de la viga.
- Nunca suponer la orientacion de la viga: el `beta` por defecto (90 grados) es un supuesto sobre la convencion de ejes; avisar que se revise en vista solida.
- Una limitacion de la API sin sustituto documentado (ver [reference/api_notas.md](reference/api_notas.md)).
- El usuario pide sobrescribir, o pide algo fuera del alcance.

## Que informar al terminar
Cumplido (lo leido), sustituido (p. ej. Linestop sin roce, soporte en near/far del codo) y no cumplido, mas lo que queda manual en la GUI: expansion y modulo en frio si faltan, direccion de las guias, analisis y revision del `.CHK` (avisos W2164-93 y W2143-76 deben desaparecer).
