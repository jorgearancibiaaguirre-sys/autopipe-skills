"""Valida los entregables de compiling-piping-input-data. No modifica nada.

Uso: python validar_entregables.py --carpeta contexto [--claude CLAUDE.md]
Revisa: columnas y continuidad de tabla_tramos.csv, columnas y progresivas de trazado_general.csv, las 6 secciones de
resumen_antecedentes.md, coherencia entre discrepancias, FALTANTES y el resumen, y que CLAUDE.md cite los archivos.
Codigo de salida: 0 sin errores, 1 con errores. Solo biblioteca estandar (Python 3.12).
"""
import argparse
import csv
import os
import re
import sys

COLS_TRAZADO = ['punto', 'tipo_nodo', 'rama', 'X_m', 'Y_m', 'Z_eje_m', 'progresiva_m']
COLS_TABLA = ['tramo', 'desde_m', 'hasta_m', 'material', 'DN_mm', 'PN', 'fuente', 'estado']
SECCIONES = ['1. Entendimiento', '2. Tabla de tramos', '3. Discrepancias', '4. Faltantes', '5. Supuestos', '6. Datos generales']
TOL_M = 1e-6          # tolerancia al comparar progresivas
ESTADOS_OK = ('vigente', 'discrepancia abierta')


def num(s):
    try:
        return float(str(s).strip().replace(',', '.'))
    except ValueError:
        return None


def leer(ruta):
    with open(ruta, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--carpeta', required=True)
    ap.add_argument('--claude', help='ruta del CLAUDE.md del proyecto (por defecto, el de la carpeta superior)')
    a = ap.parse_args()
    err, av = [], []
    carp = a.carpeta
    claude = a.claude or os.path.join(os.path.dirname(os.path.abspath(carp)), 'CLAUDE.md')

    tabla = trazado = None
    for nombre, cols in (('tabla_tramos.csv', COLS_TABLA), ('trazado_general.csv', COLS_TRAZADO)):
        ruta = os.path.join(carp, nombre)
        if not os.path.exists(ruta):
            err.append(f'falta {nombre}')
            continue
        filas = leer(ruta)
        faltan = [c for c in cols if not filas or c not in filas[0]]
        if faltan:
            err.append(f'{nombre}: faltan columnas {faltan}')
            continue
        if nombre.startswith('tabla'):
            tabla = filas
        else:
            trazado = filas

    n_disc = n_falt = 0
    if tabla is not None:
        prev = None
        for t in tabla:
            d, h = num(t['desde_m']), num(t['hasta_m'])
            if d is None or h is None or h <= d:
                err.append(f"tabla_tramos.csv: tramo {t['tramo']} con progresivas invalidas")
                continue
            if prev is not None and abs(d - prev) > TOL_M:
                err.append(f"tabla_tramos.csv: el tramo {t['tramo']} no empalma con el anterior ({prev} frente a {d})")
            prev = h
            if t['estado'].strip().lower() not in ESTADOS_OK:
                err.append(f"tabla_tramos.csv: estado '{t['estado']}' invalido en {t['tramo']} (use vigente o DISCREPANCIA abierta)")
            if t['estado'].strip().lower() == 'discrepancia abierta':
                n_disc += 1
            if not t['fuente'].strip():
                err.append(f"tabla_tramos.csv: el tramo {t['tramo']} no tiene fuente")
            n_falt += sum('FALTANTE' in str(v) for v in t.values())
            if t['estado'].strip().lower() == 'vigente' and num(t['DN_mm']) is None:
                err.append(f"tabla_tramos.csv: tramo vigente {t['tramo']} con DN no numerico ('{t['DN_mm']}')")
    if trazado is not None:
        pr = [num(n['progresiva_m']) for n in trazado]
        if any(p is None for p in pr) or any(b < a_ for a_, b in zip(pr, pr[1:])):
            err.append('trazado_general.csv: progresivas no numericas o no crecientes')
        nombres = [n['punto'] for n in trazado]
        if len(set(nombres)) != len(nombres):
            err.append('trazado_general.csv: nombres de punto repetidos')
        if tabla is not None and pr and None not in pr:
            d0, h1 = num(tabla[0]['desde_m']), num(tabla[-1]['hasta_m'])
            if d0 is not None and h1 is not None and (abs(d0 - pr[0]) > TOL_M or abs(h1 - pr[-1]) > TOL_M):
                err.append(f'la tabla cubre {d0}-{h1} m y el trazado {pr[0]}-{pr[-1]} m')

    ruta_res = os.path.join(carp, 'resumen_antecedentes.md')
    if not os.path.exists(ruta_res):
        err.append('falta resumen_antecedentes.md')
    else:
        txt = open(ruta_res, encoding='utf-8').read()
        for s in SECCIONES:
            if not re.search(r'^##\s*' + re.escape(s), txt, re.M):
                err.append(f"resumen_antecedentes.md: falta la seccion '## {s}'")
        sec3 = re.search(r'^##\s*3\. Discrepancias(.*?)(?=^##\s|\Z)', txt, re.M | re.S)
        if n_disc and (not sec3 or len(sec3.group(1).strip()) < 20 or 'ninguna' in sec3.group(1).lower()[:60]):
            err.append('hay tramos con DISCREPANCIA abierta pero la seccion 3 no las describe')
        if n_falt and 'FALTANTE' not in txt:
            err.append('la tabla tiene FALTANTE pero el resumen no los lista')

    if not os.path.exists(claude):
        err.append(f'falta {claude}')
    else:
        c = open(claude, encoding='utf-8').read()
        for nombre in ('tabla_tramos.csv', 'trazado_general.csv', 'resumen_antecedentes.md'):
            if nombre not in c:
                err.append(f'{claude} no cita {nombre}')
    if n_disc:
        av.append(f'{n_disc} tramo(s) con DISCREPANCIA abierta: building-autopipe-model-api no construira hasta resolverlas')
    for m in err:
        print('ERROR:', m)
    for m in av:
        print('AVISO:', m)
    print(f'RESUMEN: {len(err)} errores, {len(av)} avisos, {n_falt} FALTANTE en la tabla')
    return 1 if err else 0


if __name__ == '__main__':
    sys.exit(main())
