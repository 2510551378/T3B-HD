#!/usr/bin/env node
/* zstd_blob.js -- decompress one raw zstd block from a file.
 *
 *   node tools/zstd_blob.js in.zst out.bin
 */
const fs = require('fs');
const zlib = require('zlib');
const [src, dst] = process.argv.slice(2);
if (!src || !dst) {
  console.error('usage: node zstd_blob.js <in.zst> <out.bin>');
  process.exit(2);
}
try {
  const out = zlib.zstdDecompressSync(fs.readFileSync(src));
  fs.writeFileSync(dst, out);
} catch (e) {
  console.error(String(e && e.message ? e.message : e));
  process.exit(1);
}
