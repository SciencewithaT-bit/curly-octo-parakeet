import csv, collections, json, re, sys
src, app = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding='utf-8'), delimiter='\t'))
html = open(app, encoding='utf-8').read()
ref = re.findall(r"\['(\w+)', '([A-Z][a-z]+ [a-z-]+)'", html)  # (group, latin)
REF = {la: g for g, la in ref}
LICHEN_CLASSES = {'Lecanoromycetes', 'Arthoniomycetes', 'Lichinomycetes'}
MICRO_CLASSES = {'Dothideomycetes', 'Ustilaginomycetes', 'Pucciniomycetes', 'Atractiellomycetes', 'Exobasidiomycetes', 'Taphrinomycetes'}
MICRO_ORDERS = {'Verrucariales', 'Eurotiales', 'Glomerellales', 'Rhytismatales', 'Coronophorales', 'Capnodiales', 'Mycosphaerellales', 'Pleosporales'}
MICRO_FAM = {'Erysiphaceae'}
MICRO_GEN = {'Gibberella', 'Fusarium', 'Colletotrichum', 'Penicillium', 'Aspergillus', 'Hymenoscyphus', 'Bertia'}
WOOD_AGARIC = {'Pleurotus', 'Fistulina', 'Schizophyllum', 'Armillaria', 'Hypholoma', 'Pholiota', 'Kuehneromyces', 'Gymnopilus', 'Panellus', 'Mucidula', 'Flammulina', 'Cyclocybe', 'Pluteus', 'Crepidotus', 'Omphalotus', 'Tricholomopsis', 'Hohenbuehelia', 'Lentinellus', 'Plicaturopsis', 'Pleurocybella', 'Ossicaulis', 'Volvariella'}
WOOD_ORDERS = {'Polyporales', 'Hymenochaetales', 'Auriculariales', 'Tremellales', 'Dacrymycetales', 'Gloeophyllales', 'Amylocorticiales', 'Corticiales', 'Trechisporales'}
def group(c, o, f, g):
    if f == 'Amanitaceae': return 'amanites'
    if f in ('Boletaceae', 'Suillaceae', 'Gyroporaceae', 'Boletinellaceae') or g == 'Gyrodon': return 'bolets'
    if f == 'Russulaceae': return 'russules'
    if o in ('Cantharellales', 'Gomphales', 'Thelephorales') or f in ('Clavariaceae', 'Clavariadelphaceae', 'Auriscalpiaceae'): return 'chanterelles'
    if o == 'Phallales' or o == 'Geastrales': return 'curiosites'
    if f in ('Agaricaceae', 'Lycoperdaceae', 'Sclerodermataceae', 'Diplocystidiaceae', 'Nidulariaceae', 'Tulostomataceae', 'Rhizopogonaceae'): return 'agarics'
    if o in WOOD_ORDERS or (o == 'Russulales') or g in WOOD_AGARIC: return 'lignicoles'
    if c in ('Pezizomycetes', 'Leotiomycetes', 'Sordariomycetes', 'Geoglossomycetes'): return 'ascos'
    if o in ('Agaricales', 'Boletales'): return 'lames'
    return 'curiosites'
MORT = {'Lepiota subincarnata', 'Lepiota brunneoincarnata', 'Lepiota josserandii', 'Lepiota helveola', 'Amanita verna', 'Pholiotina rugosa', 'Cortinarius rubellus', 'Galerina marginata'}
TOXG = {'Inocybe', 'Inosperma', 'Pseudosperma', 'Hebeloma', 'Scleroderma', 'Lepiota'}
TOXS = {'Amanita gemmata', 'Gymnopilus junonius', 'Coprinopsis picacea', 'Clitocybe phyllophila', 'Clitocybe rivulosa', 'Clitocybe dealbata', 'Russula emetica'}
agg = {}
alias = {}
excl = collections.Counter()
for x in rows:
    if x['taxonRank'] not in ('SPECIES', 'VARIETY', 'FORM', 'SUBSPECIES'): continue
    acc = x['species'] or ' '.join(x['acceptedScientificName'].split()[:2])
    c, o, f, g = x['class'], x['order'], x['family'], x['genus']
    if c in LICHEN_CLASSES or o == 'Verrucariales' and 'Verrucaria' in acc: excl['lichen'] += 1; continue
    if c in MICRO_CLASSES or o in MICRO_ORDERS or f in MICRO_FAM or g in MICRO_GEN: excl['micro'] += 1; continue
    a = agg.setdefault(acc, {'n': 0, 'cofg': (c, o, f, g)})
    a['n'] += int(x['numberOfOccurrences'])
    nm = ' '.join(x['scientificName'].split()[:2])
    if nm != acc: alias[nm] = acc
# synonymes connus de la liste de départ (taxonomie COL)
MANUAL = {'Lactarius piperatus': 'Lactifluus piperatus', 'Neoboletus luridiformis': 'Neoboletus erythropus'}
refAcc = {}
for la in REF:
    acc = la if la in agg else alias.get(la) or MANUAL.get(la)
    if acc and acc in agg: refAcc[acc] = la
gbRef = {la: agg[acc]['n'] for acc, la in refAcc.items()}
new = [(acc, v) for acc, v in agg.items() if acc not in refAcc]
new.sort(key=lambda t: (-t[1]['n'], t[0]))
out = []
for acc, v in new:
    c, o, f, g = v['cofg']
    tox = 'mortelle' if acc in MORT else 'toxique' if (g in TOXG or acc in TOXS) else ''
    out.append([acc, group(c, o, f, g), v['n'], tox] if tox else [acc, group(c, o, f, g), v['n']])
aliasOut = {k: v for k, v in alias.items() if k != v}
for la, acc in [(la, a) for a, la in refAcc.items() if a != la]: aliasOut[acc] = la
print('lichens/micro exclus:', dict(excl), '| espèces gardées:', len(agg), '| départ trouvées:', len(refAcc), '| nouvelles:', len(out), file=sys.stderr)
print(collections.Counter(r[1] for r in out), file=sys.stderr)
print([r for r in out if len(r) > 3], file=sys.stderr)
js = ('const CH_SRC = { label: "GBIF.org, téléchargement du 24 octobre 2026", url: "https://www.gbif.org/occurrence/download/0001742-261023074918325" };\n'
      f'const CH_GB_REF = {json.dumps(gbRef, ensure_ascii=False)};\n'
      f'const CH_ALIAS = {json.dumps(aliasOut, ensure_ascii=False)};\n'
      f'const CH_RAW = {json.dumps(out, ensure_ascii=False, separators=(",", ":"))};\n')
open(sys.argv[3], 'w', encoding='utf-8').write(js)
