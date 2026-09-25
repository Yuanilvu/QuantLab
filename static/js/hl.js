/* QuantLab — tokenizer Python untuk pewarnaan sintaks (tema ABYSS, ala VS Code).
 *
 * SATU-SATUNYA sumber logika highlight kode Python di app ini:
 *   - blok kode pelajaran (pre.block-code) → dipanggil app.js
 *   - editor halaman soal (overlay)        → dipanggil hl_editor.js
 *
 * ⚠️ SINGLE-PASS regex + callback — JANGAN diubah jadi beberapa pass .replace()
 * berurutan (bug lama 9 Sep 2026: pass kedua menscan ulang markup <span> yang
 * baru disisipkan → markup korup → `class="tok-..."` tampil mentah).
 *
 * Palet warna diambil dari tema resmi VS Code "Abyss"
 * (microsoft/vscode → extensions/theme-abyss/themes/abyss-color-theme.json):
 *   kata kunci #225588 · string #22aa44 · angka #f280d0 · komentar #384887
 *   fungsi #ddbb88 · kelas #ffeebb · builtin #9966b8 · teks biasa #6688cc
 * Definisi class CSS-nya di static/css/polish.css (bagian "Editor Abyss").
 *
 * Diuji node: scripts/test_highlight_editor.js (unit + korpus kurikulum).
 */
(function (root) {
  'use strict';

  var KW = 'def|return|if|elif|else|for|while|import|from|class|try|except|finally|and|or|not|in|is|None|True|False|lambda|with|as|pass|break|continue|global|nonlocal|assert|yield|raise|del|async|await';
  var BUILTIN = 'print|len|range|input|int|float|str|list|dict|set|tuple|bool|sum|min|max|abs|round|sorted|enumerate|zip|type|open|isinstance|math|random|datetime|pd|np|plt|pandas|numpy|matplotlib';

  var RE = new RegExp(
    '(\\b0x[0-9a-fA-F]+|\\b\\d+\\.?\\d*)' +            // 1 angka
    '|("""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\')' +     // 2 string tiga kutip
    '|("(?:[^"\\\\\\n]|\\\\.)*")' +                    // 3 string "
    "|('(?:[^'\\\\\\n]|\\\\.)*')" +                    // 4 string '
    '|(#[^\\n]*)' +                                    // 5 komentar
    '|(\\b(?:def|class)\\s+[A-Za-z_]\\w*)' +           // 6 def/class + nama
    '|(\\b(?:' + BUILTIN + ')\\b)' +                   // 7 builtin/modul
    '|(\\b(?:' + KW + ')\\b)' +                        // 8 kata kunci
    '|(\\b[A-Za-z_]\\w*(?=\\s*\\())',                  // 9 pemanggilan fungsi
    'g');

  /* Escape HTML — WAJIB sebelum regex berjalan (regex bekerja di atas teks
   * yang sudah di-escape; kutip ' dan " sengaja TIDAK di-escape karena regex
   * string membutuhkannya, sedangkan & < > aman karena tidak muncul sebagai
   * kata/digit di dalam entitas). */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function span(cls, txt) {
    return '<span class="' + cls + '">' + txt + '</span>';
  }

  function highlight(kode) {
    var teks = esc(kode);
    return teks.replace(RE, function (m, num, tq, dq, sq, com, defcls, builtin, kwf, call, offset, full) {
      if (num !== undefined) { return span('tok-num', num); }
      if (tq !== undefined) { return span('tok-str', tq); }
      if (dq !== undefined) { return span('tok-str', dq); }
      if (sq !== undefined) { return span('tok-str', sq); }
      if (com !== undefined) { return span('tok-com', com); }
      if (defcls !== undefined) {
        var pisah = defcls.split(/\s+/);
        var cls = pisah[0] === 'class' ? 'tok-cls' : 'tok-fn';
        return span('tok-kw', pisah[0]) + ' ' + span(cls, pisah[1]);
      }
      /* Penjaga entitas HTML: jangan sentuh kata persis setelah '&'
       * (mis. "lt"/"gt"/"amp" di dalam &lt; &gt; &amp;). */
      var setelahAmp = offset > 0 && full.charAt(offset - 1) === '&';
      if (builtin !== undefined) { return setelahAmp ? m : span('tok-builtin', builtin); }
      if (kwf !== undefined) { return setelahAmp ? m : span('tok-kw', kwf); }
      if (call !== undefined) { return setelahAmp ? m : span('tok-fn', call); }
      return m;
    });
  }

  root.QL_HL = { highlight: highlight, esc: esc };
  if (typeof module !== 'undefined' && module.exports) { module.exports = root.QL_HL; }
})(typeof window !== 'undefined' ? window : globalThis);
