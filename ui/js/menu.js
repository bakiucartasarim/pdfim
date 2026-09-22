/* Sağ tık menüsü. Öğeler: { icon, label, hint, disabled, danger, run } ya da '-' (ayraç). */
'use strict';

function showMenu(x, y, items) {
  const m = $('ctx-menu');
  m.replaceChildren();
  for (const it of items) {
    if (it === '-') {
      const sep = document.createElement('div');
      sep.className = 'menu-sep';
      m.append(sep);
      continue;
    }
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'menu-item' + (it.danger ? ' is-danger' : '');
    b.disabled = !!it.disabled;
    b.innerHTML = `<span class="ms">${it.icon || ''}</span><span class="menu-label"></span><span class="menu-hint"></span>`;
    b.querySelector('.menu-label').textContent = it.label;
    b.querySelector('.menu-hint').textContent = it.hint || '';
    // Düzenleme kutusundan odak çalınmasın (ör. sembol menüsü)
    b.addEventListener('mousedown', (e) => e.preventDefault());
    b.addEventListener('click', () => { hideMenu(); it.run(); });
    m.append(b);
  }
  m.classList.add('is-open');
  // Pencere kenarından taşmasın
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = `${Math.max(4, Math.min(x, innerWidth - w - 4))}px`;
  m.style.top = `${Math.max(4, Math.min(y, innerHeight - h - 4))}px`;
}

function hideMenu() {
  $('ctx-menu').classList.remove('is-open');
}

function menuOpen() { return $('ctx-menu').classList.contains('is-open'); }

document.addEventListener('pointerdown', (e) => {
  if (menuOpen() && !e.target.closest('#ctx-menu')) hideMenu();
}, true);
window.addEventListener('blur', hideMenu);
