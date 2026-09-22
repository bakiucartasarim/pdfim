/* Sayfa katmanı — her sayfanın üstündeki saydam etkileşim alanı (v1 viewer.PageLabel karşılığı).
 *
 * Seçim aracı: metne tıkla → seç, sürükle → taşı, çift tıkla → düzenle; resme tıkla → seç,
 *   sürükle → taşı, tutamaçlar → boyutlandır (köşeler oranı korur, Shift → oransız),
 *   sayfa/metin kenarlarına ve diğer resimlere yapışır (Alt → serbest).
 * Metin aracı: boş yere tıkla → yeni yazı, metne tıkla → düzenle.
 * Metin Seç / Alan Sil: alan sürükle.
 */
'use strict';

const SNAP_PX = 6;          // bu kadar piksel yakına gelince kılavuza yapışır
const DRAG_START_PX = 4;    // tıklama ile sürüklemeyi ayırmak için
const HANDLE_PX = 7;
const HANDLES = { nw: 'nwse-resize', n: 'ns-resize', ne: 'nesw-resize', e: 'ew-resize',
                  se: 'nwse-resize', s: 'ns-resize', sw: 'nesw-resize', w: 'ew-resize' };

/* ── Veri ─────────────────────────────────────────────────────────────────── */

/** Sayfanın metin/resim kutularını (gerekirse) getir; sürüm değiştiyse yeniden */
function fetchLayer(i) {
  if (!app.doc) return Promise.resolve(null);
  const v = app.doc.versions[i];
  const cur = app.layers.get(i);
  if (cur && cur.version === v) return cur.promise;
  const entry = { version: v, data: null };
  entry.promise = api().page_layer(i).then((data) => {
    if (app.layers.get(i) !== entry) return null;   // bu arada sayfa yine değişti
    entry.data = data;
    renderLayer(i);
    return data;
  });
  app.layers.set(i, entry);
  return entry.promise;
}

function layerData(i) {
  const e = app.layers.get(i);
  return e && app.doc && e.version === app.doc.versions[i] ? e.data : null;
}

/* ── Seçim ────────────────────────────────────────────────────────────────── */

function setSelection(sel) {
  const prev = app.sel;
  app.sel = sel;
  if (prev) renderLayer(prev.page);
  if (sel && (!prev || prev.page !== sel.page)) renderLayer(sel.page);
  renderInspector();
}

/** Yeni eklenen / taşınan resmi seçili getir: sayfa yenilenince kutuya en yakın resim */
async function selectImageNear(i, rect) {
  const d = await fetchLayer(i);
  if (!d || !d.images.length) return;
  const c = center(rect);
  const dist = (img) => { const m = center(img.rect); return Math.abs(m[0] - c[0]) + Math.abs(m[1] - c[1]); };
  setSelection({ type: 'image', page: i, item: d.images.reduce((a, b) => (dist(a) <= dist(b) ? a : b)) });
}

function clearTransient() {
  app.hover = null;
  app.highlight = null;
  app.drag = null;
  setSelection(null);
  renderAllLayers();
}

/* ── Çizim ────────────────────────────────────────────────────────────────── */

function renderAllLayers() {
  app.pageEls.forEach((_, i) => renderLayer(i));
}

function renderLayer(i) {
  const page = app.pageEls[i];
  if (!page) return;
  const layer = page.querySelector('.layer');
  // Düzenleme kutusu ve biçim çubuğu kalıcı; gerisi her seferinde yeniden kurulur
  layer.querySelectorAll('.lx').forEach((el) => el.remove());
  const add = (el) => { el.classList.add('lx'); layer.append(el); return el; };
  const kk = k();

  if (app.highlight && app.highlight.page === i) {
    for (const r of app.highlight.rects) add(boxEl('word-hl', [r[0] - 1, r[1], r[2] + 1, r[3]]));
  }
  if (app.hover && app.hover.page === i && !app.drag) {
    add(boxEl(`hover-box is-${app.hover.kind}`, app.hover.rect));
  }

  const dr = app.drag && app.drag.page === i ? app.drag : null;
  if (app.sel && app.sel.page === i) {
    if (app.sel.type === 'span') {
      add(boxEl('sel-span', padRect(app.sel.item.rect, 1)));
      if (dr && dr.kind === 'text' && dr.cur) add(boxEl('drag-ghost', dr.cur));
    } else {
      const r = dr && dr.cur && (dr.kind === 'move' || dr.kind === 'resize') ? dr.cur : app.sel.item.rect;
      const box = add(boxEl('img-box is-selected', r));
      for (const [name, [hx, hy]] of Object.entries(handlePositions(r))) {
        const h = document.createElement('div');
        h.className = 'handle';
        h.style.left = `${(hx - r[0]) * kk}px`;
        h.style.top = `${(hy - r[1]) * kk}px`;
        h.style.cursor = HANDLES[name];
        box.append(h);
      }
    }
  }
  if (dr && dr.guides) {
    for (const [kind, v] of dr.guides) {
      const g = add(document.createElement('div'));
      g.className = `guide guide-${kind} lx`;
      g.style[kind === 'v' ? 'left' : 'top'] = `${v * kk}px`;
    }
  }
  if (dr && dr.kind === 'marquee' && dr.cur) {
    add(boxEl(`marquee${app.tool === 'alan-sil' ? ' is-erase' : ''}`, normRect(dr.start, dr.cur)));
  }
  if (app.placing && app.placing.pos && app.placing.pos.page === i) renderPlacement(add, app.placing);
}

function renderPlacement(add, pl) {
  const { x, y, snap } = pl.pos, info = pl.info, kk = k();
  if (snap) {
    const g = add(document.createElement('div'));
    g.className = 'guide guide-v lx';
    g.style.left = `${x * kk}px`;
  }
  const ghost = add(document.createElement('div'));
  ghost.className = 'place-ghost';
  const px = info.size * kk;
  Object.assign(ghost.style, {
    left: `${x * kk}px`, top: `${(y - info.size * 0.8) * kk}px`,
    fontFamily: `"${info.family}", Arial, sans-serif`, fontSize: `${px}px`,
    lineHeight: `${px * 1.25}px`,   // editor.insert_new_text ile aynı satır aralığı
    fontWeight: info.bold ? 700 : 400, color: hex(info.color),
  });
  ghost.textContent = info.lines.slice(0, 60).join('\n');
  // Taban çizgisi işareti: metin tam bu çizginin üstüne oturur
  const base = add(document.createElement('div'));
  base.className = 'place-base';
  base.style.left = `${x * kk - 6}px`;
  base.style.top = `${y * kk}px`;
}

/* ── Geometri ─────────────────────────────────────────────────────────────── */

const center = (r) => [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2];
const inRect = (r, x, y, pad = 0) => r[0] - pad <= x && x <= r[2] + pad && r[1] - pad <= y && y <= r[3] + pad;
const padRect = (r, p) => [r[0] - p, r[1] - p, r[2] + p, r[3] + p];
const normRect = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];

function handlePositions(r) {
  const [x0, y0, x1, y1] = r, mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  return { nw: [x0, y0], n: [mx, y0], ne: [x1, y0], e: [x1, my],
           se: [x1, y1], s: [mx, y1], sw: [x0, y1], w: [x0, my] };
}

function spanAt(d, x, y) {
  const pad = 3 / k();
  return d.spans.find((s) => inRect(s.rect, x, y, pad)) || null;
}

function imageAt(d, x, y) {
  return d.images.find((img) => inRect(img.rect, x, y)) || null;
}

/** Seçim aracının isabet testi: metin ve resim üst üste binmişse ekranda üstte çizilen
 *  (Python'dan gelen çizim sırası "z") kazanır → { span } | { img } | {} */
function pickAt(d, x, y) {
  const span = spanAt(d, x, y), img = imageAt(d, x, y);
  if (span && img) return img.z > span.z ? { img } : { span };
  return span ? { span } : img ? { img } : {};
}

function handleAt(r, x, y) {
  const t = HANDLE_PX / k();
  for (const [name, [hx, hy]] of Object.entries(handlePositions(r))) {
    if (Math.abs(x - hx) <= t && Math.abs(y - hy) <= t) return name;
  }
  return null;
}

function ptAt(e, layer) {
  const r = layer.getBoundingClientRect(), kk = k();
  return [(e.clientX - r.left) / kk, (e.clientY - r.top) / kk];
}

/* ── Hizalama / yapışma ───────────────────────────────────────────────────── */

/** Sayfa kenar/orta çizgileri + metin blokları + diğer resimlerin kenar ve merkezleri */
function snapTargets(d, except) {
  const xs = [...d.snapX], ys = [...d.snapY];
  for (const img of d.images) {
    if (except && img.xref === except.xref && img.rect.join() === except.rect.join()) continue;
    const [x0, y0, x1, y1] = img.rect;
    xs.push(x0, (x0 + x1) / 2, x1);
    ys.push(y0, (y0 + y1) / 2, y1);
  }
  return [xs, ys];
}

/** values içinden bir değerin eşik içinde kalan en yakın hedefi → [kaydırma, hedef] */
function nearest(values, targets) {
  const lim = SNAP_PX / k();
  let best = null;
  for (const v of values) {
    for (const t of targets) {
      const dd = t - v;
      if (Math.abs(dd) <= lim && (!best || Math.abs(dd) < Math.abs(best[0]))) best = [dd, t];
    }
  }
  return best;
}

function snapMove(rect, d, img, snap, guides) {
  if (!snap) return rect;
  let [x0, y0, x1, y1] = rect;
  const [xs, ys] = snapTargets(d, img);
  const bx = nearest([x0, (x0 + x1) / 2, x1], xs);
  if (bx) { x0 += bx[0]; x1 += bx[0]; guides.push(['v', bx[1]]); }
  const by = nearest([y0, (y0 + y1) / 2, y1], ys);
  if (by) { y0 += by[0]; y1 += by[0]; guides.push(['h', by[1]]); }
  return [x0, y0, x1, y1];
}

function computeResize(dr, x, y, d, snap, keepRatio) {
  const [ox0, oy0, ox1, oy1] = dr.orig, h = dr.handle;
  const dx = x - dr.start[0], dy = y - dr.start[1];
  const MIN = 20 / k();
  let [x0, y0, x1, y1] = dr.orig;
  if (h.includes('n')) y0 = oy0 + dy;
  if (h.includes('s')) y1 = oy1 + dy;
  if (h.includes('w')) x0 = ox0 + dx;
  if (h.includes('e')) x1 = ox1 + dx;

  let guides = [];
  if (snap) {
    const [xs, ys] = snapTargets(d, dr.item);
    const edge = (v, targets, kind) => {
      const hit = nearest([v], targets);
      if (!hit) return v;
      guides.push([kind, hit[1]]);
      return hit[1];
    };
    if (h.includes('w')) x0 = edge(x0, xs, 'v');
    if (h.includes('e')) x1 = edge(x1, xs, 'v');
    if (h.includes('n')) y0 = edge(y0, ys, 'h');
    if (h.includes('s')) y1 = edge(y1, ys, 'h');
  }
  if (h.includes('n')) y0 = Math.min(y0, oy1 - MIN);
  if (h.includes('s')) y1 = Math.max(y1, oy0 + MIN);
  if (h.includes('w')) x0 = Math.min(x0, ox1 - MIN);
  if (h.includes('e')) x1 = Math.max(x1, ox0 + MIN);

  // Köşe tutamacı → en/boy oranı korunur (logolar basıklaşmasın). Hangi boyut daha çok
  // değiştiyse o belirleyici; diğer eksenin kılavuzu geçersiz olur.
  if (keepRatio && h.length === 2) {
    const ow = ox1 - ox0, oh = oy1 - oy0;
    let w = x1 - x0, hh = y1 - y0;
    if (Math.abs(w / ow - 1) >= Math.abs(hh / oh - 1)) {
      hh = w * oh / ow;
      guides = guides.filter((g) => g[0] === 'v');
    } else {
      w = hh * ow / oh;
      guides = guides.filter((g) => g[0] === 'h');
    }
    if (h.includes('w')) x0 = x1 - w; else x1 = x0 + w;
    if (h.includes('n')) y0 = y1 - hh; else y1 = y0 + hh;
  }
  dr.guides = guides;
  return [x0, y0, x1, y1];
}

/* ── Olaylar ──────────────────────────────────────────────────────────────── */

function bindLayer(layer, i) {
  layer.addEventListener('pointerdown', (e) => onDown(e, i, layer));
  layer.addEventListener('pointermove', (e) => onMove(e, i, layer));
  layer.addEventListener('pointerup', (e) => onUp(e, i, layer));
  layer.addEventListener('dblclick', (e) => onDblClick(e, i, layer));
  layer.addEventListener('contextmenu', (e) => onContextMenu(e, i, layer));
  layer.addEventListener('pointerleave', () => {
    if (app.hover && app.hover.page === i) { app.hover = null; renderLayer(i); }
    if (app.placing && app.placing.pos && app.placing.pos.page === i) { app.placing.pos = null; renderLayer(i); }
  });
}

/** Sürükleme sayfa dışına taşsa da olaylar bu katmana gelsin */
function capture(layer, e) {
  try { layer.setPointerCapture(e.pointerId); } catch (_) { /* işaretçi zaten bırakılmış */ }
}

const fromEditor = (e) => e.target.closest('.edit-box, #fmt-bar');

function onDown(e, i, layer) {
  if (fromEditor(e) || e.button !== 0) return;
  const [x, y] = ptAt(e, layer);

  if (app.placing) {                           // yapıştırma: tıklanan yere
    const pos = app.placing.pos && app.placing.pos.page === i ? app.placing.pos : { x, y };
    endPlacement();
    mutate(() => api().paste_text(i, pos.x, pos.y), 'Yapıştırıldı · Düzenlemek için çift tıklayın');
    return;
  }
  const d = layerData(i);
  const tool = app.tool;

  if (tool === 'metin-sec' || tool === 'alan-sil') {
    app.highlight = null;
    app.drag = { kind: 'marquee', page: i, start: [x, y], cur: null };
    capture(layer, e);
    renderAllLayers();
    return;
  }
  if (!d) return;

  if (tool === 'metin') {
    const span = spanAt(d, x, y);
    // Tarayıcı fare basışının ardından odağı değiştirir; kutu ondan sonra açılsın
    setTimeout(() => openEditor(i, span, span ? null : [x, y]), 0);
    return;
  }

  // Seçim aracı
  const sel = app.sel && app.sel.page === i ? app.sel : null;
  const handle = sel && sel.type === 'image' ? handleAt(sel.item.rect, x, y) : null;
  if (handle) {
    app.drag = { kind: 'resize', page: i, handle, start: [x, y], orig: sel.item.rect, item: sel.item, cur: null };
  } else {
    const { span, img } = pickAt(d, x, y);
    if (span) {
      setSelection({ type: 'span', page: i, item: span });
      app.drag = { kind: 'text', page: i, start: [x, y], item: span, cur: null };
    } else if (img) {
      setSelection({ type: 'image', page: i, item: img });
      app.drag = { kind: 'move', page: i, start: [x, y], orig: img.rect, item: img, cur: null };
    } else {
      setSelection(null);
      return;
    }
  }
  app.hover = null;
  capture(layer, e);
}

function onMove(e, i, layer) {
  if (fromEditor(e)) return;
  const [x, y] = ptAt(e, layer);

  if (app.placing) {
    const d = layerData(i);
    const hit = d ? nearest([x], d.snapX) : null;   // metin bloklarının sol/sağ kenarına yapış
    app.placing.pos = { page: i, x: hit ? hit[1] : x, y, snap: !!hit };
    renderLayer(i);
    return;
  }

  const dr = app.drag;
  if (!dr) { updateHover(i, layer, x, y); return; }
  if (dr.page !== i) return;
  const moved = Math.hypot(x - dr.start[0], y - dr.start[1]) * k() >= DRAG_START_PX;
  if (!dr.cur && !moved) return;

  const d = layerData(i);
  if (dr.kind === 'marquee') {
    dr.cur = [x, y];
  } else if (dr.kind === 'text') {
    const [x0, y0, x1, y1] = dr.item.rect, dx = x - dr.start[0], dy = y - dr.start[1];
    dr.cur = [x0 + dx, y0 + dy, x1 + dx, y1 + dy];
  } else if (dr.kind === 'move' && d) {
    const [x0, y0, x1, y1] = dr.orig, dx = x - dr.start[0], dy = y - dr.start[1];
    dr.guides = [];
    dr.cur = snapMove([x0 + dx, y0 + dy, x1 + dx, y1 + dy], d, dr.item, !e.altKey, dr.guides);
  } else if (dr.kind === 'resize' && d) {
    dr.cur = computeResize(dr, x, y, d, !e.altKey, !e.shiftKey);
  }
  renderLayer(i);
}

function onUp(e, i, layer) {
  const dr = app.drag;
  if (!dr || dr.page !== i) return;
  app.drag = null;
  if (layer.hasPointerCapture(e.pointerId)) layer.releasePointerCapture(e.pointerId);
  renderLayer(i);
  if (!dr.cur) return;                          // sürükleme değil, tıklama

  if (dr.kind === 'marquee') {
    const r = normRect(dr.start, dr.cur);
    if ((r[2] - r[0]) * k() < 3 || (r[3] - r[1]) * k() < 3) return;
    if (app.tool === 'metin-sec') selectTextIn(i, r);
    else mutate(() => api().erase_area(i, r), 'Alan silindi');
  } else if (dr.kind === 'text') {
    // Taban çizgisi aynı miktarda kaysın (kutunun altı değil; harf kuyrukları kaymasın)
    const dx = dr.cur[0] - dr.item.rect[0], dy = dr.cur[1] - dr.item.rect[1];
    const [ox, oy] = dr.item.origin;
    setSelection(null);
    mutate(() => api().move_text(i, dr.item, ox + dx, oy + dy), 'Metin taşındı');
  } else {
    const rect = dr.cur;
    mutate(() => api().move_image(i, dr.item, rect),
      dr.kind === 'move' ? 'Resim taşındı' : 'Resim boyutlandırıldı')
      .then((r) => r && selectImageNear(i, rect));
  }
}

function onDblClick(e, i, layer) {
  if (fromEditor(e) || app.tool !== 'secim') return;
  const d = layerData(i);
  if (!d) return;
  const [x, y] = ptAt(e, layer);
  const span = spanAt(d, x, y);
  if (span) openEditor(i, span, null);
}

function updateHover(i, layer, x, y) {
  const d = layerData(i);
  let hover = null, cursor = '';
  if (d && app.tool === 'secim') {
    const sel = app.sel && app.sel.page === i && app.sel.type === 'image' ? app.sel : null;
    const handle = sel ? handleAt(sel.item.rect, x, y) : null;
    const { span, img } = handle ? {} : pickAt(d, x, y);
    if (handle) cursor = HANDLES[handle];
    else if (span) { cursor = 'move'; hover = { page: i, item: span, rect: padRect(span.rect, 1), kind: 'span' }; }
    else if (img) { cursor = 'move'; hover = { page: i, item: img, rect: img.rect, kind: 'image' }; }
  } else if (d && app.tool === 'metin') {
    const span = spanAt(d, x, y);
    cursor = 'text';
    if (span) hover = { page: i, item: span, rect: padRect(span.rect, 1), kind: 'span' };
  }
  layer.style.cursor = cursor;
  if (hover && app.sel && app.sel.item === hover.item) hover = null;   // seçili öğeye vurgu çizme
  if ((hover && hover.item) === (app.hover && app.hover.item)) return;
  const prev = app.hover;
  app.hover = hover;
  if (prev && prev.page !== i) renderLayer(prev.page);
  renderLayer(i);
}

/* ── Metin seç ────────────────────────────────────────────────────────────── */

async function selectTextIn(i, rect) {
  const r = await api().select_text(i, rect);
  app.highlight = { page: i, rects: r.rects || [], rect };
  renderLayer(i);
  if (!r.ok) return toast(r.error);
  const preview = r.text.replace(/\n/g, ' ').replace(/\t/g, ' · ').slice(0, 50);
  toast(`Kopyalandı (${r.text.length} karakter): "${preview}"`);
}

/* ── Sağ tık menüsü ───────────────────────────────────────────────────────── */

async function onContextMenu(e, i, layer) {
  e.preventDefault();
  if (fromEditor(e)) return;
  if (app.placing) { endPlacement(); return; }   // sağ tık yapıştırmayı iptal eder
  const [x, y] = ptAt(e, layer);
  const d = layerData(i);
  const items = [];
  const tool = app.tool;

  const hit = !d ? {} : tool === 'secim' ? pickAt(d, x, y) : tool === 'metin' ? { span: spanAt(d, x, y) } : {};
  const { span, img } = hit;

  if (span) {
    setSelection({ type: 'span', page: i, item: span });
    const preview = span.text.replace(/\xa0/g, ' ').trim();
    items.push(
      { icon: 'content_copy', label: `Kopyala "${preview.length > 30 ? preview.slice(0, 29) + '…' : preview}"`,
        hint: 'Ctrl+C', run: () => copyText('span', i, span) },
      { icon: 'table_rows', label: 'Satırın tamamını kopyala', run: () => copyText('line', i, span) },
      { icon: 'edit', label: 'Düzenle', hint: 'Çift tık', run: () => openEditor(i, span, null) },
    );
  } else if (img) {
    setSelection({ type: 'image', page: i, item: img });
    items.push(...alignItems(i, img), '-',
      { icon: 'delete', label: 'Sil', hint: 'Del', danger: true, run: () => deleteImage(i, img) });
  } else if (tool === 'metin-sec') {
    const hl = app.highlight && app.highlight.page === i ? app.highlight : null;
    items.push({ icon: 'content_copy', label: 'Kopyala', hint: 'Ctrl+C', disabled: !hl || !hl.rects.length,
                 run: () => selectTextIn(i, hl.rect) });
  }

  // Sağ tıklanan nokta metnin (ya da resmin) sol üst köşesi olur; metin kenarlarına yapışır
  const snap = d ? nearest([x], d.snapX) : null;
  const px = snap ? snap[1] : x;
  const info = await api().clipboard_info();
  if (items.length) items.push('-');
  items.push({ icon: 'content_paste', label: info.kind === 'image' ? 'Resmi buraya yapıştır' : 'Buraya yapıştır',
               hint: 'Ctrl+V', disabled: !info.kind, run: () => pasteAt(i, px, y, info) });
  items.push('-', tool === 'metin-sec'
    ? { icon: 'select_all', label: 'Sayfadaki tüm metni seç', hint: 'Ctrl+A', run: () => selectPageText(i) }
    : { icon: 'article', label: 'Sayfadaki tüm metni kopyala', run: () => copyText('page', i, null) });
  showMenu(e.clientX, e.clientY, items);
}

function alignItems(i, img) {
  const it = (icon, label, how) => ({ icon, label, run: () => alignImage(i, img, how) });
  return [
    it('align_horizontal_left', 'Sola hizala', 'left'),
    it('align_horizontal_center', 'Yatay ortala', 'hcenter'),
    it('align_horizontal_right', 'Sağa hizala', 'right'),
    '-',
    it('align_vertical_top', 'Üste hizala', 'top'),
    it('align_vertical_center', 'Dikey ortala', 'vcenter'),
    it('align_vertical_bottom', 'Alta hizala', 'bottom'),
  ];
}

/* ── İşlemler (menü, klavye, panel ortak) ─────────────────────────────────── */

async function copyText(kind, i, span) {
  const r = await api().copy_text(kind, i, span);
  if (!r.ok) return toast(r.error);
  const what = kind === 'line' ? ' — satır' : kind === 'page' ? ` — sayfa ${i + 1}` : '';
  toast(`Kopyalandı${what} (${r.text.length} karakter)`);
}

function selectPageText(i) {
  setTool('metin-sec');
  const [w, h] = app.doc.pages[i];
  selectTextIn(i, [0, 0, w, h]);
}

function alignImage(i, img, how) {
  mutate(() => api().align_image(i, img, how), 'Resim hizalandı')
    .then((r) => r && selectImageNear(i, r.rect));
}

function deleteImage(i, img) {
  if (!window.confirm('Bu resmi PDF\'ten kalıcı olarak silmek istiyor musunuz?')) return;
  setSelection(null);
  mutate(() => api().delete_image(i, img), 'Resim silindi');
}

/** Yapıştırma önizlemesi: metin imleci takip eder, tıklanan yere yazılır */
function startPlacement(info) {
  const lines = info.text.replace(/\r\n/g, '\n').replace(/\t/g, '    ').replace(/\n+$/, '').split('\n');
  app.placing = { info: { ...info, lines }, pos: null };
  setSelection(null);
  $('pages').classList.add('is-placing');
  updateStatus();
}

function endPlacement() {
  if (!app.placing) return;
  const page = app.placing.pos && app.placing.pos.page;
  app.placing = null;
  $('pages').classList.remove('is-placing');
  if (page != null) renderLayer(page);
  updateStatus();
}

async function pasteAt(i, x, y, info) {
  if (info.kind === 'image') {
    const r = await mutate(() => api().paste_image(i, [x, y]), 'Resim yapıştırıldı');
    if (r) { setTool('secim'); selectImageNear(i, r.rect); }
  } else if (info.kind === 'text') {
    // Tıklanan nokta metnin sol üstü; PDF'e taban çizgisi verilir → bir satır yüksekliği aşağı
    mutate(() => api().paste_text(i, x, y + info.size * 0.8), 'Yapıştırıldı · Düzenlemek için çift tıklayın');
  }
}
