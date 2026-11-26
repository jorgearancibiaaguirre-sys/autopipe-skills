# autopipe-skills

Skills de Claude Code para analisis de flexibilidad de lineas de tuberias con Bentley AutoPIPE 2025 (Python DataAPI).

| Skill | Funcion |
|---|---|
| `compiling-piping-input-data` | Compila antecedentes (memoria, trazado, planos) de una linea HDPE, de acero u otro material en `trazado_general.csv` (con ramas, tees y soportes sobre viga; cota del eje desde fondo y OD), `tabla_tramos.csv` y resumen, sin inventar datos; valida los entregables |
| `building-autopipe-model-api` | Construye un modelo `.dat` (B31.4) con la DataAPI a partir de esos CSV y un `config_proyecto.json`: HDPE o acero/otro material por material y schedule, reductores, tees, derivaciones y lazos, soportes de suelo, guias sobre vigas, anclajes, casos P/T, sismo estatico y analysis sets; verifica leyendo el archivo. No construye valvulas, bridas, toberas ni la union entre materiales |
| `auditing-autopipe-model` | Audita sin modificar un modelo leyendo el `.DB`, `.CHK` y logs |

Guia de usuario (inputs, entregables, limites y precauciones): [GUIA_USUARIO.md](GUIA_USUARIO.md).

Instalacion: copiar las carpetas a `~/.claude/skills/` (usuario) o `<proyecto>/.claude/skills/`.
Requisitos: Python 3.12, AutoPIPE 2025 con licencia activa (solo para construir/verificar).
Validadas con subagentes solo con Sonnet; sin probar con Haiku/Opus. Acero, tees, ramas y vigas se probaron con scripts, no con subagentes ni en la GUI de AutoPIPE.


