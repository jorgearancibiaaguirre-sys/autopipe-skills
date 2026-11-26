"""Carga y validacion de las entradas de la skill building-autopipe-model-api.

Entradas: trazado_general.csv y tabla_tramos.csv (salida de la skill compiling-piping-input-data) y config_proyecto.json.
Sin dependencias externas (solo biblioteca estandar). Lo usan preflight.py, build_model.py y verify_model.py.
"""
import csv
import json
import os

# Version de la DataAPI contra la que se probo la skill. No es una restriccion: solo se informa si difiere.
DATAAPI_DEFAULT = 'C:/Program Files/Bentley/AutoPIPE 2025/DataAPI'
PRINCIPAL = 'PRINCIPAL'
# 'tee': nace una derivacion; 'soporte_viga': guia conectada a una viga vertical anclada al suelo (en vez del apoyo de suelo)
TIPOS_NODO_SOPORTADOS = {'extremo', 'soporte', 'vertice_trazado', 'punto', 'tee', 'soporte_viga'}
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
        with open(ruta, encoding='utf-8-sig') as f:      # utf-8-sig: tambien acepta JSON guardado con BOM (editores de Windows)
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


def rama_nodo(n):
    r = (n.get('rama') or '').strip()
    return PRINCIPAL if r == '' or r.upper() == PRINCIPAL else r


def rama_tramo(t):
    """Rama de un tramo: columna opcional 'rama' de tabla_tramos.csv; vacia o ausente = PRINCIPAL."""
    r = (t.get('rama') or '').strip()
    return PRINCIPAL if r == '' or r.upper() == PRINCIPAL else r


def agrupar_ramas(nodos):
    """dict rama -> lista de nodos, en el orden del CSV (la rama PRINCIPAL primero si existe)."""
    out = {}
    for n in nodos:
        out.setdefault(rama_nodo(n), []).append(n)
    if PRINCIPAL in out:
        out = {PRINCIPAL: out[PRINCIPAL], **{k: v for k, v in out.items() if k != PRINCIPAL}}
    return out


def es_hdpe(clave):
    """True si la clase es HDPE (la clave empieza con 'HDPE'); cualquier otra se trata como material de la libreria de AutoPIPE."""
    return clave.strip().upper().startswith('HDPE')


# Correspondencia estandar DN (ISO 6708) -> NPS (pulgadas) para tuberia de acero; el usuario puede fijar 'nps_in' en la clase.
DN_A_NPS = {15: 0.5, 20: 0.75, 25: 1.0, 32: 1.25, 40: 1.5, 50: 2.0, 65: 2.5, 80: 3.0, 100: 4.0, 125: 5.0, 150: 6.0, 200: 8.0, 250: 10.0,
            300: 12.0, 350: 14.0, 400: 16.0, 450: 18.0, 500: 20.0, 550: 22.0, 600: 24.0, 650: 26.0, 700: 28.0, 750: 30.0, 800: 32.0,
            850: 34.0, 900: 36.0, 1000: 40.0, 1050: 42.0, 1100: 44.0, 1200: 48.0}
CAMPOS_PROP = ('densidad_kg_m3', 'modulo_caliente_MPa', 'fluencia_MPa', 'poisson')


def nps_clase(c, dn_mm):
    """NPS en pulgadas: 'nps_in' de la clase o la correspondencia estandar con el DN; None si no se puede determinar."""
    if c.get('nps_in') not in (None, ''):
        return float(c['nps_in'])
    return DN_A_NPS.get(int(round(dn_mm))) if dn_mm is not None else None


def props_clase(cfg, clave, c):
    """Propiedades de material que la skill SOBRESCRIBE en el modelo: HDPE -> cfg['material_hdpe']; otro material -> c['propiedades']
    si el usuario las dio; si no, None (AutoPIPE las carga de su libreria segun material y schedule)."""
    if es_hdpe(clave):
        return cfg.get('material_hdpe', {})
    return c.get('propiedades') or None


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
        if n['tipo_nodo'].strip() not in TIPOS_NODO_SOPORTADOS:
            stops.append(f"nodo {n['punto']}: tipo_nodo '{n['tipo_nodo']}' no soportado ({sorted(TIPOS_NODO_SOPORTADOS)})")
    nombres = [n['punto'] for n in nodos]
    ramas = agrupar_ramas(nodos)
    ref_rama = {}           # punto de tee -> rama donde esta definida (para validar el arranque y el cierre de las otras ramas)
    if PRINCIPAL not in ramas:
        stops.append("trazado_general.csv: no hay nodos de la rama PRINCIPAL")
    # un punto puede repetirse solo como arranque o cierre de una rama (mismo nombre que su tee); fuera de eso, nombres unicos
    for rama, rn in ramas.items():
        for j, n in enumerate(rn):
            if n['tipo_nodo'].strip() == 'tee':
                ref_rama.setdefault(n['punto'], (rama, n))
    cuenta = {}
    for rama, rn in ramas.items():
        for j, n in enumerate(rn):
            es_ref = rama != PRINCIPAL and n['punto'] in ref_rama and ref_rama[n['punto']][0] != rama and j in (0, len(rn) - 1)
            if not es_ref:
                cuenta[n['punto']] = cuenta.get(n['punto'], 0) + 1
    if any(v > 1 for v in cuenta.values()):
        stops.append('trazado_general.csv: nombres de punto repetidos: ' + ', '.join(k for k, v in cuenta.items() if v > 1))
    for rama, rn in ramas.items():
        if len(rn) < 2:
            stops.append(f'rama {rama}: se necesitan al menos 2 nodos')
            continue
        if rama == PRINCIPAL:
            continue
        a = rn[0]
        if a['punto'] not in ref_rama or ref_rama[a['punto']][0] == rama:
            stops.append(f"rama {rama}: su primer nodo '{a['punto']}' debe ser un nodo tipo 'tee' de otra rama definida antes en el CSV")
        else:
            t0 = ref_rama[a['punto']][1]
            if any(abs((num(a[c]) or 0) - (num(t0[c]) or 0)) > 1e-3 for c in ('X_m', 'Y_m', 'Z_eje_m')):
                stops.append(f"rama {rama}: su primer nodo '{a['punto']}' no coincide en coordenadas con la tee de la rama {ref_rama[a['punto']][0]}")
            elif list(ramas).index(ref_rama[a['punto']][0]) > list(ramas).index(rama):
                stops.append(f"rama {rama}: la tee '{a['punto']}' esta en la rama {ref_rama[a['punto']][0]}, que aparece despues en el CSV; ordenar las ramas")
        z = rn[-1]
        if rama != PRINCIPAL and z['punto'] in ref_rama and ref_rama[z['punto']][0] != rama and z['tipo_nodo'].strip() != 'tee':
            stops.append(f"rama {rama}: su ultimo nodo '{z['punto']}' repite una tee de otra rama (cierre de lazo) pero no es tipo 'tee'")
        for n in rn[1:-1] if rama != PRINCIPAL else rn:
            if n['tipo_nodo'].strip() == 'tee' and rama != PRINCIPAL and n['punto'] in ref_rama and ref_rama[n['punto']][0] != rama:
                stops.append(f"rama {rama}: la tee '{n['punto']}' ya existe en la rama {ref_rama[n['punto']][0]}")
    # tabla de tramos: estado, continuidad y cobertura, por rama (columna opcional 'rama'; vacia = PRINCIPAL)
    tabla_r = {}
    for t in tramos:
        tabla_r.setdefault(rama_tramo(t), []).append(t)
    for rama in ramas:
        if rama not in tabla_r:
            stops.append(f"tabla_tramos.csv: la rama {rama} no tiene tramos (columna 'rama')")
    for rama, trs in tabla_r.items():
        if rama not in ramas:
            stops.append(f"tabla_tramos.csv: tramos de la rama {rama}, que no existe en el trazado")
        prev_hasta = None
        for t in trs:
            if not t['estado'].strip().lower().startswith('vigente'):
                stops.append(f"tramo {t['tramo']}: estado '{t['estado']}' (resolver la discrepancia en la compilacion de antecedentes antes de modelar)")
            d, h = num(t['desde_m']), num(t['hasta_m'])
            if d is None or h is None or h <= d:
                stops.append(f"tramo {t['tramo']}: progresivas invalidas ({t['desde_m']}-{t['hasta_m']})")
                continue
            if prev_hasta is not None and abs(d - prev_hasta) > TOL_M:
                stops.append(f"tramo {t['tramo']}: no empalma con el anterior (hasta {prev_hasta} frente a desde {d})")
            prev_hasta = h
            if num(t['DN_mm']) is None:
                stops.append(f"tramo {t['tramo']}: DN no definido ('{t['DN_mm']}')")
        if rama in ramas and trs:
            p0, p1 = num(ramas[rama][0]['progresiva_m']), num(ramas[rama][-1]['progresiva_m'])
            d0, h1 = num(trs[0]['desde_m']), num(trs[-1]['hasta_m'])
            if p0 is not None and p1 is not None and (d0 is not None and abs(d0 - p0) > TOL_M or h1 is not None and abs(h1 - p1) > TOL_M):
                stops.append(f'rama {rama}: la tabla cubre {d0}-{h1} m y el trazado {p0}-{p1} m')
    # vigas de soporte
    if any(n['tipo_nodo'].strip() == 'soporte_viga' for n in nodos):
        v = cfg.get('soportes', {}).get('viga', {})
        for sec, campos in (('seccion', ('nombre', 'profundidad_mm', 'ancho_mm', 'ala_mm', 'alma_mm')),
                            ('material', ('nombre', 'E_MPa', 'poisson', 'densidad_kg_m3', 'dilatacion_1e6_por_C', 'fluencia_MPa', 'rotura_MPa')),
                            ('guia', ('roce', 'gap_lateral_mm', 'gap_arriba_mm', 'gap_abajo_mm'))):
            for c in campos:
                if (v.get(sec) or {}).get(c) in (None, ''):
                    stops.append(f'config_proyecto.json: hay nodos soporte_viga y falta soportes.viga.{sec}.{c} (el material de la viga es obligatorio: sin el la API guarda un .dat que no se reabre)')
        for c in ('altura_viga_mm', 'suelo_a_eje_mm'):
            if v.get(c) in (None, ''):
                stops.append(f'config_proyecto.json: hay nodos soporte_viga y falta soportes.viga.{c}')
        if not v.get('beta_offset_deg') and v.get('beta_offset_deg') != 0:
            avisos.append('soportes.viga.beta_offset_deg no indicado: se usa 90 grados (alma colineal con el eje de la tuberia, supuesto sobre la convencion de ejes locales); verificar en vista solida')
    # clases y datos de la config
    clases = cfg.get('clases', {})
    for t in tramos:
        k = clave_clase(t)
        c = clases.get(k)
        if c is None:
            stops.append(f"clase '{k}' (tramo {t['tramo']}) no esta en config_proyecto.json > clases: falta OD, espesor, id y presion")
            continue
        # HDPE: OD y espesor obligatorios. Otro material: opcionales; sin ellos AutoPIPE asigna OD y espesor desde su base segun NPS y schedule
        campos = ('id', 'presion_operacion_MPa') if not es_hdpe(k) else ('id', 'od_mm', 'espesor_mm', 'presion_operacion_MPa')
        for campo in campos:
            if c.get(campo) in (None, ''):
                stops.append(f"clase '{k}': falta {campo}")
        if not es_hdpe(k):
            hay = [c.get(x) not in (None, '') for x in ('od_mm', 'espesor_mm')]
            if any(hay) and not all(hay):
                stops.append(f"clase '{k}': od_mm y espesor_mm van juntos (ambos o ninguno)")
            if not any(hay):
                avisos.append(f"clase '{k}': sin od_mm/espesor_mm: AutoPIPE asigna OD y espesor desde su base segun NPS y schedule; "
                              "la skill no los escribe ni los verifica (revisar en Pipe Properties)")
        if len(str(c.get('id', ''))) > ID_MAX:
            stops.append(f"clase '{k}': id '{c.get('id')}' supera {ID_MAX} caracteres")
        if not es_hdpe(k):
            # material de la libreria de AutoPIPE: el usuario indica material y schedule; OD y espesor los da el usuario (la API no los completa)
            for campo in ('material_id', 'schedule'):
                if c.get(campo) in (None, ''):
                    stops.append(f"clase '{k}': material distinto de HDPE requiere {campo} (id de AutoPIPE, p. ej. A53-B, y schedule, p. ej. STD o 40)")
            if nps_clase(c, num(t['DN_mm'])) is None:
                stops.append(f"clase '{k}': DN {t['DN_mm']} sin NPS estandar conocido: indicar 'nps_in' en la clase")
            if str(c.get('material_id', '')).strip().upper() == 'NS':
                falta = [x for x in CAMPOS_PROP if (c.get('propiedades') or {}).get(x) in (None, '')]
                if falta:
                    stops.append(f"clase '{k}': material NS (no estandar) requiere propiedades.{falta}")
            if len(str(c.get('material_id', ''))) > 8 and c.get('material_id'):
                avisos.append(f"clase '{k}': material_id '{c.get('material_id')}' de mas de 8 caracteres: verificar que exista en la libreria")
            if props_clase(cfg, k, c) is None and str(c.get('material_id', '')).strip().upper() != 'NS':
                avisos.append(f"clase '{k}': propiedades de '{c.get('material_id')}' ({c.get('schedule')}) tomadas de la libreria de AutoPIPE; la skill no las sobrescribe ni las verifica (comprobar en Pipe Properties)")
    ids = [c.get('id') for c in clases.values()]
    if len(set(ids)) != len(ids):
        stops.append('config_proyecto.json: ids de clase repetidos')
    hay_hdpe = any(es_hdpe(clave_clase(t)) for t in tramos)
    secciones = [('codigo', ('edicion', 'libreria_materiales')), ('fluido', ('densidad_kg_m3',)), ('soportes', ('suelo',)), ('codo', ('radio_en_diametros',))]
    if hay_hdpe:
        secciones.append(('material_hdpe', CAMPOS_PROP))
    for sec, campos in secciones:
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
    if hay_hdpe and mat.get('coef_expansion_1e6_por_C') in (None, ''):
        avisos.append('FALTANTE material_hdpe.coef_expansion_1e6_por_C: la expansion termica queda en 0 (el caso termico no sera representativo)')
    if hay_hdpe and mat.get('modulo_frio_MPa') in (None, ''):
        avisos.append('FALTANTE material_hdpe.modulo_frio_MPa: el modulo en frio queda en 0')
    for k in {clave_clase(t) for t in tramos}:
        c = clases.get(k, {})
        p = props_clase(cfg, k, c) if c else None
        if not es_hdpe(k) and p:
            for campo, que in (('coef_expansion_1e6_por_C', 'expansion termica'), ('modulo_frio_MPa', 'modulo en frio')):
                if p.get(campo) in (None, ''):
                    avisos.append(f"FALTANTE clase '{k}' propiedades.{campo}: {que} queda en 0")
    # un cambio de material en un mismo DN no inserta reductor: se informa
    for trs in tabla_r.values():
        for a_, b_ in zip(trs, trs[1:]):
            if es_hdpe(clave_clase(a_)) != es_hdpe(clave_clase(b_)):
                avisos.append(f"cambio HDPE/otro material entre {a_['tramo']} y {b_['tramo']} (progresiva {a_['hasta_m']}): la skill no modela la union (brida, electrofusion, adaptador); definirla en la GUI")
    for rama, rn in ramas.items():
        if rama != PRINCIPAL and rn and rn[-1]['tipo_nodo'].strip() != 'tee':
            avisos.append(f"rama {rama}: termina en un extremo libre ('{rn[-1]['punto']}'); sin anclaje salvo que se liste en soportes.anclajes_rigidos_en")
    return stops, list(dict.fromkeys(avisos))
