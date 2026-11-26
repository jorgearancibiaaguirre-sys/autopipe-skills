"""Construye un modelo AutoPIPE (.dat) con la Python DataAPI a partir de trazado_general.csv, tabla_tramos.csv y config_proyecto.json.

Uso: python build_model.py --config C --trazado T --tabla R --base BASE.dat --out SALIDA.dat
- Solo lee BASE.dat (trabaja sobre una copia) y se niega a escribir sobre un archivo existente.
- Se detiene (codigo 2) ante cualquier condicion de inputs.validar: clase sin datos, discrepancia abierta, rama no soportada, material no HDPE sin material_id/schedule.
- Escribe SALIDA.dat y SALIDA.informe.md (supuestos, FALTANTES, sustituciones) y verifica al final con verify_model.py.
Requisitos: Python 3.12, AutoPIPE con licencia, misma version del modelo base y de la DataAPI.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import inputs  # noqa: E402

IN = 1 / 25.4               # mm -> in (la API usa pulgadas, lb, psi y F)
MPA = 145.0377377           # MPa -> psi
KGM3 = 3.6127292e-5         # kg/m3 -> lb/in3
IN100FT = 1200.0            # deformacion unitaria -> in/100 ft (100 ft = 1200 in)
LOG = []


def log(s):
    LOG.append(s)
    print(s)


def fahr(c):
    return c * 9 / 5 + 32


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ('config', 'trazado', 'tabla', 'base', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    if os.path.exists(a.out):
        raise SystemExit(f'{a.out} ya existe: esta skill nunca sobrescribe. Elegir otro nombre.')
    cfg = inputs.leer_config(a.config)
    nodos = inputs.leer_csv(a.trazado)
    tramos = inputs.leer_csv(a.tabla)
    stops, avisos = inputs.validar(cfg, nodos, tramos)
    stops += cambios_en_nodo(nodos, tramos)
    if stops:
        for s in stops:
            print('DETENERSE Y PREGUNTAR:', s)
        return 2
    sys.path.insert(0, cfg.get('ruta_dataapi', inputs.DATAAPI_DEFAULT))
    global autopipe
    import autopipe
    from autopipe.enum import SupportType, GapSetting, LoadCase, SeismicCode, OccasionalLoadType
    globals().update(SupportType=SupportType, GapSetting=GapSetting, LoadCase=LoadCase, SeismicCode=SeismicCode, OccasionalLoadType=OccasionalLoadType)

    tmp = tempfile.mkdtemp(prefix='ap_build_')
    base = os.path.join(tmp, 'base.dat')
    shutil.copyfile(a.base, base)
    try:
        m = autopipe.open_dat(base)
    except RuntimeError as e:
        raise SystemExit(f'No se pudo abrir el modelo base: {e} (E4 = licencia; E0 = modelo de otra version)')

    # --- modelo
    m.use_hdpe = any(inputs.es_hdpe(inputs.clave_clase(t)) for t in tramos)
    m.piping_code_year = str(cfg['codigo']['edicion'])
    m.material_library = cfg['codigo']['libreria_materiales']
    Tm = float(cfg['temperatura_montaje_C'])
    m.ambient_temperature = fahr(Tm)
    casos = cfg['casos']
    m.pt_cases = len(casos)
    if cfg.get('proyecto'):
        m.project_id = cfg['proyecto']

    # --- pipe properties, una por clase usada en la tabla
    #   HDPE: material NS, schedule NS y propiedades de cfg['material_hdpe'] sobrescritas.
    #   Otro material: material_id y schedule del usuario; AutoPIPE carga las propiedades de su libreria (no se sobrescriben salvo 'propiedades' de la clase).
    PP, CL, MATC = {}, {}, {}
    for t in tramos:
        k = inputs.clave_clase(t)
        if k in PP:
            continue
        c = cfg['clases'][k]
        od, e = float(c['od_mm']), float(c['espesor_mm'])
        mat = inputs.props_clase(cfg, k, c)
        MATC[k] = mat
        if inputs.es_hdpe(k):
            kw = dict(pipe_id=c['id'], nominal_diameter=od * IN, outside_diameter=od * IN, wall_thickness=e * IN, material_id='NS', schedule='NS',
                      material_density=mat['densidad_kg_m3'] * KGM3, poisson_ratio=mat['poisson'], is_hdpe_material=True)
            if c.get('sdr'):
                kw['dimension_ratio'] = str(c['sdr'])
        else:
            kw = dict(pipe_id=c['id'], nominal_diameter=inputs.nps_clase(c, inputs.num(t['DN_mm'])), outside_diameter=od * IN, wall_thickness=e * IN,
                      material_id=str(c['material_id']), schedule=str(c['schedule']))
            if mat:
                kw['material_density'] = mat['densidad_kg_m3'] * KGM3
                kw['poisson_ratio'] = mat['poisson']
        if mat and mat.get('modulo_frio_MPa'):
            kw['cold_modulus'] = mat['modulo_frio_MPa'] * MPA
        pp = m.add_pipe_property(**kw)
        di = od - 2 * e
        pp.content_weight = cfg['fluido']['densidad_kg_m3'] * KGM3 * math.pi * (di * IN) ** 2 / 4   # lb/in: densidad del fluido x area interior
        PP[k], CL[k] = pp, c
        log(f"pipe property {c['id']} <- {k}: OD {od} mm, espesor {e} mm, material {kw['material_id']}, schedule {kw['schedule']}")

    tr = [(num(t['desde_m']), num(t['hasta_m']), inputs.clave_clase(t), float(t['DN_mm'])) for t in tramos]
    DNC = {k: dn for _, _, k, dn in tr}      # DN por clase: el reductor se inserta cuando cambia el DN, no el OD

    def clase_en(p):
        for d, h, k, dn in tr:
            if d - inputs.TOL_M <= p <= h + inputs.TOL_M:
                return k
        return tr[-1][2]

    # --- geometria: nodos, estaciones intermedias (cambios de clase y discretizacion), codos y reductores
    seg = m.add_segment()
    M = 1000 * IN
    P = [(float(n['X_m']) * M, float(n['Y_m']) * M, float(n['Z_eje_m']) * M) for n in nodos]
    PR = [float(num(n['progresiva_m'])) for n in nodos]
    rcodo = float(cfg['codo']['radio_en_diametros'])
    Lred = float(cfg['reductor_largo_mm']) * IN
    disc = cfg.get('discretizacion_m')
    REG = []     # (handle, clase, tipo)  tipo: nodo:<tipo_nodo>, intermedio, bend_near, bend_far, bend_mid, red_near, red_far
    cur = None
    nred = 0
    stn = 0
    for i, n in enumerate(nodos):
        tipo = n['tipo_nodo'].strip()
        if i == 0:
            cur = m.add_run(name=n['punto'], segment=seg, pipe_property=PP[clase_en(PR[0])], position=P[0])
            REG.append((cur, clase_en(PR[0]), 'nodo:' + tipo))
            continue
        p0, p1 = PR[i - 1], PR[i]
        L = p1 - p0
        estac = []
        for d, h, k, dn in tr[1:]:
            if p0 + inputs.TOL_M < d < p1 - inputs.TOL_M:
                estac.append((d, 'limite'))
        if disc:
            for j in range(1, int(math.ceil(L / disc))):
                pj = p0 + j * L / math.ceil(L / disc)
                estac.append((pj, 'intermedio'))
        estac.sort()
        for p, kind in estac:
            f = (p - p0) / L
            pos = tuple(P[i - 1][q] + f * (P[i][q] - P[i - 1][q]) for q in range(3))
            antes, despues = clase_en(p - 2 * inputs.TOL_M), clase_en(p + 2 * inputs.TOL_M)
            dn_a, dn_d = DNC[antes], DNC[despues]
            if kind == 'limite' and dn_a != dn_d:
                nred += 1
                dirv = [(P[i][q] - P[i - 1][q]) / math.dist(P[i - 1], P[i]) for q in range(3)]
                rd = cur.add_reducer(name=f'R{nred:02d}', far_pipe_property=PP[despues])
                rd.near.position = tuple(pos[q] - dirv[q] * Lred / 2 for q in range(3))
                rd.far.position = tuple(pos[q] + dirv[q] * Lred / 2 for q in range(3))
                try:
                    rd.near.pipe_property = PP[antes]
                except Exception as e:
                    log(f'  ! pipe_property en el lado near del reductor R{nred:02d}: {str(e)[:70]}')
                REG += [(rd.near, antes, 'red_near'), (rd.far, despues, 'red_far')]
                cur = rd
                log(f'reductor R{nred:02d} en progresiva {p:g} m: {dn_a} -> {dn_d} mm, largo {cfg["reductor_largo_mm"]} mm')
            else:
                stn += 1
                cur = cur.add_run(name=f'S{stn:03d}', position=pos)
                cur.pipe_property = PP[antes]
                REG.append((cur, antes, 'intermedio' if kind == 'intermedio' else 'nodo:punto'))
        k_seg = clase_en((p0 + p1) / 2)
        od_seg = float(CL[k_seg]['od_mm'])
        es_vertice = tipo == 'vertice_trazado' and 0 < i < len(nodos) - 1
        if es_vertice:
            rc = float(CL[k_seg].get('radio_codo_en_diametros', rcodo))   # por clase si el usuario lo fija (p. ej. codo largo de acero = 1,5)
            b = cur.add_bend(name=n['punto'], position=P[i], radius=rc * od_seg * IN)
            for ph in (b.near, b.mid, b.tangent, b.far):
                try:
                    ph.pipe_property = PP[k_seg]
                except Exception as e:
                    log(f"  ! pipe_property en un punto del codo {n['punto']}: {str(e)[:70]}")
                    break
            if cfg['codo'].get('factor_flexibilidad') and inputs.es_hdpe(k_seg):
                b.flexibility_factor = float(cfg['codo']['factor_flexibilidad'])
            REG += [(b.near, k_seg, 'bend_near'), (b.mid, k_seg, 'bend_mid'), (b.far, k_seg, 'bend_far'), (b.tangent, k_seg, 'bend_vertex')]   # el punto de interseccion de tangentes (nombre del codo) tambien lleva P/T
            cur = b
        else:
            cur = cur.add_run(name=n['punto'], position=P[i])
            cur.pipe_property = PP[k_seg]
            REG.append((cur, k_seg, 'nodo:' + tipo))

    # --- soportes de suelo y anclajes
    s = cfg['soportes']['suelo']
    tipos_ok = set(s.get('aplicar_en_tipos_nodo', ['extremo', 'soporte', 'vertice_trazado']))
    nsup = 0
    for h, k, kind in REG:
        if CL[k].get('sin_soporte_suelo'):
            continue            # clase indicada por el usuario como no apoyada en suelo (p. ej. acero sobre soportes propios)
        aplica = (kind.startswith('nodo:') and kind[5:] in tipos_ok) or kind in ('bend_near', 'bend_far') or (kind == 'intermedio' and s.get('en_intermedios', True))
        if not aplica:
            continue
        try:
            h.add_support(type=SupportType.LINE_STOP)    # sin roce ni gaps: la API rechaza ambos en un Linestop (E19008/E19007)
            h.add_support(type=SupportType.GUIDE, friction=float(s['roce']), gap_left=s.get('gap_lateral_mm', 0) * IN, gap_right=s.get('gap_lateral_mm', 0) * IN,
                          gap_up=s['gap_arriba_mm'] * IN, gap_down=s.get('gap_abajo_mm', 0) * IN, gap_setting=GapSetting.WEIGHTLESS)
            nsup += 1
        except RuntimeError as e:
            log(f'  ! soporte de suelo: {str(e)[:80]}')
    anc = cfg['soportes'].get('anclajes_rigidos_en', 'extremos')
    nombres_anc = [REG[0][0], REG[-1][0]] if anc == 'extremos' else [h for h, k, kd in REG if getattr(h, 'name', '') in anc]
    for h in nombres_anc:
        h.add_anchor(rigid=True)
    log(f'soportes de suelo en {nsup} puntos; anclajes rigidos: {len(nombres_anc)}')

    # --- sismo y P/T
    g = cfg.get('sismo_estatico_g', {})
    nq = 0
    for key, vec in (('E1_X', (1, 0, 0)), ('E2_Y', (0, 1, 0)), ('E3_Z', (0, 0, 1))):
        if g.get(key):
            m.add_static_earthquake_load(seismic_code=SeismicCode.USER, direction=tuple(v * g[key] for v in vec), multiplication_factor=1.0)
            nq += 1
    for h, k, kind in REG:
        mat = MATC[k]
        for ci, caso in enumerate(casos):
            L = h.pt_loads[ci]
            L.temperature = fahr(caso['T_C'])
            pr = CL[k]['presion_operacion_MPa'] if caso['presion'] == 'clase' else float(caso['presion'])
            L.pressure = pr * MPA
            if not mat:
                continue        # material de la libreria: modulo, fluencia y expansion los da AutoPIPE; no se sobrescriben
            L.override_hot_modulus = True
            L.hot_modulus = mat['modulo_caliente_MPa'] * MPA
            L.override_yield_stress = True
            L.yield_stress = mat['fluencia_MPa'] * MPA
            alfa = mat.get('coef_expansion_1e6_por_C')
            if alfa:
                L.override_expansion = True
                L.expansion = alfa * 1e-6 * (caso['T_C'] - Tm) * IN100FT

    # --- load sets (pipe_contents: False = contenido INCLUIDO; ver reference/api_notas.md)
    an = cfg.get('analisis', {})
    EQ = [LoadCase.EARTHQUAKE1, LoadCase.EARTHQUAKE2, LoadCase.EARTHQUAKE3][:nq]
    for i, caso in enumerate(casos, start=1):
        cases = {LoadCase.GRAVITY, getattr(LoadCase, f'TEMPERATURE{i}'), getattr(LoadCase, f'PRESSURE{i}')} | set(EQ)
        ls = m.add_load_set(number=i, description=caso['nombre'], static_cases=cases, pipe_contents=not caso['contenido'], hot_modulus_case=i)
        ls.friction_factor = float(an.get('friction_scale_factor', 1.0))
        if caso['contenido']:
            ls.fluid_density_factor = float(an.get('fluid_density_factor_lleno', 1.0))
        if an.get('no_lineal'):
            ls.nl_occasional_type = OccasionalLoadType.NONLINEAR
            ls.max_nl_iterations = int(an.get('iteraciones', 30))
            ls.add_nl_static_case(LoadCase.GRAVITY)
    m.save()
    # la API guarda base_API_1.dat junto al modelo base; se mueve al destino pedido
    gen = [f for f in os.listdir(tmp) if f.startswith('base_API_') and f.endswith('.dat')]
    if not gen:
        raise SystemExit('La API no genero el .dat (revisar los errores anteriores)')
    shutil.move(os.path.join(tmp, gen[0]), a.out)
    shutil.rmtree(tmp, ignore_errors=True)
    informe(a.out, cfg, tramos, avisos, nred, nsup, nq)
    log(f'Modelo escrito en {a.out}')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'verify_model.py'), '--config', a.config, '--tabla', a.tabla, '--trazado', a.trazado, '--modelo', a.out])
    return r.returncode


def num(s):
    return inputs.num(s)


def cambios_en_nodo(nodos, tramos):
    """Un cambio de clase que cae justo en un nodo con cambio de DN exigiria decidir donde va el reductor: se pregunta."""
    out = []
    pr = [inputs.num(n['progresiva_m']) for n in nodos]
    for a_, b_ in zip(tramos, tramos[1:]):
        dn_a, dn_b = inputs.num(a_['DN_mm']), inputs.num(b_['DN_mm'])
        h = inputs.num(a_['hasta_m'])
        if dn_a is not None and dn_b is not None and dn_a != dn_b and h is not None and any(p is not None and abs(p - h) < inputs.TOL_M for p in pr):
            out.append(f'cambio de DN {dn_a:g}->{dn_b:g} en la progresiva {h:g} coincide con un nodo: indicar donde va el reductor')
    return out


def informe(ruta, cfg, tramos, avisos, nred, nsup, nq):
    txt = [f'# Informe de construccion: {os.path.basename(ruta)}', '',
           f"- Codigo: B31.4 edicion {cfg['codigo']['edicion']}, libreria {cfg['codigo']['libreria_materiales']}",
           f'- Tramos: {len(tramos)}; reductores insertados: {nred}; puntos con soporte de suelo: {nsup}; cargas sismicas: {nq}',
           '- Contenido: en la API pipe_contents=False significa contenido incluido (set LLENO escrito con False)', '', '## FALTANTES / avisos', '']
    txt += [f'- {a}' for a in avisos] or ['- (ninguno)']
    txt += ['', '## Supuestos de la skill (no vienen de las entradas)', '',
            '- Linestop sin roce ni gaps (la API los rechaza); el roce va en la Guide.',
            '- Soportes en los puntos con tipo_nodo configurado, en los puntos intermedios y en near/far de cada codo (el vertice no admite soportes).',
            '- Reductor centrado en la progresiva del cambio de clase.',
            '- Casos no lineales: solo GRAVITY cuando analisis.no_lineal es true.', '',
            '## Sin verificar', '', '- Analisis en AutoPIPE (la skill no analiza).', '- Orientacion de las guias y su direccion.']
    open(os.path.splitext(ruta)[0] + '.informe.md', 'w', encoding='utf-8').write('\n'.join(txt))


if __name__ == '__main__':
    sys.exit(main())
