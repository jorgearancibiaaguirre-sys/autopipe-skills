"""Comprobaciones previas a construir un modelo AutoPIPE. No escribe nada.

Uso: python preflight.py --config config_proyecto.json --trazado trazado_general.csv --tabla tabla_tramos.csv --base base.dat
Salida: lista de DETENERSE (obligan a preguntar al usuario) y de AVISOS. Codigo de salida 0 = sin stops, 2 = hay stops, 3 = API no disponible.
Requisitos: Python 3.12, AutoPIPE instalado (misma version que el modelo base) y licencia activa para abrir el modelo base.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputs  # noqa: E402


def probar_api(cfg, base):
    """Abre el modelo base con la DataAPI. Devuelve un texto de error o None si abre."""
    ruta = cfg.get('ruta_dataapi', inputs.DATAAPI_DEFAULT)
    if not os.path.isdir(ruta):
        return f'No existe la carpeta de la DataAPI: {ruta} (ajustar ruta_dataapi en la config)'
    sys.path.insert(0, ruta)
    try:
        import autopipe  # noqa: F401
        autopipe.open_dat(os.path.abspath(base))
    except ImportError as e:
        return f'No se pudo importar autopipe (Python 3.12 y la version de la DataAPI): {e}'
    except RuntimeError as e:
        msg = str(e)
        if msg.startswith('E4'):
            return f'{msg}. Licencia de AutoPIPE no disponible: iniciar sesion en Bentley Connect y reintentar.'
        if msg.startswith('E0'):
            return f'{msg}. Un .dat guardado por la GUI puede no abrir con la API (causa no determinada; la documentacion indica que solo abre modelos de su misma version). Leer el .DB con la skill auditing-autopipe-model.'
        return msg
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--config', required=True)
    ap.add_argument('--trazado', required=True)
    ap.add_argument('--tabla', required=True)
    ap.add_argument('--base', required=True, help='modelo base .dat (solo se lee)')
    a = ap.parse_args()
    cfg = inputs.leer_config(a.config)
    stops, avisos = inputs.validar(cfg, inputs.leer_csv(a.trazado), inputs.leer_csv(a.tabla))
    err = probar_api(cfg, a.base)
    for s in stops:
        print('DETENERSE Y PREGUNTAR:', s)
    for s in avisos:
        print('AVISO:', s)
    if err:
        print('API NO DISPONIBLE:', err)
        return 3
    if stops:
        return 2
    print('Preflight OK: entradas coherentes y la API abre el modelo base.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
