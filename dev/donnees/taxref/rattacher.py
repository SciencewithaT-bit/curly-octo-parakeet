"""Rattache les espèces du Mycodex à TAXREF.

  python3 rattacher.py <noms.json> <champignons.tsv> <export GBIF.csv> <rattachements.json>

  noms.json        : sorti par names.js depuis la source de l'app
  champignons.tsv  : sorti par pq.js depuis le fichier TAXREF (voir LISEZMOI.md)

Règles (un rattachement douteux n'est pas gardé) :
 1. le nom latin de la case, s'il désigne un seul taxon de référence (CD_REF) dans TAXREF ;
 2. sinon, les noms sous lesquels les observations de Charente ont été saisies (export GBIF), s'ils mènent tous au même CD_REF ;
 3. sinon, rien.
Les lignes « sensu … » / « auct. » de TAXREF (noms mal appliqués) ne servent jamais ; entre homonymes, l'auteur départage,
puis la ligne qui est elle-même le nom valide."""
import collections, csv, json, re, sys
csv.field_size_limit(10**9)
NAMES, FUNGI, GBIF, OUT = sys.argv[1:5]
names = json.load(open(NAMES, encoding='utf-8'))
rows = list(csv.DictReader(open(FUNGI, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE))
by_name = collections.defaultdict(list); by_cd = {}
SENSU = re.compile(r'sensu|auct|\bnon\b|\bss\b', re.I)
for r in rows:
    by_cd[r['CD_NOM']] = r
    if r['RANG'] == 'ES' and not SENSU.search(r['LB_AUTEUR'] or ''): by_name[r['LB_NOM']].append(r)
norm_auth = lambda a: re.sub(r'[^a-zà-ÿ]', '', re.sub(r'\d{4}', '', (a or '').lower()))
rec = collections.defaultdict(collections.Counter)
for r in csv.DictReader(open(GBIF, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
    sp, sn = (r.get('species') or '').strip(), (r.get('scientificName') or '').strip()
    parts = sn.split(' ')
    if sp and len(parts) >= 2 and parts[1][:1].islower() and parts[2:3] not in (['var.'], ['f.'], ['subsp.']):
        rec[sp][(' '.join(parts[:2]), ' '.join(parts[2:]))] += 1
# Deux lignes homonymes valides dans TAXREF ; celle de Retz., 1769 est le nom accepté par GBIF et porte le nom français.
OVERRIDE = {'Tremella mesenterica': '44992'}

def resolve(canon, auth=''):
    c = by_name.get(canon, [])
    if len({r['CD_REF'] for r in c}) > 1 and auth:
        same = [r for r in c if norm_auth(r['LB_AUTEUR']) == norm_auth(auth)]
        if same: c = same
    if len({r['CD_REF'] for r in c}) > 1:
        valid = [r for r in c if r['CD_NOM'] == r['CD_REF']]
        if valid: c = valid
    return {r['CD_REF'] for r in c}

out, absent, conflict = {}, [], []
for t in names['ref'] + names['ch']:
    la = t['la']
    if la in OVERRIDE: cds, via = {OVERRIDE[la]}, 'choix documenté'
    else:
        cds, via = resolve(la), 'nom'
        if len(cds) != 1:
            rc = set()
            for (canon, auth), n in rec.get(la, {}).items(): rc |= resolve(canon, auth)
            if len(rc) == 1: cds, via = rc, 'noms saisis'
            elif rc and not cds: cds = rc
    if not cds: absent.append(la); continue
    if len(cds) > 1: conflict.append((la, sorted(by_cd[c]['NOM_VALIDE'] for c in cds))); continue
    ref = by_cd[next(iter(cds))]
    vern = [v.strip() for v in (ref['NOM_VERN'] or '').split(',') if v.strip()]
    out[la] = {'cd': int(ref['CD_NOM']), 'valid': ref['LB_NOM'], 'vern': vern, 'via': via}
json.dump({'absent': absent, 'conflit': conflict, 'tx': out}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ch = [t['la'] for t in names['ch']]
print('rattachés :', len(out), '/', len(names['ref']) + len(ch), '· via', dict(collections.Counter(v['via'] for v in out.values())))
print('avec nom français :', sum(1 for v in out.values() if v['vern']), '· Charente :', sum(1 for n in ch if n in out and out[n]['vern']), '/', len(ch))
print('ABSENTS', len(absent), absent)
print('CONFLITS', len(conflict), conflict)
print('VIA NOMS SAISIS :', [(k, v['valid']) for k, v in out.items() if v['via'] != 'nom'])
bad = [(k, x) for k, v in out.items() for x in v['vern'] if '�' in x or '?' in x or re.search(r'\d', x) or len(x) > 45 or not x[0].isupper()]
print('NOMS À REGARDER', len(bad), bad)
allv = collections.Counter(x.lower() for v in out.values() for x in v['vern'])
print('NOMS PARTAGÉS PAR PLUSIEURS ESPÈCES', [(n, c) for n, c in allv.items() if c > 1])
print('nombre total de noms vernaculaires :', sum(len(v['vern']) for v in out.values()), '· caractères :', sum(len(', '.join(v['vern'])) for v in out.values()))
