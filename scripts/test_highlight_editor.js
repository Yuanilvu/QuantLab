#!/usr/bin/env node
/* Tes tokenizer Abyss (static/js/hl.js) — jalankan dari ~/quantlab:
 *
 *   node scripts/test_highlight_editor.js [korpus.json]
 *
 * korpus.json = array string (opsional) — dibuat dari kurikulum via
 * `python scripts/...` (lihat skill quantlab-app: extractor /tmp/extract_kode.py).
 * Invariant yang dicek untuk SETIAP output:
 *   (a) jumlah <span class="..."> == jumlah </span>
 *   (b) tidak ada "<span <span" (span bersarang korup)
 *   (c) setelah tag span dilepas, tidak ada '<' mentah (semua sudah &lt;)
 *   (d) tidak ada '&' yatim (semua entitas &amp; &lt; &gt;)
 */
'use strict';
const path = require('path');
const fs = require('fs');
const QL_HL = require(path.join(__dirname, '..', 'static', 'js', 'hl.js'));

let total = 0;
let fail = 0;
function check(nama, cond) {
  total++;
  if (!cond) { fail++; console.log('  FAIL:', nama); }
}
function invariant(label, html) {
  const open = (html.match(/<span class="/g) || []).length;
  const close = (html.match(/<\/span>/g) || []).length;
  check('span balance: ' + label, open === close);
  check('span korup: ' + label, !html.includes('<span <span'));
  const strip = html.replace(/<\/?span[^>]*>/g, '');
  check("'<' mentah: " + label, !strip.includes('<'));
  check('& yatim: ' + label, !/&(?!(amp|lt|gt);)/.test(strip));
}

/* ---------- Unit: token & warna kelasnya ---------- */
const h = QL_HL.highlight;

check('angka', h('umur = 17').includes('<span class="tok-num">17</span>'));
check('angka desimal', h('pi = 3.14').includes('<span class="tok-num">3.14</span>'));
check('angka tidak potong identifier', !h('data2 = 1').includes('tok-num">2'));
check('string ganda', h('print("halo")').includes('<span class="tok-str">"halo"</span>'));
check('string tunggal', h("s = 'don\\'t'").includes('tok-str'));
check('string tiga kutip', h('"""doc\nmulti"""').includes('tok-str'));
check('komentar', h('# catatan kecil').includes('<span class="tok-com"># catatan kecil</span>'));
check('komentar berisi kutip', h('# jangan "ini" ya').includes('tok-com'));
check('def + nama', h('def hitung(x):').includes('<span class="tok-kw">def</span> <span class="tok-fn">hitung</span>'));
check('class + nama', h('class Mobil:').includes('<span class="tok-kw">class</span> <span class="tok-cls">Mobil</span>'));
check('keyword if', h('if x:').includes('<span class="tok-kw">if</span>'));
check('if tidak jadi fungsi', !h('if (x):').includes('tok-fn">if'));
check('builtin print', h('print(x)').includes('<span class="tok-builtin">print</span>'));
check('builtin len', h('len(data)').includes('<span class="tok-builtin">len</span>'));
check('panggilan fungsi user', h('total = tambah(2, 3)').includes('<span class="tok-fn">tambah</span>'));
check('method call', h('df.read_csv(p)').includes('<span class="tok-fn">read_csv</span>'));
check('alias modul', h('import pandas as pd').includes('<span class="tok-builtin">pd</span>'));

/* ---------- Unit: keselamatan HTML ---------- */
invariant('escape < >', h('x = a < b > c # kecil'));
check('escape < benar', h('a < b').includes('a &lt; b'));
check('entity lt tidak diwarnai', !h('a < b').includes('tok-fn">lt'));
check('script tag aman', !h('s = "<script>"').includes('<script'));
check('ampersand aman', h('x = a & b').includes('&amp;'));
invariant('kutip nyasar', h("s = 'teks\nlanjut = 1"));
invariant('docstring', h('"""a\nb"""\nx = 1'));

/* ---------- Korpus massal (opsional) ---------- */
const korpusPath = process.argv[2] || '/tmp/hl_corpus.json';
if (fs.existsSync(korpusPath)) {
  const arr = JSON.parse(fs.readFileSync(korpusPath, 'utf8'));
  console.log(`== korpus: ${arr.length} string dari kurikulum ==`);
  arr.forEach((s, i) => invariant('korpus#' + i, h(String(s))));
} else {
  console.log('(korpus dilewati — ' + korpusPath + ' tidak ada)');
}

console.log(`\nHASIL: ${total - fail}/${total} cek lolos${fail ? ' — ' + fail + ' GAGAL' : ' ✓'}`);
process.exit(fail ? 1 : 0);
