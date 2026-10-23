#!/usr/bin/env node
/* ppst_extract.js -- turn a PPSSPP savestate into a flat RAM blob.
 *
 *   node tools/ppst_extract.js state.ppst ram.bin
 *
 * PPSSPP stores each save block zstd-compressed (magic 28 B5 2F FD).  We do not
 * rely on the container layout: every zstd frame we can decode is appended to the
 * output, so the result is "everything the savestate carried, decompressed".
 * If the file holds no zstd frame (older uncompressed save), it is copied as-is.
 */
const fs = require('fs');
const zlib = require('zlib');

const src = process.argv[2];
const dst = process.argv[3] || 'ram.bin';
if (!src) {
  console.error('usage: node ppst_extract.js <state.ppst> [ram.bin]');
  process.exit(2);
}
const buf = fs.readFileSync(src);
console.log(`input ${src}: ${buf.length.toLocaleString()} bytes`);

const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
const parts = [];
let frames = 0, failed = 0, pos = 0, total = 0;
const sizes = [];

while (true) {
  const i = buf.indexOf(MAGIC, pos);
  if (i < 0) break;
  let ok = false;
  for (const end of [undefined]) {
    try {
      const out = zlib.zstdDecompressSync(buf.subarray(i));
      parts.push(out);
      total += out.length;
      sizes.push(out.length);
      frames++;
      ok = true;
    } catch (e) {
      /* try next occurrence */
    }
  }
  if (!ok) failed++;
  pos = i + 4;
}

if (frames === 0) {
  fs.writeFileSync(dst, buf);
  console.log(`no zstd frame found -> wrote the file verbatim (${buf.length.toLocaleString()} bytes)`);
  process.exit(0);
}

const out = Buffer.concat(parts);
fs.writeFileSync(dst, out);
sizes.sort((a, b) => b - a);
console.log(`decoded ${frames} zstd frames (${failed} candidate starts failed)`);
console.log(`largest blocks: ${sizes.slice(0, 6).map(x => x.toLocaleString()).join(', ')}`);
console.log(`-> ${dst}: ${out.length.toLocaleString()} bytes`);
