// QuantLab — JS ringan
document.addEventListener('DOMContentLoaded', () => {
  // Petunjuk skenario
  const hintBtn = document.getElementById('hintbtn');
  const hints = document.getElementById('hints');
  if (hintBtn && hints) {
    hintBtn.addEventListener('click', () => hints.classList.toggle('hidden'));
  }

  // Validasi form skenario
  const form = document.getElementById('scenform');
  if (form) {
    form.addEventListener('submit', e => {
      if (!form.querySelector('input[name="choice"]:checked')) {
        e.preventDefault();
        alert('Pilih dulu salah satu keputusan.');
      }
    });
  }

  // Tombol "Saya Paham" — +5 XP sekali per pelajaran
  document.querySelectorAll('button.paham').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.classList.contains('done')) return;
      const lid = btn.dataset.lid;
      const csrf = document.getElementById('csrf')?.value || '';
      const base = window.QL_BASE || '';
      try {
        const r = await fetch(base + '/api/lesson/' + lid + '/done', {
          method: 'POST',
          headers: { 'X-CSRF-Token': csrf },
          body: new URLSearchParams({ _csrf: csrf })
        });
        const j = await r.json();
        if (j.ok && j.inserted) {
          btn.classList.add('done');
          btn.textContent = '✓ Selesai (+' + j.xp + ' XP)';
          const badge = document.querySelector('details[data-lid="' + lid + '"] .donebadge');
          if (!badge) {
            const sum = document.querySelector('details[data-lid="' + lid + '"] summary');
            sum.insertAdjacentHTML('beforeend', ' <span class="donebadge">✓ +5 XP</span>');
          }
          // update XP di topbar
          const chip = document.querySelector('.chip.xp');
          if (chip) {
            const m = chip.textContent.match(/(\d+)/);
            if (m) chip.textContent = (parseInt(m[1]) + j.xp) + ' XP';
          }
        }
      } catch (e) { /* offline / error — biarkan tombol tetap aktif */ }
    });
  });

  // Syntax highlighting kode Python (ringan, tanpa dependency)
  document.querySelectorAll('pre.block-code code').forEach(el => {
    const code = el.textContent;
    const esc = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const html = esc
      .replace(/\b(0x[0-9a-fA-F]+|\d+\.?\d*)\b/g, '<span class="tok-num">$1</span>')
      .replace(/(&quot;|")(?:[^"\\]|\\.)*\1|(')(?:[^'\\]|\\.)*\2/g, '<span class="tok-str">$&</span>')
      .replace(/(#.*)$/gm, '<span class="tok-com">$1</span>')
      .replace(/\b(def|return|if|elif|else|for|while|import|from|print|class|try|except|and|or|not|in|is|None|True|False|lambda|with|as|pass|break|continue|range|len|sum|min|max|abs|round|int|float|str|list|dict|set|math|random|datetime)\b/g, '<span class="tok-kw">$1</span>');
    el.innerHTML = html;
  });
});
