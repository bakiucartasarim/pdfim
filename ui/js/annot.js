/* Açıklama & Not modu — vurgu, altı/üstü çizili, not, dikdörtgen, elips, çizgi, ok, serbest çizim.
 *
 * Hepsi standart PDF açıklama nesnesi (Acrobat, Edge'de de ayrı öğe). Seçili açıklama
 * nesneyle değil xref'le tutulur: renk değişince sayfa yenilenir ama seçim kaybolmaz,
 * silinen açıklama kendiliğinden seçimden düşer.
 */
'use strict';

const ANNOT_COLORS = [['#facc15', 'Sarı'], ['#4ade80', 'Yeşil'], ['#f472b6', 'Pembe'],
                      ['#60a5fa', 'Mavi'], ['#ef4444', 'Kırmızı'], ['#111827', 'Siyah']];
const ANNOT_DEFAULT = { highlight: '#facc15', underline: '#ef4444', strikeout: '#ef4444', note: '#facc15',
                        rect: '#ef4444', ellipse: '#ef4444', line: '#ef4444', arrow: '#ef4444', ink: '#2563eb' };
const ANNOT_NAMES = { highlight: 'Vurgu', underline: 'Altı çizili', strikeout: 'Üstü çizili', squiggly: 'Dalgalı çizgi',
                      note: 'Not', freetext: 'Metin kutusu', rect: 'Dikdörtgen', ellipse: 'Elips', line: 'Çizgi / ok',
                      ink: 'Serbest çizim', polygon: 'Çokgen', polyline: 'Çoklu çizgi', stamp: 'Damga' };
const ANNOT_ICONS = { highlight: 'ink_highlighter', underline: 'format_underlined', strikeout: 'strikethrough_s',
                      squiggly: 'format_underlined_squiggle', note: 'sticky_note_2', freetext: 'text_fields',
                      rect: 'rectangle', ellipse: 'circle', line: 'arrow_right_alt', ink: 'draw',
                      polygon: 'pentagon', polyline: 'polyline', stamp: 'approval' };
const ANNOT_HINTS = {
  secim: 'Açıklamaya tıklayın: seç · Kutu türlerini sürükleyerek taşıyın · Del: sil',
  highlight: 'Vurgulanacak metnin üstünden sürükleyin', underline: 'Altı çizilecek metnin üstünden sürükleyin',
  strikeout: 'Üstü çizilecek metnin üstünden sürükleyin', note: 'Not eklenecek yere tıklayın',
  rect: 'Dikdörtgen için sürükleyin', ellipse: 'Elips için sürükleyin', line: 'Çizgi için sürükleyin',
  arrow: 'Ok için başlangıçtan uca doğru sürükleyin', ink: 'Serbestçe çizin',
};

app.annotTool = 'secim';
app.annotColors = {};        // araç → seçilen renk (hex)
app.annotWidth = 2;
app.annotSel = null;         // { page, xref }
app.annotHover = null;       // { page, xref }
let adrag = null;
let notePop = null;

const hexInt = (h) => parseInt(h.slice(1), 16);
const toolColor = (t = app.annotTool) => app.annotColors[t] || ANNOT_DEFAULT[t] || '#ef4444';

function annotItem(ref) {
  if (!ref) return null;
  const d = layerData(ref.page);
  return d && d.annots ? d.annots.find((a) => a.xref === ref.xref) || null : null;
}

function annotAt(d, x, y) {
  const pad = 4 / k();
  const list = (d && d.annots) || [];
  for (let n = list.length - 1; n >= 0; n--) {          // en son eklenen üstte
    if (inRect(list[n].rect, x, y, pad)) return list[n];
  }
  return null;
}

/* ── Araç ve şerit ────────────────────────────────────────────────────────── */

function setAnnotTool(t) {
  closeNotePop(false);
  app.annotTool = t;
  document.querySelectorAll('#annot-strip [data-atool]').forEach((b) => b.classList.toggle('is-active', b.dataset.atool === t));
  $('pages').dataset.atool = t;
  syncSwatches();
  updateStatus();
}

function syncSwatches() {
  const sel = annotItem(app.annotSel);
  const cur = app.annotTool === 'secim' && sel && sel.color != null ? `#${sel.color.toString(16).padStart(6, '0')}` : toolColor();
  document.querySelectorAll('#annot-colors [data-color]').forEach((b) => b.classList.toggle('is-active', b.dataset.color === cur));
}

function pickColor(c) {
  const sel = annotItem(app.annotSel);
  if (app.annotTool === 'secim' && sel) {               // seçili açıklamanın rengini değiştir
    mutate(() => api().update_annot(app.annotSel.page, sel.xref, { color: hexInt(c) }), 'Renk değişti');
  } else {
    app.annotColors[app.annotTool] = c;
  }
  syncSwatches();
}

function annotHint() { return ANNOT_HINTS[app.annotTool]; }

function selectAnnot(ref) {
  const prev = app.annotSel;
  app.annotSel = ref;
  if (prev) renderLayer(prev.page);
  if (ref && (!prev || prev.page !== ref.page)) renderLayer(ref.page);
  syncSwatches();
  renderInspector();
}

/* ── Fare (layer.js buraya yönlendirir) ───────────────────────────────────── */

function annotDown(e, i, layer, x, y) {
  const t = app.annotTool, d = layerData(i);
  if (t === 'secim') {
    const a = annotAt(d, x, y);
    selectAnnot(a ? { page: i, xref: a.xref } : null);
    if (a && a.movable) { adrag = { kind: 'move', page: i, start: [x, y], orig: a.rect, xref: a.xref, cur: null }; capture(layer, e); }
    return;
  }
  if (t === 'note') { setTimeout(() => openNotePop(i, x, y), 0); return; }
  selectAnnot(null);
  if (t === 'ink') adrag = { kind: 'ink', page: i, points: [[x, y]] };
  else adrag = { kind: ['highlight', 'underline', 'strikeout'].includes(t) ? 'marquee' : 'shape', page: i, start: [x, y], cur: null };
  capture(layer, e);
}

function annotMove(e, i, layer, x, y) {
  if (!adrag) {                                          // üzerine gelince vurgula
    if (app.annotTool !== 'secim') return;
    const a = annotAt(layerData(i), x, y);
    layer.style.cursor = a ? (a.movable ? 'move' : 'pointer') : '';
    const h = a ? { page: i, xref: a.xref } : null;
    if ((h && h.xref) !== (app.annotHover && app.annotHover.xref)) { app.annotHover = h; renderLayer(i); }
    return;
  }
  if (adrag.page !== i) return;
  if (adrag.kind === 'ink') {
    const last = adrag.points[adrag.points.length - 1];
    if (Math.hypot(x - last[0], y - last[1]) * k() >= 2) adrag.points.push([x, y]);
  } else {
    adrag.cur = [x, y];
  }
  renderLayer(i);
}

function annotUp(e, i, layer) {
  const d = adrag;
  if (!d || d.page !== i) return;
  adrag = null;
  if (layer.hasPointerCapture(e.pointerId)) layer.releasePointerCapture(e.pointerId);
  renderLayer(i);
  const color = hexInt(toolColor()), w = app.annotWidth, t = app.annotTool;
  const tiny = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]) * k() < 4;
  if (d.kind === 'move') {
    if (!d.cur || tiny(d.start, d.cur)) return;
    const dx = d.cur[0] - d.start[0], dy = d.cur[1] - d.start[1], r = d.orig;
    mutate(() => api().update_annot(i, d.xref, { rect: [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy] }), 'Taşındı');
  } else if (d.kind === 'marquee') {
    if (!d.cur || tiny(d.start, d.cur)) return;
    const msg = { highlight: 'Vurgulandı', underline: 'Altı çizildi', strikeout: 'Üstü çizildi' }[t];
    mutate(() => api().add_markup(i, normRect(d.start, d.cur), t, color), msg, true);
  } else if (d.kind === 'shape') {
    if (!d.cur || tiny(d.start, d.cur)) return;
    mutate(() => api().add_shape(i, t, d.start, d.cur, color, w), `${ANNOT_NAMES[t === 'arrow' ? 'line' : t]} eklendi`, true);
  } else if (d.kind === 'ink') {
    if (d.points.length < 2) return;
    mutate(() => api().add_ink(i, [d.points], color, w), '', true);
  }
}

/* ── Çizim (renderLayer'dan) ──────────────────────────────────────────────── */

function renderAnnots(i, add) {
  if (app.mode !== 'aciklama') return;
  const kk = k();
  const hov = app.annotHover && app.annotHover.page === i ? annotItem(app.annotHover) : null;
  const sel = app.annotSel && app.annotSel.page === i ? annotItem(app.annotSel) : null;
  if (hov && hov !== sel) add(boxEl('annot-hover', padRect(hov.rect, 2)));
  const d = adrag && adrag.page === i ? adrag : null;
  if (sel) {
    let r = sel.rect;
    if (d && d.kind === 'move' && d.cur) {
      const dx = d.cur[0] - d.start[0], dy = d.cur[1] - d.start[1];
      r = [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy];
    }
    add(boxEl('annot-sel', padRect(r, 2)));
  }
  if (!d || d.kind === 'move') return;
  const c = toolColor();
  if (d.kind === 'marquee' && d.cur) {
    const m = add(boxEl('annot-marquee', normRect(d.start, d.cur)));
    m.style.setProperty('--c', c);
    return;
  }
  // Çizgi, ok, elips, serbest çizim: SVG önizleme
  const svg = add(document.createElementNS('http://www.w3.org/2000/svg', 'svg'));
  svg.classList.add('annot-preview');
  const sw = app.annotWidth * kk;
  const P = (p) => `${p[0] * kk},${p[1] * kk}`;
  let shape;
  if (d.kind === 'ink') {
    shape = document.createElementNS(svg.namespaceURI, 'polyline');
    shape.setAttribute('points', d.points.map(P).join(' '));
  } else if (d.cur) {
    const t = app.annotTool, [x0, y0, x1, y1] = normRect(d.start, d.cur);
    if (t === 'rect') {
      shape = document.createElementNS(svg.namespaceURI, 'rect');
      Object.entries({ x: x0 * kk, y: y0 * kk, width: (x1 - x0) * kk, height: (y1 - y0) * kk })
        .forEach(([a, v]) => shape.setAttribute(a, v));
    } else if (t === 'ellipse') {
      shape = document.createElementNS(svg.namespaceURI, 'ellipse');
      Object.entries({ cx: (x0 + x1) / 2 * kk, cy: (y0 + y1) / 2 * kk, rx: (x1 - x0) / 2 * kk, ry: (y1 - y0) / 2 * kk })
        .forEach(([a, v]) => shape.setAttribute(a, v));
    } else {
      shape = document.createElementNS(svg.namespaceURI, 'polyline');
      const pts = [d.start, d.cur];
      if (t === 'arrow') {                               // ok ucu: uca doğru iki kısa kanat
        const [a, b] = pts, ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = 10 / kk + app.annotWidth * 2;
        const wing = (s) => [b[0] - L * Math.cos(ang + s * 0.45), b[1] - L * Math.sin(ang + s * 0.45)];
        pts.push(wing(1), b, wing(-1));
      }
      shape.setAttribute('points', pts.map(P).join(' '));
    }
  }
  if (!shape) return;
  Object.entries({ fill: 'none', stroke: c, 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })
    .forEach(([a, v]) => shape.setAttribute(a, v));
  svg.append(shape);
}

/* ── Not ekleme kutusu ────────────────────────────────────────────────────── */

function openNotePop(i, x, y) {
  closeNotePop(false);
  const layer = app.pageEls[i].querySelector('.layer'), kk = k();
  const box = document.createElement('div');
  box.className = 'note-pop';
  box.style.left = `${x * kk}px`;
  box.style.top = `${y * kk}px`;
  box.innerHTML = '<textarea placeholder="Notunuzu yazın…" rows="4"></textarea>'
    + '<div class="note-pop-bar"><span class="muted">Ctrl+Enter: ekle</span><span class="strip-spacer"></span>'
    + '<button type="button" class="btn btn-ghost" data-act="cancel">Vazgeç</button>'
    + '<button type="button" class="btn btn-primary" data-act="add">Ekle</button></div>';
  layer.append(box);
  notePop = { page: i, x, y, box };
  const ta = box.querySelector('textarea');
  box.addEventListener('pointerdown', (e) => e.stopPropagation());
  box.querySelector('[data-act=cancel]').addEventListener('click', () => closeNotePop(false));
  box.querySelector('[data-act=add]').addEventListener('click', () => closeNotePop(true));
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); closeNotePop(true); }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeNotePop(false); }
  });
  ta.focus();
}

function closeNotePop(commit) {
  if (!notePop) return;
  const p = notePop;
  notePop = null;
  const text = p.box.querySelector('textarea').value.trim();
  p.box.remove();
  if (!commit) return;
  if (!text) return toast('Not boş, eklenmedi.');
  const color = hexInt(toolColor('note'));
  mutate(() => api().add_note(p.page, p.x, p.y, text, color), 'Not eklendi');
}

/* ── İşlemler, klavye, panel ──────────────────────────────────────────────── */

function deleteSelectedAnnot() {
  const a = annotItem(app.annotSel);
  if (!a) return false;
  const page = app.annotSel.page;
  selectAnnot(null);
  mutate(() => api().delete_annot(page, a.xref), `${ANNOT_NAMES[a.kind] || 'Açıklama'} silindi`);
  return true;
}

function onAnnotKey(e) {
  if (e.key === 'Delete' || e.key === 'Backspace') return deleteSelectedAnnot();
  if (e.key === 'Escape') {
    if (notePop) { closeNotePop(false); return true; }
    if (app.annotSel) { selectAnnot(null); return true; }
  }
  return false;
}

function bindAnnot() {
  document.querySelectorAll('#annot-strip [data-atool]').forEach((b) => b.addEventListener('click', () => setAnnotTool(b.dataset.atool)));
  const pal = $('annot-colors');
  for (const [c, name] of ANNOT_COLORS) {
    const b = document.createElement('button');
    b.type = 'button';
    b.dataset.color = c;
    b.title = name;
    b.style.setProperty('--c', c);
    b.addEventListener('click', () => pickColor(c));
    pal.append(b);
  }
  $('annot-width').addEventListener('change', (e) => { app.annotWidth = +e.target.value; });
  setAnnotTool('secim');
}

function renderAnnotInspector(body) {
  const sel = annotItem(app.annotSel);
  if (sel) {
    const sw = document.createElement('div');
    sw.className = 'annot-swatches';
    for (const [c, name] of ANNOT_COLORS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.title = name;
      b.style.setProperty('--c', c);
      b.classList.toggle('is-active', sel.color === hexInt(c));
      b.addEventListener('click', () => pickColor(c));
      sw.append(b);
    }
    const ta = document.createElement('textarea');
    ta.className = 'fmt-input annot-content';
    ta.rows = 4;
    ta.value = sel.content || '';
    ta.placeholder = sel.kind === 'note' ? 'Not metni' : 'Yorum (isteğe bağlı)';
    const ref = { ...app.annotSel };
    const save = btn('save', 'Kaydet', () => {
      if (ta.value !== (sel.content || '')) mutate(() => api().update_annot(ref.page, sel.xref, { content: ta.value }), 'Kaydedildi');
    });
    body.append(
      section(ANNOT_NAMES[sel.kind] || 'Açıklama', [
        row('Sayfa', String(app.annotSel.page + 1)),
        ...(sel.author ? [row('Ekleyen', sel.author)] : []),
      ]),
      section('Renk', [sw]),
      section(sel.kind === 'note' ? 'Not' : 'Yorum', [ta]),
      actions([save, btn('delete', 'Sil', deleteSelectedAnnot, false, true)]),
      note(sel.movable ? 'Sürükleyerek taşıyabilirsiniz · Del: sil' : 'Del: sil'),
    );
    return;
  }
  const all = [];
  app.layers.forEach((e, page) => { if (e.data && e.data.annots) e.data.annots.forEach((a) => all.push({ ...a, page })); });
  all.sort((a, b) => a.page - b.page || a.rect[1] - b.rect[1]);
  const list = document.createElement('div');
  list.className = 'field-list';
  for (const a of all.slice(0, 80)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'field-item';
    b.innerHTML = '<span class="field-name"><span class="ms"></span><span></span></span><span class="field-val"></span>';
    b.querySelector('.ms').textContent = ANNOT_ICONS[a.kind] || 'label';
    b.querySelector('.field-name span:last-child').textContent = `${ANNOT_NAMES[a.kind] || a.kind} · s.${a.page + 1}`;
    b.querySelector('.field-val').textContent = a.content || '';
    b.addEventListener('click', () => {
      setAnnotTool('secim');
      scrollToPage(a.page, 'auto');
      selectAnnot({ page: a.page, xref: a.xref });
    });
    list.append(b);
  }
  body.append(
    section('Açıklamalar', all.length ? [row('Görünen sayfalarda', String(all.length)), list]
      : [note('Görünen sayfalarda açıklama yok. Şeritten bir araç seçin.')]),
    note('Açıklamalar standart PDF nesneleridir: Acrobat, Edge gibi programlarda da görünür, taşınır, silinir.'),
  );
}
