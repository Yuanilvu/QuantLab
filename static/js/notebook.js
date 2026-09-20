/* QuantLab — Notebook editor (ala Kaggle).
 * Fungsi murni (esc, mdToHtml) diekspor utk uji node: require('.../notebook.js').
 */
(function (root) {
  'use strict';

  // ---------- fungsi murni ----------
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function inlineMd(s) {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/\*([^*]+)\*/g, '<i>$1</i>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }

  function mdToHtml(src) {
    var text = esc(src || '');
    var blocks = [];
    text = text.replace(/```([\s\S]*?)```/g, function (_m, code) {
      blocks.push('<pre class="md-code"><code>' + code.replace(/^\n+|\n+$/g, '') + '</code></pre>');
      return '\u0000B' + (blocks.length - 1) + '\u0000';
    });
    var lines = text.split('\n');
    var out = [];
    var para = [];
    var i = 0;
    function flush() {
      if (para.length) { out.push('<p>' + inlineMd(para.join(' ')) + '</p>'); para = []; }
    }
    while (i < lines.length) {
      var ln = lines[i];
      var m;
      if ((m = ln.match(/^\u0000B(\d+)\u0000$/))) { flush(); out.push(blocks[+m[1]]); i++; continue; }
      if (/^\s*$/.test(ln)) { flush(); i++; continue; }
      if ((m = ln.match(/^(#{1,4})\s+(.*)$/))) {
        flush();
        var lv = m[1].length;
        out.push('<h' + lv + '>' + inlineMd(m[2]) + '</h' + lv + '>');
        i++; continue;
      }
      if (/^(-{3,}|\*{3,})\s*$/.test(ln)) { flush(); out.push('<hr>'); i++; continue; }
      if (/^&gt;\s?/.test(ln)) {
        flush();
        var q = [];
        while (i < lines.length && /^&gt;\s?/.test(lines[i])) {
          q.push(lines[i].replace(/^&gt;\s?/, '')); i++;
        }
        out.push('<blockquote>' + inlineMd(q.join(' ')) + '</blockquote>');
        continue;
      }
      if (/^\s*([-*+])\s+/.test(ln)) {
        flush();
        var items = [];
        while (i < lines.length && /^\s*([-*+])\s+/.test(lines[i])) {
          items.push('<li>' + inlineMd(lines[i].replace(/^\s*([-*+])\s+/, '')) + '</li>'); i++;
        }
        out.push('<ul>' + items.join('') + '</ul>');
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(ln)) {
        flush();
        var oitems = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          oitems.push('<li>' + inlineMd(lines[i].replace(/^\s*\d+[.)]\s+/, '')) + '</li>'); i++;
        }
        out.push('<ol>' + oitems.join('') + '</ol>');
        continue;
      }
      para.push(ln); i++;
    }
    flush();
    return out.join('\n');
  }

  root.NB = { esc: esc, mdToHtml: mdToHtml };
  if (typeof module !== 'undefined' && module.exports) { module.exports = root.NB; }
  if (typeof document === 'undefined') { return; }  // node (uji) → cukup fungsi murni

  // ---------- editor (browser) ----------
  var HEAD = document.querySelector('.nbhead');
  if (!HEAD) { return; }
  var NID = HEAD.getAttribute('data-nid');
  var cellsEl = document.getElementById('cells');
  var titleEl = document.getElementById('nbTitle');
  var saveState = document.getElementById('saveState');
  var kernelPill = document.getElementById('kernelPill');

  function api(p) { return (window.QL_BASE || '') + '/api/notebook/' + NID + p; }
  function csrf() { var el = document.getElementById('csrf'); return el ? el.value : ''; }

  var cells = [];
  try { cells = JSON.parse(document.getElementById('cellData').textContent || '[]'); } catch (e) { cells = []; }
  if (!cells.length) { cells = [{ type: 'code', source: '' }]; }

  var dirty = false, saving = false, saveTimer = null, lastFocusIdx = null, busy = false;

  // ---------- render ----------
  function cellAt(i) { return cellsEl.querySelector('.nbcell[data-i="' + i + '"]'); }

  function syncAll() {
    for (var i = 0; i < cells.length; i++) { syncFromDom(i); }
  }

  function syncFromDom(i) {
    var el = cellAt(i);
    if (!el) { return; }
    var ta = el.querySelector('.nbtext');
    if (ta && cells[i]) { cells[i].source = ta.value; }
  }

  function renderCells() {
    syncAll();
    var html = '';
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i];
      var isPrev = c.type === 'md' && (c.source || '').trim() !== '';
      html += '<div class="nbcell' + (c.type === 'md' ? ' nbmdc' : '') + (isPrev ? ' md-preview' : '') + '" data-i="' + i + '">';
      html += '<div class="nbgutter">';
      html += '<button class="runbtn" data-act="run" type="button" title="Jalankan (Shift+Enter)">▶</button>';
      html += '<span class="incount" id="in-' + i + '">' +
        (c.output && c.output.n ? '[' + c.output.n + ']' : '[ ]') + '</span>';
      html += '</div><div class="nbmain">';
      if (c.type === 'md') {
        html += '<div class="mdview" data-role="mdview"></div>';
        html += '<textarea class="nbtext nbmdtext" data-role="editor" spellcheck="false" placeholder="Tulis penjelasan (mendukung markdown)...">' + esc(c.source) + '</textarea>';
      } else {
        html += '<textarea class="nbtext" data-role="editor" spellcheck="false" placeholder="# tulis kodemu di sini...">' + esc(c.source) + '</textarea>';
      }
      html += '<div class="nbtools">';
      html += '<button class="tool" data-act="up" type="button" title="Pindah ke atas">↑</button>';
      html += '<button class="tool" data-act="down" type="button" title="Pindah ke bawah">↓</button>';
      html += '<button class="tool" data-act="add" type="button" title="Tambah sel kode di bawah">＋</button>';
      if (c.type === 'md') { html += '<button class="tool" data-act="preview" type="button" title="Pratinjau / edit">👁</button>'; }
      html += '<button class="tool danger" data-act="del" type="button" title="Hapus sel">🗑</button>';
      html += '</div>';
      html += '<div class="nbout" data-role="out"></div>';
      html += '</div></div>';
    }
    cellsEl.innerHTML = html;
    for (var j = 0; j < cells.length; j++) {
      if (cells[j].type === 'md') { updateMdView(j); }
      paintOutput(j, cells[j].output);
    }
  }

  function updateMdView(i) {
    var el = cellAt(i); if (!el) { return; }
    var view = el.querySelector('[data-role="mdview"]');
    if (view) { view.innerHTML = mdToHtml(cells[i].source); }
  }

  var MD_ICONS = { ok: '', error: '', timeout: '', unavailable: '' };
  function paintOutput(i, res) {
    var el = cellAt(i); if (!el) { return; }
    var box = el.querySelector('[data-role="out"]');
    if (!res) { box.innerHTML = ''; return; }
    var html = '';
    var msgs = [];
    if (res.status === 'timeout') { msgs.push(res.message || '⏱ Kode berjalan terlalu lama dan dihentikan.'); }
    else if (res.status !== 'ok' && res.status !== 'error' && res.message) { msgs.push(res.message); }
    if (msgs.length) { html += '<pre class="out-err">' + esc(msgs.join('\n')) + '</pre>'; }
    if (res.stdout) { html += '<pre class="out-std">' + esc(res.stdout) + '</pre>'; }
    if (res.error) { html += '<pre class="out-err">' + esc(res.error) + '</pre>'; }
    else if (res.stderr) { html += '<pre class="out-err">' + esc(res.stderr) + '</pre>'; }
    if (res.result) {
      html += '<div class="out-res"><span class="outlbl">Out[' + (res.n || '?') + ']:</span><pre>' + esc(res.result) + '</pre></div>';
    }
    if (res.images && res.images.length) {
      for (var k = 0; k < res.images.length; k++) {
        html += '<img class="out-img" src="data:image/png;base64,' + res.images[k] + '" alt="grafik">';
      }
    }
    if (typeof res.ms === 'number' && (res.status === 'ok' || res.status === 'error')) {
      html += '<div class="out-ms">⏱ ' + (res.ms / 1000).toFixed(2) + ' s</div>';
    }
    box.innerHTML = html || '<div class="out-empty">(selesai tanpa output)</div>';
  }

  function setBusy(i, on) {
    var el = cellAt(i); if (!el) { return; }
    el.classList.toggle('running', !!on);
    var b = el.querySelector('.runbtn');
    if (b) { b.disabled = !!on; }
  }

  function focusCell(i) {
    var el = cellAt(i); if (!el) { return; }
    var ta = el.querySelector('.nbtext');
    if (ta) {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = ta.value.length;
      lastFocusIdx = i;
    }
  }

  // ---------- eksekusi ----------
  function runCell(i) {
    syncFromDom(i);
    var c = cells[i];
    if (!c) { return Promise.resolve(); }
    if (c.type === 'md') { updateMdView(i); return Promise.resolve(); }
    var el = cellAt(i);
    var out = el.querySelector('[data-role="out"]');
    setBusy(i, true);
    out.innerHTML = '<div class="runspin">⏳ menjalankan…</div>';
    return fetch(api('/jalankan'), {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf() },
      body: new URLSearchParams({ _csrf: csrf(), code: c.source, cell: String(i) })
    }).then(function (r) { return r.json(); }).then(function (res) {
      setBusy(i, false);
      c.output = res;
      paintOutput(i, res);
      var inc = document.getElementById('in-' + i);
      if (inc && res.n) { inc.textContent = '[' + res.n + ']'; }
      pollKernel();
      scheduleSave();
    }).catch(function () {
      setBusy(i, false);
      out.innerHTML = '<div class="out-err">⚠️ Gagal menghubungi server. Coba lagi.</div>';
    });
  }

  function runAll() {
    var idxs = [];
    for (var i = 0; i < cells.length; i++) { if (cells[i].type === 'code') { idxs.push(i); } }
    var p = Promise.resolve();
    idxs.forEach(function (i) { p = p.then(function () { return runCell(i); }); });
    return p;
  }

  // ---------- simpan ----------
  function cleanCell(c) {
    var o = { type: c.type, source: c.source || '' };
    if (c.output) {
      var out = {};
      ['stdout', 'stderr', 'error'].forEach(function (k) {
        if (c.output[k]) { out[k] = String(c.output[k]).slice(0, 20000); }
      });
      if (c.output.result) { out.result = String(c.output.result).slice(0, 20000); }
      if (c.output.n) { out.n = c.output.n; }
      if (c.output.status) { out.status = c.output.status; }
      if (Object.keys(out).length) { o.output = out; }
    }
    return o;
  }

  function scheduleSave() {
    dirty = true;
    if (saveState) { saveState.textContent = 'menyimpan…'; }
    if (saveTimer) { clearTimeout(saveTimer); }
    saveTimer = setTimeout(saveNow, 1200);
  }

  function saveNow() {
    if (saving) { scheduleSave(); return Promise.resolve(); }
    saving = true;
    syncAll();
    var payload = JSON.stringify({
      judul: titleEl ? titleEl.value : '',
      cells: cells.map(cleanCell)
    });
    return fetch(api('/simpan'), {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf() },
      body: new URLSearchParams({ _csrf: csrf(), payload: payload })
    }).then(function (r) { return r.json(); }).then(function (res) {
      saving = false;
      if (res.ok) {
        dirty = false;
        if (saveState) { saveState.textContent = 'tersimpan ' + (res.saved_wib || '') + ' ✔'; }
      } else if (saveState) {
        saveState.textContent = '⚠️ ' + (res.error || 'gagal simpan');
      }
    }).catch(function () {
      saving = false;
      if (saveState) { saveState.textContent = '⚠️ gagal simpan (koneksi?)'; }
    });
  }

  // ---------- pill kernel ----------
  function setPill(cls, text) {
    if (!kernelPill) { return; }
    kernelPill.className = 'kpill ' + cls;
    kernelPill.textContent = text;
  }

  function pollKernel() {
    fetch(api('/status')).then(function (r) { return r.json(); }).then(function (s) {
      if (s.status === 'unavailable') { setPill('down', '🔴 Kernel mati'); return; }
      if (!s.exists || !s.alive) { setPill('asleep', '⚪ Kernel belum aktif — nyala saat ▶'); return; }
      setPill(s.busy ? 'busy' : 'idle', (s.busy ? '🟠 Sedang jalan…' : '🟢 Kernel siap') + (s.python ? ' · Python ' + s.python : ''));
    }).catch(function () { setPill('down', '🔴 Kernel mati'); });
  }

  // ---------- aksi sel ----------
  function moveCell(i, dir) {
    var j = i + dir;
    if (j < 0 || j >= cells.length) { return; }
    syncAll();
    var tmp = cells[i]; cells[i] = cells[j]; cells[j] = tmp;
    renderCells();
    scheduleSave();
  }

  function toggleMd(i) {
    var el = cellAt(i); if (!el) { return; }
    el.classList.toggle('md-preview');
    if (el.classList.contains('md-preview')) { updateMdView(i); }
    else { focusCell(i); }
  }

  cellsEl.addEventListener('click', function (e) {
    var mv = e.target.closest('[data-role="mdview"]');
    if (mv) {
      toggleMd(parseInt(mv.closest('.nbcell').getAttribute('data-i'), 10));
      return;
    }
    var btn = e.target.closest('button[data-act]');
    if (!btn) { return; }
    var cellEl = btn.closest('.nbcell');
    var i = parseInt(cellEl.getAttribute('data-i'), 10);
    var act = btn.getAttribute('data-act');
    syncAll();
    if (act === 'run') { runCell(i); }
    else if (act === 'up') { moveCell(i, -1); }
    else if (act === 'down') { moveCell(i, 1); }
    else if (act === 'del') {
      cells.splice(i, 1);
      if (!cells.length) { cells.push({ type: 'code', source: '' }); }
      renderCells(); scheduleSave();
    }
    else if (act === 'add') { cells.splice(i + 1, 0, { type: 'code', source: '' }); renderCells(); focusCell(i + 1); scheduleSave(); }
    else if (act === 'preview') { toggleMd(i); }
  });

  cellsEl.addEventListener('input', function (e) {
    var ta = e.target;
    if (!ta.classList || !ta.classList.contains('nbtext')) { return; }
    var cellEl = ta.closest('.nbcell');
    var i = parseInt(cellEl.getAttribute('data-i'), 10);
    if (cells[i]) { cells[i].source = ta.value; }
    scheduleSave();
  });

  cellsEl.addEventListener('focusin', function (e) {
    var cellEl = e.target.closest ? e.target.closest('.nbcell') : null;
    if (cellEl) { lastFocusIdx = parseInt(cellEl.getAttribute('data-i'), 10); }
  });

  cellsEl.addEventListener('keydown', function (e) {
    var ta = e.target;
    if (!ta.classList || !ta.classList.contains('nbtext')) { return; }
    var cellEl = ta.closest('.nbcell');
    var i = parseInt(cellEl.getAttribute('data-i'), 10);
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      syncFromDom(i);
      runCell(i).then(function () {
        if (i === cells.length - 1) {
          cells.push({ type: 'code', source: '' });
          renderCells(); focusCell(cells.length - 1); scheduleSave();
        } else {
          focusCell(i + 1);
        }
      });
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      syncFromDom(i);
      if (e.target.value === undefined) { return; }
      var s = ta.selectionStart, en = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + '    ' + ta.value.slice(en);
      ta.selectionStart = ta.selectionEnd = s + 4;
      syncFromDom(i); scheduleSave();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      var pos = ta.selectionStart;
      var before = ta.value.slice(0, pos);
      var lineStart = before.lastIndexOf('\n') + 1;
      var currentLine = before.slice(lineStart);
      var mm = currentLine.match(/^(\s*)/);
      var indent = mm ? mm[1] : '';
      if (/:\s*$/.test(currentLine)) { indent += '    '; }
      if (indent) {
        e.preventDefault();
        var ins = '\n' + indent;
        ta.value = ta.value.slice(0, pos) + ins + ta.value.slice(ta.selectionEnd);
        ta.selectionStart = ta.selectionEnd = pos + ins.length;
        syncFromDom(i); scheduleSave();
      }
    }
  });

  // ---------- tombol toolbar ----------
  var btnSave = document.getElementById('btnSave');
  if (btnSave) { btnSave.addEventListener('click', function () { saveNow(); }); }
  var btnRunAll = document.getElementById('btnRunAll');
  if (btnRunAll) { btnRunAll.addEventListener('click', function () { runAll(); }); }
  var btnRestart = document.getElementById('btnRestart');
  if (btnRestart) {
    btnRestart.addEventListener('click', function () {
      if (!confirm('Restart kernel? Semua variabel di notebook ini akan direset.')) { return; }
      fetch(api('/restart'), {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrf() },
        body: new URLSearchParams({ _csrf: csrf() })
      }).then(function (r) { return r.json(); }).then(function () {
        for (var i = 0; i < cells.length; i++) {
          if (cells[i].type === 'code') {
            delete cells[i].output;
            paintOutput(i, null);
            var inc = document.getElementById('in-' + i);
            if (inc) { inc.textContent = '[ ]'; }
          }
        }
        setPill('asleep', '⚪ Kernel direset');
        scheduleSave();
      }).catch(function () { setPill('down', '🔴 Kernel mati'); });
    });
  }
  var btnAddCode = document.getElementById('btnAddCode');
  if (btnAddCode) { btnAddCode.addEventListener('click', function () { cells.push({ type: 'code', source: '' }); renderCells(); focusCell(cells.length - 1); scheduleSave(); }); }
  var btnAddMd = document.getElementById('btnAddMd');
  if (btnAddMd) { btnAddMd.addEventListener('click', function () { cells.push({ type: 'md', source: '' }); renderCells(); focusCell(cells.length - 1); scheduleSave(); }); }

  // ---------- datasets rail ----------
  var dslist = document.getElementById('dslist');
  if (dslist) {
    dslist.addEventListener('click', function (e) {
      var b = e.target.closest('.dsitem');
      if (!b) { return; }
      var name = b.getAttribute('data-ds');
      var snippet = "import pandas as pd\n\ndf = pd.read_csv('/datasets/" + name + "')\ndf.head()";
      insertIntoActive(snippet);
    });
  }

  // ---------- uploads rail (file upload user) ----------
  var uplist = document.getElementById('uplist');
  if (uplist) {
    uplist.addEventListener('click', function (e) {
      var b = e.target.closest('.dsitem');
      if (!b) { return; }
      var uname = b.getAttribute('data-up');
      var usnip = "import pandas as pd\n\ndf = pd.read_csv('/work/uploads/" + uname + "')\ndf.head()";
      insertIntoActive(usnip);
    });
  }

  function insertIntoActive(text) {
    syncAll();
    var i = lastFocusIdx;
    if (i === null || !cells[i] || cells[i].type !== 'code') {
      i = null;
      for (var j = cells.length - 1; j >= 0; j--) {
        if (cells[j].type === 'code') { i = j; break; }
      }
    }
    if (i === null) {
      cells.push({ type: 'code', source: text });
      renderCells(); focusCell(cells.length - 1); scheduleSave();
      return;
    }
    var cur = cells[i].source || '';
    cells[i].source = (cur.replace(/\s+$/, '') ? cur.replace(/\s+$/, '') + '\n\n' : '') + text;
    // renderCells() memanggil syncAll() -> baca nilai DOM; tulis dulu ke textarea
    // supaya hasil sisipan tidak tertimpa nilai lama (bug: sisipan hilang sebelum ini).
    var elI = cellAt(i), taI = elI && elI.querySelector('.nbtext');
    if (taI) { taI.value = cells[i].source; }
    renderCells(); focusCell(i);
    scheduleSave();
  }

  // ---------- judul & autosave judul ----------
  if (titleEl) {
    titleEl.addEventListener('input', function () { scheduleSave(); });
  }
  window.addEventListener('beforeunload', function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  // ---------- init ----------
  renderCells();
  pollKernel();
  setInterval(pollKernel, 15000);
})(typeof window !== 'undefined' ? window : globalThis);
