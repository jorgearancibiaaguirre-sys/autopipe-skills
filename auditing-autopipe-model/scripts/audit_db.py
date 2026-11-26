"""Audita SIN MODIFICAR un modelo AutoPIPE a partir de su .DB (SQLite del ultimo analisis), su .CHK y los logs L00n.LOG.

Uso: python audit_db.py --db M.DB [--chk M.CHK] [--logs L001.LOG L002.LOG] [--dat M.dat] [--spec spec.json] [--out informe.md]
- Abre el .DB en modo solo lectura y reporta el sha256 de cada entrada antes y despues (deben coincidir).
- El .DB refleja el ULTIMO ANALISIS, no necesariamente el .dat actual: se compara su fecha con la de los demas archivos.
Requisitos: Python 3.12, solo biblioteca estandar. Unidades esperadas en el .DB: SI (mm, N, MPa); si no, no se estiman pesos.
"""
import argparse
import collections
import datetime
import hashlib
import json
import math
import os
import re
import sqlite3
import sys

G = 9.81                   # m/s2; solo para convertir kg a N si hiciera falta
IGUALES_REL = 1e-6         # dos sumas de reacciones se consideran identicas si difieren menos que esto (relativo)
AVISOS_CLAVE = {           # codigo de aviso del .CHK -> significado (ver reference/avisos.md)
    'W2164-93': 'Fluid Density Factor en 0: el contenido no pesa aunque el set lo incluya',
    'W2143-76': 'Friction Scale Factor en 0: se ignora toda la friccion de los soportes',
    'W2164-78': 'D/t menor que 20: la ecuacion de esfuerzo circunferencial puede no aplicar',
    'W726-9': 'Guide o Line Stop en un punto con quiebre',
    'W726-93': 'Brida de peso cero',
}


def sha(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()[:16]


def fecha(ruta):
    return datetime.datetime.fromtimestamp(os.path.getmtime(ruta))


def q(c, sql, *p):
    try:
        cur = c.execute(sql, p)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error as e:
        return [{'_error': f'{sql[:60]}: {e}'}]


def sumar_gr(ruta):
    """Suma de reacciones GR (primer bloque de cada soporte) del resumen de soportes no lineales. Devuelve (suma_N, n_soportes) o (None, 0)."""
    try:
        lineas = open(ruta, encoding='latin-1').read().split('\n')
    except OSError:
        return None, 0
    ini = next((k for k, l in enumerate(lineas) if 'ERROR SUMMARY FOR NONLINEAR SUPPORTS' in l), None)
    if ini is None:
        return None, 0
    cur, lc, blk, tot, ns = None, None, collections.Counter(), 0.0, set()
    for l in lineas[ini:]:
        m = re.match(r'\s{2}(\S.*?)\s{2,}(GUIDE|VSTOP|LSTOP|\S+)\s*$', l)
        if m and l.startswith('  ') and not l.startswith('   '):
            cur = m.group(1).strip()
            blk = collections.Counter()
            continue
        m = re.match(r'\s{19}(\w+)\s*$', l)
        if m and cur:
            lc = m.group(1)
            continue
        m = re.match(r'\s+(\w+)\s+([-\d.E+]+)\s+[-\d.E+]+\s+[-\d.E+]+\s*$', l)
        if m and cur and lc:
            blk[lc] += 1
            if lc == 'GR' and blk[lc] == 1:
                tot += float(m.group(2))
                ns.add(cur)
    return tot, len(ns)


def avisos_chk(ruta):
    try:
        t = open(ruta, encoding='latin-1').read()
    except OSError:
        return {}
    out = {}
    for m in re.finditer(r'(W\d+-\d+):', t):
        out.setdefault(m.group(1), 0)
        out[m.group(1)] += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True)
    ap.add_argument('--chk')
    ap.add_argument('--logs', nargs='*', default=[])
    ap.add_argument('--dat')
    ap.add_argument('--spec')
    ap.add_argument('--out')
    a = ap.parse_args()
    entradas = [x for x in [a.db, a.chk, a.dat, a.spec] + a.logs if x]
    antes = {x: sha(x) for x in entradas}
    H, R = [], []          # hallazgos, secciones del informe
    c = sqlite3.connect('file:' + os.path.abspath(a.db).replace('\\', '/') + '?mode=ro', uri=True)

    # 1. identidad y vigencia
    mi = (q(c, 'select * from Model_Info') or [{}])[0]
    sa = q(c, 'select * from Static_Analysis order by Analysis_Set_Number')
    R.append('## 1. Modelo y vigencia del analisis')
    R.append(f"- Modelo {mi.get('Model_Name')}, {mi.get('Piping_Code')} edicion {mi.get('Edition')}, libreria {mi.get('Material_Library')}, revision {mi.get('Model_Revision')}, ambiente {mi.get('Ambient_Temperature')} C")
    if sa:
        R.append(f"- Analisis registrado en el .DB: {sa[0].get('Analysis_Date')} {sa[0].get('Analysis_Time')} (revision {sa[0].get('Model_Revision_Number')})")
    for etiqueta, ruta in [('CHK', a.chk), ('dat', a.dat)] + [(f'log{i + 1}', r) for i, r in enumerate(a.logs)]:
        if ruta:
            R.append(f'- {etiqueta}: modificado {fecha(ruta):%Y-%m-%d %H:%M}')
            if fecha(ruta) > fecha(a.db) + datetime.timedelta(minutes=1):
                H.append(f'DESFASE: {etiqueta} es posterior al .DB ({fecha(ruta):%Y-%m-%d %H:%M} frente a {fecha(a.db):%Y-%m-%d %H:%M}); el .DB puede no reflejar las ultimas ediciones')
    R.append(f'- .DB modificado {fecha(a.db):%Y-%m-%d %H:%M}')
    # fecha de cabecera del .CHK frente a la del analisis del .DB (las fechas de archivo cambian al copiar; las de cabecera no)
    if a.chk and sa:
        try:
            tx = open(a.chk, encoding='latin-1').read()[:2000]
            mm_, dd_, yy_ = re.search(r'(\d{2})/(\d{2})/(\d{4})', tx).groups()
            hh_ = re.search(r'(\d{1,2}:\d{2} [AP]M)', tx).group(1)
            f_chk = datetime.datetime.strptime(f'{yy_}-{mm_}-{dd_} {hh_}', '%Y-%m-%d %I:%M %p')
            f_db = datetime.datetime.strptime(re.sub(r'\s+', ' ', f"{sa[0]['Analysis_Date']} {sa[0]['Analysis_Time']}").replace(' ,', ','), '%b %d, %Y %I:%M %p')
            R.append(f'- Cabecera del .CHK: {f_chk:%Y-%m-%d %H:%M}; analisis del .DB: {f_db:%Y-%m-%d %H:%M}')
            if f_chk > f_db + datetime.timedelta(minutes=1):
                H.append(f'DESFASE: el .CHK ({f_chk:%Y-%m-%d %H:%M}) es posterior al analisis del .DB ({f_db:%Y-%m-%d %H:%M}); lo que muestra el .DB puede estar corregido o cambiado en el analisis mas nuevo')
        except (AttributeError, ValueError, OSError) as e:
            R.append(f'- No se pudo comparar la fecha del .CHK con la del .DB ({e})')

    # 2. analysis sets
    R += ['', '## 2. Analysis sets', '', '| Set | Descripcion | Contenido incluido | Fluid density factor | Friction scale factor | Modulo caliente | Tipo |', '|---|---|---|---|---|---|---|']
    for s in sa:
        R.append(f"| {s['Analysis_Set_Number']} | {s['Description']} | {s['Contents_Weight_Included']} | {s['Fluid_Density_Fact_Contents']} | {s['Friction_Scale_Factor']} | {s['Hot_Modulus_Case']} | {s['Occasional_Load_Analysis_Type']} |")
        n = s['Analysis_Set_Number']
        if str(s['Contents_Weight_Included']).lower().startswith('y') and not s['Fluid_Density_Fact_Contents']:
            H.append(f'Set {n}: incluye contenido pero Fluid Density Factor = 0 (el contenido no pesa; cargas de gravedad iguales a las del set sin contenido)')
        if not s['Friction_Scale_Factor']:
            H.append(f'Set {n}: Friction Scale Factor = 0 (la friccion de todos los soportes se ignora)')

    # 3. soportes y anclajes
    R += ['', '## 3. Soportes y anclajes', '', '| Tipo | Gap 1 | Gap 2 | Roce | Gap setting | Rigidez | Cantidad |', '|---|---|---|---|---|---|---|']
    for r in q(c, "select Support_Type t, round(Gap_1,1) g1, round(Gap_2,1) g2, round(Friction_Coefficient,2) mu, trim(Gap_Setting) gs, trim(Stiffness_Text) st, count(*) n from Support_Data_Listing group by 1,2,3,4,5,6 order by n desc"):
        R.append(f"| {r['t']} | {r['g1']} | {r['g2']} | {r['mu']} | {r['gs'] or '-'} | {r['st'] or '-'} | {r['n']} |")
    na = q(c, 'select count(*) n from Anchor_Data_Listing')[0].get('n')
    R.append(f'- Anclajes: {na}')

    # 4. tuberias y coherencia de P/T por pipe id
    R += ['', '## 4. Pipe properties', '', '| Id | OD | Espesor | Peso tubo (N/m) | Peso contenido (N/m) | Material |', '|---|---|---|---|---|---|']
    pp = q(c, 'select Pipe_Identifier id, Actual_OD od, Wall_Thickness t, Pipe_Weight wp, Content_Weight wc, Pipe_Material m from Pipe_Properties_Data_Listing')
    for r in pp:
        R.append(f"| {r['id']} | {r['od']:.1f} | {r['t']:.2f} | {r['wp']:.0f} | {r['wc']:.0f} | {r['m']} |")
    R += ['', '## 5. Coherencia de presion/temperatura por pipe id (valor dominante frente a minoritarios)', '']
    for campo, col, f in (('modulo (MPa)', 'Modulus', 1e6), ('fluencia (MPa)', 'Yield_Stress', 1.0)):
        por = collections.defaultdict(list)
        for r in q(c, f'select Pipe_ID pid, PT_Case cs, round({col},6) v, count(*) n from Press_Temp_Data_Listing group by 1,2,3'):
            por[(r['pid'], r['cs'])].append((r['n'], r['v']))
        for (pid, cs), lst in sorted(por.items()):
            if len(lst) > 1:
                lst.sort(reverse=True)
                dom = lst[0]
                for n, v in lst[1:]:
                    m = f'{campo} de {pid} caso {cs}: {n} puntos con {v * f:g} frente a {dom[1] * f:g} dominante ({dom[0]} puntos)'
                    R.append('- ' + m)
                    if col == 'Modulus':
                        H.append('INCOHERENCIA P/T: ' + m)
    if R[-1] == '':
        R.append('- (sin incoherencias)')
    R.append('')
    for r in q(c, 'select PT_Case cs, round(Temperature,1) t, round(Pressure,3) p, count(*) n from Press_Temp_Data_Listing group by 1,2,3 order by 1,3'):
        R.append(f"- caso {r['cs']}: T {r['t']} C, P {r['p']} MPa, {r['n']} puntos")

    # 6. codos, toberas, sismo
    R += ['', '## 6. Codos, toberas y sismo']
    bz = collections.Counter()
    for r in q(c, 'select round(Radius/OD,2) k, round(Radius) rad, count(*) n from Bend_Data_Listing where Analysis_Set=1 group by 1,2'):
        bz[(r['k'], r['rad'])] = r['n']
    R += [f'- Codos: radio/OD = {k}, radio {rad} mm: {n}' for (k, rad), n in sorted(bz.items(), key=str)] or ['- Codos: ninguno']
    R += [f"- Tobera {r['Point_Name']}: {r['Flexibility_Method']}, recipiente R {r['Vessel_Radius']} mm, t {r['Vessel_Thickness']} mm" for r in q(c, 'select * from Nozzle_Data_Lisitng')]
    R += [f"- {r['Load_Case']}: X {r['X_Resultant']:.2f} Y {r['Y_Resultant']:.2f} Z {r['Z_Resultant']:.2f} g" for r in q(c, 'select * from EQ_Load_Cases')]

    # 7. avisos del CHK
    if a.chk:
        av = avisos_chk(a.chk)
        R += ['', '## 7. Avisos del .CHK']
        for cod, n in sorted(av.items()):
            R.append(f"- {cod} x{n}" + (f': {AVISOS_CLAVE[cod]}' if cod in AVISOS_CLAVE else ''))
            if cod in ('W2164-93', 'W2143-76'):
                H.append(f'CHK {cod}: {AVISOS_CLAVE[cod]}')

    # 8. reacciones de gravedad y peso analitico
    sumas = []
    if a.logs:
        R += ['', '## 8. Reacciones de gravedad (GR) en los logs']
        for ruta in a.logs:
            tot, ns = sumar_gr(ruta)
            sumas.append(tot)
            R.append(f"- {os.path.basename(ruta)}: suma GR {tot / 1000:.1f} kN en {ns} soportes" if tot is not None else f'- {os.path.basename(ruta)}: sin resumen de soportes no lineales')
            n_db = q(c, 'select count(distinct Point_Name) n from Support_Data_Listing')[0].get('n')
            if tot is not None and n_db and ns < 0.9 * n_db:
                R.append(f'  - COBERTURA PARCIAL: el log trae {ns} de {n_db} puntos con soporte del .DB; la suma GR es parcial (log recortado o soportes lineales omitidos) y no se compara con el peso total')
                if 'cobertura' not in ' '.join(H):
                    H.append(f'Cobertura parcial de reacciones GR en los logs ({ns} de {n_db} soportes): no usar la suma como peso total')
        validas = [s for s in sumas if s is not None]
        if len(validas) >= 2 and all(abs(s - validas[0]) <= IGUALES_REL * max(abs(validas[0]), 1) for s in validas):
            H.append('Las sumas de GR de los logs son IDENTICAS: los sets no estan cargando distinto peso')
    coords = q(c, 'select Pipe_ID pid, Segment sg, X, Y, Z from Coordinates_Data_Listing')
    long_por = collections.Counter()
    prev = None
    for r in coords:
        p = (r['X'], r['Y'], r['Z'])
        if prev and prev[0] == r['sg']:
            d = math.dist(p, prev[1]) / 1000
            long_por[r['pid']] += d
        prev = (r['sg'], p)
    wp = {r['id']: (r['wp'], r['wc']) for r in pp}
    if long_por and wp:
        tubo = sum(wp[k][0] * l for k, l in long_por.items() if k in wp) / 1000
        cont = sum(wp[k][1] * l for k, l in long_por.items() if k in wp) / 1000
        R += ['', '## 9. Peso analitico (longitud entre puntos consecutivos de cada segmento x peso por metro; aproximado)',
              f'- Tubo {tubo:.0f} kN, contenido {cont:.0f} kN, total lleno {tubo + cont:.0f} kN (longitud total {sum(long_por.values()):.0f} m)']
        v = [s for s in sumas if s is not None]
        if v:
            R.append(f'- Suma GR de los logs: {", ".join(f"{s / 1000:.0f} kN" for s in v)}. Con cobertura completa, un set lleno cercano al peso del tubo solo indica que el contenido no esta pesando')

    # 10. especificacion
    if a.spec:
        spec = json.load(open(a.spec, encoding='utf-8'))
        R += ['', '## 10. Contra la especificacion', '', '| Item | Esperado | Encontrado | Resultado |', '|---|---|---|---|']
        def fila(item, esp, enc, ok):
            R.append(f'| {item} | {esp} | {enc} | {"cumple" if ok else ("NO CUMPLE" if ok is False else "no verificable")} |')
        if 'codigo' in spec:
            fila('codigo y edicion', f"{spec['codigo'].get('norma')} {spec['codigo'].get('edicion')}", f"{mi.get('Piping_Code')} {mi.get('Edition')}", str(mi.get('Edition')) == str(spec['codigo'].get('edicion')))
        an = spec.get('analysis_sets', {})
        for i, s in enumerate(sa[:2], start=1):
            e = an.get(f'set{i}', {})
            if 'contenido_incluido' in e:
                fila(f'set {i} contenido', e['contenido_incluido'], s['Contents_Weight_Included'], str(s['Contents_Weight_Included']).lower().startswith('y') == e['contenido_incluido'])
            if 'fluid_density_factor' in e:
                fila(f'set {i} fluid density factor', e['fluid_density_factor'], s['Fluid_Density_Fact_Contents'], abs((s['Fluid_Density_Fact_Contents'] or 0) - e['fluid_density_factor']) < 1e-6)
        if 'friction_scale_factor' in an:
            fila('friction scale factor', an['friction_scale_factor'], [s['Friction_Scale_Factor'] for s in sa], all(abs((s['Friction_Scale_Factor'] or 0) - an['friction_scale_factor']) < 1e-6 for s in sa))
        cs = spec.get('casos', {})
        if 'temperatura_montaje_C' in cs:
            fila('temperatura de montaje', cs['temperatura_montaje_C'], mi.get('Ambient_Temperature'), abs((mi.get('Ambient_Temperature') or 0) - cs['temperatura_montaje_C']) < 0.05)
        temps = {r['t'] for r in q(c, 'select distinct round(Temperature,1) t from Press_Temp_Data_Listing')}
        for k in ('T1_C', 'T2_C'):
            if k in cs:
                fila(k, cs[k], sorted(temps), float(cs[k]) in temps)
        if 'sismo_g' in cs:
            eq = {r['Load_Case']: (r['X_Resultant'], r['Y_Resultant'], r['Z_Resultant']) for r in q(c, 'select * from EQ_Load_Cases')}
            fila('sismo (g)', cs['sismo_g'], {k: max(v) for k, v in eq.items()}, all(abs(max(eq.get(k, (0, 0, 0))) - g_) < 1e-3 for k, g_ in cs['sismo_g'].items()))
        hd = spec.get('hdpe', {})
        if 'modulo_caliente_MPa' in hd:
            vals = {round(r['v'] * 1e6) for r in q(c, "select distinct Modulus v from Press_Temp_Data_Listing where Pipe_ID like 'H%' or Pipe_ID like '%PN%'")}
            fila('modulo caliente HDPE (MPa)', hd['modulo_caliente_MPa'], sorted(vals), vals == {round(hd['modulo_caliente_MPa'])})
        if 'fluencia_MPa' in hd:
            vals = {round(r['v'], 1) for r in q(c, "select distinct Yield_Stress v from Press_Temp_Data_Listing where Pipe_ID like 'H%' or Pipe_ID like '%PN%'")}
            fila('fluencia HDPE (MPa)', hd['fluencia_MPa'], sorted(vals), vals == {round(hd['fluencia_MPa'], 1)})
        ch = spec.get('codos_hdpe', {})
        if 'radio_en_diametros' in ch:
            fila('radio de codos (x OD)', ch['radio_en_diametros'], sorted(k for (k, rad) in bz), all(abs(k - ch['radio_en_diametros']) < 0.02 for (k, rad) in bz) if bz else None)
        ss = spec.get('soporte_suelo_hdpe', {})
        if ss:
            tipos = {r['t'] for r in q(c, 'select distinct Support_Type t from Support_Data_Listing')}
            if 'tipos_por_punto' in ss:
                fila('tipos de soporte de suelo', ss['tipos_por_punto'], sorted(tipos), set(ss['tipos_por_punto']) <= tipos)
            gv = q(c, "select distinct round(Gap_1,1) a, round(Gap_2,1) b from Support_Data_Listing where Support_Type='Guide-V'")
            if 'guide_v_gap_arriba_mm' in ss:
                fila('Guide-V gap arriba (mm)', ss['guide_v_gap_arriba_mm'], sorted({r['b'] for r in gv}), ss['guide_v_gap_arriba_mm'] in {r['b'] for r in gv})
            mus = {r['mu'] for r in q(c, "select distinct round(Friction_Coefficient,2) mu from Support_Data_Listing where Support_Type like 'Guide%'")}
            fila('roces presentes en las guias', [ss.get('roce_aguas_arriba_drop_box'), ss.get('roce_aguas_abajo_drop_box')], sorted(mus), None)
        ga = spec.get('guias_acero', {})
        if 'roce' in ga:
            fila('roce de guias de acero', ga['roce'], 'ver seccion 3 (el .DB no separa acero de HDPE por soporte)', None)

    despues = {x: sha(x) for x in entradas}
    R += ['', '## Integridad de las entradas', ''] + [f"- {os.path.basename(x)}: {antes[x]} -> {despues[x]} ({'sin cambios' if antes[x] == despues[x] else 'MODIFICADO'})" for x in entradas]
    out = ['# Auditoria de modelo AutoPIPE (solo lectura)', '', '## Hallazgos', ''] + ([f'- {h}' for h in H] or ['- (ninguno automatico)']) + [''] + R
    txt = '\n'.join(out)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(txt)
        print(f'Informe escrito en {a.out}')
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
