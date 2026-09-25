/* QuantLab — editor berwarna (overlay highlight di belakang textarea).
 *
 * Pasang otomatis ke setiap <textarea data-editor="python"> (halaman soal).
 * Cara kerja: <pre> berisi HTML berwarna (QL_HL.highlight) diletakkan TEPAT
 * di belakang textarea; teks textarea dibikin transparan (warna teks dari
 * lapisan <pre>), kursor (caret) tetap terlihat. Semua ketikan, seleksi,
 * undo/redo, dan fitur QL_EDITOR (auto-pair dkk) TIDAK berubah.
 *
 * Syarat selaras: font/padding/line-height/ukuran huruf lapisan <pre> harus
 * SAMA dengan textarea → diatur di static/css/polish.css (bagian "Editor Abyss").
 * ⚠️ Kalau salah satu sisi diubah, ubah dua-duanya.
 */
(function (root) {
  'use strict';

  function pasang(ta) {
    if (!ta || ta.__hl || !root.QL_HL) { return; }
    ta.__hl = true;

    var wrap = document.createElement('div');
    wrap.className = 'hl-wrap';
    ta.parentNode.insertBefore(wrap, ta);

    var bg = document.createElement('div');
    bg.className = 'hl-bg';
    bg.setAttribute('aria-hidden', 'true');
    var pre = document.createElement('pre');
    pre.className = 'hl-pre';
    bg.appendChild(pre);

    wrap.appendChild(bg);
    wrap.appendChild(ta);
    ta.classList.add('hl-ta');

    function render() {
      pre.innerHTML = root.QL_HL.highlight(ta.value) + '\n';
    }
    function syncScroll() {
      bg.scrollTop = ta.scrollTop;
      bg.scrollLeft = ta.scrollLeft;
    }
    function segarkan() { render(); syncScroll(); }

    ta.addEventListener('input', segarkan);
    ta.addEventListener('change', segarkan);
    ta.addEventListener('scroll', syncScroll);
    root.addEventListener('resize', render);
    /* Klik di area kosong wrapper → fokuskan textarea */
    wrap.addEventListener('mousedown', function (e) {
      if (e.target === wrap || e.target === bg) { ta.focus(); }
    });

    segarkan();
  }

  function init() {
    if (!root.QL_HL) { return; }
    var daftar = document.querySelectorAll('textarea[data-editor]');
    for (var i = 0; i < daftar.length; i++) { pasang(daftar[i]); }
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  root.QL_HL_EDITOR = { pasang: pasang };
})(typeof window !== 'undefined' ? window : globalThis);
