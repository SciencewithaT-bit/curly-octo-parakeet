// Lecteur Parquet minimal (colonnes plates, pages V1/V2, encodages PLAIN et dictionnaire, codecs sans compression ou zstd).
// Usage : node pq.js <fichier.parquet> schema
//         node pq.js <fichier.parquet> dump COL1,COL2,... [COLFILTRE=valeur] > lignes.tsv
'use strict';
const fs = require('fs');
const zlib = require('zlib');

const file = process.argv[2], mode = process.argv[3];
const fd = fs.openSync(file, 'r');
const size = fs.fstatSync(fd).size;
const readAt = (pos, len) => { const b = Buffer.alloc(len); fs.readSync(fd, b, 0, len, pos); return b; };

// ---------- Thrift compact ----------
function thrift(buf, pos = 0) {
  const varint = () => { let r = 0n, s = 0n; for (;;) { const b = buf[pos++]; r |= BigInt(b & 0x7f) << s; if (!(b & 0x80)) break; s += 7n; } return r; };
  const zz = () => { const v = varint(); return Number((v >> 1n) ^ -(v & 1n)); };
  const value = t => {
    switch (t) {
      case 1: return true; case 2: return false;
      case 3: return buf.readInt8(pos++);
      case 4: case 5: case 6: return zz();
      case 7: { const v = buf.readDoubleLE(pos); pos += 8; return v; }
      case 8: { const n = Number(varint()); const b = buf.subarray(pos, pos + n); pos += n; return b; }
      case 9: case 10: {
        const h = buf[pos++]; let n = h >> 4; const et = h & 15; if (n === 15) n = Number(varint());
        const out = []; for (let i = 0; i < n; i++) out.push(et === 1 || et === 2 ? buf[pos++] === 1 : value(et)); return out;
      }
      case 11: { const n = Number(varint()); if (!n) return []; const kv = buf[pos++]; const out = []; for (let i = 0; i < n; i++) out.push([value(kv >> 4), value(kv & 15)]); return out; }
      case 12: return struct();
      default: throw new Error('type thrift ' + t);
    }
  };
  function struct() {
    const o = {}; let last = 0;
    for (;;) {
      const h = buf[pos++]; if (h === 0) return o;
      const d = h >> 4, t = h & 15; const id = d ? last + d : zz(); last = id;
      o[id] = value(t);
    }
  }
  const v = struct();
  return { v, pos };
}

// ---------- pied de fichier ----------
if (readAt(0, 4).toString('latin1') !== 'PAR1' || readAt(size - 4, 4).toString('latin1') !== 'PAR1') throw new Error('pas un fichier Parquet');
const flen = readAt(size - 8, 4).readUInt32LE(0);
const meta = thrift(readAt(size - 8 - flen, flen)).v;
const schema = meta[2].slice(1).map(e => ({ name: e[4].toString('utf8'), type: e[1], rep: e[3] }));
if (meta[2].slice(1).some(e => e[5])) throw new Error('colonnes imbriquées non gérées');
const TYPES = ['BOOLEAN', 'INT32', 'INT64', 'INT96', 'FLOAT', 'DOUBLE', 'BYTE_ARRAY', 'FIXED'];
if (mode === 'schema') {
  console.log('lignes :', meta[3], '| groupes :', meta[4].length, '| créé par :', (meta[6] || '').toString());
  console.log(schema.map(c => `${c.name}:${TYPES[c.type]}${c.rep === 1 ? '?' : ''}`).join('  '));
  const kv = (meta[5] || []).map(k => [k[1].toString(), (k[2] || '').toString().slice(0, 200)]);
  console.log('métadonnées :', kv.map(k => k[0]).join(', '));
  process.exit(0);
}

// ---------- décodage ----------
function hybrid(buf, pos, end, bw, count, out) {
  // RLE / bit-packing hybride ; écrit `count` valeurs dans out, renvoie la position atteinte
  let n = 0; const bytesW = (bw + 7) >> 3;
  while (n < count && pos < end) {
    let h = 0, s = 0; for (;;) { const b = buf[pos++]; h |= (b & 0x7f) << s; if (!(b & 0x80)) break; s += 7; }
    if (h & 1) {
      const groups = h >>> 1; let bitPos = pos * 8; const total = groups * 8;
      for (let i = 0; i < total; i++) {
        if (n < count) { let v = 0; for (let k = 0; k < bw; k++) { const bp = bitPos + k; if (buf[bp >> 3] & (1 << (bp & 7))) v |= 1 << k; } out[n++] = v; }
        bitPos += bw;
      }
      pos += groups * bw;
    } else {
      const run = h >>> 1; let v = 0; for (let k = 0; k < bytesW; k++) v |= buf[pos + k] << (8 * k); pos += bytesW;
      for (let i = 0; i < run && n < count; i++) out[n++] = v;
    }
  }
  if (n < count) throw new Error(`niveaux tronqués ${n}/${count}`);
  return pos;
}
function plain(buf, pos, type, count) {
  const out = new Array(count);
  for (let i = 0; i < count; i++) {
    if (type === 6) { const n = buf.readUInt32LE(pos); pos += 4; out[i] = buf.toString('utf8', pos, pos + n); pos += n; }
    else if (type === 2) { out[i] = buf.readBigInt64LE(pos).toString(); pos += 8; }
    else if (type === 1) { out[i] = String(buf.readInt32LE(pos)); pos += 4; }
    else if (type === 5) { out[i] = String(buf.readDoubleLE(pos)); pos += 8; }
    else throw new Error('type ' + TYPES[type]);
  }
  return out;
}
const unpack = (codec, buf, usize) => codec === 0 ? buf : codec === 6 ? zlib.zstdDecompressSync(buf, { maxOutputLength: Math.max(usize * 2, 1 << 20) }) : (() => { throw new Error('codec ' + codec); })();

function readColumn(rg, ci) {
  const cm = rg[1][ci][3], col = schema[ci], codec = cm[4], total = cm[5];
  let pos = cm[11] != null && cm[11] > 0 ? Math.min(cm[11], cm[9]) : cm[9];
  const endChunk = pos + cm[7];
  const out = new Array(total); let n = 0, dict = null;
  while (n < total && pos < endChunk) {
    const head = readAt(pos, Math.min(4096, size - pos)); const { v: ph, pos: hl } = thrift(head);
    const body = readAt(pos + hl, ph[3]); pos += hl + ph[3];
    if (ph[1] === 2) { dict = plain(unpack(codec, body, ph[2]), 0, col.type, ph[7][1]); continue; }
    if (ph[1] !== 0 && ph[1] !== 3) continue;
    let data, p = 0, nv, enc, defs = null;
    if (ph[1] === 0) {
      data = unpack(codec, body, ph[2]); nv = ph[5][1]; enc = ph[5][2];
      if (col.rep === 1) { const len = data.readUInt32LE(0); defs = new Uint8Array(nv); hybrid(data, 4, 4 + len, 1, nv, defs); p = 4 + len; }
    } else {
      const h2 = ph[8]; nv = h2[1]; enc = h2[4]; const dl = h2[5], rl = h2[6];
      if (col.rep === 1 && dl) { defs = new Uint8Array(nv); hybrid(body, rl, rl + dl, 1, nv, defs); }
      const rest = body.subarray(rl + dl); data = h2[7] === false ? rest : unpack(codec, rest, ph[2] - rl - dl); p = 0;
    }
    let nn = nv; if (defs) { nn = 0; for (let i = 0; i < nv; i++) nn += defs[i]; }
    let vals;
    if (enc === 0) vals = plain(data, p, col.type, nn);
    else if (enc === 2 || enc === 8) { const bw = data[p]; const idx = new Uint32Array(nn); hybrid(data, p + 1, data.length, bw, nn, idx); vals = Array.from(idx, i => dict[i]); }
    else throw new Error('encodage ' + enc + ' colonne ' + col.name);
    for (let i = 0, k = 0; i < nv; i++) out[n++] = !defs || defs[i] ? vals[k++] : '';
  }
  if (n !== total) throw new Error(`colonne ${col.name} : ${n}/${total} valeurs`);
  return out;
}

const want = process.argv[4].split(',');
const filt = (process.argv[5] || '').split('=');
const idx = want.map(w => { const i = schema.findIndex(c => c.name === w); if (i < 0) throw new Error('colonne absente : ' + w); return i; });
const fi = filt[0] ? schema.findIndex(c => c.name === filt[0]) : -1;
const lines = [want.join('\t')];
let rows = 0, kept = 0;
for (const rg of meta[4]) {
  const cols = idx.map(i => readColumn(rg, i));
  const fcol = fi >= 0 ? readColumn(rg, fi) : null;
  const nr = cols[0].length; rows += nr;
  for (let r = 0; r < nr; r++) {
    if (fcol && fcol[r] !== filt[1]) continue;
    lines.push(cols.map(c => String(c[r] ?? '').replace(/[\t\r\n]+/g, ' ')).join('\t')); kept++;
  }
}
process.stdout.write(lines.join('\n') + '\n');
console.error(`${rows} lignes lues, ${kept} gardées`);
