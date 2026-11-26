# autopipe-skills

Skills de Claude Code para analisis de flexibilidad de lineas de tuberias con Bentley AutoPIPE 2025 (Python DataAPI).

| Skill | Funcion |
|---|---|
| `compiling-piping-input-data` | Compila antecedentes (memoria, trazado, planos) en `trazado_general.csv`, `tabla_tramos.csv` y resumen, sin inventar datos |
| `building-autopipe-model-api` | Construye un modelo `.dat` HDPE (B31.4) con la DataAPI a partir de esos CSV y un `config_proyecto.json`; alcance: HDPE, rama principal |
| `auditing-autopipe-model` | Audita sin modificar un modelo leyendo el `.DB`, `.CHK` y logs |

Instalacion: copiar las carpetas a `~/.claude/skills/` (usuario) o `<proyecto>/.claude/skills/`.
Requisitos: Python 3.12, AutoPIPE 2025 con licencia activa (solo para construir/verificar).
Validadas solo con Sonnet; sin probar con Haiku/Opus ni en acero, tees o ramas.
