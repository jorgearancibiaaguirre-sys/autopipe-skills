"""Verifica por LECTURA un .dat generado contra config_proyecto.json + tabla_tramos.csv + trazado_general.csv.

Uso: python verify_model.py --config C --tabla R --trazado T --modelo SALIDA.dat
Codigo de salida: 0 todo PASS, 1 hay FAIL, 3 no se pudo abrir el modelo.
Todo valor se lee del archivo guardado (no del script que lo escribio). Requisitos: Python 3.12, AutoPIPE con licencia.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inputs  # noqa: E402

IN, MPA = 25.4, 0.00689476     # in -> mm ; psi -> MPa
TOL = 0.02                     # 2 %: cubre el redondeo de unidades internas de la API
RES = {}


def chk(k, ok, det=''):
    RES[k] = ('PASS' if ok else 'FAIL') + (f' ({det})' if det else '')


def near(a, b, t=TOL):
    return abs(a - b) <= t * max(abs(b), 1e-9)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ('config', 'tabla', 'trazado', 'modelo'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    cfg = inputs.leer_config(a.config)
    tramos = inputs.leer_csv(a.tabla)
    sys.path.insert(0, cfg.get('ruta_dataapi', inputs.DATAAPI_DEFAULT))
    import autopipe
    try:
        m = autopipe.open_dat(os.path.abspath(a.modelo))
    except RuntimeError as e:
        print(f'FAIL opens: {e}')
        return 3
    chk('opens', True)
    chk('codigo', str(m.piping_code_year) == str(cfg['codigo']['edicion']) and m.material_library == cfg['codigo']['libreria_materiales'], f'{m.piping_code_year} {m.material_library}')
    chk('ambiente', near(m.ambient_temperature, cfg['temperatura_montaje_C'] * 9 / 5 + 32), f'{m.ambient_temperature:.1f} F')
    props = {p.pipe_id: p for p in m.all_pipe_properties}
    clases = {inputs.clave_clase(t) for t in tramos}
    for k in sorted(clases):
        c = cfg['clases'][k]
        p = props.get(c['id'])
        if c.get('od_mm') in (None, ''):     # material de libreria sin dimensiones: las asigna AutoPIPE en la GUI y la API las lee como 0
            chk(f"pipe_property {c['id']}", p is not None, 'existe; OD y espesor NO verificados (los asigna AutoPIPE segun NPS y schedule)' if p else 'no existe')
        else:
            ok = p is not None and near(p.outside_diameter * IN, c['od_mm'], 0.01) and near(p.wall_thickness * IN, c['espesor_mm'], 0.03)
            chk(f"pipe_property {c['id']}", ok, f'{p.outside_diameter * IN:.1f} x {p.wall_thickness * IN:.2f} mm' if p else 'no existe')
        if p is not None:
            chk(f"pipe_property {c['id']}: densidad del contenido", near(p.content_weight, cfg['fluido']['densidad_kg_m3'] * 0.062427961), f'{p.content_weight:.2f} lb/ft3 (el peso por longitud lo calcula AutoPIPE)')
            if inputs.es_hdpe(k):
                chk(f"pipe_property {c['id']}: material NS", p.material_id == 'NS', f'{p.material_id} (el schedule NS no se relee: la API lo devuelve vacio)')
            else:
                chk(f"pipe_property {c['id']}: material y schedule", p.material_id == str(c['material_id']) and p.schedule == str(c['schedule']), f'{p.material_id} / {p.schedule}')
    nodos = inputs.leer_csv(a.trazado)
    n_dn = 0
    for rama in {inputs.rama_tramo(t) for t in tramos}:
        trs = [t for t in tramos if inputs.rama_tramo(t) == rama]
        n_dn += sum(1 for t0, t1 in zip(trs, trs[1:]) if t0['DN_mm'] != t1['DN_mm'])
    nred = sum(1 for c in m.all_components if str(c.type).split('.')[-1] == 'REDUCER')
    chk('reductores = cambios de DN', nred == n_dn, f'{nred} de {n_dn}')
    # una tee se construye una vez: en su rama de origen; el primer y el ultimo nodo de una derivacion solo la referencian
    n_tee = 0
    for rama, rn in inputs.agrupar_ramas(nodos).items():
        for j, n in enumerate(rn):
            if n['tipo_nodo'].strip() == 'tee' and (rama == inputs.PRINCIPAL or 0 < j < len(rn) - 1):
                n_tee += 1
    nte = sum(1 for c in m.all_components if str(c.type).split('.')[-1] == 'TEE')
    chk('tees = nodos tee construidos', nte == n_tee, f'{nte} de {n_tee}')
    n_viga = sum(1 for n in nodos if n['tipo_nodo'].strip() == 'soporte_viga')
    vigas = list(m.all_beams) if hasattr(m, 'all_beams') else []
    chk('vigas = nodos soporte_viga', len(vigas) == n_viga, f'{len(vigas)} de {n_viga}')
    if n_viga:
        sv = cfg['soportes']['viga']
        sec = {s_.name: s_ for s_ in m.all_sections}.get(sv['seccion']['nombre'])
        chk('seccion de viga', sec is not None and near(sec.depth * IN, sv['seccion']['profundidad_mm'], 0.01), f'{sec.depth * IN:.1f} mm' if sec else 'no existe')
        chk('vigas: seccion y beta', all(b.section.name == sv['seccion']['nombre'] for b in vigas), f'beta {sorted({round(b.beta_angle, 1) for b in vigas})} grados (el valor se lee del archivo; la orientacion real se revisa en vista solida)')

    # propiedades sobrescritas por clase (HDPE: material_hdpe; otro material: solo si la clase trae 'propiedades'); por id de pipe property
    esperado = {cfg['clases'][k]['id']: inputs.props_clase(cfg, k, cfg['clases'][k]) for k in clases}
    casos = cfg['casos']
    pr_leidas = [set() for _ in casos]
    malos = {'hot': 0, 'yield': 0, 'temp': 0}
    npts = nverif = nsin_clase = 0
    for q in (p for p in m.all_points if p.name):
        npts += 1
        try:
            mat = esperado.get(q.pipe_property.pipe_id, 'desconocida')
        except Exception:
            mat = 'desconocida'
        if mat == 'desconocida':
            nsin_clase += 1
        for ci, caso in enumerate(casos):
            L = q.pt_loads[ci]
            malos['temp'] += not near(L.temperature, caso['T_C'] * 9 / 5 + 32, 0.01)
            pr_leidas[ci].add(round(L.pressure * MPA, 3))
            if mat and mat != 'desconocida':
                nverif += 1
                malos['hot'] += not near(L.hot_modulus, mat['modulo_caliente_MPa'] / MPA)
                malos['yield'] += not near(L.yield_stress, mat['fluencia_MPa'] / MPA)
    chk('puntos con nombre', npts >= 2, str(npts))
    for k, lbl in (('hot', 'modulo caliente (puntos con propiedades sobrescritas)'), ('yield', 'fluencia (idem, incluido el caso 1)'), ('temp', 'temperaturas por caso')):
        chk(lbl, malos[k] == 0, f'{malos[k]} lecturas fuera de tolerancia')
    if nsin_clase:
        print(f'AVISO: {nsin_clase} puntos sin pipe property legible: no se verifico su modulo ni su fluencia')
    if nverif == 0:
        print('AVISO: ningun punto con propiedades sobrescritas (material de libreria): modulo, fluencia y expansion NO verificados por la skill')
    for ci, caso in enumerate(casos):
        if caso['presion'] == 'clase':
            esperadas = {round(cfg['clases'][k]['presion_operacion_MPa'], 3) for k in clases}
        else:
            esperadas = {round(float(caso['presion']), 3)}
        ok = all(any(near(x, e, 0.03) or abs(x - e) < 1e-3 for x in pr_leidas[ci]) for e in esperadas)
        chk(f"presiones caso {ci + 1} ({caso['nombre']})", ok, f'leidas {sorted(pr_leidas[ci])} MPa, esperadas {sorted(esperadas)}')

    sup = list(m.all_supports)
    tipos = {}
    for s in sup:
        t = str(s.type).split('.')[-1]
        tipos[t] = tipos.get(t, 0) + 1
    # las guias conectadas a una viga (connected) son las de los nodos soporte_viga; las demas son las de suelo, pareadas con un Linestop
    def conectada(s):
        """En la API `connected` nunca es None: un soporte sin conexion devuelve un Handle invalido que da E2006 al pedir su nombre."""
        try:
            return bool(s.connected.name)
        except Exception:
            return False
    gv = [s for s in sup if 'GUIDE' in str(s.type) and conectada(s)]
    gs = [s for s in sup if 'GUIDE' in str(s.type) and not conectada(s)]
    sc = cfg['soportes']['suelo']
    chk('Linestop y Guide de suelo pareados', tipos.get('LINE_STOP', 0) == len(gs) > 0, f'{tipos}; guias de viga {len(gv)}')
    chk('guias conectadas a viga = vigas', len(gv) == n_viga, f'{len(gv)} de {n_viga}')
    if gs:
        chk('Guide: roce', all(near(s.friction, sc['roce']) for s in gs))
        chk('Guide: gap arriba', all(near(s.gap_up * IN, sc['gap_arriba_mm'], 0.01) for s in gs))
        chk('Guide: gap abajo', all(abs(s.gap_down * IN - sc.get('gap_abajo_mm', 0)) < 0.01 for s in gs))
        chk('Guide: Weightless', all('WEIGHTLESS' in str(s.gap_setting) for s in gs))
    if gv:
        g = cfg['soportes']['viga']['guia']
        def gaps_ok(s):
            lat = abs(s.gap_left * IN - g['gap_lateral_mm']) < 0.01 + 0.01 * g['gap_lateral_mm']
            return lat and near(s.gap_up * IN, g['gap_arriba_mm'], 0.01) and abs(s.gap_down * IN - g['gap_abajo_mm']) < 0.01
        chk('Guide de viga: gaps lateral/arriba/abajo', all(gaps_ok(s) for s in gv))
        mus = {round(s.friction, 3) for s in gv}
        esp = {round(float(g['roce']), 3), round(float(g.get('roce_no_hdpe', g['roce'])), 3)}
        chk('Guide de viga: roce', mus <= esp, f'leidos {sorted(mus)}, esperados {sorted(esp)}')
    chk('anclajes rigidos', sum(1 for a_ in m.all_anchors if a_.rigid) >= 2, f'{len(m.all_anchors)} anclajes')

    ls = list(m.all_load_sets)
    an = cfg.get('analisis', {})
    chk('analysis sets', len(ls) == len(casos), f'{len(ls)}')
    for l, caso in zip(ls, casos):
        # semantica de la API: pipe_contents False = el set INCLUYE el peso del contenido
        chk(f"{caso['nombre']}: contenido", l.pipe_contents == (not caso['contenido']), f'pipe_contents={l.pipe_contents} (False = incluido)')
        chk(f"{caso['nombre']}: friction scale factor", near(l.friction_factor, an.get('friction_scale_factor', 1.0)), str(l.friction_factor))
        if caso['contenido']:
            chk(f"{caso['nombre']}: fluid density factor", near(l.fluid_density_factor, an.get('fluid_density_factor_lleno', 1.0)), str(l.fluid_density_factor))
    g = cfg.get('sismo_estatico_g', {})
    esp = sorted(round(v, 2) for v in g.values() if v)
    leid = sorted(round(max(abs(e.direction.x), abs(e.direction.y), abs(e.direction.z)), 2) for e in m.all_static_earthquake_loads)
    chk('sismo estatico', esp == leid, f'{leid} g')

    for k, v in RES.items():
        print(f'{k:48s} {v}')
    nf = sum(v.startswith('FAIL') for v in RES.values())
    print(f'RESUMEN: {len(RES) - nf} PASS / {len(RES)}')
    return 1 if nf else 0


if __name__ == '__main__':
    sys.exit(main())
