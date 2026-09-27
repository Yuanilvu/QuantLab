/* QuantLab — console mini di halaman skenario ("🧪 Coba di sini").
 *
 * Menjalankan cuplikan Python lewat /api/mini/jalankan — KERNEL yang sama
 * dengan Notebook (per user), jadi variabel nyambung dua arah dengan notebook
 * milik user. Highlight pakai hl.js/hl_editor.js (overlay Abyss yang sama
 * dengan editor halaman soal & notebook).
 */
(function (root) {
  'use strict';

  var box = document.getElementById('mini');
  if (!box) { return; }
  var ta = document.getElementById('miniCode');
  var btnRun = document.getElementById('miniRun');
  var btnClear = document.getElementById('miniClear');
  var out = document.getElementById('miniOut');
  var statusEl = document.getElementById('miniStatus');
  var CSRF = box.getAttribute('data-csrf') || '';
  var busy = false;

  if (!ta || !btnRun || !out) { return; }

  function api(p) { return (window.QL_BASE || '') + p; }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }

  function setStatus(txt) { if (statusEl) { statusEl.textContent = txt; } }

  function render(res) {
    out.innerHTML = '';
    if (!res) { return; }
    if (res.status === 'timeout') {
      out.appendChild(el('pre', 'm-err', res.message || '⏱ Kode berjalan terlalu lama dan dihentikan.'));
    } else if (res.status !== 'ok' && res.status !== 'error' && res.message) {
      out.appendChild(el('pre', 'm-err', res.message));
    }
    if (res.stdout) { out.appendChild(el('pre', 'm-std', res.stdout)); }
    if (res.error) {
      out.appendChild(el('pre', 'm-err', res.error));
    } else if (res.stderr) {
      out.appendChild(el('pre', 'm-err', res.stderr));
    }
    if (res.result) {
      out.appendChild(el('pre', 'm-res', 'Out[' + (res.n || '?') + ']: ' + res.result));
    }
    if (res.images && res.images.length) {
      for (var k = 0; k < res.images.length; k++) {
        var img = el('img', 'm-img');
        img.src = 'data:image/png;base64,' + res.images[k];
        img.alt = 'grafik';
        out.appendChild(img);
      }
    }
    if (typeof res.ms === 'number' && (res.status === 'ok' || res.status === 'error')) {
      out.appendChild(el('div', 'm-ms', '⏱ ' + (res.ms / 1000).toFixed(2) + ' s'));
    }
    if (!out.childNodes.length) {
      out.appendChild(el('div', 'm-empty', '(selesai tanpa output — pakai print() untuk melihat hasil)'));
    }
  }

  function refreshStatus() {
    fetch(api('/api/mini/status'))
      .then(function (r) { return r.json(); })
      .then(function (s) {
        if (s.status === 'unavailable') { setStatus('🔴 kernel mati'); return; }
        if (!s.exists || !s.alive) { setStatus('⚪ kernel tidur — nyala otomatis saat ▶'); return; }
        setStatus(s.busy ? '🟠 sedang jalan…' : '🟢 kernel siap' + (s.python ? ' · ' + s.python : ''));
      })
      .catch(function () { setStatus('⚪ kernel belum aktif'); });
  }

  function run() {
    if (busy) { return; }
    var code = ta.value || '';
    if (!code.trim()) { ta.focus(); return; }
    busy = true;
    btnRun.disabled = true;
    out.innerHTML = '';
    out.appendChild(el('div', 'm-spin', '⏳ menjalankan…'));
    fetch(api('/api/mini/jalankan'), {
      method: 'POST',
      headers: { 'X-CSRF-Token': CSRF },
      body: new URLSearchParams({ _csrf: CSRF, code: code })
    }).then(function (r) { return r.json(); }).then(function (res) {
      busy = false;
      btnRun.disabled = false;
      render(res);
      refreshStatus();
    }).catch(function () {
      busy = false;
      btnRun.disabled = false;
      out.innerHTML = '';
      out.appendChild(el('pre', 'm-err', '⚠️ Gagal menghubungi server. Coba lagi.'));
    });
  }

  btnRun.addEventListener('click', run);
  if (btnClear) {
    btnClear.addEventListener('click', function () { out.innerHTML = ''; });
  }
  ta.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      run();
    }
  });

  /* Pewarnaan Abyss (overlay yang sama dengan editor soal & notebook) */
  if (root.QL_HL_EDITOR && root.QL_HL_EDITOR.pasang) { root.QL_HL_EDITOR.pasang(ta); }
  refreshStatus();
})(typeof window !== 'undefined' ? window : globalThis);
