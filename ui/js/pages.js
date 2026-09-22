/* Sayfalar modu — sayfa ızgarası, seçim, sürükleyerek sıralama ve sayfa işlemleri.
 *
 * Seçim: tıkla → yalnız o; Ctrl → ekle/çıkar; Shift → aralık; onay kutusu → ekle/çıkar.
 * Sürükle → seçili sayfalar mavi çizginin olduğu yere taşınır. Çift tık → Düzenle modunda o sayfa.
 * Yapıyı değiştiren her işlem Python'da tek geri alma adımıdır; dönen "pages" yeni seçimdir.
 */
'use strict';

const CARD_W = { kucuk: 130, orta: 190, buyuk: 280 };
const PAGE_DRAG_PX = 6;

app.pageSel = new Set();
app.pageAnchor = null;       // Shift ile aralık seçiminin başlangıcı
app.cardSize = 'orta';
app.dropIndex = null;        // Explorer'dan PDF sürüklenirken ekleneceği yer

let cards = [];
let pageDrag = null;         // { index, x, y, active, to }

/* ── Mod ──────────────────────────────────────────────────────────────────── */

function enterPagesMode() {
  commitOpenEdit();
  endPlacement();
  clearTransient();
  document.body.classList.add('mode-sayfalar');
  if (app.doc && !app.pageSel.size) app.pageSel = new Set([app.current]);
  buildGrid();
  const first = firstSelected();
  if (first != null && cards[first]) cards[first].scrollIntoView({ block: 'center' });
}

function leavePagesMode() {
  document.body.classList.remove('mode-sayfalar');
  gridObserver.disconnect();
  $('page-grid').replaceChildren($('page-drop-line'));
  cards = [];
  const first = firstSelected();
  if (first != null) requestAnimationFrame(() => scrollToPage(first, 'auto'));
}

const firstSelected = () => (app.pageSel.size ? Math.min(...app.pageSel) : null);
const selectedList = () => [...app.pageSel].sort((a, b) => a - b);

/* ── Izgara ───────────────────────────────────────────────────────────────── */

function paperShort(wPt, hPt) {
  const name = paperName(wPt, hPt);
  return name.includes('(') ? name.split(' (')[0] : name;
}

function buildGrid() {
  const grid = $('page-grid');
  gridObserver.disconnect();
  grid.replaceChildren($('page-drop-line'));      // bırakma çizgisi ızgaranın içinde kalır
  cards = [];
  if (!app.doc) return;
  grid.style.setProperty('--card-w', `${CARD_W[app.cardSize]}px`);
  // Sayfa sayısı değiştiyse (silme) seçim geçerli numaralara kırpılır
  app.pageSel = new Set([...app.pageSel].filter((i) => i < app.doc.pages.length));

  app.doc.pages.forEach(([w, h], i) => {
    const card = document.createElement('div');
    card.className = 'pcard';
    card.dataset.index = i;
    card.innerHTML = '<div class="pcard-head"><span class="pcard-num"></span>'
      + '<button type="button" class="pcard-check" title="Seç / bırak"><span class="ms"></span></button></div>'
      + '<div class="pcard-img"><img alt="" draggable="false"></div><div class="pcard-foot"></div>';
    card.querySelector('.pcard-num').textContent = `Sayfa ${i + 1}`;
    card.querySelector('img').style.aspectRatio = `${w} / ${h}`;
    const rot = (app.doc.rotations || [])[i] || 0;
    card.querySelector('.pcard-foot').textContent = `${paperShort(w, h)} · ${rot}°`;
    grid.append(card);
    cards.push(card);
    gridObserver.observe(card);
  });

  const add = document.createElement('div');
  add.className = 'pcard-add';
  add.innerHTML = '<span class="ms">add_circle</span><p>Sona sayfa ekle</p>'
    + '<div class="pcard-add-actions"><button type="button" class="btn" data-add="blank"><span class="ms">note_add</span><span>Boş sayfa</span></button>'
    + '<button type="button" class="btn btn-primary" data-add="pdf"><span class="ms">picture_as_pdf</span><span>PDF ekle</span></button></div>'
    + '<p class="muted">ya da PDF dosyasını buraya sürükleyin</p>';
  add.querySelector('[data-add=blank]').addEventListener('click', () => pageActions.blank(app.doc.pages.length));
  add.querySelector('[data-add=pdf]').addEventListener('click', () => pageActions.pdf(app.doc.pages.length));
  grid.append(add);
  syncSelection();
}

const gridObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    const i = +e.target.dataset.index, img = e.target.querySelector('img');
    const s = +(CARD_W[app.cardSize] / app.doc.pages[i][0] * (window.devicePixelRatio || 1)).toFixed(3);
    const key = `${app.doc.versions[i]}:${s}`;
    if (img.dataset.key !== key) { img.dataset.key = key; img.src = pageUrl(i, s); }
  }
}, { root: $('page-grid'), rootMargin: '300px 0px' });

function syncSelection() {
  cards.forEach((c, i) => {
    const on = app.pageSel.has(i);
    c.classList.toggle('is-selected', on);
    c.querySelector('.pcard-check .ms').textContent = on ? 'check_box' : 'check_box_outline_blank';
  });
  const n = app.pageSel.size;
  $('psel-count').textContent = app.doc ? `${n} / ${app.doc.pages.length} seçili` : '';
  document.querySelectorAll('#page-strip [data-needs-sel]').forEach((b) => { b.disabled = !n; });
  renderInspector();
}

function setPageSel(indices, anchor) {
  app.pageSel = new Set(indices);
  if (anchor !== undefined) app.pageAnchor = anchor;
  syncSelection();
}

function quickSelect(kind) {
  const n = app.doc ? app.doc.pages.length : 0;
  const all = [...Array(n).keys()];
  setPageSel(kind === 'all' ? all : kind === 'odd' ? all.filter((i) => i % 2 === 0)
    : kind === 'even' ? all.filter((i) => i % 2 === 1) : [], null);
}

/* ── Fare: seçim ve sürükleyerek sıralama ─────────────────────────────────── */

/** İmlecin olduğu yere göre ekleme konumu: kartın sol yarısı → önüne, sağ yarısı → arkasına */
function insertionIndexAt(x, y) {
  let best = null;
  cards.forEach((c, i) => {
    const r = c.getBoundingClientRect();
    if (y < r.top - 12 || y > r.bottom + 12) return;
    const d = Math.abs(x - (r.left + r.width / 2));
    if (!best || d < best.d) best = { d, i: x < r.left + r.width / 2 ? i : i + 1 };
  });
  if (best) return best.i;
  // Satırların arasında / en altta: en yakın satırın sonu
  const last = cards[cards.length - 1];
  return last && y > last.getBoundingClientRect().bottom ? cards.length : null;
}

function showIndicator(index) {
  const ind = $('page-drop-line'), grid = $('page-grid');
  if (index == null || !cards.length) { ind.hidden = true; return; }
  const gr = grid.getBoundingClientRect();
  const ref = cards[Math.min(index, cards.length - 1)].getBoundingClientRect();
  const x = index < cards.length ? ref.left - 9 : ref.right + 7;
  ind.hidden = false;
  ind.style.left = `${x - gr.left + grid.scrollLeft}px`;
  ind.style.top = `${ref.top - gr.top + grid.scrollTop}px`;
  ind.style.height = `${ref.height}px`;
}

function bindPageGrid() {
  const grid = $('page-grid');

  grid.addEventListener('pointerdown', (e) => {
    const card = e.target.closest('.pcard');
    if (!card || e.button !== 0) return;
    const i = +card.dataset.index;
    if (e.target.closest('.pcard-check')) {             // onay kutusu: ekle / çıkar
      const s = new Set(app.pageSel);
      if (s.has(i)) s.delete(i); else s.add(i);
      setPageSel(s, i);
      return;
    }
    pageDrag = { index: i, x: e.clientX, y: e.clientY, active: false, to: null, e };
    capture(grid, e);
  });

  grid.addEventListener('pointermove', (e) => {
    if (!pageDrag) return;
    if (!pageDrag.active) {
      if (Math.hypot(e.clientX - pageDrag.x, e.clientY - pageDrag.y) < PAGE_DRAG_PX) return;
      pageDrag.active = true;
      if (!app.pageSel.has(pageDrag.index)) setPageSel([pageDrag.index], pageDrag.index);
      document.body.classList.add('is-page-dragging');
      const badge = $('page-drag-badge');
      badge.textContent = app.pageSel.size > 1 ? `${app.pageSel.size} sayfa` : `Sayfa ${pageDrag.index + 1}`;
      badge.hidden = false;
    }
    const badge = $('page-drag-badge');
    badge.style.left = `${e.clientX + 14}px`;
    badge.style.top = `${e.clientY + 14}px`;
    pageDrag.to = insertionIndexAt(e.clientX, e.clientY);
    showIndicator(pageDrag.to);
    // Kenara yaklaşınca kaydır
    const r = grid.getBoundingClientRect();
    if (e.clientY < r.top + 40) grid.scrollTop -= 14;
    else if (e.clientY > r.bottom - 40) grid.scrollTop += 14;
  });

  const endDrag = (e) => {
    if (!pageDrag) return;
    const d = pageDrag;
    pageDrag = null;
    if (grid.hasPointerCapture(e.pointerId)) grid.releasePointerCapture(e.pointerId);
    $('page-drop-line').hidden = true;
    $('page-drag-badge').hidden = true;
    document.body.classList.remove('is-page-dragging');
    if (e.type === 'pointercancel') return;
    if (!d.active) {                                    // tıklama: seçim
      const i = d.index, ev = d.e;
      if (ev.shiftKey && app.pageAnchor != null) {
        const [a, b] = [Math.min(app.pageAnchor, i), Math.max(app.pageAnchor, i)];
        const range = [...Array(b - a + 1).keys()].map((k) => a + k);
        setPageSel(ev.ctrlKey ? [...app.pageSel, ...range] : range);
      } else if (ev.ctrlKey) {
        const s = new Set(app.pageSel);
        if (s.has(i)) s.delete(i); else s.add(i);
        setPageSel(s, i);
      } else {
        setPageSel([i], i);
      }
      return;
    }
    if (d.to == null) return;
    const sel = selectedList();
    // Sıra değişmiyorsa (seçim zaten orada, bitişik) boşuna geri alma adımı açma
    const rest = [...Array(app.doc.pages.length).keys()].filter((i) => !app.pageSel.has(i));
    const pos = rest.filter((i) => i < d.to).length;
    const order = [...rest.slice(0, pos), ...sel, ...rest.slice(pos)];
    if (order.every((v, i) => v === i)) return;
    runPageOp(() => api().move_pages(sel, d.to), sel.length > 1 ? `${sel.length} sayfa taşındı` : 'Sayfa taşındı');
  };
  grid.addEventListener('pointerup', endDrag);
  grid.addEventListener('pointercancel', endDrag);

  grid.addEventListener('dblclick', (e) => {
    const card = e.target.closest('.pcard');
    if (!card || e.target.closest('.pcard-check')) return;
    const i = +card.dataset.index;
    setMode('duzenle');
    requestAnimationFrame(() => scrollToPage(i, 'auto'));
  });

  // Explorer'dan PDF sürüklenirken nereye ekleneceğini göster (bırakmayı app.py yakalar)
  grid.addEventListener('dragover', (e) => {
    app.dropIndex = insertionIndexAt(e.clientX, e.clientY) ?? app.doc.pages.length;
    showIndicator(app.dropIndex);
  });
  grid.addEventListener('dragleave', (e) => {
    if (!grid.contains(e.relatedTarget)) { app.dropIndex = null; $('page-drop-line').hidden = true; }
  });

  document.querySelectorAll('#page-strip [data-pact]').forEach((b) =>
    b.addEventListener('click', () => pageActions[b.dataset.pact]()));
  document.querySelectorAll('#card-size [data-size]').forEach((b) => b.addEventListener('click', () => {
    app.cardSize = b.dataset.size;
    document.querySelectorAll('#card-size [data-size]').forEach((x) => x.classList.toggle('is-active', x === b));
    buildGrid();
  }));
}

/* ── İşlemler ─────────────────────────────────────────────────────────────── */

async function runPageOp(call, okMsg) {
  const r = await mutate(call, okMsg);
  if (r && Array.isArray(r.pages)) {
    setPageSel(r.pages, r.pages[0]);
    const first = firstSelected();
    if (first != null && cards[first]) cards[first].scrollIntoView({ block: 'nearest' });
  }
  return r;
}

/** Yeni sayfalar seçimin arkasına, seçim yoksa sona */
const insertAt = () => (app.pageSel.size ? Math.max(...app.pageSel) + 1 : app.doc.pages.length);

const pageActions = {
  'select-all': () => quickSelect(app.pageSel.size === app.doc.pages.length ? 'none' : 'all'),
  'rotate-left': () => runPageOp(() => api().rotate_pages(selectedList(), -90), 'Döndürüldü'),
  'rotate-right': () => runPageOp(() => api().rotate_pages(selectedList(), 90), 'Döndürüldü'),
  duplicate: () => runPageOp(() => api().duplicate_pages(selectedList()), 'Çoğaltıldı'),
  delete() {
    const sel = selectedList();
    if (!sel.length) return;
    if (sel.length >= app.doc.pages.length) return toast('Belgenin tüm sayfaları silinemez; en az bir sayfa kalmalı.');
    const what = sel.length === 1 ? `${sel[0] + 1}. sayfa` : `${sel.length} sayfa`;
    if (!window.confirm(`${what} silinsin mi? (Geri al ile geri getirilebilir)`)) return;
    runPageOp(() => api().delete_pages(sel), `${what} silindi`);
  },
  blank: (at = insertAt()) => runPageOp(() => api().insert_blank_page(at), 'Boş sayfa eklendi'),
  pdf: (at = insertAt()) => runPageOp(() => api().insert_pdf_dialog(at), 'PDF eklendi'),
  async export() {
    const sel = selectedList();
    const r = await serial(() => api().export_pages_dialog(sel));
    if (!r) return;
    if (!r.ok) return showError(r.error);
    toast(`${r.count} sayfa kaydedildi: ${r.path.split(/[\\/]/).pop()}`);
  },
};

/** Pencereye bırakılan PDF'ler (app.py): Sayfalar modunda araya ekle, yoksa aç */
app.onDropFiles = async (paths) => {
  if (app.mode === 'sayfalar' && app.doc) {
    const at = app.dropIndex ?? insertAt();
    app.dropIndex = null;
    $('page-drop-line').hidden = true;
    const what = paths.length > 1 ? `${paths.length} PDF eklendi` : 'PDF eklendi';
    runPageOp(() => api().insert_pdf_paths(paths, at), what);
  } else {
    handleOpenResult(await serial(() => api().open_dropped(paths[0])));
  }
};

/* ── Klavye (Sayfalar modu) ───────────────────────────────────────────────── */

function onPagesKey(e, key) {
  if (e.key === 'Delete') { pageActions.delete(); return true; }
  if (e.key === 'Escape') { setPageSel([], null); return true; }
  if (e.ctrlKey && key === 'a') { quickSelect('all'); return true; }
  if (e.ctrlKey && key === 'd') { pageActions.duplicate(); return true; }
  return false;
}
