// Sort les noms latins du Mycodex (liste de départ et liste Charente) depuis la source de l'app.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const grab = name => { const a = src.indexOf(`const ${name} = [`); const b = src.indexOf('\n];', a); const c = src.indexOf('];\n', a); const end = (b >= 0 && b < c ? b + 3 : c + 2); return src.slice(a + `const ${name} = `.length, end).replace(/;\s*$/, ''); };
const M = (a, b) => [a, b];
const REF_RAW = eval(grab('REF_RAW')), CH_RAW = eval(grab('CH_RAW'));
console.log(JSON.stringify({ ref: REF_RAW.map(r => ({ la: r[1], fr: r[2], g: r[0] })), ch: CH_RAW.map(r => ({ la: r[0], g: r[1] })) }));
