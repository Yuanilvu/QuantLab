/* QuantLab — editor kode pintar (auto-tutup kurung/kutip + auto-indent).
 *
 * Dipakai di dua tempat:
 *   1. Halaman soal      → textarea ber-atribut data-editor="python" (auto-init).
 *   2. Sel Notebook      → notebook.js memanggil QL_EDITOR.handleKey(ta, e, opts).
 *
 * Inti logika ada di apply() yang MURNI (tanpa DOM) sehingga bisa diuji dengan
 * node — lihat scripts/test_editor.js di skill quantlab-app.
 *
 * Fitur: pasangan kurung ( ) [ ] { } dan kutip " ' otomatis; menimpa kurung
 * penutup = lompat (skip-over); Backspace di pasangan kosong menghapus keduanya;
 * Tab = 4 spasi / indent blok (Shift+Tab = kurangi); Enter mengikuti indentasi,
 * menambah level setelah `:` atau `(` dan mekar di antara kurung `(|)`.
 */
(function (root) {
  'use strict';

  var INDENT = '    ';
  var PASANGAN = { '(': ')', '[': ']', '{': '}' };
  var PENUTUP = { ')': '(', ']': '[', '}': '{' };
  var KUTIP = ['"', "'"];

  function spasiAwal(baris) {
    var m = baris.match(/^[ \t]*/);
    return m ? m[0] : '';
  }

  /* Terapkan satu tombol ke state {value, start, end}.
   * Return {value, start, end} kalau ditangani (harus preventDefault),
   * atau null kalau biarkan perilaku bawaan browser. */
  function apply(st, ev, opts) {
    opts = opts || {};
    var pairs = opts.pairs !== false;
    var key = ev && ev.key;
    var shift = !!(ev && ev.shiftKey);
    if (!key || (ev && (ev.ctrlKey || ev.metaKey || ev.altKey))) { return null; }

    var v = st.value, s = st.start, e = st.end;
    if (s > e) { var t = s; s = e; e = t; }

    // ------------------------------------------------ karakter tunggal
    if (key.length === 1) {
      var adaPilihan = s !== e;
      var sebelum = s > 0 ? v.charAt(s - 1) : '';
      var sesudah = v.charAt(e);

      if (PASANGAN[key]) {                      // ( [ {  → pasangkan / bungkus
        if (!pairs) { return null; }
        var isi = adaPilihan ? v.slice(s, e) : '';
        return { value: v.slice(0, s) + key + isi + PASANGAN[key] + v.slice(e),
                 start: s + 1, end: s + 1 + isi.length };
      }
      if (PENUTUP[key]) {                       // ) ] }  → lompat kalau sudah ada
        if (!adaPilihan && sesudah === key) {
          return { value: v, start: s + 1, end: s + 1 };
        }
        return null;
      }
      if (KUTIP.indexOf(key) !== -1) {          // " '  → pasangkan / lompat
        if (adaPilihan) {
          if (!pairs) { return null; }
          var isi2 = v.slice(s, e);
          return { value: v.slice(0, s) + key + isi2 + key + v.slice(e),
                   start: s + 1, end: s + 1 + isi2.length };
        }
        if (sesudah === key) {                  // kutip penutup sudah ada → lompat
          return { value: v, start: s + 1, end: s + 1 };
        }
        var setelahKata = /[\w)]/.test(sebelum);
        if (pairs && !setelahKata) {
          return { value: v.slice(0, s) + key + key + v.slice(e),
                   start: s + 1, end: s + 1 };
        }
        return null;
      }
      return null;
    }

    // ------------------------------------------------ Enter
    if (key === 'Enter') {
      if (s !== e) { v = v.slice(0, s) + v.slice(e); e = s; }   // pilihan = diganti
      var awalan = v.slice(0, s);
      var barisMulai = awalan.lastIndexOf('\n') + 1;
      var barisSkr = awalan.slice(barisMulai);
      var indent = spasiAwal(barisSkr);

      // baris yang dimulai penutup )]} → turun satu level
      if (/^[ \t]*[)\]}]/.test(barisSkr) && indent.slice(-INDENT.length) === INDENT) {
        indent = indent.slice(0, indent.length - INDENT.length);
      }

      // kursor persis di antara pasangan kosong ( | ) → mekar jadi 3 baris
      var charSbl = s > 0 ? v.charAt(s - 1) : '';
      var charStl = v.charAt(s);
      if (pairs && PASANGAN[charSbl] && charStl === PASANGAN[charSbl]) {
        var dalam = indent + INDENT;
        var insMekar = '\n' + dalam + '\n' + indent;
        return { value: v.slice(0, s) + insMekar + v.slice(s),
                 start: s + 1 + dalam.length, end: s + 1 + dalam.length };
      }

      var tambah = '';
      if (/:\s*$/.test(barisSkr)) { tambah = INDENT; }
      else if (pairs && /[([{]\s*$/.test(barisSkr) && indent.length < 32) { tambah = INDENT; }
      var ins = '\n' + indent + tambah;
      return { value: v.slice(0, s) + ins + v.slice(s),
               start: s + ins.length, end: s + ins.length };
    }

    // ------------------------------------------------ Tab / Shift+Tab
    if (key === 'Tab') {
      var mulaiBaris = v.lastIndexOf('\n', s - 1) + 1;
      var habisBaris = v.indexOf('\n', e);
      if (habisBaris === -1) { habisBaris = v.length; }

      if (s !== e) {                             // blok: indent / dedent semua baris
        var potongan = v.slice(mulaiBaris, habisBaris).split('\n');
        for (var i = 0; i < potongan.length; i++) {
          if (shift) {
            var mD = potongan[i].match(/^ {1,4}/) || potongan[i].match(/^\t/);
            if (mD) { potongan[i] = potongan[i].slice(mD[0].length); }
          } else {
            potongan[i] = INDENT + potongan[i];
          }
        }
        var blokBaru = potongan.join('\n');
        return { value: v.slice(0, mulaiBaris) + blokBaru + v.slice(habisBaris),
                 start: mulaiBaris, end: mulaiBaris + blokBaru.length };
      }

      if (shift) {                               // dedent baris sekarang
        var barisIni = v.slice(mulaiBaris, habisBaris);
        var mK = barisIni.match(/^ {1,4}/) || barisIni.match(/^\t/);
        if (!mK) { return { value: v, start: s, end: e }; }
        return { value: v.slice(0, mulaiBaris) + barisIni.slice(mK[0].length) + v.slice(habisBaris),
                 start: Math.max(mulaiBaris, s - mK[0].length),
                 end: Math.max(mulaiBaris, s - mK[0].length) };
      }
      return { value: v.slice(0, s) + INDENT + v.slice(e),           // sisip 4 spasi
               start: s + INDENT.length, end: s + INDENT.length };
    }

    // ------------------------------------------------ Backspace
    if (key === 'Backspace') {
      if (s === e && s > 0) {
        var c1 = v.charAt(s - 1), c2 = v.charAt(s);
        if ((PASANGAN[c1] && c2 === PASANGAN[c1]) || (KUTIP.indexOf(c1) !== -1 && c2 === c1)) {
          return { value: v.slice(0, s - 1) + v.slice(s + 1), start: s - 1, end: s - 1 };
        }
      }
      return null;
    }

    return null;
  }

  /* Pasang ke satu textarea nyata. Return true kalau tombol ditangani. */
  function handleKey(ta, ev, opts) {
    if (!ta || ta.tagName !== 'TEXTAREA') { return false; }
    var res = apply({ value: ta.value, start: ta.selectionStart, end: ta.selectionEnd }, ev, opts);
    if (!res) { return false; }
    ev.preventDefault();
    ta.value = res.value;
    ta.selectionStart = res.start;
    ta.selectionEnd = res.end;
    return true;
  }

  /* Auto-init untuk textarea[data-editor] (halaman soal). */
  function init() {
    if (typeof document === 'undefined') { return; }
    var daftar = document.querySelectorAll('textarea[data-editor]');
    for (var i = 0; i < daftar.length; i++) {
      (function (ta) {
        ta.addEventListener('keydown', function (e) {
          var pairs = ta.getAttribute('data-editor') === 'python';
          if (handleKey(ta, e, { pairs: pairs })) {
            ta.dispatchEvent(new Event('input', { bubbles: true }));
          }
        });
      })(daftar[i]);
    }
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  root.QL_EDITOR = { apply: apply, handleKey: handleKey, init: init,
                     INDENT: INDENT, PASANGAN: PASANGAN };
  if (typeof module !== 'undefined' && module.exports) { module.exports = root.QL_EDITOR; }
})(typeof window !== 'undefined' ? window : globalThis);
