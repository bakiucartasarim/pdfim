/* Sağ panel — seçili metnin / resmin özellikleri ve hızlı işlemleri. */
'use strict';

function renderInspector() {
  const body = $('inspector-body');
  body.replaceChildren();
  const sel = app.sel;

  if (!app.doc) {
    body.append(note('Bir PDF açın.'));
    return;
  }
  if (!sel) {
    const [w, h] = app.doc.pages[app.current];
    body.append(
      section('Sayfa', [
        row('Sayfa', `${app.current + 1} / ${app.doc.pages.length}`),
        row('Boyut', `${mm(w)} × ${mm(h)} mm`),
      ]),
      note('Bir metin ya da resim seçildiğinde özellikleri burada görünür.'),
    );
    return;
  }

  const it = sel.item, r = it.rect;
  if (sel.type === 'span') {
    const text = it.text.replace(/\xa0/g, ' ').trim();
    const swatch = document.createElement('span');
    swatch.className = 'swatch';
    swatch.style.background = hex(it.color);
    body.append(
      section('Metin', [
        quote(text.length > 120 ? text.slice(0, 119) + '…' : text),
        row('Font', it.family || it.font.split('+').pop()),
        row('Punto', String(+it.size.toFixed(1)).replace('.', ',')),
        row('Renk', hex(it.color).toUpperCase(), swatch),
        row('Konum', `${mm(r[0])} ; ${mm(r[1])} mm`),
      ]),
      actions([
        btn('edit', 'Düzenle', () => openEditor(sel.page, it, null), true),
        btn('content_copy', 'Kopyala', () => copyText('span', sel.page, it)),
      ]),
    );
  } else {
    const grid = document.createElement('div');
    grid.className = 'align-grid';
    for (const [icon, how, tip] of [
      ['align_horizontal_left', 'left', 'Sola hizala'], ['align_horizontal_center', 'hcenter', 'Yatay ortala'],
      ['align_horizontal_right', 'right', 'Sağa hizala'], ['align_vertical_top', 'top', 'Üste hizala'],
      ['align_vertical_center', 'vcenter', 'Dikey ortala'], ['align_vertical_bottom', 'bottom', 'Alta hizala'],
    ]) {
      const b = iconBtn(icon, tip, () => alignImage(sel.page, it, how));
      grid.append(b);
    }
    body.append(
      section('Resim', [
        row('Boyut', `${mm(r[2] - r[0])} × ${mm(r[3] - r[1])} mm`),
        row('Piksel', `${it.w} × ${it.h}`),
        row('Konum', `${mm(r[0])} ; ${mm(r[1])} mm`),
      ]),
      section('Hizalama', [grid]),
      note('Sürükleyince kılavuzlara yapışır · Alt → serbest · Köşeden boyutlandırırken Shift → oransız'),
      actions([btn('delete', 'Resmi sil', () => deleteImage(sel.page, it), false, true)]),
    );
  }
}

/* ── Küçük yapı taşları ───────────────────────────────────────────────────── */

function section(title, children) {
  const s = document.createElement('section');
  s.className = 'insp-section';
  const h = document.createElement('div');
  h.className = 'caps';
  h.textContent = title;
  s.append(h, ...children);
  return s;
}

function row(label, value, extra) {
  const r = document.createElement('div');
  r.className = 'insp-row';
  const l = document.createElement('span');
  l.textContent = label;
  const v = document.createElement('span');
  v.className = 'insp-value';
  if (extra) v.append(extra);
  v.append(document.createTextNode(value));
  r.append(l, v);
  return r;
}

function quote(text) {
  const q = document.createElement('div');
  q.className = 'insp-quote';
  q.textContent = text;
  return q;
}

function note(text) {
  const p = document.createElement('p');
  p.className = 'muted';
  p.textContent = text;
  return p;
}

function actions(buttons) {
  const d = document.createElement('div');
  d.className = 'insp-actions';
  d.append(...buttons);
  return d;
}

function btn(icon, label, run, primary = false, danger = false) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `btn${primary ? ' btn-primary' : ''}${danger ? ' btn-danger' : ''}`;
  b.innerHTML = `<span class="ms">${icon}</span><span></span>`;
  b.lastChild.textContent = label;
  b.addEventListener('click', run);
  return b;
}

function iconBtn(icon, title, run) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'icon-btn';
  b.title = title;
  b.innerHTML = `<span class="ms">${icon}</span>`;
  b.addEventListener('click', run);
  return b;
}
