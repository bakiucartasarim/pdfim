/* İmza penceresi — çiz / yaz / yükle / kayıtlı. Sonuç kenarları kırpılmış şeffaf PNG'dir;
 * imza alanına sığdırılarak ya da imleçle taşınıp tıklanan yere yerleştirilir.
 * Görsel imzadır: güvenli elektronik imza (5070 sayılı Kanun) değildir. */
'use strict';

const SIGN_COLORS = ['#1e3a8a', '#111827', '#2563eb'];
// Windows'ta çoğunlukla kurulu el yazısı fontları; olmayanlar listelenmez
const SIGN_FONTS = ['Segoe Script', 'Ink Free', 'Lucida Handwriting', 'Segoe Print', 'Brush Script MT', 'Freestyle Script', 'Gabriola'];
const SIGN_W_PT = 150;       // yerleştirmede varsayılan imza genişliği (≈ 5,3 cm)

let sig = null;              // { target, tab, color, strokes, font, upload }

function openSignature(target) {
  sig = { target, tab: 'draw', color: SIGN_COLORS[0], strokes: [], font: null, upload: null };
  $('sig-modal').hidden = false;
  $('sig-save').checked = true;
  $('sig-text').value = '';
  $('sig-upload-preview').replaceChildren();
  setupFontList();
  loadSaved();
  setSigTab('draw');
  resizeCanvas();
}

function closeSignature() {
  $('sig-modal').hidden = true;
  sig = null;
}

function setSigTab(tab) {
  sig.tab = tab;
  document.querySelectorAll('#sig-tabs [data-tab]').forEach((b) => b.classList.toggle('is-active', b.dataset.tab === tab));
  document.querySelectorAll('.sig-pane').forEach((p) => { p.hidden = p.dataset.pane !== tab; });
  $('sig-save-row').hidden = tab === 'saved';
  $('sig-place').hidden = tab === 'saved';          // kayıtlıda imzaya tıklamak yeter
  if (tab === 'type') $('sig-text').focus();
}

/* ── Çiz ──────────────────────────────────────────────────────────────────── */

function resizeCanvas() {
  const c = $('sig-canvas'), dpr = window.devicePixelRatio || 1;
  c.width = Math.round(c.clientWidth * dpr);
  c.height = Math.round(c.clientHeight * dpr);
  redraw();
}

function redraw() {
  const c = $('sig-canvas'), g = c.getContext('2d'), dpr = window.devicePixelRatio || 1;
  g.clearRect(0, 0, c.width, c.height);
  g.lineCap = 'round';
  g.lineJoin = 'round';
  for (const s of sig.strokes) drawStroke(g, s, dpr);
  $('sig-draw-hint').hidden = sig.strokes.length > 0;
}

function drawStroke(g, s, scale) {
  g.strokeStyle = s.color;
  g.lineWidth = 2.6 * scale;
  g.beginPath();
  const p = s.points;
  g.moveTo(p[0][0] * scale, p[0][1] * scale);
  // Noktalar arası yumuşak eğri: el yazısı kırık çizgi gibi görünmesin
  for (let i = 1; i < p.length - 1; i++) {
    const mx = (p[i][0] + p[i + 1][0]) / 2, my = (p[i][1] + p[i + 1][1]) / 2;
    g.quadraticCurveTo(p[i][0] * scale, p[i][1] * scale, mx * scale, my * scale);
  }
  const last = p[p.length - 1];
  g.lineTo(last[0] * scale, last[1] * scale);
  g.stroke();
}

function bindCanvas() {
  const c = $('sig-canvas');
  let cur = null;
  const pt = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  c.addEventListener('pointerdown', (e) => {
    cur = { color: sig.color, points: [pt(e)] };
    sig.strokes.push(cur);
    try { c.setPointerCapture(e.pointerId); } catch (_) { /* yok */ }
    redraw();
  });
  c.addEventListener('pointermove', (e) => {
    if (!cur) return;
    cur.points.push(pt(e));
    redraw();
  });
  const end = () => { cur = null; };
  c.addEventListener('pointerup', end);
  c.addEventListener('pointercancel', end);
}

/* ── Yaz ──────────────────────────────────────────────────────────────────── */

async function setupFontList() {
  const box = $('sig-fonts');
  if (box.dataset.ready) return;
  box.dataset.ready = '1';
  const installed = new Set(await api().system_fonts());
  const fontsAvail = SIGN_FONTS.filter((f) => installed.has(f));
  if (!fontsAvail.length) fontsAvail.push('cursive');
  fontsAvail.forEach((f, idx) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'sig-font';
    b.dataset.font = f;
    b.style.fontFamily = `"${f}", cursive`;
    b.textContent = 'Ad Soyad';
    b.addEventListener('click', () => {
      box.querySelectorAll('.sig-font').forEach((x) => x.classList.toggle('is-active', x === b));
      if (sig) sig.font = f;
    });
    box.append(b);
    if (idx === 0) b.click();
  });
  $('sig-text').addEventListener('input', () => {
    const t = $('sig-text').value.trim() || 'Ad Soyad';
    box.querySelectorAll('.sig-font').forEach((b) => { b.textContent = t; });
  });
}

/* ── Yükle ────────────────────────────────────────────────────────────────── */

function loadUpload(file) {
  if (!file) return;
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    sig.upload = img;
    const prev = $('sig-upload-preview');
    prev.replaceChildren();
    const out = new Image();
    out.src = uploadToPng();
    prev.append(out);
  };
  img.src = url;
}

function uploadToPng() {
  const img = sig.upload;
  const scale = Math.min(1, 1400 / Math.max(img.width, img.height));
  const c = document.createElement('canvas');
  c.width = Math.round(img.width * scale);
  c.height = Math.round(img.height * scale);
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0, c.width, c.height);
  if ($('sig-clear-bg').checked) {
    // Taranmış / fotoğraflanmış imzanın kâğıt rengi şeffaf olsun (yumuşak geçişli)
    const d = g.getImageData(0, 0, c.width, c.height), a = d.data;
    for (let i = 0; i < a.length; i += 4) {
      const light = Math.min(a[i], a[i + 1], a[i + 2]);
      if (light > 225) a[i + 3] = 0;
      else if (light > 170) a[i + 3] = Math.round(a[i + 3] * (225 - light) / 55);
    }
    g.putImageData(d, 0, 0);
  }
  return trimCanvas(c);
}

/* ── Sonuç ────────────────────────────────────────────────────────────────── */

/** Şeffaf kenarları kırp → PNG data URL (boşsa null) */
function trimCanvas(c) {
  const g = c.getContext('2d'), { data, width, height } = g.getImageData(0, 0, c.width, c.height);
  let x0 = width, y0 = height, x1 = -1, y1 = -1;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] > 8) {
        if (x < x0) x0 = x; if (x > x1) x1 = x;
        if (y < y0) y0 = y; if (y > y1) y1 = y;
      }
    }
  }
  if (x1 < 0) return null;
  const pad = 4, w = x1 - x0 + 1 + pad * 2, h = y1 - y0 + 1 + pad * 2;
  const out = document.createElement('canvas');
  out.width = w;
  out.height = h;
  out.getContext('2d').drawImage(c, x0 - pad, y0 - pad, w, h, 0, 0, w, h);
  return out.toDataURL('image/png');
}

function currentPng() {
  if (sig.tab === 'draw') {
    if (!sig.strokes.length) return null;
    const src = $('sig-canvas'), scale = 3;             // yüksek çözünürlük: büyütünce bulanmasın
    const c = document.createElement('canvas');
    c.width = src.clientWidth * scale;
    c.height = src.clientHeight * scale;
    const g = c.getContext('2d');
    g.lineCap = 'round';
    g.lineJoin = 'round';
    sig.strokes.forEach((s) => drawStroke(g, s, scale));
    return trimCanvas(c);
  }
  if (sig.tab === 'type') {
    const text = $('sig-text').value.trim();
    if (!text) return null;
    const c = document.createElement('canvas'), g = c.getContext('2d');
    const font = `120px "${sig.font}", cursive`;
    g.font = font;
    c.width = Math.ceil(g.measureText(text).width) + 80;
    c.height = 220;
    g.font = font;                                      // boyut değişince bağlam sıfırlanır
    g.fillStyle = sig.color;
    g.textBaseline = 'middle';
    g.fillText(text, 40, 110);
    return trimCanvas(c);
  }
  if (sig.tab === 'upload') return sig.upload ? uploadToPng() : null;
  return null;
}

async function useSignature(png, save) {
  const target = sig.target;
  closeSignature();
  if (save) api().save_signature(png);
  const img = await new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.src = png; });
  const ratio = img.height / img.width;
  if (target) {
    // İmza alanına sığdır (oran korunur, ortalanır — Python tarafında insert_image yapar)
    const r = target.rect;
    mutate(() => api().place_image(target.page, png, r), 'İmza eklendi');
    return;
  }
  const w = SIGN_W_PT, h = Math.min(w * ratio, 90);
  const ww = h / ratio;
  startImagePlacement(png, ww, h, (i, x, y) => api().place_image(i, png, [x - ww / 2, y - h / 2, x + ww / 2, y + h / 2]),
    'İmza eklendi · Düzenle > Seçim ile taşıyıp boyutlandırabilirsiniz');
}

async function loadSaved() {
  const list = await api().list_signatures();
  const box = $('sig-saved');
  box.replaceChildren();
  $('sig-tab-saved').hidden = !list.length;
  for (const s of list) {
    const item = document.createElement('div');
    item.className = 'sig-saved-item';
    const im = new Image();
    im.src = s.data;
    im.title = 'Bu imzayı kullan';
    im.addEventListener('click', () => useSignature(s.data, false));
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'icon-btn sig-del';
    del.title = 'Kayıtlı imzayı sil';
    del.innerHTML = '<span class="ms">close</span>';
    del.addEventListener('click', async () => { await api().delete_signature(s.id); loadSaved(); });
    item.append(im, del);
    box.append(item);
  }
  if (list.length && sig && !sig.target) setSigTab('saved');   // kayıtlı varsa önce onlar
}

function bindSignature() {
  document.querySelectorAll('#sig-tabs [data-tab]').forEach((b) => b.addEventListener('click', () => setSigTab(b.dataset.tab)));
  $('sig-close').addEventListener('click', closeSignature);
  $('sig-cancel').addEventListener('click', closeSignature);
  $('sig-modal').addEventListener('pointerdown', (e) => { if (e.target === $('sig-modal')) closeSignature(); });
  $('sig-clear').addEventListener('click', () => { sig.strokes = []; redraw(); });
  $('sig-undo').addEventListener('click', () => { sig.strokes.pop(); redraw(); });
  document.querySelectorAll('#sig-colors [data-color]').forEach((b) => b.addEventListener('click', () => {
    sig.color = b.dataset.color;
    document.querySelectorAll('#sig-colors [data-color]').forEach((x) => x.classList.toggle('is-active', x === b));
  }));
  $('sig-file').addEventListener('change', (e) => loadUpload(e.target.files[0]));
  $('sig-clear-bg').addEventListener('change', () => {
    const prev = $('sig-upload-preview').firstChild;
    const png = sig && sig.upload && prev ? uploadToPng() : null;
    if (png) prev.src = png;
  });
  $('sig-place').addEventListener('click', () => {
    const png = currentPng();
    if (!png) return toast(sig.tab === 'type' ? 'Önce adınızı yazın.' : sig.tab === 'upload' ? 'Önce bir resim seçin.' : 'Önce imzanızı çizin.');
    useSignature(png, $('sig-save').checked);
  });
  document.addEventListener('keydown', (e) => {
    if (!$('sig-modal').hidden && e.key === 'Escape') { e.stopPropagation(); closeSignature(); }
  }, true);
  bindCanvas();
}
