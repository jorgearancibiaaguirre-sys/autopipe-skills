"""Carga y validacion de las entradas de la skill building-autopipe-model-api.

Entradas: trazado_general.csv y tabla_tramos.csv (salida de la skill compiling-piping-input-data) y config_proyecto.json.
Sin dependencias externas (solo biblioteca estandar). Lo usan preflight.py, build_model.py y verify_model.py.
"""
import csv
import json
import os

# Version de la DataAPI contra la que se probo la skill. No es una restriccion: solo se informa si difiere.
DATAAPI_DEFAULT = 'C:/Program Files/Bentley/AutoPIPE 2025/DataAPI'
TIPOS_NODO_SOPORTADOS = {'extremo', 'soporte', 'vertice_trazado', 'punto'}
COLS_TRAZADO = ['punto', 'tipo_nodo', 'rama', 'X_m', 'Y_m', 'Z_eje_m', 'progresiva_m']
COLS_TABLA = ['tramo', 'desde_m', 'hasta_m', 'material', 'DN_mm', 'PN', 'fuente', 'estado']
ID_MAX = 8            # AutoPIPE corta pipe_id a 8 caracteres (verificado en la linea base)
TOL_M = 1e-6          # tolerancia al comparar progresivas en metros (el CSV trae mm como maximo)


def leer_csv(ruta):
    """Lee un CSV con separador ';' (utf-8 con o sin BOM). Devuelve lista de dicts."""
    try:
        with open(ruta, encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f, delimiter=';'))
    except OSError as e:
        raise SystemExit(f'No se puede leer {ruta}: {e}')


def leer_config(ruta):
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f'No se puede leer la configuracion {ruta}: {e}')


def num(s):
    """Convierte '12,5' o '12.5' a float; None si es vacio o FALTANTE."""
    s = str(s).strip()
    if s == '' or s.upper().startswith('FALTANTE'):
        return None
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return None      # texto no numerico (p. ej. '250 (trazado) / 315 (memoria)'): el validador lo informa


def clave_clase(t):
    """Clave de clase = 'material|DN|PN' (la misma que usa config_proyecto.json en 'clases')."""
    return f"{t['material'].strip()}|{str(t['DN_mm']).strip()}|{t['PN'].strip()}"


def validar(cfg, nodos, tramos):
    """Devuelve (stops, avisos). Un 'stop' obliga a detenerse y preguntar al usuario; un aviso se informa al final."""
    stops, avisos = [], []
    for c in COLS_TRAZADO:
        if nodos and c not in nodos[0]:
            stops.append(f'trazado_general.csv: falta la columna {c}')
    for c in COLS_TABLA:
        if tramos and c not in tramos[0]:
            stops.append(f'tabla_tramos.csv: falta la columna {c}')
    if stops:
        return stops, avisos
    if len(nodos) < 2:
        stops.append('trazado_general.csv: se necesitan al menos 2 nodos')
    for n in nodos:
        if n['rama'].strip().upper() != 'PRINCIPAL':
            stops.append(f"nodo {n['punto']}: rama {n['rama']} no soportada (solo PRINCIPAL; tees y ramales no estan implementados)")
        if n['tipo_nodo'].strip() not in TIPOS_NODO_SOPORTADOS:
            stops.append(f"nodo {n['punto']}: tipo_nodo '{n['tipo_nodo']}' no soportado ({sorted(TIPOS_NODO_SOPORTADOS)})")
    nombres = [n['punto'] for n in nodos]
    if len(set(nombres)) != len(nombres):
        stops.append('trazado_general.csv: nombres de punto repetidos')
    # tabla de tramos: estado, continuidad, cobertura
    prev_hasta = None
    for t in tramos:
        if not t['estado'].strip().lower().startswith('vigente'):
            stops.append(f"tramo {t['tramo']}: estado '{t['estado']}' (resolver la discrepancia en la compilacion de antecedentes antes de modelar)")
        d, h = num(t['desde_m']), num(t['hasta_m'])
        if d is None or h is None or h <= d:
            stops.append(f"tramo {t['tramo']}: progresivas invalidas ({t['desde_m']}-{t['hasta_m']})")
            continue
        if prev_hasta is not None and abs(d - prev_hasta) > TOL_M:
            stops.append(f"tramo {t['tramo']}: no empalma con el anterior (hasta {prev_hasta} frente a desde {d})")
        prev_hasta = h
        if not t['material'].strip().upper().startswith('HDPE'):
            stops.append(f"tramo {t['tramo']}: material '{t['material']}' no soportado (esta version solo construye HDPE)")
        if num(t['DN_mm']) is None:
            stops.append(f"tramo {t['tramo']}: DN no definido ('{t['DN_mm']}')")
    p0, p1 = num(nodos[0]['progresiva_m']), num(nodos[-1]['progresiva_m'])
    if tramos and p0 is not None and p1 is not None:
        d0, h1 = num(tramos[0]['desde_m']), num(tramos[-1]['hasta_m'])
        if d0 is not None and abs(d0 - p0) > TOL_M or h1 is not None and abs(h1 - p1) > TOL_M:
            stops.append(f'la tabla cubre {d0}-{h1} m y el trazado {p0}-{p1} m')
    # clases y datos de la config
    clases = cfg.get('clases', {})
    for t in tramos:
        k = clave_clase(t)
        c = clases.get(k)
        if c is None:
            stops.append(f"clase '{k}' (tramo {t['tramo']}) no esta en config_proyecto.json > clases: falta OD, espesor, id y presion")
            continue
        for campo in ('id', 'od_mm', 'espesor_mm', 'presion_operacion_MPa'):
            if c.get(campo) in (None, ''):
                stops.append(f"clase '{k}': falta {campo}")
        if len(str(c.get('id', ''))) > ID_MAX:
            stops.append(f"clase '{k}': id '{c.get('id')}' supera {ID_MAX} caracteres")
    ids = [c.get('id') for c in clases.values()]
    if len(set(ids)) != len(ids):
        stops.append('config_proyecto.json: ids de clase repetidos')
    for sec, campos in (('codigo', ('edicion', 'libreria_materiales')),
                        ('material_hdpe', ('densidad_kg_m3', 'modulo_caliente_MPa', 'fluencia_MPa', 'poisson')),
                        ('fluido', ('densidad_kg_m3',)), ('soportes', ('suelo',)), ('codo', ('radio_en_diametros',))):
        for c in campos:
            if cfg.get(sec, {}).get(c) in (None, ''):
                stops.append(f'config_proyecto.json: falta {sec}.{c}')
    for c in ('temperatura_montaje_C', 'reductor_largo_mm', 'casos'):
        if cfg.get(c) in (None, '', []):
            stops.append(f'config_proyecto.json: falta {c}')
    for caso in cfg.get('casos', []):
        for c in ('nombre', 'T_C', 'presion', 'contenido'):
            if c not in caso:
                stops.append(f"caso {caso.get('nombre', '?')}: falta {c}")
    # datos opcionales: si faltan, NO se inventan; se informan
    mat = cfg.get('material_hdpe', {})
    if mat.get('coef_expansion_1e6_por_C') in (None, ''):
        avisos.append('FALTANTE material_hdpe.coef_expansion_1e6_por_C: la expansion termica queda en 0 (el caso termico no sera representativo)')
    if mat.get('modulo_frio_MPa') in (None, ''):
        avisos.append('FALTANTE material_hdpe.modulo_frio_MPa: el modulo en frio queda en 0')
    return stops, avisos
