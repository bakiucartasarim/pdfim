/* PDFim v2 — ortak durum ve yardımcılar. Diğer betiklerden önce yüklenir.
 *
 * Koordinat kuralı: Python'dan gelen her şey PDF noktası (pt). Ekrana çizerken k() ile çarpılır
 * (CSS pikseli / pt). Yakınlaştırma değişince yalnız k() değişir, veriler aynı kalır.
 */
'use strict';

const PT_TO_PX = 96 / 72;          // %100 yakınlaştırmada 1 pt kaç CSS pikseli

const $ = (id) => document.getElementById(id);

/* Masaüstünde sayfa /<belirteç>/ui/ altından (page_server.py), webde /ui/ altından (server.py) gelir */
const IS_WEB = location.pathname.startsWith('/ui/');

/* Webde köprü metotları HTTP üzerinden: api().replace_text(a, b) → POST /api/replace_text [a, b] */
const httpApi = new Proxy({}, {
  get: (_, name) => async (...args) => {
    const res = await fetch(`../api/${name}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args),
    });
    if (!res.ok) {
      let msg = res.statusText;
      try { const j = await res.json(); msg = j.detail || j.error || msg; } catch (_) { /* gövde yok */ }
      if (res.status === 429) return { ok: false, error: msg };
      throw new Error(msg);
    }
    return res.json();
  },
});

const api = () => (IS_WEB ? httpApi : window.pywebview && window.pywebview.api);

const app = window.app = {
  doc: null,          // Python get_state() çıktısı; belge yoksa null
  zoom: 1,
  fit: 'width',       // 'width' | 'page' | null — pencere boyu değişince yeniden sığdırılır
  current: 0,         // ekrandaki sayfa (0 tabanlı)
  mode: 'duzenle',
  tool: 'secim',
  pageEls: [],
  thumbEls: [],
  layers: new Map(),  // sayfa → { version, data, promise } (metin/resim kutuları)
  sel: null,          // { type: 'span' | 'image', page, item }
  hover: null,        // { page, rect, kind } — imlecin altındaki öğe
  highlight: null,    // { page, rects, rect } — Metin Seç ile seçilen kelimeler
  placing: null,      // yapıştırma önizlemesi { info, pos }
  drag: null,
};

/** CSS pikseli / PDF noktası */
function k() { return PT_TO_PX * app.zoom; }

/* Belgeyi değiştiren istekler sırayla gitsin. Örn. düzenleme kutusu odak kaybıyla
 * uygulanırken hemen "Geri al"a basılırsa geri alma, uygulamadan önce çalışmasın. */
let queue = Promise.resolve();
function serial(fn) {
  const p = queue.then(fn, fn);
  queue = p.catch(() => {});
  return p;
}

/** Değiştiren bir köprü çağrısı: sırala, sonucu uygula, hatayı göster. Başarıda sonucu döner. */
async function mutate(call, okMsg) {
  const r = await serial(call);
  if (!r) return null;                 // kullanıcı iletişim kutusunda vazgeçti
  if (!r.ok) { showError(r.error); return null; }
  applyState(r.state);
  if (okMsg) toast(okMsg);
  return r;
}

let toastTimer = 0;
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('is-visible'), 2600);
}

function showError(msg) {
  window.alert(msg || 'Beklenmeyen bir hata oluştu.');
}

function hex(rgb) { return `#${(rgb & 0xffffff).toString(16).padStart(6, '0')}`; }

/** pt dikdörtgeni → sayfa katmanında konumlanmış kutu */
function boxEl(cls, r) {
  const kk = k(), el = document.createElement('div');
  el.className = cls;
  el.style.left = `${r[0] * kk}px`;
  el.style.top = `${r[1] * kk}px`;
  el.style.width = `${(r[2] - r[0]) * kk}px`;
  el.style.height = `${(r[3] - r[1]) * kk}px`;
  return el;
}

function mm(pt) { return (pt / 72 * 25.4).toFixed(1).replace('.', ','); }
