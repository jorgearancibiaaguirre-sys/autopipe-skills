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
KGM3_FT3 = 0.062427961      # kg/m3 -> lb/ft3
MM2_IN2 = 645.16            # mm2 por in2 (area, cortante)
MM4_IN4 = 416231.4          # mm4 por in4 (inercias)
IN100FT = 1200.0           # deformacion unitaria -> in/100 ft (100 ft = 1200 in)
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
    from autopipe.enum import SupportType, GapSetting, LoadCase, SeismicCode, OccasionalLoadType, SectionShape, SectionType, MaterialType
    globals().update(SupportType=SupportType, GapSetting=GapSetting, LoadCase=LoadCase, SeismicCode=SeismicCode, OccasionalLoadType=OccasionalLoadType,
                     SectionShape=SectionShape, SectionType=SectionType, MaterialType=MaterialType)

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
        dims = c.get('od_mm') not in (None, '') and c.get('espesor_mm') not in (None, '')
        od, e = (float(c['od_mm']), float(c['espesor_mm'])) if dims else (None, None)
        mat = inputs.props_clase(cfg, k, c)
        MATC[k] = mat
        if inputs.es_hdpe(k):
            kw = dict(pipe_id=c['id'], nominal_diameter=od * IN, outside_diameter=od * IN, wall_thickness=e * IN, material_id='NS', schedule='NS',
                      material_density=mat['densidad_kg_m3'] * KGM3, poisson_ratio=mat['poisson'], is_hdpe_material=True)
            if c.get('sdr'):
                kw['dimension_ratio'] = str(c['sdr'])
        else:
            kw = dict(pipe_id=c['id'], nominal_diameter=inputs.nps_clase(c, inputs.num(t['DN_mm'])), material_id=str(c['material_id']), schedule=str(c['schedule']))
            if dims:      # sin OD ni espesor, AutoPIPE los asigna desde su base segun NPS y schedule
                kw.update(outside_diameter=od * IN, wall_thickness=e * IN)
            if mat:
                kw['material_density'] = mat['densidad_kg_m3'] * KGM3
                kw['poisson_ratio'] = mat['poisson']
        if mat and mat.get('modulo_frio_MPa'):
            kw['cold_modulus'] = mat['modulo_frio_MPa'] * MPA
        pp = m.add_pipe_property(**kw)
        pp.content_weight = cfg['fluido']['densidad_kg_m3'] * KGM3_FT3   # en la API content_weight es la DENSIDAD del fluido (lb/ft3); AutoPIPE calcula el peso por longitud
        PP[k], CL[k] = pp, c
        log(f"pipe property {c['id']} <- {k}: " + (f'OD {od} mm, espesor {e} mm' if dims else f"NPS {kw['nominal_diameter']:g} in (OD y espesor: los asigna AutoPIPE)") + f", material {kw['material_id']}, schedule {kw['schedule']}")

    ramas = inputs.agrupar_ramas(nodos)
    TR = {}                                  # rama -> [(desde, hasta, clave de clase, DN)]
    for t in tramos:
        TR.setdefault(inputs.rama_tramo(t), []).append((num(t['desde_m']), num(t['hasta_m']), inputs.clave_clase(t), float(t['DN_mm'])))
    DNC = {k: dn for trs in TR.values() for _, _, k, dn in trs}      # DN por clase: el reductor se inserta cuando cambia el DN, no el OD

    # --- seccion de la viga de soporte (solo si hay nodos soporte_viga). Sin los campos de material la API guarda un .dat que no se reabre (E0).
    SEC = None
    vcfg = cfg.get('soportes', {}).get('viga', {})
    if any(n['tipo_nodo'].strip() == 'soporte_viga' for n in nodos):
        s_, mt_ = vcfg['seccion'], vcfg['material']
        d_, b_, tf_, tw_ = (float(s_[x]) for x in ('profundidad_mm', 'ancho_mm', 'ala_mm', 'alma_mm'))
        A_ = 2 * b_ * tf_ + (d_ - 2 * tf_) * tw_
        Izz = (b_ * d_ ** 3 - (b_ - tw_) * (d_ - 2 * tf_) ** 3) / 12            # eje fuerte
        Iyy = 2 * tf_ * b_ ** 3 / 12 + (d_ - 2 * tf_) * tw_ ** 3 / 12           # eje debil
        J_ = (2 * b_ * tf_ ** 3 + (d_ - 2 * tf_) * tw_ ** 3) / 3
        SEC = m.add_section(name=s_['nombre'], shape=SectionShape.W, depth=d_ * IN, width=b_ * IN, flange_thickness=tf_ * IN, web_thickness=tw_ * IN,
                            axial_area=A_ / MM2_IN2, zz_bending=Izz / MM4_IN4, yy_bending=Iyy / MM4_IN4, torsional_inertia=J_ / MM4_IN4,
                            yy_shear=(d_ - 2 * tf_) * tw_ / MM2_IN2, zz_shear=5 * b_ * tf_ / 3 / MM2_IN2,
                            young_modulus=mt_['E_MPa'] * MPA, poisson_ratio=mt_['poisson'], density=mt_['densidad_kg_m3'] * KGM3,
                            thermal_expansion=mt_['dilatacion_1e6_por_C'] * 1e-6 / 1.8, yield_stress=mt_['fluencia_MPa'] * MPA, ultimate_strength=mt_['rotura_MPa'] * MPA,
                            material_name=mt_['nombre'], material_type=MaterialType.STEEL, type=SectionType.NSTD)
        log(f"seccion de viga {s_['nombre']}: {d_:g}x{b_:g}, ala {tf_:g}, alma {tw_:g} mm; A={A_:.0f} mm2, Izz={Izz / 1e4:.0f} cm4, Iyy={Iyy / 1e4:.0f} cm4; material {mt_['nombre']}")

    M = 1000 * IN
    rcodo = float(cfg['codo']['radio_en_diametros'])
    Lred = float(cfg['reductor_largo_mm']) * IN
    disc = cfg.get('discretizacion_m')
    REG = []     # (handle, clase, tipo)  tipo: nodo:<tipo_nodo>, intermedio, bend_near, bend_far, bend_mid, red_near, red_far, tee_branch
    TEES = {}    # punto -> (tee, posicion, rama)
    ESTADO = {'nred': 0, 'stn': 0, 'nviga': 0, 'lazos': 0, 'fallos_lazo': []}
    EXTREMOS = {}

    class Branch:
        """Derivacion de una tee aun sin elementos: el primer elemento se coloca por offset respecto de la tee."""
        def __init__(self, tee, ref):
            self.tee, self.ref = tee, ref

    def agregar(cur, metodo, name, pos, **kw):
        if isinstance(cur, Branch):
            return getattr(cur.tee.branch, metodo)(name=name, offset=tuple(p - q for p, q in zip(pos, cur.ref)), **kw)
        return getattr(cur, metodo)(name=name, position=pos, **kw)

    def poner_viga(c, rn, i, pos, k):
        """Guia sobre el punto c, conectada al tope de una viga vertical cuyo pie (anclado) esta a suelo_a_eje_mm bajo el eje."""
        ESTADO['nviga'] += 1
        j = ESTADO['nviga']
        g = vcfg['guia']
        a_ = rn[i - 1] if i > 0 else rn[i]
        b_ = rn[i + 1] if i + 1 < len(rn) else rn[i]
        theta = math.degrees(math.atan2(float(b_['Y_m']) - float(a_['Y_m']), float(b_['X_m']) - float(a_['X_m'])))
        beta = (theta + float(vcfg.get('beta_offset_deg', 90.0))) % 180.0
        ztop = pos[2] - (float(vcfg['suelo_a_eje_mm']) - float(vcfg['altura_viga_mm'])) * IN
        zbot = pos[2] - float(vcfg['suelo_a_eje_mm']) * IN
        mu = g['roce'] if inputs.es_hdpe(k) else g.get('roce_no_hdpe', g['roce'])
        kw = dict(type=SupportType.GUIDE, friction=float(mu), gap_left=g['gap_lateral_mm'] * IN, gap_right=g['gap_lateral_mm'] * IN,
                  gap_up=g['gap_arriba_mm'] * IN, gap_down=g['gap_abajo_mm'] * IN, gap_setting=GapSetting.WEIGHTLESS)
        if g.get('rigidez_transversal_rigida', True):
            kw['trans_stiffness'] = -1.0
        s = c.add_support(**kw)
        pre = vcfg.get('prefijo', 'VG')
        ntop = m.add_frame_node(name=f'{pre}T{j:02d}', position=(pos[0], pos[1], ztop))
        nbot = m.add_frame_node(name=f'{pre}B{j:02d}', position=(pos[0], pos[1], zbot))
        m.add_beam(name=f'{pre}{j:02d}', i=nbot, j=ntop, section=SEC, beta_angle=beta)
        nbot.add_anchor()
        s.connected = ntop

    def construir(rama, rn, inicio):
        """Construye una rama. inicio=None: primera rama (segmento nuevo); inicio=(tee, pos): derivacion de esa tee."""
        tr = TR[rama]
        P = [(float(n['X_m']) * M, float(n['Y_m']) * M, float(n['Z_eje_m']) * M) for n in rn]
        PR = [float(num(n['progresiva_m'])) for n in rn]

        def clase_en(p):
            for d, h, k, dn in tr:
                if d - inputs.TOL_M <= p <= h + inputs.TOL_M:
                    return k
            return tr[-1][2]

        cierre = None
        if rama != inputs.PRINCIPAL and rn[-1]['tipo_nodo'].strip() == 'tee' and rn[-1]['punto'] in TEES and TEES[rn[-1]['punto']][2] != rama:
            cierre = TEES[rn[-1]['punto']]          # la rama vuelve a una tee de otra rama: lazo
        fin = len(rn) - 1 if cierre else len(rn)
        k0 = clase_en(PR[0])
        if inicio is None:
            cur = m.add_run(name=rn[0]['punto'], segment=m.add_segment(), pipe_property=PP[k0], position=P[0])
            REG.append((cur, k0, 'nodo:' + rn[0]['tipo_nodo'].strip()))
            EXTREMOS[rama] = [cur, cur]
        else:
            tee, tpos = inicio
            tee.branch.segment = m.add_segment()
            tee.branch.pipe_property = PP[k0]
            REG.append((tee.branch, k0, 'tee_branch'))
            cur = Branch(tee, tpos)
        for i in range(1, fin):
            n = rn[i]
            tipo = n['tipo_nodo'].strip()
            p0, p1 = PR[i - 1], PR[i]
            L = p1 - p0
            estac = []
            for d, h, k, dn in tr[1:]:
                if p0 + inputs.TOL_M < d < p1 - inputs.TOL_M:
                    estac.append((d, 'limite'))
            if disc:
                for j in range(1, int(math.ceil(L / disc))):
                    estac.append((p0 + j * L / math.ceil(L / disc), 'intermedio'))
            estac.sort()
            for p, kind in estac:
                f = (p - p0) / L
                pos = tuple(P[i - 1][q] + f * (P[i][q] - P[i - 1][q]) for q in range(3))
                antes, despues = clase_en(p - 2 * inputs.TOL_M), clase_en(p + 2 * inputs.TOL_M)
                if kind == 'limite' and DNC[antes] != DNC[despues]:
                    ESTADO['nred'] += 1
                    nr = ESTADO['nred']
                    dirv = [(P[i][q] - P[i - 1][q]) / math.dist(P[i - 1], P[i]) for q in range(3)]
                    base_c = cur.tee.branch if isinstance(cur, Branch) else cur
                    rd = base_c.add_reducer(name=f'R{nr:02d}', far_pipe_property=PP[despues])
                    rd.near.position = tuple(pos[q] - dirv[q] * Lred / 2 for q in range(3))
                    rd.far.position = tuple(pos[q] + dirv[q] * Lred / 2 for q in range(3))
                    try:
                        rd.near.pipe_property = PP[antes]
                    except Exception as e:
                        log(f'  ! pipe_property en el lado near del reductor R{nr:02d}: {str(e)[:70]}')
                    REG.extend([(rd.near, antes, 'red_near'), (rd.far, despues, 'red_far')])
                    cur = rd
                    log(f'reductor R{nr:02d} (rama {rama}) en progresiva {p:g} m: DN {DNC[antes]:g} -> {DNC[despues]:g}, largo {cfg["reductor_largo_mm"]} mm')
                else:
                    ESTADO['stn'] += 1
                    cur = agregar(cur, 'add_run', f"S{ESTADO['stn']:03d}", pos)
                    cur.pipe_property = PP[antes]
                    REG.append((cur, antes, 'intermedio' if kind == 'intermedio' else 'nodo:punto'))
            k_seg = clase_en((p0 + p1) / 2)
            # radio del codo: HDPE en multiplos del OD; otro material en multiplos del diametro nominal (codo largo de acero = 1,5 NPS)
            od_seg = float(CL[k_seg]['od_mm']) if inputs.es_hdpe(k_seg) else inputs.nps_clase(CL[k_seg], DNC[k_seg]) * 25.4
            es_vertice = tipo == 'vertice_trazado' and (i < fin - 1 or cierre)
            if es_vertice:
                rc = float(CL[k_seg].get('radio_codo_en_diametros', rcodo))
                b = agregar(cur, 'add_bend', n['punto'], P[i], radius=rc * od_seg * IN)
                for ph in (b.near, b.mid, b.tangent, b.far):
                    try:
                        ph.pipe_property = PP[k_seg]
                    except Exception as e:
                        log(f"  ! pipe_property en un punto del codo {n['punto']}: {str(e)[:70]}")
                        break
                if cfg['codo'].get('factor_flexibilidad') and inputs.es_hdpe(k_seg):
                    b.flexibility_factor = float(cfg['codo']['factor_flexibilidad'])
                REG.extend([(b.near, k_seg, 'bend_near'), (b.mid, k_seg, 'bend_mid'), (b.far, k_seg, 'bend_far'), (b.tangent, k_seg, 'bend_vertex')])
                cur = b
            elif tipo == 'tee':
                tee = agregar(cur, 'add_tee', n['punto'], P[i])
                tee.pipe_property = PP[k_seg]
                TEES[n['punto']] = (tee, P[i], rama)
                REG.append((tee, k_seg, 'nodo:tee'))
                cur = tee
            else:
                cur = agregar(cur, 'add_run', n['punto'], P[i])
                cur.pipe_property = PP[k_seg]
                REG.append((cur, k_seg, 'nodo:' + tipo))
                if tipo == 'soporte_viga':
                    try:
                        poner_viga(cur, rn, i, P[i], k_seg)
                    except Exception as e:
                        log(f"  ! viga en {n['punto']}: {str(e)[:100]}")
        if rama in EXTREMOS:
            EXTREMOS[rama][1] = cur
        if cierre:
            try:
                cur.link(cierre[0].branch)
                ESTADO['lazos'] += 1
                log(f"rama {rama}: cierre del lazo con la tee {rn[-1]['punto']} (link a la derivacion de la tee)")
            except Exception as e:
                ESTADO['fallos_lazo'].append(rama)
                log(f"  ! LAZO NO CERRADO en la rama {rama} con la tee {rn[-1]['punto']}: {str(e)[:100]}")
        return cur

    for rama, rn in ramas.items():
        if rama == inputs.PRINCIPAL:
            construir(rama, rn, None)
        else:
            tee, tpos, _ = TEES[rn[0]['punto']]
            log(f"rama {rama}: derivacion de la tee {rn[0]['punto']} ({len(rn)} nodos)")
            construir(rama, rn, (tee, tpos))

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
    pr_ext = EXTREMOS[inputs.PRINCIPAL] if inputs.PRINCIPAL in EXTREMOS else []
    nombres_anc = list(pr_ext) if anc == 'extremos' else [h for h, k, kd in REG if getattr(h, 'name', '') in anc]
    for h in nombres_anc:
        h.add_anchor(rigid=True)
    nred, nviga = ESTADO['nred'], ESTADO['nviga']
    log(f'soportes de suelo en {nsup} puntos; anclajes rigidos: {len(nombres_anc)}; ramas: {len(ramas)}; tees: {len(TEES)}; vigas: {nviga}; lazos cerrados: {ESTADO["lazos"]}')

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
    extra = f"ramas: {len(ramas)}; tees: {len(TEES)}; vigas de soporte: {nviga}; lazos cerrados: {ESTADO['lazos']}"
    if ESTADO['fallos_lazo']:
        avisos = avisos + [f"LAZO NO CERRADO en la(s) rama(s) {ESTADO['fallos_lazo']}: conectar en la GUI"]
    if nviga:
        avisos = avisos + ['orientacion beta de las vigas (alma colineal con el eje de la tuberia) no verificada: revisar en vista solida']
    informe(a.out, cfg, tramos, avisos, nred, nsup, nq, extra)
    log(f'Modelo escrito en {a.out}')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'verify_model.py'), '--config', a.config, '--tabla', a.tabla, '--trazado', a.trazado, '--modelo', a.out])
    return r.returncode


def num(s):
    return inputs.num(s)


def cambios_en_nodo(nodos, tramos):
    """Un cambio de clase que cae justo en un nodo con cambio de DN exigiria decidir donde va el reductor: se pregunta (por rama)."""
    out = []
    for rama, rn in inputs.agrupar_ramas(nodos).items():
        pr = [inputs.num(n['progresiva_m']) for n in rn]
        trs = [t for t in tramos if inputs.rama_tramo(t) == rama]
        for a_, b_ in zip(trs, trs[1:]):
            dn_a, dn_b = inputs.num(a_['DN_mm']), inputs.num(b_['DN_mm'])
            h = inputs.num(a_['hasta_m'])
            if dn_a is not None and dn_b is not None and dn_a != dn_b and h is not None and any(p is not None and abs(p - h) < inputs.TOL_M for p in pr):
                out.append(f'rama {rama}: cambio de DN {dn_a:g}->{dn_b:g} en la progresiva {h:g} coincide con un nodo: indicar donde va el reductor')
    return out


def informe(ruta, cfg, tramos, avisos, nred, nsup, nq, extra=''):
    txt = [f'# Informe de construccion: {os.path.basename(ruta)}', '',
           f"- Codigo: B31.4 edicion {cfg['codigo']['edicion']}, libreria {cfg['codigo']['libreria_materiales']}",
           f'- Tramos: {len(tramos)}; reductores insertados: {nred}; puntos con soporte de suelo: {nsup}; cargas sismicas: {nq}', f'- {extra}',
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
