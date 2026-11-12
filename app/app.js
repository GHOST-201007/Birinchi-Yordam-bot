// ── Mavzu: saqlangan tanlov BIRINCHI CHIZISHDAN OLDIN qo'llanadi (app.js boshida; body allaqachon bor) ──
// "auto" — Telegram mavzusiga (tg.colorScheme / themeChanged) ergashadi; "light" / "dark" — qo'lda.
// Faqat localStorage (try/catch, xato bo'lsa jim o'tadi). CloudStorage ATAYLAB ishlatilmaydi (eski mijozlarda xato).
const THEME_KEY = 'theme_mode';
const THEME_MODES = ['auto', 'light', 'dark'];
let themePrefInSession = null;       // shu oynada tanlangan (localStorage ishlamasa ham eslab qolinadi)

function readThemePref() {
    if (themePrefInSession !== null) return themePrefInSession;   // shu oynada tanlangan
    try {
        const v = window.localStorage.getItem(THEME_KEY);
        return THEME_MODES.includes(v) ? v : 'auto';
    } catch (e) {
        return 'auto';
    }
}

function saveThemePref(value) {
    try { window.localStorage.setItem(THEME_KEY, value); } catch (e) { /* saqlanmasa ham joriy oynada ishlaydi */ }
}

function autoThemeMode() {
    const w = window.Telegram && window.Telegram.WebApp;
    if (w && (w.colorScheme === 'dark' || w.colorScheme === 'light')) return w.colorScheme;
    try {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    } catch (e) { /* eski brauzer */ }
    return 'light';
}

(function bootTheme() {
    try {
        const pref = readThemePref();
        const mode = pref === 'auto' ? autoThemeMode() : pref;
        if (document.body) document.body.classList.toggle('dark-mode', mode === 'dark');
    } catch (e) { /* mavzu standart bo'lib qoladi */ }
})();

// Safe localStorage wrapper with Telegram CloudStorage sync
const SafeStorage = {
    getItem: function (key) {
        try {
            return window.localStorage ? window.localStorage.getItem(key) : null;
        } catch (e) {
            console.warn("SafeStorage.getItem failed:", e);
            return null;
        }
    },
    setItem: function (key, value) {
        try {
            if (window.localStorage) window.localStorage.setItem(key, value);
            // Sync with Telegram CloudStorage
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.CloudStorage) {
                window.Telegram.WebApp.CloudStorage.setItem(key, value, function(err) {
                    if (err) console.error("CloudStorage setItem error:", err);
                });
            }
        } catch (e) {
            console.warn("SafeStorage.setItem failed:", e);
        }
    },
    removeItem: function (key) {
        try {
            if (window.localStorage) window.localStorage.removeItem(key);
            // Sync with Telegram CloudStorage
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.CloudStorage) {
                window.Telegram.WebApp.CloudStorage.removeItem(key, function(err) {
                    if (err) console.error("CloudStorage removeItem error:", err);
                });
            }
        } catch (e) {
            console.warn("SafeStorage.removeItem failed:", e);
        }
    },
    // Initialize cache from CloudStorage on startup
    initFromCloud: function (callback) {
        let called = false;
        function done() {
            if (!called) {
                called = true;
                if (callback) callback();
            }
        }
        try {
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.CloudStorage && window.Telegram.WebApp.isVersionAtLeast && window.Telegram.WebApp.isVersionAtLeast('6.9')) {
                setTimeout(done, 1000);
                window.Telegram.WebApp.CloudStorage.getKeys(function(err, keys) {
                    try {
                        if (!err && keys && keys.length > 0) {
                            window.Telegram.WebApp.CloudStorage.getItems(keys, function(err, values) {
                                if (!err && values) {
                                    for (let k in values) {
                                        if (window.localStorage) window.localStorage.setItem(k, values[k]);
                                    }
                                }
                                done();
                            });
                        } else {
                            done();
                        }
                    } catch(e) { done(); }
                });
            } else {
                done();
            }
        } catch(e) { done(); }
    }
};

// Telegram WebApp Initialization
const tg = window.Telegram ? window.Telegram.WebApp : null;

// Foydalanuvchiga xabar ko'rsatish (Telegram ichida showAlert, brauzerda alert)
function notify(msg) {
    if (tg && tg.showAlert) tg.showAlert(msg); else alert(msg);
}
// Xatoni konsolga yozadi, foydalanuvchiga esa stack trace'siz oddiy xabar ko'rsatadi
function reportError(where, err) {
    console.error('[' + where + ']', err);
    notify("Kutilmagan xatolik yuz berdi. Iltimos, mini appni qayta oching.");
}

const BOT_USERNAME = "Birinchiyordam1Bot";

// ── Ikonkalar: index.html dagi inline SVG sprite (#i-<nom>). FontAwesome yo'q, tashqi so'rov yo'q. ──
// Ma'lumotlardagi eski icon nomlari (masalan "fa-fire-burner") o'zgarmaydi — bu yerda sprite nomiga o'giriladi.
const FA_ICON_MAP = {
    'fa-arrow-left': 'arrow-left',
    'fa-bone': 'bone',
    'fa-brain': 'brain',
    'fa-briefcase-medical': 'book',
    'fa-chart-line': 'chart',
    'fa-chevron-down': 'chevron-down',
    'fa-chevron-left': 'chevron-left',
    'fa-chevron-right': 'chevron-right',
    'fa-child-reaching': 'person-standing',
    'fa-circle-check': 'circle-check',
    'fa-circle-info': 'info',
    'fa-coins': 'star',
    'fa-crosshairs': 'crosshair',
    'fa-droplet': 'droplet',
    'fa-face-dizzy': 'dizzy',
    'fa-fire': 'flame',
    'fa-fire-burner': 'flame',
    'fa-gift': 'gift',
    'fa-glass-water-droplet': 'glass-water',
    'fa-head-side-cough': 'wind',
    'fa-heart-circle-xmark': 'heart-crack',
    'fa-heart-pulse': 'heart-pulse',
    'fa-kit-medical': 'first-aid',
    'fa-magnifying-glass': 'search',
    'fa-person': 'user',
    'fa-person-walking-arrow-right': 'repeat',
    'fa-phone-flip': 'phone',
    'fa-rotate': 'rotate-cw',
    'fa-spinner': 'loader',
    'fa-star': 'star',
    'fa-sun': 'sun',
    'fa-triangle-exclamation': 'alert-triangle',
    'fa-user-doctor': 'stethoscope',
    'fa-vial': 'test-tube',
    'fa-wand-magic-sparkles': 'sparkles',
    'fa-xmark': 'x'
};
function iconName(name) {
    return FA_ICON_MAP[name] || name || 'activity';
}
function svgIcon(name, cls) {
    return '<svg class="icon' + (cls ? ' ' + cls : '') + '" aria-hidden="true" focusable="false"><use href="#i-' + iconName(name) + '"/></svg>';
}

// Mini App -> bot API (/api/...). Foydalanuvchi faqat tekshirilgan initData orqali aniqlanadi.
// initData yo'q bo'lsa yoki so'rov xato bersa istisno ko'tariladi: chaqiruvchi URL-parametr zaxira yo'liga o'tadi.
function canUseApi() {
    return !!(tg && tg.initData);
}

// opts (ixtiyoriy): timeoutMs — standart 8 s; withStatus — xato holatida ham {status, data, retryAfter} qaytaradi
async function api(path, extra, opts) {
    const o = opts || {};
    const initData = (tg && tg.initData) || '';
    if (!initData) throw new Error('no-initdata');
    const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), o.timeoutMs || 8000) : null;
    try {
        const r = await fetch('/api/' + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(Object.assign({ init_data: initData }, extra || {})),
            signal: ctrl ? ctrl.signal : undefined
        });
        if (o.withStatus) {
            let data = null;
            try { data = await r.json(); } catch (e) { data = null; }      // JSON emas (masalan nginx 502)
            const ra = parseInt(r.headers.get('Retry-After') || '', 10);
            return { status: r.status, data: data, retryAfter: Number.isFinite(ra) ? ra : null };
        }
        if (!r.ok) throw new Error('http-' + r.status);
        return await r.json();
    } finally {
        if (timer) clearTimeout(timer);
    }
}

// /api/state natijasi — butun ilova uchun BITTA nusxa (header, kunlik bonus, baraban).
// Bir vaqtda bir nechta so'rov bo'lsa ham tarmoqqa bitta so'rov ketadi.
const AppState = { data: null, ts: 0, inflight: null, listeners: [] };

// Holat yangilanganda (serverdan olinganda yoki claim'dan keyin) chaqiriladi
function onAppStateChange(fn) {
    AppState.listeners.push(fn);
}
function notifyAppState() {
    AppState.listeners.forEach((fn) => {
        try { fn(AppState.data); } catch (e) { console.warn('[state] tinglovchi xatosi:', e); }
    });
}

// Holatni qaytaradi (hech qachon istisno tashlamaydi). API ishlamasa null — chaqiruvchi URL zaxira yo'liga o'tadi.
// maxAgeMs dan yangi natija keshdan beriladi, aks holda qayta so'raladi.
function getAppState(maxAgeMs) {
    if (!canUseApi()) return Promise.resolve(null);
    if (AppState.data && (Date.now() - AppState.ts) <= (maxAgeMs || 0)) return Promise.resolve(AppState.data);
    if (AppState.inflight) return AppState.inflight;
    AppState.inflight = api('state').then((s) => {
        if (!s || s.ok !== true) throw new Error('bad-state');
        AppState.data = s;
        AppState.ts = Date.now();
        notifyAppState();
        return s;
    }).catch((err) => {
        console.warn("[state] /api/state ishlamadi, URL zaxira yo'li ishlatiladi:", err);
        return null;
    }).finally(() => {
        AppState.inflight = null;
    });
    return AppState.inflight;
}

// Claim'dan keyin keshni serverdagi yangi holatga moslaydi (qayta so'ramasdan)
function patchAppState(patch) {
    if (AppState.data) {
        Object.assign(AppState.data, patch);
        AppState.ts = Date.now();
        notifyAppState();
    }
}

function invalidateAppState() {
    AppState.ts = 0;
}

// Claim javobi kelmasa (timeout / tarmoq / 5xx) server ballni ALLAQACHON bergan bo'lishi mumkin
// (server uzoqda, javob 8 s dan kechikishi mumkin). Shuning uchun darhol botga otmasdan, holat qayta so'raladi.
// Qaytaradi: yangi state yoki null (holat ham olinmadi — chaqiruvchi eski deep link zaxira yo'liga o'tadi).
async function recoverStateAfterClaimFailure() {
    invalidateAppState();
    return await getAppState(0);
}

// Headerdagi umumiy ball
function setGlobalScore(value) {
    const scoreEl = document.getElementById('global-score');
    const scoreValEl = document.getElementById('global-score-val');
    if (scoreEl && scoreValEl && value !== null && value !== undefined) {
        scoreValEl.textContent = String(value);
        scoreEl.hidden = false;
    }
}

// ═══════════════════════════════════════════════════════════════════
// PREMIUM KO'RINISHI (A1–A4): header belgisi, "Mening Premiumim" kartasi, tugash banneri, tarif rangi.
// Hammasi /api/state dagi HAQIQIY holatdan: is_premium, premium_type, premium_expires_at (muddatsizda null),
// premium_unlimited, premium_days_left (muddatsizda null), ai_remaining / ai_limit / ai_bonus.
// Matnlar textContent bilan qo'yiladi; ikonkalar sprite'dan (emoji emas). Bepul foydalanuvchida hech narsa ko'rinmaydi.
// ═══════════════════════════════════════════════════════════════════
const PREMIUM_TIER_KEYS = ['pro', 'plus', 'ultra'];
const PREMIUM_TIERS = {
    pro: { name: 'Pro', icon: 'star' },
    plus: { name: 'Plus', icon: 'gem' },
    ultra: { name: 'Ultra', icon: 'crown' }
};
const PREMIUM_BANNER_KEY = 'premium_banner_dismissed';       // yopilgan banner: shu premium_expires_at qiymati uchun
const PREMIUM_BANNER_DAYS = 2;                                 // 2 kun yoki undan kam qolganda

// Holatdan Premium ma'lumoti yoki null (bepul / noma'lum tarif). Muddat maydonlari bo'lmasa (eski server) — faqat tarif.
function premiumInfo(s) {
    if (!s || !s.is_premium || !PREMIUM_TIERS[s.premium_type]) return null;
    const unlimited = s.premium_unlimited === true;
    const expires = (typeof s.premium_expires_at === 'string' && s.premium_expires_at) ? s.premium_expires_at : null;
    const days = (typeof s.premium_days_left === 'number') ? s.premium_days_left : null;
    const hasTerm = !unlimited && expires !== null && days !== null;
    const meta = PREMIUM_TIERS[s.premium_type];
    return {
        tier: s.premium_type, name: meta.name, icon: meta.icon,
        unlimited: unlimited, expires: expires, days: days, hasTerm: hasTerm,
        // Server qolgan kunni ceil((tugash - hozir) / 1 kun) deb beradi: 1 — tugashiga 24 soatdan oshmagan, ya'ni
        // "bugun tugaydi". Qurilma soatiga tayanilmaydi (soat noto'g'ri bo'lsa ham matn server bilan mos qoladi)
        today: hasTerm && days <= 1
    };
}

// Header: "Ultra · 5 kun" | "Ultra · ♾" | "Ultra · bugun" | "Ultra" (muddat noma'lum)
function premiumShortText(p) {
    if (p.unlimited) return `${p.name} · ♾`;
    if (!p.hasTerm) return p.name;
    return p.today ? `${p.name} · bugun` : `${p.name} · ${p.days} kun`;
}

// "2026-12-15T18:00:00+05:00" -> "15.12.2026" (server Toshkent vaqtida beradi; qurilma mintaqasiga bog'liq emas)
function premiumDateText(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

// Qolgan kunlar chizig'ining to'liq uzunligi: 1–7 kun -> 7, 8–30 kun -> 30, undan ko'p -> 90
function premiumBarMax(days) {
    return days <= 7 ? 7 : (days <= 30 ? 30 : 90);
}

function openPremiumModalFromUi() {
    const btn = document.getElementById('btn-open-premium');       // mavjud Premium oynasi (#premium-modal)
    if (btn) btn.click();
}

function setPremiumBadge(s) {
    const el = document.getElementById('hdr-premium');
    const nameEl = document.getElementById('hdr-premium-name');
    if (el && nameEl) {
        PREMIUM_TIER_KEYS.forEach((t) => el.classList.remove('hdr-premium--' + t));
        const p = premiumInfo(s);
        if (p) {
            nameEl.textContent = premiumShortText(p);
            el.classList.add('hdr-premium--' + p.tier);
            const use = el.querySelector('use');
            if (use) use.setAttribute('href', '#i-' + p.icon);
            el.setAttribute('aria-label', `Premium ${p.name}`);
            el.hidden = false;
        } else {
            el.removeAttribute('aria-label');
            el.hidden = true;
        }
    }
    const banner = document.getElementById('btn-open-premium');
    if (banner) banner.hidden = !!(s && s.is_premium);
}

// A2: Sog'liq tabining tepasidagi "Mening Premiumim" kartasi
function renderPremiumCard(s) {
    const card = document.getElementById('my-premium');
    if (!card) return;
    const p = premiumInfo(s);
    if (!p) { card.hidden = true; return; }
    card.hidden = false;
    document.getElementById('mp-tier').textContent = `Premium ${p.name}`;
    const use = card.querySelector('.mp-badge use');
    if (use) use.setAttribute('href', '#i-' + p.icon);
    document.getElementById('mp-until').textContent = p.unlimited ? 'Muddatsiz' : premiumDateText(p.expires);

    const bar = document.getElementById('mp-bar');
    const left = document.getElementById('mp-left');
    if (p.hasTerm) {
        const max = premiumBarMax(p.days);
        const now = Math.min(Math.max(p.days, 0), max);
        bar.setAttribute('aria-valuemax', String(max));
        bar.setAttribute('aria-valuenow', String(now));
        bar.setAttribute('aria-valuetext', p.today ? 'Bugun tugaydi' : `${p.days} kun qoldi`);
        bar.style.setProperty('--mp-pct', String(Math.round((now / max) * 100)));
        bar.hidden = false;
        left.textContent = p.today ? 'Bugun tugaydi' : `${p.days} kun qoldi`;
        left.hidden = false;
    } else {
        bar.hidden = true;                                    // muddatsiz yoki muddat noma'lum: chiziq ma'nosiz
        left.textContent = p.unlimited ? 'Muddatsiz' : '';
        left.hidden = !p.unlimited;
    }

    const ai = document.getElementById('mp-ai');
    if (typeof s.ai_remaining === 'number' && typeof s.ai_limit === 'number') {
        const bonus = Number(s.ai_bonus) || 0;                // ai_remaining bonusni ham o'z ichiga oladi
        ai.textContent = `Bugungi AI limit: ${Math.max(0, s.ai_remaining - bonus)}/${s.ai_limit}` +
            (bonus > 0 ? ` + ${bonus} bonus` : '');
        ai.hidden = false;
    } else {
        ai.hidden = true;
    }
    document.getElementById('mp-extend').hidden = p.unlimited;   // muddatsizda uzaytirish yo'q
}

// A3: bosh ekran tepasida tugash ogohlantirishi (muddatli, <= 2 kun). Yopilishi shu premium_expires_at uchun saqlanadi
function renderPremiumBanner(s) {
    const banner = document.getElementById('prem-banner');
    if (!banner) return;
    const p = premiumInfo(s);
    const show = !!p && !p.unlimited && p.hasTerm && p.days <= PREMIUM_BANNER_DAYS &&
        SafeStorage.getItem(PREMIUM_BANNER_KEY) !== p.expires;
    banner.hidden = !show;
    if (show) {
        banner.dataset.expires = p.expires;
        document.getElementById('prem-banner-text').textContent = p.today
            ? 'Premiumingiz bugun tugaydi'
            : `Premiumingiz ${p.days} kundan keyin tugaydi`;
    }
}

// A4: tarif rangidagi aksent (faqat --primary / --on-primary / --primary-soft); Premium tugasa klass olib tashlanadi
function applyPremiumTier(s) {
    const p = premiumInfo(s);
    PREMIUM_TIER_KEYS.forEach((t) => document.body.classList.remove('tier-' + t));
    if (p) document.body.classList.add('tier-' + p.tier);
    MainButtonCtl.refreshColors();                            // Telegram MainButton rangi ham tarifga mos
}

function renderPremiumUi(s) {
    setPremiumBadge(s);
    renderPremiumCard(s);
    renderPremiumBanner(s);
    applyPremiumTier(s);
}

document.addEventListener('DOMContentLoaded', () => {
    const extend = document.getElementById('mp-extend');
    if (extend) extend.addEventListener('click', openPremiumModalFromUi);
    const bannerExtend = document.getElementById('prem-banner-extend');
    if (bannerExtend) bannerExtend.addEventListener('click', openPremiumModalFromUi);
    const bannerClose = document.getElementById('prem-banner-close');
    if (bannerClose) {
        bannerClose.addEventListener('click', () => {
            const banner = document.getElementById('prem-banner');
            if (banner && banner.dataset.expires) SafeStorage.setItem(PREMIUM_BANNER_KEY, banner.dataset.expires);
            if (banner) banner.hidden = true;
        });
    }
});

// Mini app ochilganda (menyu tugmasidan ham — URL'da hech narsa bo'lmaydi) ball serverdan olinadi
document.addEventListener('DOMContentLoaded', () => {
    getAppState(60000).then((s) => { if (s) { setGlobalScore(s.score); setPremiumBadge(s); } });
});

if (tg) {
    try {
        tg.ready();
        tg.expand();
    } catch (e) {
        console.warn("Telegram WebApp ready/expand failed:", e);
    }
}

// ═══════════════════════════════════════════════════════════════════
// UNIVERSAL NAVIGATION MANAGER
// ═══════════════════════════════════════════════════════════════════
const AppNavigation = (function () {
    const stack = [];   // [{type, close}]
    let backBtn = null;
    let lastBackTime = 0;

    function getBackBtn() {
        if (!backBtn) backBtn = document.getElementById('header-back-btn');
        return backBtn;
    }

    // Telegram ichida o'z tugmamiz o'rniga tg.BackButton (stek bo'sh bo'lmasa ko'rinadi)
    function tgBackButton() {
        return (tg && tg.initData && tg.BackButton) ? tg.BackButton : null;
    }

    function updateBtn() {
        const btn = getBackBtn();
        const tgBtn = tgBackButton();
        if (tgBtn) {
            try {
                if (stack.length > 0) tgBtn.show(); else tgBtn.hide();
            } catch (e) { /* eski klient */ }
            if (btn) btn.classList.add('hidden');
            return;
        }
        if (!btn) return;
        btn.classList.toggle('hidden', stack.length === 0);
    }

    function push(entry) {
        // entry = { type: string, close: function }
        stack.push(entry);
        updateBtn();
    }

    function pop() {
        if (stack.length === 0) return;
        stack.pop();
        updateBtn();
    }

    function back() {
        const now = Date.now();
        if (now - lastBackTime < 300) return;  // debounce 300ms
        lastBackTime = now;

        if (stack.length === 0) return;
        const top = stack[stack.length - 1];
        if (top && typeof top.close === 'function') {
            top.close();
        }
        // pop() is called inside close handlers
    }

    function init() {
        const btn = getBackBtn();
        if (btn) {
            btn.addEventListener('click', back);
        }
        const tgBtn = tgBackButton();
        if (tgBtn && tgBtn.onClick) {
            try { tgBtn.onClick(back); } catch (e) { /* eski klient */ }
        }
        document.body.classList.toggle('has-tg-back', !!tgBtn);
        updateBtn();
    }

    return { push, pop, back, init };
})();

document.addEventListener('DOMContentLoaded', () => { AppNavigation.init(); });

// ═══════════════════════════════════════════════════════════════════
// GLOBAL SCORE DISPLAY
// ═══════════════════════════════════════════════════════════════════
const urlParams = new URLSearchParams(window.location.search);
const userScore = urlParams.get('score');
if (userScore !== null) {
    document.addEventListener('DOMContentLoaded', () => {
        const scoreEl = document.getElementById('global-score');
        const scoreValEl = document.getElementById('global-score-val');
        if (scoreEl && scoreValEl) {
            scoreValEl.textContent = userScore;
            scoreEl.hidden = false;
        }
    });
}

// ═══════════════════════════════════════════════════════════════════
// DARK / LIGHT MODE
// ═══════════════════════════════════════════════════════════════════

// Mavzu: foydalanuvchi tanlovi (Avto/Kunduzgi/Tungi). Avto — Telegram (tg.colorScheme, themeChanged),
// Telegram tashqarisida — tizim sozlamasi.
function currentThemeMode() {
    const pref = readThemePref();
    return pref === 'auto' ? autoThemeMode() : pref;
}

function applyTheme(mode) {
    const body = document.body;
    body.classList.toggle('dark-mode', mode === 'dark');
    // Telegram'ning yorug' mavzu ranglari faqat Telegram ham yorug' bo'lsa ishlatiladi (aks holda aralash ranglar)
    body.classList.toggle('tg-light', mode === 'light' && !!tg && tg.colorScheme === 'light');
    syncTelegramChrome();
    // Ko'rinib turgan MainButton ham yangi mavzu ranglarini oladi (--primary / --on-primary)
    try { MainButtonCtl.refreshColors(); } catch (e) { /* hali e'lon qilinmagan */ }
    // Grafik ranglari CSS tokenlaridan olinadi — mavzu o'zgarsa qayta chiziladi
    if (document.getElementById('bmi-chart')) { try { drawChart(currentHistory); } catch (e) { /* hali tayyor emas */ } }
}

// Telegram sarlavha va fon rangini ilova tokenlariga moslaydi (--surface / --bg)
function syncTelegramChrome() {
    if (!tg) return;
    try {
        const cs = getComputedStyle(document.body);
        const surface = cs.getPropertyValue('--surface').trim();
        const bg = cs.getPropertyValue('--bg').trim();
        if (tg.setHeaderColor && /^#[0-9a-f]{6}$/i.test(surface)) tg.setHeaderColor(surface);
        if (tg.setBackgroundColor && /^#[0-9a-f]{6}$/i.test(bg)) tg.setBackgroundColor(bg);
    } catch (e) {
        console.warn("Telegram rangini o'rnatib bo'lmadi:", e);
    }
}

function initTheme() {
    applyTheme(currentThemeMode());
    // Qo'lda tanlangan bo'lsa (Kunduzgi/Tungi) Telegram/tizim mavzusi o'zgarishi e'tiborga olinmaydi
    const followAuto = () => { if (readThemePref() === 'auto') applyTheme(currentThemeMode()); };
    if (tg && tg.onEvent) {
        try { tg.onEvent('themeChanged', followAuto); } catch (e) { /* eski klient */ }
    } else if (window.matchMedia) {
        try {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', followAuto);
        } catch (e) { /* eski brauzer */ }
    }
    initThemePicker();
    initThemeToggle();
}

// "Ko'rinish" — radiogroup (roving tabindex, ←/→/↑/↓, Home/End)
function renderThemePicker() {
    const pref = readThemePref();
    document.querySelectorAll('[data-theme-mode]').forEach(btn => {
        const on = btn.getAttribute('data-theme-mode') === pref;
        btn.setAttribute('aria-checked', on ? 'true' : 'false');
        btn.tabIndex = on ? 0 : -1;
    });
    renderThemeToggle();                     // headerdagi tugma ham shu tanlovni ko'rsatadi (ikki tomonlama sinxron)
}

// Headerdagi rejim tugmasi (ism yonida): joriy tanlov ikonkasi; bosilganda Avto -> Kunduzgi -> Tungi -> Avto.
// Saqlash, qo'llash, haptic, MainButton ranglari — mavjud setThemePref() orqali (mantiq o'zgarmagan).
const THEME_NAMES = { auto: 'Avto', light: 'Kunduzgi', dark: 'Tungi' };
const THEME_ICONS = { auto: 'monitor', light: 'sun', dark: 'moon' };

function renderThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const pref = readThemePref();
    btn.setAttribute('aria-label', `Rejim: ${THEME_NAMES[pref]}. Almashtirish uchun bosing`);
    btn.setAttribute('data-theme-pref', pref);
    const use = btn.querySelector('use');
    if (use) use.setAttribute('href', '#i-' + THEME_ICONS[pref]);
}

function initThemeToggle() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const next = THEME_MODES[(THEME_MODES.indexOf(readThemePref()) + 1) % THEME_MODES.length];
        setThemePref(next, false);
        showToast(`Rejim: ${THEME_NAMES[next]}`);          // #toast — role="status", aria-live="polite"
    });
    renderThemeToggle();
}

function setThemePref(value, focus) {
    if (!THEME_MODES.includes(value)) return;
    saveThemePref(value);
    themePrefInSession = value;
    applyTheme(currentThemeMode());          // setHeaderColor / setBackgroundColor ham shu yerda (syncTelegramChrome)
    renderThemePicker();
    if (focus) {
        const btn = document.querySelector(`[data-theme-mode="${value}"]`);
        if (btn) btn.focus();
    }
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged(); } catch (e) { /* yo'q */ }
}


function initThemePicker() {
    const group = document.querySelector('.theme-seg');
    if (!group) return;
    group.querySelectorAll('[data-theme-mode]').forEach(btn => {
        btn.addEventListener('click', () => setThemePref(btn.getAttribute('data-theme-mode'), false));
    });
    group.addEventListener('keydown', (e) => {
        const order = THEME_MODES;
        const i = order.indexOf(readThemePref());
        let j = null;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % order.length;
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i + order.length - 1) % order.length;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = order.length - 1;
        if (j === null) return;
        e.preventDefault();
        setThemePref(order[j], true);
    });
    renderThemePicker();
}


// ═══════════════════════════════════════════════════════════════════
// DATA SETS
// ═══════════════════════════════════════════════════════════════════

const FIRST_AID_ITEMS = [
    {
        id: "kuyish",
        title: "🔥 Kuyish",
        icon: "fa-fire-burner",
        color: "var(--accent-orange)",
        bgColor: "var(--accent-orange-bg)",
        urgency: "high",
        desc: "Kuyganda to'g'ri birinchi yordam ko'rsatish va sovutish.",
        symptoms: ["Qizarish va shish paydo bo'lishi", "Pufakchalar hosil bo'lishi", "Kuchli achishish va og'riq", "3-darajali kuyishda teri qorayib, sezgisiz bo'lib qoladi"],
        steps: [
            "Kuygan joyni zudlik bilan kamida 20 daqiqa davomida oqib turgan sovuq (lekin muzdek emas) suv ostida tuting.",
            "Kuygan sohaga steril bog'lam yoki toza latta yoping — mahkam o'ramasdan, yumshoq qo'ying.",
            "Agar kiyim teriga yopishib qolgan bo'lsa, uni majburlab sug'urib olmang! Atrofini kesib oling.",
            "Bemorga ko'proq suyuqlik (suv, choy) ichiring — organizm suyuqlikni ko'p yo'qotadi.",
            "Og'riqni kamaytirish uchun ibuprofen yoki paracetamol bering."
        ],
        prohibited: "Kuygan joyga yog', sariyog', tish pastasi yoki spirt surtmang! Hosil bo'lgan pufakchalarni aslo yormang!",
        tips: ["Kuyish maydoni kaft o'lchamidan katta bo'lsa — shifokorga boring", "Qovoq yoki kartoshka shirasi xalq tabobatida ishlatilsa ham, tibbiy jihatdan tavsiya etilmaydi"],
        whenToCall103: ["Kuyish maydoni katta bo'lsa (kaft o'lchamidan katta)", "Yuz, qo'l, oyoq, jinsiy a'zolar yoki bo'g'imlar kuygan bo'lsa", "Bemor 5 yoshdan kichik yoki 60 yoshdan katta bo'lsa", "Kuyish kimyoviy modda yoki elektr tokidan bo'lsa"]
    },
    {
        id: "qon_ketishi",
        title: "🩸 Qon ketishi",
        icon: "fa-droplet",
        color: "var(--accent-red)",
        bgColor: "var(--accent-red-bg)",
        urgency: "critical",
        desc: "Kuchli qon ketishini to'xtatish va jgut bog'lash qoidalari.",
        symptoms: ["Qip-qizil (vena) yoki och qizil, otilib chiquvchi (arteriya) qon", "Bosh aylanishi va keskin holsizlanish", "Rangi o'chib, terisi oqarishi", "Yurak tez urishi va sovuq ter"],
        steps: [
            "Yara ustiga toza bog'lam yoki latta qo'yib, qo'l bilan 5-10 daqiqa davomida mahkam bosing.",
            "Iloji bo'lsa, jarohatlangan a'zoni yurak sathidan balandroq ko'taring.",
            "Kuchli arterial qon ketishida yaraning yuqori qismidan turniket (jgut) bog'lang va ALBATTA vaqtini yozib qo'ying.",
            "Birinchi yordamchi jgutni aslo bo'shatmasligi kerak, uni faqat shifokor bo'shatishi yoki yechishi mumkin.",
            "Qon bog'lamni shimib o'tgan bo'lsa, uni surib olmang — ustiga yangi qavat qo'ying."
        ],
        prohibited: "Yaradagi yot jismlarni (shisha bo'lagi, sim, mix) o'zboshimchalik bilan sug'urib olmang! Bu qon ketishini kuchaytiradi.",
        tips: ["Turniket vaqtini bemorning manglayiga yoki qog'ozga yozing — shifoxona uchun muhim", "Qo'lqop bilan qon bilan aloqani cheklang — infeksiyadan himoya"],
        whenToCall103: ["Qon ketish to'xtatib bo'lmasa", "Kuchli arterial qon ketish bo'lsa", "Bemor hushini yo'qotsa", "Yara juda katta va chuqur bo'lsa"]
    },
    {
        id: "sinish",
        title: "🦴 Suyak sinishi",
        icon: "fa-bone",
        color: "var(--accent-blue)",
        bgColor: "var(--accent-blue-bg)",
        urgency: "high",
        desc: "Suyak singanda shina qo'yish va og'riqsizlantirish.",
        symptoms: ["Shikastlangan joyda keskin og'riq", "Shish va ko'karish paydo bo'lishi", "A'zoni harakatlantira olmaslik", "Ba'zan suyak ko'rinib qolishi (ochiq sinish)"],
        steps: [
            "Shikastlangan a'zoni harakatsiz holatga keltiring.",
            "Shina sifatida taxtacha, qattiq karton yoki tekis buyumdan foydalanib bog'lang — singan bo'g'imning pastki va yuqori qismini qamrab olsin.",
            "Shish va og'riqni kamaytirish uchun latta bilan o'ralgan muz qo'ying (20 daq, keyin 20 daq tanaffus).",
            "Ochiq sinishda avval yaraga steril bog'lam qo'ying, so'ngra shinani mahkamlang.",
            "Og'riqsizlantirish uchun ibuprofen bering va tez yordamni kutish davomida bemorni iliq saqlang."
        ],
        prohibited: "Singan suyakni o'z joyiga solishga yoki to'g'rilashga urinmang! Bemorni ortiqcha harakatlantirmang.",
        tips: ["Shina juda qattiq bog'lanmasin — barmoqlar ko'karsa bo'shatib qo'ying", "Sinish sohasini yurakdan baland tutish shishni kamaytiradi"],
        whenToCall103: ["Bel umurtqasi, tos suyagi yoki bosh suyagi singanda", "Suyak teriga tashqariga chiqib qolgan bo'lsa (ochiq sinish)", "Bemor qo'l-oyog'ini his qilmayotgan bo'lsa", "A'zo g'ayriy tabiiy holda qiyshayib qolgan bo'lsa"]
    },
    {
        id: "bogilish",
        title: "🫣 Bo\'g\'ilish",
        icon: "fa-head-side-cough",
        color: "var(--accent-orange)",
        bgColor: "var(--accent-orange-bg)",
        urgency: "critical",
        desc: "Tomoqqa narsa tiqilib qolganda Geymlix usulini qo\'llash.",
        symptoms: ["Birdan gapirishda qiynalish yoki ovoz chiqmasligi", "Nafas olishda xirillash yoki hech nafas yo'qligi", "Yuz binafsha yoki ko'karishi", "Ikkala qo'l bilan tomoqni ushlab turish (universal bo'g'ilish belgisi)"],
        steps: [
            "Agar bemor yo'tala olsa, uni qattiqroq yo'talishga undang — eng yaxshi tabiiy yo'l.",
            "Bemor ozroq oldinga engashsin. Kaftingiz asosi bilan kuraklari orasiga 5 marta kuchli zarb bilan uring.",
            "Geymlix usuli: Bemor orqasidan turib, belidan quchoqlang. Bir qo'lni musht qilib, kindikdan biroz yuqoriga qo'ying. Ikkinchi qo'l bilan mushtni tutib, o'zingizga va yuqoriga 5 marta keskin torting. (1 yoshgacha bolalarga qo'llanilmaydi).",
            "Kerak bo'lsa, 5 zarb + 5 Geymlix kombinatsiyasini navbatlashing.",
            "Hushsiz holatda: Bemorni yotqizib, og'izni tekshiring, ko'rinadigan jismni olib tashlang va CPR boshlang."
        ],
        prohibited: "Tomoqdagi yot jismni ko'rmasdan turib barmoq bilan qidirib tortishga urinmang! Uni yanada chuqurroq tiqib yuborishingiz mumkin.",
        tips: ["Chaqaloqlarda (1 yoshgacha) Geymlix usuli QILINMAYDI — maxsus usul qo'llaniladi", "Jism chiqqan bo'lsa ham, 103 ga qo'ng'iroq qiling — shifokor tekshirishi kerak"],
        whenToCall103: ["Jism chiqmasa va bemor nafas ololmayotgan bo'lsa — DARHOL", "Bemor hushini yo'qotsa", "Jism chiqqandan keyin ham nafas qiynalsa", "Bolada bo'g'ilish bo'lsa"]
    },
    {
        id: "yurak_xuruji",
        title: "💔 Yurak xuruji",
        icon: "fa-heart-circle-xmark",
        color: "var(--accent-red)",
        bgColor: "var(--accent-red-bg)",
        urgency: "critical",
        desc: "Ko'krak qafasidagi kuchli siquvchi og'riqda tezkor choralar.",
        symptoms: ["Ko'krakda siquvchi, ezuvchi og'riq (15 daqiqadan ortiq)", "Og'riq chap qo'l, yelka, bo'yin yoki jagga tarqalishi", "Nafas qisilishi va sovuq ter", "Ko'ngil aynishi va qusish", "Qo'rquv va holsizlik"],
        steps: [
            "Bemorni zudlik bilan yarim o'tirgan holatga keltiring, tinchlantiring.",
            "Yoqasini oching, bo'yinbog'ini bo'shating, toza havo kelishini ta'minlang.",
            "DARHOL 103 chaqiring — har daqiqa muhim!",
            "Agar mavjud bo'lsa, til ostiga 1 ta Nitrogliserin tabletkasini qo'ying — 5 daqiqadan keyin o'tmasa yana 1 ta.",
            "Bemor hushini yo'qotsa va nafasdan qolsa — CPR (yurak-o'pka reanimatsiyasi) ni boshlang."
        ],
        prohibited: "Bemorni turishga, yurishga yoki jismoniy zo'riqishga majburlamang! Bemorni yolg'iz qoldirmang.",
        tips: ["CPR: To'sh suyagining markaziga ikkala qo'l bilan minutiga 100-120 marta 5 sm chuqurlikda bosing", "Aspirin chaynash (qon suyultiradi) — faqat allergiyasi bo'lmasa"],
        whenToCall103: ["Ko'krakda og'riq 5 daqiqadan ko'p davom etsa — DARHOL", "Nafas qisilishi boshlanib qolsa", "Bemor hushini yo'qotsa", "Birinchi marta shunday og'riq bo'lsa"]
    },
    {
        id: "hushdan_ketish",
        title: "😵 Hushdan ketish",
        icon: "fa-face-dizzy",
        color: "var(--accent-blue)",
        bgColor: "var(--accent-blue-bg)",
        urgency: "medium",
        desc: "Hushini yo'qotgan odamni o'ziga keltirish va yotqizish.",
        symptoms: ["To'satdan kuchsizlanish va ko'z qorayishi", "Ko'ngil aynishi va terlash", "Rangi o'chib, terisi oqarishi", "Quloqlarda shovqin"],
        steps: [
            "Bemorni tekis joyga orqasi bilan yotqizib, oyoqlarini 30 sm balandlikka ko'taring — miyaga qon oqimini oshirish uchun.",
            "Nafas olishini osonlashtirish uchun kiyimlarini bo'shating.",
            "Agar bemor 1 daqiqada o'ziga kelmasa yoki nafas olmasa, zudlik bilan 103 chaqiring va kerak bo'lsa yurak-o'pka reanimatsiyasini boshlang.",
            "Agar bemor nafas olayotgan bo'lsa-yu hushiga kelmasa, uni xavfsiz yonbosh holatga yotqizib qo'ying.",
            "Hushiga kelgach, 5-10 daqiqa yotsin — shoshilinch turg'izib yubormang."
        ],
        prohibited: "Hushsiz odamning og'ziga suv quymang yoki dori tiqmang! U bo'g'ilib qolishi mumkin.",
        tips: ["Hushdan ketishdan oldin ko'pincha ogohlantiruv belgilari bo'ladi — darhol o'tirib qolsa qon aylanish tiklanadi", "Ko'p takrorlansa — shifokorga murojaat zarur (yurak yoki asab kasalligi)"],
        whenToCall103: ["Bemor 1 daqiqadan ko'p hushsiz qolsa", "Hushiga kelgandan keyin gapirishda muammo bo'lsa", "Yiqilib, boshini urib olgan bo'lsa", "Yurak kasalligi tarixi bo'lgan odamda hushdan ketish bo'lsa"]
    },
    {
        id: "zaharlanish",
        title: "🧪 Zaharlanish",
        icon: "fa-vial",
        color: "var(--accent-green)",
        bgColor: "var(--accent-green-bg)",
        urgency: "high",
        desc: "Kimyoviy moddalar yoki eskirgan taomdan zaharlanish.",
        symptoms: ["Ko'ngil aynishi va qusish", "Qorin og'rig'i va ich ketishi", "Bosh og'rig'i va bosh aylanishi", "Og'izda achish yoki achchiq ta'm", "Ko'z qorachig'i kengayishi yoki torayishi (kimyoviy zaharlanishda)"],
        steps: [
            "Darhol 103 ga qo'ng'iroq qiling: nima, qancha va qachon ichilganini ayting.",
            "Bemorni qustirishga urinmang. Zahar turiga ko'ra bu vaziyatni yomonlashtirishi mumkin.",
            "Qadoqni saqlab qo'ying — bu shifoxonada davolashni osonlashtiradi.",
            "Zaharli gazdan zaharlanganda zudlik bilan toza havoga olib chiqing va kiyimlarini bo'shating.",
            "Agar bemor hushsiz, lekin nafas olayotgan bo'lsa, xavfsiz yonbosh holatga yotqizib qo'ying."
        ],
        prohibited: "Kislota, ishqor yoki neft mahsulotlari bilan zaharlanganda qustirish mutlaqo taqiqlanadi! (Va umuman, oddiy odamga qustirish tavsiya etilmaydi).",
        tips: ["Zaharlanish o'tgan ovqatni saqlang yoki rasmga oling — laboratoriya uchun kerak", "Zahar qutisini yoki nomini yozib, 103 operatoriga ayting"],
        whenToCall103: ["Kimyoviy modda bilan zaharlanishda — DARHOL", "Bemor hushsiz bo'lsa", "Bolada zaharlanish bo'lsa", "Simptomlar 6 soatdan ko'p davom etsa"]
    },
    {
        id: "issiqlik_urishi",
        title: "☀️ Issiqlik urishi",
        icon: "fa-sun",
        color: "var(--accent-orange)",
        bgColor: "var(--accent-orange-bg)",
        urgency: "high",
        desc: "Quyosh va issiq havoda tana harorati ko'tarilganda sovutish.",
        symptoms: ["Tana harorati 40°C dan oshishi", "Ter chiqmasligi — xavfli belgi!", "Qizil va quruq teri", "Bosh og'rig'i, ko'ngil aynishi, qayt qilish", "Ong butalishi yoki hushdan ketish"],
        steps: [
            "Bemorni ZUDLIK bilan soya, salqin va havo aylanadigan joyga olib o'ting.",
            "Ustki kiyimlarini yeching yoki bo'shating.",
            "Peshonasiga, bo'yniga, qo'ltiq ostiga sovuq suvda ho'llangan latta qo'ying.",
            "Hushida bo'lsa, tez-tez oz-ozdan sovuq suv yoki mineral suv ichiring.",
            "Tana haroratini 38°C gacha tushirishga harakat qiling."
        ],
        prohibited: "Tana harorati juda yuqori bo'lganda bemorni muzdek suvli vannaga birdan solmang — shok holatiga tushishi mumkin.",
        tips: ["Issiq kunlarda qorni to'q holda, tush paytida uzoq qolmang", "Harorat 38°C ga tushgach, sovutishni to'xtating — ortiqcha sovutish ham xavfli"],
        whenToCall103: ["Tez yordam: issiqlik urishi shoshilinch holat, zudlik bilan 103 chaqiring!", "Bemor hushini yo'qotsa", "Tana harorati 40°C dan oshsa", "Ter chiqmayotgan bo'lsa"]
    },
    {
        id: "reanimatsiya",
        title: "🫀 CPR (Yurak-o'pka reanimatsiyasi)",
        icon: "fa-heart-pulse",
        color: "var(--accent-red)",
        bgColor: "var(--accent-red-bg)",
        urgency: "critical",
        desc: "Yurak to'xtaganda va nafas olmaganda zudlik bilan qo'llaniladigan usul.",
        symptoms: ["Bemor hushsiz", "Nafas olmayapti yoki normal nafas olmayapti (masalan, og'ir hansirash)", "Tomir urishi sezilmaydi"],
        steps: [
            "Tez yordam (103) ga qo'ng'iroq qiling (telefonni baland ovozga qo'yib CPR ni boshlang).",
            "Bemorni qattiq, tekis yuzaga yotqizing. Ikkala qo'lingizni ustma-ust qilib, ko'krak qafasining o'rtasiga qo'ying.",
            "Ko'krak qafasini kamida 5-6 sm chuqurlikda, tez va kuchli (daqiqasiga 100-120 marta tezlikda) bosing.",
            "Har 30 ta bosishdan so'ng, bemorning burnini qisib, og'zidan 2 marta oddiy nafas bering (qila olmasangiz, faqat bosishda davom eting).",
            "Tez yordam kelguncha yoki bemor o'ziga kelguncha CPR ni to'xtatmang."
        ],
        prohibited: "Bemorni yumshoq joyda yotqizib CPR qilmang (kuch yo'qoladi). Qo'llarni bukmang (to'g'ri tursin).",
        tips: ["Bosishlar o'rtasida ko'krak qafasining to'liq ko'tarilishiga ruxsat bering"],
        whenToCall103: ["Darhol chaqirilishi shart!"]
    }
];

const DISEASES_DATA = [
    { name: "Gripp", cat: "Infeksiya", desc: "O'tkir respirator virusli infeksiya. Yuqori harorat, burun oqishi va bo'g'imlar og'rig'i bilan kechadi.", aid: "Bemorga ko'p iliq suyuqlik ichiring, isitma tushiruvchi dorilar bering, xonani tez-tez shamollating." },
    { name: "SORS (shamollash)", cat: "Infeksiya", desc: "Burun va tomoqning o'tkir shamollashi.", aid: "Dam olish, iliq choy ichish, tomoqni chayish va burunga sho'r suv tomizish." },
    { name: "Angina", cat: "Tomoq", desc: "Tomoq bezlarining o'tkir yallig'lanishi, yutish qiyinligi va yuqori harorat.", aid: "Antiseptik eritmalarda tomoqni chayish, shifokor buyurgan antibiotiklarni qabul qilish." },
    { name: "Bronxit", cat: "Nafas", desc: "Bronxlar shilliq qavatining yallig'lanishi, kuchli yo'tal.", aid: "Ko'p suyuqlik ichish, ingalyatsiya qilish, yo'talga qarshi shifokor yozgan dorilar." },
    { name: "Pnevmoniya", cat: "Nafas", desc: "O'pkaning yallig'lanishi. Qiyin nafas olish va isitma bilan kechadi.", aid: "Zudlik bilan shifokor chaqirish, shifoxonada davolanish tavsiya etiladi." },
    { name: "Astma", cat: "Nafas", desc: "Nafas qisilishi xurujlari bilan kechadigan surunkali kasallik.", aid: "Xuruj paytida bemorni o'tqizib, bronx kengaytiruvchi shaxsiy ingalyatoridan foydalanishga yordam bering." },
    { name: "Sil (tuberkulyoz)", cat: "Infeksiya", desc: "O'pkani shikastlovchi yuqumli bakterial kasallik.", aid: "Zudlik bilan shifokor nazoratida uzoq muddatli maxsus antibiotiklar kursini olish." },
    { name: "COVID-19", cat: "Infeksiya", desc: "Koronavirus keltirib chiqaradigan o'tkir infeksiya.", aid: "Izolyatsiya qilish, tana haroratini nazorat qilish va shifokor ko'rsatmasi bilan davolanish." },
    { name: "Sinusit", cat: "Nafas", desc: "Burun atrofi bo'shliqlarining yallig'lanishi, bosh og'rig'i.", aid: "Burunni tuzli suv bilan yuvish, shifokor buyurgan tomchilar va dori vositalari." },
    { name: "Otit (quloq yallig'lanishi)", cat: "Quloq", desc: "Quloq yo'lining o'tkir yallig'lanishi, kuchli og'riq va isitma.", aid: "Quloqqa issiq narsa bosmaslik, shifokor buyurgan tomchilardan foydalanish, og'riqsizlantirish." },
    { name: "Gastrit", cat: "Oshqozon", desc: "Oshqozon shilliq qavati yallig'lanishi, achishish og'rig'i.", aid: "Parhez qilish (achchiq va yog'lidan tiyilish), me'yorida ovqatlanish, shifokor dorilari." },
    { name: "Oshqozon yarasi", cat: "Oshqozon", desc: "Oshqozon yoki o'n ikki barmoqli ichak devorida yara paydo bo'lishi.", aid: "Qat'iy parhez, kislotalilikni kamaytiruvchi dorilar ichish, shoshilinchda shifokorga murojaat." },
    { name: "Pankreatit", cat: "Oshqozon", desc: "Oshqozon osti bezining yallig'lanishi, kuchli o'rab oluvchi og'riq.", aid: "Ochlik (1-2 kun ovqat yemaslik), sovuq kompres, zudlik bilan shifokor chaqirish." },
    { name: "Xoletsistit", cat: "Oshqozon", desc: "O't pufagining yallig'lanishi, o'ng qovurg'a ostida og'riq.", aid: "Yog'li ovqatlardan voz kechish, spasmolitiklar va shifokor nazoratida davolanish." },
    { name: "Gepatit", cat: "Jigar", desc: "Jigarning virusli yoki toksik yallig'lanishi, sarg'ayish.", aid: "Jismoniy zo'riqishdan qochish, qat'iy parhez, gepatolog shifokor nazorati." },
    { name: "Kolit", cat: "Ichak", desc: "Yo'g'on ichak shilliq qavatining yallig'lanishi, qorin dam bo'lishi.", aid: "Yengil hazm bo'luvchi taomlar, ko'p suyuqlik, shifokor buyurgan fermentlar." },
    { name: "Appenditsit", cat: "Oshqozon", desc: "Ko'richak o'simtasining o'tkir yallig'lanishi, o'ng yonboshdagi kuchli og'riq.", aid: "Hech qanday og'riq qoldiruvchi yoki issiq narsa bosmasdan, tez yordam chaqirish." },
    { name: "Gemorroy", cat: "Ichak", desc: "To'g'ri ichak venalarining kengayishi va tugunlar hosil bo'lishi.", aid: "Faol harakat, toza gigiyena, parhez (kletchatkaga boy taomlar), shamchalar." },
    { name: "Qabziyat (ich qotishi)", cat: "Ichak", desc: "Defekatsiyaning qiyinlashishi yoki kechikishi.", aid: "Ko'p suv ichish, kletchatkaga boy mevalar yeyish, surkash dori vositalari." },
    { name: "Diareya (ich ketishi)", cat: "Ichak", desc: "Tez-tez va suyuq axlat kelishi, suvsizlanish xavfi.", aid: "Regidron eritmasini ichish, adsorbentlar (faollashtirilgan ko'mir) qabul qilish." },
    { name: "Gipertoniya", cat: "Yurak", desc: "Qon bosimining surunkali ravishda yuqoki bo'lishi.", aid: "Tinch holatda o'tirish, shifokor buyurgan bosim tushiruvchi dori qabul qilish." },
    { name: "Gipotoniya", cat: "Yurak", desc: "Qon bosimining me'yordan past bo'lishi, holsizlik.", aid: "Iliq shirin choy yoki qahva ichish, oyoqlarni balandroq ko'tarib yotish." },
    { name: "Aritmiya", cat: "Yurak", desc: "Yurak urish maromining buzilishi (tezlashishi yoki sekinlashishi).", aid: "Tinchlanish, chuqur nafas olish, shifokor buyurgan dori vositalarini ichish." },
    { name: "Ateroskleroz", cat: "Yurak", desc: "Qon tomirlarida xolesterin pilyakalari to'planishi va torayishi.", aid: "Yog'siz parhez, sport bilan shug'ullanish, shifokor nazoratida xolesterinni kamaytirish." },
    { name: "Varikoz", cat: "Yurak", desc: "Oyoq venalarining kengayishi va qon aylanishi buzilishi.", aid: "Uzoq tik turmaslik, maxsus elastik paypoqlar kiyish, oyoqlarni ko'tarib dam olish." },
    { name: "Stenokardiya", cat: "Yurak", desc: "Yurak mushagiga qon yetishmasligi tufayli ko'krakdagi qisqa og'riq.", aid: "Bemorni tinchlantirish, til ostiga nitroglicerin qo'yish, og'riq o'tmasa tez yordam chaqirish." },
    { name: "Insult belgilari", cat: "Miya", desc: "Miyada qon aylanishining to'satdan buzilishi (nutq va harakat yo'qolishi).", aid: "Bemorni yotqizib, boshini biroz ko'tarish, zudlik bilan 103 chaqirish." },
    { name: "Infarkt belgilari", cat: "Yurak", desc: "Yurak mushagi bir qismining qon kelmasligi tufayli nobud bo'lishi.", aid: "Nitroglicerin bering, yoqasini ochib toza havo bering va darhol tez yordam chaqiring!" },
    { name: "Anemiya (kamqonlik)", cat: "Qon", desc: "Qonda gemoglobin va qizil qon tanachalari kamayishi.", aid: "Temir moddasiga boy taomlar yeyish (go'sht, anor), shifokor yozgan temir preparatlari." },
    { name: "Tromboflebit", cat: "Yurak", desc: "Vena tomirlarida tromb hosil bo'lishi va yallig'lanish.", aid: "Jarohatlangan oyoqni harakatsiz saqlash, sovuq kompres, shifokorga murojaat qilish." },
    { name: "Qandli diabet", cat: "Endokrin", desc: "Qonda glyukoza (shakar) miqdorining oshib ketishi.", aid: "Parhez, glyukoza miqdorini muntazam tekshirish va shaxsiy insulindan foydalanish." },
    { name: "Zob (buqoq)", cat: "Endokrin", desc: "Qalqonsimon bezning kattalashishi va yod yetishmasligi.", aid: "Ratsionda yodlangan tuz va dengiz mahsulotlarini ko'paytirish, endokrinolog nazorati." },
    { name: "Semizlik", cat: "Metabolizm", desc: "Tana vaznining yog' hisobiga me'yordan ortiq bo'lishi.", aid: "Kam kaloriyali parhez, muntazam jismoniy mashqlar, shifokor ko'rigi." },
    { name: "Gipotireoz", cat: "Endokrin", desc: "Qalqonsimon bez gormonlarining yetishmasligi, charchoq.", aid: "Endokrinolog shifokor buyurgan gormonal o'rinbosar dorilarni qabul qilish." },
    { name: "Buyrak toshi", cat: "Buyrak", desc: "Buyrak bo'shliqlarida tuz va minerallardan tosh hosil bo'lishi.", aid: "Ko'p suv ichish, spasmolitiklar ichish, kuchli og'riqda shifokorga borish." },
    { name: "Sistit", cat: "Siydik", desc: "Qovuq shilliq qavatining yallig'lanishi, og'riqli siyish.", aid: "Iliq kiyinish, ko'p iliq suyuqlik ichish, urolog buyurgan antibakterial dorilar." },
    { name: "Pielonefrit", cat: "Buyrak", desc: "Buyrak jomining bakterial yallig'lanishi, bel og'rig'i, isitma.", aid: "Issiq saqlanish, zudlik bilan shifokorga murojaat qilish va antibiotik davolash." },
    { name: "Prostatit", cat: "Tanosil", desc: "Prostata bezining yallig'lanishi, siyish qiyinlashishi.", aid: "Sovuq qotishdan saqlanish, urolog shifokor ko'rigidan o'tish va dori olish." },
    { name: "Uretrit", cat: "Siydik", desc: "Siydik yo'lining yallig'lanishi, achishish va og'riq.", aid: "Shaxsiy gigiyena, ko'p suv ichish, shifokor buyurgan antibiotiklar." },
    { name: "Adneksit", cat: "Tanosil", desc: "Ayollarda tuxumdon va bachadon naylarining yallig'lanishi.", aid: "Sovuqdan saqlanish, zudlik bilan ginekolog shifokor ko'rigidan o'tish." },
    { name: "Dermatit", cat: "Teriga", desc: "Teri yallig'lanishi, qizarish, qichishish va toshmalar.", aid: "Allergenlar bilan aloqani uzish, namlantiruvchi kremlar surtish, shifokor malhamlari." },
    { name: "Ekzema", cat: "Teriga", desc: "Terining surunkali allergik yallig'lanishi, qavariqlar.", aid: "Terini quritmaslik, parhez qilish, dermatolog yozgan gormonal malhamlar." },
    { name: "Psoriaz", cat: "Teriga", desc: "Terida kumushsimon tangachalar hosil qiluvchi surunkali kasallik.", aid: "Stressdan qochish, quyosh nuri, terini namlash, shifokor nazoratida davolash." },
    { name: "Allergiya", cat: "Teriga", desc: "Tashqi omillarga terining qizarish va toshma ko'rinishidagi reaksiyasi.", aid: "Antigistamin dori ichish, allergen moddani aniqlab undan uzoq bo'lish." },
    { name: "Eshakemi", cat: "Teriga", desc: "Terida qichishuvchi shishlar paydo bo'lishi (allergik reaksiya).", aid: "Antigistamin dori qabul qilish, sovuq kompres qo'yish, parhez qilish." },
    { name: "Husnbuzar (akne)", cat: "Teriga", desc: "Yog' bezlarining tiqilishi va yallig'lanishi, toshmalar.", aid: "Yuzni toza saqlash, yog'li ovqatlardan cheklanish, kosmetolog/dermatolog tavsiyalari." },
    { name: "Temiratki", cat: "Teriga", desc: "Terining infeksion yoki virusli kasalligi, halqasimon toshmalar.", aid: "Shaxsiy gigiyena buyumlarini ajratish, zudlik bilan dermatologga uchrash." },
    { name: "Gribok", cat: "Teriga", desc: "Teri yoki tirnoqlarning zamburug'li kasalligi.", aid: "Oyoqlarni quruq saqlash, maxsus zamburug'ga qarshi malhamlar surtish." },
    { name: "Qazg'oq", cat: "Teriga", desc: "Bosh terisining quruqlashishi yoki yog'lanishi natijasida tangachalar to'kilishi.", aid: "Maxsus shampunlar ishlatish, shirinliklarni kamaytirish." },
    { name: "Soch to'kilishi", cat: "Teriga", desc: "Sochlarning me'yordan ortiq to'kilishi (alopetsiya).", aid: "Vitaminlar qabul qilish (B guruhi, rux), tricholog shifokor ko'rigi." },
    { name: "Migren", cat: "Asab", desc: "Boshning bir yarmini qoplab oladigan kuchli xurujli og'riq.", aid: "Qorong'i va tinch xonada yotish, og'riq qoldiruvchi dori ichish, boshga sovuq latta qo'yish." },
    { name: "Nevralgiya", cat: "Asab", desc: "Asab tolalari bo'ylab kuchli va to'satdan paydo bo'luvchi og'riq.", aid: "Og'rigan joyni issiq saqlash, tinchlik, shifokor buyurgan vitamin va spasmolitiklar." },
    { name: "Radikulit", cat: "Tayanch", desc: "Orqa miya asab ildizlarining siqilishi va og'rishi.", aid: "Qattiq o'rinda yotish, belni issiq jun ro'mol bilan o'rash, yallig'lanishga qarshi malhamlar." },
    { name: "Osteoxondroz", cat: "Tayanch", desc: "Umarqa disklarining yemirilishi, bel va bo'yindagi og'riq.", aid: "To'g'ri qomatni saqlash, yengil mashqlar qilish, massaj, shifokor ko'rsatmalari." },
    { name: "Artrit", cat: "Tayanch", desc: "Bo'g'imlarning yallig'lanishi, shish va harakat qiyinligi.", aid: "Bo'g'imlarga og'irlik bermaslik, issiq bog'lamlar qilish, shifokor dori vositalari." },
    { name: "Artroz", cat: "Tayanch", desc: "Bo'g'im tog'aylarining surunkali yemirilishi va qotishi.", aid: "Vaznni kamaytirish, mo''tadil jismoniy faollik, shifokor buyurgan xondroprotektorlar." },
    { name: "Podagra", cat: "Tayanch", desc: "Organizmda siydik kislotasi to'planishi tufayli bo'g'imlar og'rig'i.", aid: "Go'sht va dukkakli mahsulotlarni cheklash (parhez), ko'p suv ichish, og'riqsizlantirish." },
    { name: "Skolioz", cat: "Tayanch", desc: "Umarqa pog'onasining yon tomonga qiyshayishi.", aid: "Davolash gimnastikasi bilan shug'ullanish, suzish, ortopedik matrasda yotish." },
    { name: "Oyoq uvishishi", cat: "Asab", desc: "Oyoqlarda qon aylanishi yoki asab o'tkazuvchanligi buzilishi.", aid: "Oyoqlarni uqalash, oyoq kiyimni tekshirish, shifokor ko'rigidan o'tish." },
    { name: "Uyqusizlik", cat: "Asab", desc: "Uxlashga qiynalish yoki uyqu sifatining yomonligi.", aid: "Kechasi telefondan foydalanmaslik, xonani shamollatish, iliq dush va tinchlantiruvchi choylar." },
    { name: "Kon'yunktivit", cat: "Ko'z", desc: "Ko'z shilliq pardasining yallig'lanishi, qizarish va yoshlanish.", aid: "Ko'zni qaynatilgan iliq suv yoki moychechak suvi bilan yuvish, antiseptik tomchilar tomizish." },
    { name: "Katarakta", cat: "Ko'z", desc: "Ko'z gavharining xiralashishi, ko'rish qobiliyati pasayishi.", aid: "Faqat jarrohlik yo'li bilan davolanadi, ko'z shifokori (oftalmolog) ko'rigi shart." },
    { name: "Glaukoma", cat: "Ko'z", desc: "Ko'z ichki bosimining oshishi, ko'rish asabining shikastlanishi.", aid: "Muntazam ravishda ko'z bosimini o'lchash, shifokor buyurgan tomchilarni tomizish." },
    { name: "Arpa (ko'zda)", cat: "Ko'z", desc: "Ko'z qovog'idagi yog' bezining o'tkir yiringli yallig'lanishi.", aid: "Yiringni aslo siqmang! Ko'zni toza tuting, shifokor buyurgan antibiotikli malhamlar surting." },
    { name: "Blefarit", cat: "Ko'z", desc: "Ko'z qovoqlari chetlarining surunkali yallig'lanishi.", aid: "Qovoqlarni maxsus eritmalar bilan tozalash, gigiyena qoidalariga rioya etish." },
    { name: "Karies", cat: "Tish", desc: "Tish qattiq to'qimalarining yemirilishi va bo'shliq hosil bo'lishi.", aid: "Tishlarni kuniga 2 marta yuvish, stomatolog shifokorga borib tishni plombalash." },
    { name: "Stomatit", cat: "Og'iz", desc: "Og'iz shilliq qavatida mayda yaralar paydo bo'lishi, og'riq.", aid: "Og'izni furatsilin yoki moychechak damlamasi bilan chayish, shifokor yozgan gellar." },
    { name: "Gingivit", cat: "Tish", desc: "Milklarning yallig'lanishi va qonashi, og'izdan hid kelishi.", aid: "Yumshoq tish cho'tkasidan foydalanish, og'izni chayish, tish toshlarini tozalash." },
    { name: "Pulpit", cat: "Tish", desc: "Tish ichidagi asab tolasining yallig'lanishi, chidab bo'lmas kuchli og'riq.", aid: "Og'riq qoldiruvchi dori ichish va tezda stomatolog shifokorga murojaat qilish." },
    { name: "Tish og'rig'i", cat: "Tish", desc: "Tish yoki uning atrofidagi to'qimalarda og'riq sezilishi.", aid: "Iliq tuzli suvda og'izni chayish, og'riq qoldiruvchi dori qabul qilish va shifokorga uchrash." },
    { name: "Suvchechak", cat: "Yuqumli", desc: "Isitma va butun tanaga qichishuvchi pufakchalar toshishi bilan kechuvchi virus.", aid: "Toshmalarga ko'k dori (zelenka) surtish, bemorni alohidalash, qichishga qarshi dori ichish." },
    { name: "Qizamiq", cat: "Yuqumli", desc: "Yuqori harorat, yo'tal va butun tanaga toshma toshishi.", aid: "Bemorni alohidalash, ko'p suyuqlik ichirish, qorong'iroq xonada saqlash (ko'zlarni himoyalash)." },
    { name: "Tepki (parotit)", cat: "Yuqumli", desc: "Quloq oldi so'lak bezlarining yallig'lanishi va shishishi.", aid: "Tomoq va bo'yinni issiq saqlash, yengil chaynaladigan ovqatlar yeyish, shifokor nazorati." },
    { name: "Qizilcha", cat: "Yuqumli", desc: "Mayda pushti toshmalar toshishi va limfa tugunlari kattalashishi.", aid: "Ko'p suyuqlik ichish, dam olish, harorat ko'tarilsa isitma tushiruvchi dorilar berish." },
    { name: "Dizenteriya", cat: "Yuqumli", desc: "Yo'g'on ichakning og'ir shikastlanishi, qonli diareya, isitma.", aid: "Zudlik bilan shifokorga murojaat qilish, ko'p suyuqlik va regidron ichish." },
    { name: "Gelmintoz (gijja)", cat: "Yuqumli", desc: "Gijjalar bilan zararlanish, qorin og'rig'i, ishtahasizlik.", aid: "Shaxsiy gigiyenaga rioya qilish, shifokor tavsiya qilgan gijjaga qarshi dorilarni ichish." },
    { name: "Salmonellyoz", cat: "Yuqumli", desc: "Bakterial ichak infeksiyasi, qusish, diareya va isitma.", aid: "Regidron eritmasini ichish, adsorbentlar qabul qilish, zudlik bilan shoshilinch yordam olish." },
    { name: "Vabo", cat: "Yuqumli", desc: "Kuchli qusish va ich ketishi natijasida suvsizlanish keltiruvchi vabo.", aid: "Zudlik bilan kasalxonaga yotqizish, organizmda tuz va suv balansini tiklash (tuzli eritmalar)." },
    { name: "Kuydirgi", cat: "Yuqumli", desc: "Hayvonlardan yuquvchi xavfli yuqumli kasallik, terida qora yaralar.", aid: "Zudlik bilan infeksionist shifokor nazoratida kasalxonada antibiotik davolash olish." },
    { name: "Quturish", cat: "Yuqumli", desc: "Quturgan hayvonlar tishlaganda yuqadigan o'lim xavfi bor virus.", aid: "Jarohatni zudlik bilan sovunlab yuvish va 1-2 soat ichida shoshilinch vaksina olish!" },
    { name: "Depressiya", cat: "Ruhiy", desc: "Uzoq muddatli tushkunlik, hayotga qiziqish yo'qolishi.", aid: "Yaqinlar bilan suhbatlashish, jismoniy faollik, psixoterapevt shifokor yordami." },
    { name: "Nevroz", cat: "Ruhiy", desc: "Asab tizimining charchashi tufayli yuzaga keladigan asabiylik.", aid: "Ish va dam olish rejimini to'g'rilash, tinchlantiruvchi damlamalar ichish, dam olish." },
    { name: "Vahima xuruji", cat: "Ruhiy", desc: "To'satdan kuchli qo'rquv va yurak tez urishi xuruji.", aid: "Chuqur va sekin nafas oling, o'zingizga xavfsiz joyda ekanligingizni qayta-qayta ayting." },
    { name: "Stress", cat: "Ruhiy", desc: "Tashqi bosimlarga nisbatan organizmning himoya reaksiyasi.", aid: "Chuqur nafas olish mashqlari, meditatsiya, toza havoda yurish, kofeinni kamaytirish." },
    { name: "Surunkali charchash", cat: "Ruhiy", desc: "Uzoq dam olishdan keyin ham o'tib ketmaydigan holsizlik.", aid: "Uyqu rejimini tartibga solish, vitaminlar qabul qilish, dam olish kunlarini tashkil etish." },
    { name: "Asabiylik", cat: "Ruhiy", desc: "Tez ta'sirlanish va his-tuyg'ularni nazorat qila olmaslik.", aid: "Biroz tinchlanish, vaziyatdan uzoqlashish, tinchlantiruvchi o'tli choylar ichish." },
    { name: "Bosh aylanishi", cat: "Umumiy", desc: "Muvozanatni yo'qotish va atrofdagi narsalar aylanayotgandek tuyulishi.", aid: "Bemorni darhol yotqizish yoki o'tqizish, boshini qimirlatmaslik, shirin choy berish." },
    { name: "Quloq bitishi", cat: "Quloq", desc: "Quloq ichida havo bosimi o'zgarishi yoki oltingugurt tiqilishi.", aid: "Yutunish harakatlari qilish, aslo quloqni o'tkir buyumlar bilan kovlamaslik!" },
    { name: "Burun qonashi", cat: "Umumiy", desc: "Burun bo'shlig'i tomirlarining yorilishi va qon ketishi.", aid: "Boshni biroz oldinga engash (orqaga emas!), burun qanotlarini 5-10 daqiqa siqib turish." },
    { name: "Tomoq og'rig'i", cat: "Tomoq", desc: "Tomoq yallig'lanishi tufayli yutish va gapirishda noqulaylik.", aid: "Iliq tuzli suvda tomoqni tez-tez chayish, ko'p iliq choy va suyuqliklar ichish." },
    { name: "Quyosh urishi", cat: "Travma", desc: "Quyosh nurlari ostida uzoq qolib ketish natijasida bosh og'rishi, isitma.", aid: "Bemorni soya va salqin joyga olib o'tish, peshonaga sovuq kompres qo'yish, suv ichirish." },
    { name: "Sovuq urishi", cat: "Travma", desc: "Past harorat ta'sirida tana a'zolarining muzlashi va shikastlanishi.", aid: "Bemorni asta-sekin iliq xonaga olib kirish, iliq choy berish (birdan issiq suvga solmang!)." },
    { name: "Miya chayqalishi", cat: "Travma", desc: "Boshga kuchli zarba tegishi natijasida ko'ngil aynishi, bosh og'rig'i.", aid: "Bemorni tekis yotqizib, boshini biroz ko'tarib qo'ying va zudlik bilan 103 chaqiring." },
    { name: "Lat yeyish", cat: "Travma", desc: "Yumshoq to'qimalarning yopiq shikastlanishi, shish va ko'karish.", aid: "Zararlangan joyga darhol muz qo'yish (latta orqali), shikastlangan a'zoni tinch saqlash." },
    { name: "Pay cho'zilishi", cat: "Travma", desc: "Bo'g'imlardagi paylarning keskin harakat tufayli cho'zilishi, kuchli og'riq.", aid: "Bo'g'imni elastik bint bilan mahkamlash (harakatsiz qilish), muz qo'yish va baland ko'tarish." },
    { name: "Kuyish jarohati", cat: "Travma", desc: "Issiqlik yoki kimyoviy moddalar ta'sirida terining shikastlanishi.", aid: "Kuygan joyni 10-15 daqiqa oqib turgan sovuq suvda tuting, so'ng toza steril bog'lam yoping." },
    { name: "Kesilgan yara", cat: "Travma", desc: "O'tkir buyumlar bilan terining kesilishi va qon ketishi.", aid: "Yarani vodorod peroksid bilan tozalang, atrofiga yod surting va steril bint bilan bog'lang." },
    { name: "Hasharot chaqishi", cat: "Travma", desc: "Ari, chayon yoki boshqa hasharotlar chaqishi, og'riq va shish.", aid: "Nishni pinset bilan sug'urib oling (ari chaqsa), sovuq qo'ying, allergiya dori bering." },
    { name: "Ilon chaqishi", cat: "Travma", desc: "Zaharli ilon tishlashi, tishlangan joyda qattiq og'riq va ko'karish.", aid: "Tishlangan a'zoni harakatsiz saqlang, zahar so'rmang, zudlik bilan tez yordamga yetkazing!" },
    { name: "It qopishi", cat: "Travma", desc: "Hayvon tishlashi natijasida yaralanish, quturish yuqishi xavfi.", aid: "Yarani zudlik bilan kir sovun va ko'p miqdorda suv bilan yuvib tashlang, shifoxonaga boring." },
    { name: "Tomoq bitishi (Laringit)", cat: "Tomoq", desc: "Ovoz boylamlarining yallig'lanishi, ovoz bo'g'ilishi.", aid: "Gapirmaslik, iliq suyuqlik ichish, bug'li ingalyatsiya qilish." },
    { name: "Bosh og'rig'i (Zo'riqish)", cat: "Asab", desc: "Kun davomidagi charchoq va zo'riqish tufayli keladigan bosh og'rig'i.", aid: "Tinchlanish, yetarli uyqu, toza havo, ko'p suv ichish." },
    { name: "Oyoq sinishi (Gips)", cat: "Travma", desc: "Oyoq suyaklarining butunligi buzilishi.", aid: "Oyoqni to'liq harakatsizlantirish, sovuq bosish, zudlik bilan travmatologga borish." },
    { name: "Kuyish (Kimyoviy)", cat: "Travma", desc: "Kimyoviy kislota yoki ishqorlar bilan terining kuyishi.", aid: "Zudlik bilan 20 daqiqa davomida ko'p miqdorda oqib turgan suv bilan yuvish." },
    { name: "Moychechak terapiyasi", cat: "Profilaktika", desc: "Tinchlantiruvchi va yallig'lanishga qarshi o'simlik damlamasi.", aid: "Moychechak gullarini qaynoq suvda damlab, iliq holda ichish yoki tomoq chayish." }
];

// ═══════════════════════════════════════════════════════════════════
// UI LOGIC & EVENT LISTENERS
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    SafeStorage.initFromCloud(function() {
        try {
            initTheme();

            // Safe Telegram User Info Setup inside DOMContentLoaded
            if (tg) {
                const user = tg.initDataUnsafe ? tg.initDataUnsafe.user : null;
                if (user) {
                    const nameEl = document.getElementById('user-name');
                    if (nameEl) nameEl.innerText = `${user.first_name} ${user.last_name || ''}`.trim();

                    const avatarEl = document.getElementById('user-avatar');
                    if (avatarEl) avatarEl.textContent = userInitials(user.first_name, user.last_name);
                }
            }

            initTabs();
            renderFirstAidGrid();
            initFirstAidSearch();
            initHomeActions();
            initBodyFigure();
            initSearch();
            initCalculators();
            initOverlay();
            initQuiz();
            initHistory();
        } catch (e) {
            reportError('DOM Init 1', e);
        }
    });
});

// TAB SYSTEM
// Nav'da yo'q bo'limlar qaysi tab ostida ekani (pastki menyuda shu tab faol ko'rinadi)
const NAV_PARENT = { 'tab-history': 'tab-health', 'tab-quiz': 'tab-first-aid', 'tab-first-aid-all': 'tab-first-aid' };

function showTab(tabId) {
    const section = document.getElementById(tabId);
    if (!section) return;
    document.querySelectorAll('.tab-content').forEach(tc => tc.classList.toggle('active', tc === section));
    const navId = NAV_PARENT[tabId] || tabId;
    document.querySelectorAll('.nav-btn').forEach(b => {
        const on = b.getAttribute('data-tab') === navId;
        b.classList.toggle('active', on);
        if (on) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-show-tab]').forEach(b => {
        b.setAttribute('aria-selected', b.getAttribute('data-show-tab') === tabId ? 'true' : 'false');
    });
    const content = document.querySelector('.app-content');
    if (content) content.scrollTop = 0;
    syncCalcMainButton();
    document.body.classList.toggle('ai-tab-on', tabId === 'tab-ai');     // suhbat: xabarlar skroll, yozish paneli pastda
    if (tabId !== 'tab-first-aid') hideBodySheet();      // sheet bosh ekrandagi tana figurasiga tegishli
    if (tabId === 'tab-ai') onAiTabShown();
    if (tabId === 'tab-first-aid') fitBodyFigure();       // yashirin bo'limda o'lcham 0 edi (strelkalar ham)
    if (tabId === 'tab-history') drawChart(currentHistory);     // yashirin bo'limda kenglik 0 edi
}

function initTabs() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            showTab(btn.getAttribute('data-tab'));
            // Switching main tabs clears the navigation stack
            AppNavigation.pop();
        });
    });
    // Segmented control (masalan Sog'liq: Kalkulyator | Tarix)
    document.querySelectorAll('[data-show-tab]').forEach(btn => {
        btn.addEventListener('click', () => showTab(btn.getAttribute('data-show-tab')));
    });
}

// Boshidagi emoji faqat ro'yxat qatorida ko'rsatilmaydi (qatorda o'z ikonkasi bor). Ma'lumot o'zgarmaydi.
function displayTitle(text) {
    const t = String(text || '');
    const stripped = t.replace(/^[^\p{L}\p{N}]+/u, '').trim();
    return stripped || t;
}

// Qidiruv: katta-kichik harf va apostroflar (o', g', ' ‘ ’ ʻ) farqi e'tiborga olinmaydi: "bogilish" = "bo'g'ilish"
function normalizeSearch(text) {
    return String(text || '').toLowerCase().replace(/['ʻʼ‘’`´]/g, '');
}

// BIRINCHI YORDAM RO'YXATI (inset grouped, 4.4-B)
function renderFirstAidGrid() {
    const list = document.getElementById('first-aid-grid');
    if (!list) return;
    list.innerHTML = '';

    FIRST_AID_ITEMS.forEach(item => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'list-row';
        row.setAttribute('data-id', item.id);
        row.setAttribute('data-search', normalizeSearch(item.title + ' ' + item.desc));
        const severe = item.urgency === 'critical';
        row.innerHTML = `
            <span class="row-icon ${severe ? 'row-icon--danger' : 'row-icon--primary'}">${svgIcon(item.icon)}</span>
            <span class="row-text"><span class="row-title"></span><span class="row-sub"></span></span>
            ${svgIcon('chevron-right', 'row-chevron')}
        `;
        row.querySelector('.row-title').textContent = displayTitle(item.title);
        row.querySelector('.row-sub').textContent = item.desc;
        row.addEventListener('click', () => {
            openFirstAidDetail(item);
        });
        list.appendChild(row);
    });
}

function initFirstAidSearch() {
    const input = document.getElementById('first-aid-search');
    const list = document.getElementById('first-aid-grid');
    const empty = document.getElementById('first-aid-empty');
    if (!input || !list) return;
    input.addEventListener('input', () => {
        const q = normalizeSearch(input.value.trim());
        let visible = 0;
        list.querySelectorAll('.list-row').forEach(row => {
            const show = !q || row.getAttribute('data-search').includes(q);
            row.hidden = !show;
            if (show) visible++;
        });
        list.hidden = visible === 0;
        if (empty) empty.hidden = visible !== 0;
    });
}

// ── Bosh ekran (G): Test qatori, "Hammasi" sahifasi, holat chiplari, "Bugun" kartalari ──
function userInitials(first, last) {
    const parts = [first, last].map(x => String(x || '').trim()).filter(Boolean);
    const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] || 'SH').slice(0, 2);
    return letters.toUpperCase();
}

// Bosh ekrandan ochiladigan ichki sahifa (Test, "Hammasi"): BackButton bosh ekranga qaytaradi
function openHomeSubpage(tabId, type) {
    showTab(tabId);
    AppNavigation.push({
        type: type,
        close: function () {
            showTab('tab-first-aid');
            AppNavigation.pop();
        }
    });
}

function openQuizFromHome() { openHomeSubpage('tab-quiz', 'quiz'); }
function openFirstAidAll() { openHomeSubpage('tab-first-aid-all', 'first-aid-all'); }

// "Yoki holatni tanlang": FIRST_AID_ITEMS tartibida, kritiklari oldinda; oxirida "Hammasi"
function renderHomeChips() {
    const bar = document.getElementById('home-chips');
    if (!bar) return;
    bar.innerHTML = '';
    const critical = FIRST_AID_ITEMS.filter(i => i.urgency === 'critical');
    const rest = FIRST_AID_ITEMS.filter(i => i.urgency !== 'critical');
    critical.concat(rest).forEach(item => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'home-chip';
        chip.setAttribute('role', 'listitem');
        chip.setAttribute('data-id', item.id);
        chip.innerHTML = `${svgIcon(iconName(item.icon))}<span></span>`;
        chip.querySelector('span').textContent = displayTitle(item.title);
        chip.addEventListener('click', () => openFirstAidDetail(item));
        bar.appendChild(chip);
    });
    const all = document.createElement('button');
    all.type = 'button';
    all.className = 'home-chip home-chip--all';
    all.setAttribute('role', 'listitem');
    all.id = 'home-chip-all';
    all.innerHTML = `<span>Hammasi</span>${svgIcon('chevron-right')}`;
    all.addEventListener('click', openFirstAidAll);
    bar.appendChild(all);
}

function initHomeActions() {
    renderHomeChips();
    const quiz = document.getElementById('home-quiz-row');
    if (quiz) quiz.addEventListener('click', () => {
        if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
        openQuizFromHome();
    });
    // "Olish +N": kunlik bonus sheet'idagi bilan bir xil handler (api('bonus/claim') + zaxira deep link).
    // Handler hali tayyor bo'lmasa (holat yuklanmagan) — bonus sheet ochiladi.
    const claim = document.getElementById('today-bonus-claim');
    if (claim) claim.addEventListener('click', () => {
        const sheetBtn = document.getElementById('btn-claim-daily-bonus');
        if (sheetBtn && typeof sheetBtn.onclick === 'function') sheetBtn.onclick();
        else document.getElementById('btn-open-daily-bonus').click();
    });
}

const BONUS_REWARDS = [1, 2, 3, 3, 3, 3, 20];
let todayWheelTimer = null;

function formatHMS(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds));
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

// "Bugun" kartalari /api/state dan (API ishlamasa — URL parametrlaridan, bo'lmasa umumiy matn)
function renderTodayCard(s) {
    const bonusSub = document.getElementById('today-bonus-sub');
    const bonusBtn = document.getElementById('today-bonus-claim');
    const wheelSub = document.getElementById('today-wheel-sub');
    const wheelBtn = document.getElementById('btn-open-wheel');
    if (!s || !bonusSub || !wheelSub) return;

    const streak = Math.min(7, Math.max(1, Number(s.streak) || 1));
    bonusSub.textContent = `${streak}-kun seriya`;
    if (s.daily_claimed) {
        bonusBtn.innerHTML = `${svgIcon('check')}<span>Olindi</span>`;
        bonusBtn.disabled = true;
        bonusBtn.classList.add('is-done');
    } else {
        bonusBtn.textContent = `Olish +${BONUS_REWARDS[streak - 1]}`;
        bonusBtn.disabled = false;
        bonusBtn.classList.remove('is-done');
    }

    if (todayWheelTimer) { clearInterval(todayWheelTimer); todayWheelTimer = null; }
    const baseTs = s === AppState.data ? AppState.ts : Date.now();
    const endAt = baseTs + Math.max(0, Number(s.cooldown_seconds) || 0) * 1000;
    const tick = () => {
        const left = (endAt - Date.now()) / 1000;
        if (left > 0) {
            // Kutish: taymer (o'chirilgan ko'rinishda; bosilsa baraban oynasi kutish holati bilan ochiladi)
            wheelSub.textContent = 'Keyingisi';
            wheelBtn.textContent = formatHMS(left);
            wheelBtn.classList.add('is-waiting');
            wheelBtn.setAttribute('aria-label', `Baraban: keyingisi ${formatHMS(left)} dan keyin`);
        } else {
            if (todayWheelTimer) { clearInterval(todayWheelTimer); todayWheelTimer = null; }
            wheelSub.textContent = (typeof s.prize === 'number' || s.cooldown_seconds) ? 'Tayyor' : 'Har kuni bepul';
            wheelBtn.textContent = 'Aylantirish';
            wheelBtn.classList.remove('is-waiting');
            wheelBtn.removeAttribute('aria-label');
        }
    };
    tick();
    if (endAt > Date.now()) todayWheelTimer = setInterval(tick, 1000);
}

function todayStateFromUrl() {
    const p = new URLSearchParams(window.location.search);
    if (!p.has('streak') && !p.has('prize')) return null;
    return {
        streak: parseInt(p.get('streak') || '1', 10),
        daily_claimed: p.get('daily_claimed') === '1',
        prize: p.has('prize') ? parseInt(p.get('prize'), 10) : null,
        cooldown_seconds: 0,
    };
}

onAppStateChange((s) => { renderPremiumUi(s); renderTodayCard(s); renderAiOffer(s); renderAiQuota(s); });
document.addEventListener('DOMContentLoaded', () => {
    getAppState(60000).then((s) => renderTodayCard(s || todayStateFromUrl()));
});

// OPEN FIRST AID DETAILS
// ── Telegram MainButton ──
// Telegram ichida (initData bor) — tg.MainButton. Tashqarida (initData bo'sh) — sahifadagi zaxira tugma (.inpage-main).
// MainButton ko'rinib turganda body.tg-main-on: kontent pastidan qo'shimcha joy (tugma hech narsani yopmaydi).
const MainButtonCtl = {
    handler: null,
    owner: null,
    active: true,
    opts: null,
    fallback: null,
    available() {
        return !!(tg && tg.initData && tg.MainButton);
    },
    colors(active) {
        const cs = getComputedStyle(document.body);
        const pick = (name, dflt) => cs.getPropertyValue(name).trim() || dflt;
        if (!active) return { color: pick('--text-2', '#5E6B7E'), text_color: pick('--on-primary', '#FFFFFF') };
        return {
            color: (this.opts && this.opts.color) || pick('--primary', '#0E7C72'),
            text_color: (this.opts && this.opts.textColor) || pick('--on-primary', '#FFFFFF')
        };
    },
    set(opts, fallbackEl) {
        this.clear();
        this.opts = opts;
        this.owner = opts.owner || null;
        this.active = true;
        const useTg = this.available();
        document.body.classList.toggle('tg-main', useTg);
        if (fallbackEl) {
            this.fallback = fallbackEl;
            fallbackEl.textContent = opts.text;
            fallbackEl.disabled = false;
            fallbackEl.onclick = () => { if (this.opts) this.opts.onClick(); };
        }
        if (!useTg) return false;
        const mb = tg.MainButton;
        try {
            mb.setText(opts.text);
            if (mb.setParams) {
                const c = this.colors(true);
                if (/^#[0-9a-f]{6}$/i.test(c.color)) mb.setParams({ color: c.color, text_color: c.text_color });
            }
            if (mb.enable) mb.enable();
            this.handler = () => { if (this.opts) this.opts.onClick(); };
            mb.onClick(this.handler);
            mb.show();
            document.body.classList.add('tg-main-on');
            return true;
        } catch (e) {
            console.warn('MainButton ishlamadi:', e);
            document.body.classList.remove('tg-main');      // sahifadagi tugma ko'rinadi
            return false;
        }
    },
    // Mavzu almashganda: joriy holat (faol / nofaol) bo'yicha ranglarni qayta qo'yadi
    refreshColors() {
        if (!this.handler || !this.available() || !tg.MainButton.setParams) return;
        try {
            const c = this.colors(this.active !== false);
            if (/^#[0-9a-f]{6}$/i.test(c.color)) tg.MainButton.setParams({ color: c.color, text_color: c.text_color });
        } catch (e) { /* eski klient */ }
    },
    // Input to'g'ri bo'lsagina tugma faol (4.4-E)
    setActive(on) {
        this.active = !!on;
        if (this.fallback) this.fallback.disabled = !on;
        if (!this.handler || !this.available()) return;
        const mb = tg.MainButton;
        try {
            if (on && mb.enable) mb.enable();
            if (!on && mb.disable) mb.disable();
            if (mb.setParams) {
                const c = this.colors(on);
                if (/^#[0-9a-f]{6}$/i.test(c.color)) mb.setParams({ color: c.color, text_color: c.text_color, is_active: !!on });
            }
        } catch (e) { /* eski klient */ }
    },
    clear() {
        if (this.fallback) this.fallback.onclick = null;
        this.fallback = null;
        this.opts = null;
        this.owner = null;
        document.body.classList.remove('tg-main-on');
        if (!tg || !tg.MainButton) return;
        try {
            if (this.handler && tg.MainButton.offClick) tg.MainButton.offClick(this.handler);
            tg.MainButton.hide();
        } catch (e) { /* eski klient */ }
        this.handler = null;
    }
};

function dial103() {
    window.location.href = 'tel:103';
}

// "AI'dan so'rash" (detal / kasallik): AI tabi shu holat konteksti bilan ochiladi, xabar avtomatik YUBORILMAYDI.
// Zaxira (API ishlamasa): AI tabidagi "Botda davom etish" — eski tg.sendData yo'li.
let detailAiContext = null;

// Kasallik nomidan kontekst kaliti — bot.py ai_disease_key bilan AYNAN bir xil qoida
function aiDiseaseKey(name) {
    return String(name || '').toLowerCase().replace(/['ʻʼ‘’`]/g, '').replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function askAiFromDetail() {
    const ctx = detailAiContext;
    closeDetail();
    openAiChat(ctx);
}

// Kasalliklar: qidiruv natija bermasa — AI tabi, so'rov matni yozish maydoniga qo'yiladi (yuborilmaydi)
function askAiFromSearch() {
    const input = document.getElementById('disease-search-input');
    openAiChat(null, input ? input.value.trim() : '');
}

const URGENCY_CHIPS = {
    critical: { label: 'Kritik holat', cls: 'chip--danger' },
    high: { label: 'Muhim holat', cls: 'chip--warning' },
    medium: { label: "O'rta holat", cls: 'chip--primary' }
};

function detailSection(title, inner) {
    return `<section class="detail-block"><h2 class="detail-h">${title}</h2>${inner}</section>`;
}

// HTML qatorni oddiy matnga (ulashish uchun). DOMParser — skriptlar ishlamaydi, hujjatga qo'shilmaydi.
function plainText(htmlText) {
    const doc = new DOMParser().parseFromString(String(htmlText || ''), 'text/html');
    return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
}

// "Qilmang!" matnini bandlarga ajratadi: "!" bilan tugagan har gap — alohida band, izoh gaplar oldingi bandga qo'shiladi.
// Matnning o'zi o'zgarmaydi (faqat bo'linadi).
function splitProhibited(text) {
    const parts = String(text || '').split(/(?<=[!.])\s+/).filter(Boolean);
    const out = [];
    parts.forEach(p => {
        if (out.length && !/!$/.test(p)) out[out.length - 1] += ' ' + p;   // izoh gap — oldingi bandga
        else out.push(p);
    });
    return out;
}

// ── Toast (qisqa xabar) ──
let toastTimer = null;
function showToast(msg, ms) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, Math.min(10000, Math.max(2200, ms || 0)));
}

// ── Ulashish: matnni nusxalash (tg.shareToStory rasm talab qiladi — bu yerda mos emas) ──
let detailShareText = '';
function copyText(text) {
    const fallback = () => {
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.setAttribute('readonly', '');
            ta.className = 'sr-only';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            ta.remove();
            return ok;
        } catch (e) { return false; }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(() => true, () => fallback());
    }
    return Promise.resolve(fallback());
}

function shareDetail() {
    if (!detailShareText) return;
    copyText(detailShareText).then(ok => {
        showToast(ok ? "Matn nusxalandi — xohlagan chatga yuboring" : "Nusxalab bo'lmadi");
        try { if (ok && tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success'); } catch (e) { /* yo'q */ }
    });
}

// ── Qadamlarni belgilash: faqat sahifa ochiq turganda (saqlanmaydi) ──
let detailSevere = false;

function updateStepsProgress() {
    const steps = document.querySelectorAll('#overlay-body-content .timeline-btn');
    if (!steps.length) return false;
    const done = document.querySelectorAll('#overlay-body-content .timeline-btn[aria-checked="true"]').length;
    const label = document.getElementById('steps-progress-count');
    if (label) label.textContent = `${done}/${steps.length}`;
    const fill = document.getElementById('steps-bar-fill');
    if (fill) fill.style.width = `${Math.round(done / steps.length * 100)}%`;
    const all = done === steps.length;
    const box = document.getElementById('steps-done');
    if (box) {
        const was = box.classList.contains('is-done');
        box.classList.toggle('is-done', all);
        if (all && !was) {
            box.innerHTML = `<span class="chip chip--teal chip--done">${svgIcon('circle-check')}<span>Barcha qadamlar bajarildi</span></span>` +
                (detailSevere ? `<div class="steps-done-103"><span>Baribir 103 ga qo'ng'iroq qiling</span>` +
                                `<a href="tel:103" class="call-btn call-btn--sm">${svgIcon('phone')}<span>103</span></a></div>` : '');
        } else if (!all) {
            box.innerHTML = '';
        }
    }
    return all;
}

function initStepToggles() {
    document.querySelectorAll('#overlay-body-content .timeline-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const on = btn.getAttribute('aria-checked') !== 'true';
            btn.setAttribute('aria-checked', on ? 'true' : 'false');
            btn.closest('.timeline-step').classList.toggle('done', on);
            const all = updateStepsProgress();
            try {
                if (tg && tg.HapticFeedback) {
                    if (on && all) tg.HapticFeedback.notificationOccurred('success');
                    else tg.HapticFeedback.impactOccurred('light');
                }
            } catch (e) { /* eski klient */ }
        });
    });
    updateStepsProgress();
}

// ── Sticky sarlavha: katta sarlavha ko'rinmay qolganda ixcham holat ──
function updateDetailBar() {
    const overlay = document.getElementById('overlay-details');
    const bar = document.getElementById('detail-bar');
    const title = document.getElementById('overlay-title');
    if (!overlay || !bar || !title) return;
    // Katta sarlavha panel ostiga kirib ketgach (Telegram ichida panel bo'sh — kamida 24px skrolldan keyin)
    const threshold = Math.max(24, title.offsetTop + title.offsetHeight - bar.offsetHeight);
    bar.classList.toggle('compact', overlay.scrollTop > threshold);
}

let detailOpener = null;

function closeDetail() {
    document.getElementById('overlay-details').classList.remove('active');
    MainButtonCtl.clear();
    const fb = document.getElementById('detail-main-fallback');
    if (fb) fb.hidden = true;
    AppNavigation.pop();
    syncCalcMainButton();
    // Fokus detalni ochgan elementga qaytadi (klaviatura / ekran o'quvchi)
    if (detailOpener && document.body.contains(detailOpener)) {
        try { detailOpener.focus({ preventScroll: true }); } catch (e) { /* eski brauzer */ }
    }
    detailOpener = null;
}

// Detal sahifani ochadi (birinchi yordam va kasallik uchun umumiy)
function showDetail(titleText, chipsHtml, bodyHtml, mainButton, extra) {
    extra = extra || {};
    const overlay = document.getElementById('overlay-details');
    detailOpener = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
    document.getElementById('overlay-title').textContent = titleText;
    document.getElementById('overlay-chips').innerHTML = chipsHtml;
    document.getElementById('detail-bar-name').textContent = titleText;
    document.getElementById('detail-bar-chip').innerHTML = chipsHtml;
    document.getElementById('overlay-body-content').innerHTML = bodyHtml;
    detailShareText = extra.shareText || '';
    const ai = document.getElementById('detail-ai-btn');
    if (ai) ai.hidden = !extra.secondaryAi;
    initStepToggles();
    overlay.classList.add('active');
    overlay.scrollTop = 0;
    document.getElementById('detail-bar').classList.remove('compact');
    const fb = document.getElementById('detail-main-fallback');
    if (fb) fb.hidden = !mainButton;
    if (mainButton) MainButtonCtl.set(Object.assign({ owner: 'detail' }, mainButton), fb); else MainButtonCtl.clear();
    AppNavigation.push({ type: 'detail', close: closeDetail });
    try { document.getElementById('overlay-title').focus({ preventScroll: true }); } catch (e) { /* eski brauzer */ }
}

function openFirstAidDetail(item) {
    const urg = URGENCY_CHIPS[item.urgency] || URGENCY_CHIPS.medium;
    const chips = `<span class="chip ${urg.cls}">${urg.label}</span>`;
    const severe = item.urgency === 'critical';
    detailSevere = severe;
    detailAiContext = { type: 'condition', key: item.id, label: displayTitle(item.title), prefix: 'Holat' };
    const has103 = item.whenToCall103 && item.whenToCall103.length;
    const hasSymptoms = item.symptoms && item.symptoms.length;

    const callCard = (top) => `<section class="call-card${top ? ' call-card--top' : ''}">
            <h2 class="detail-h">${top ? svgIcon('siren') : ''}<span>Qachon 103 chaqirish kerak?</span></h2>
            ${has103 ? `<ul class="dot-list">${item.whenToCall103.map(c => `<li>${c}</li>`).join('')}</ul>` : ''}
            <a href="tel:103" class="call-btn">${svgIcon('phone')}<span>103 — Tez yordam</span></a>
        </section>`;
    const symptomTags = hasSymptoms ? `<div class="chips-wrap">${item.symptoms.map(s => `<span class="symptom-tag">${s}</span>`).join('')}</div>` : '';
    const stepsHtml = `<ol class="timeline">${item.steps.map((step, idx) => `
        <li class="timeline-step"><button type="button" class="timeline-btn" role="checkbox" aria-checked="false">
            <span class="timeline-num tabular" aria-hidden="true"><span class="timeline-n">${idx + 1}</span>${svgIcon('check', 'timeline-check')}</span>
            <span class="timeline-text">${step}</span>
        </button></li>`).join('')}
    </ol>`;
    const stepsSection = `<section class="detail-block steps-section">
        <div class="steps-head">
            <h2 class="detail-h">Bosqichma-bosqich yordam</h2>
            <span class="steps-progress" aria-live="polite"><span class="tabular" id="steps-progress-count">0/${item.steps.length}</span><span class="sr-only"> qadam bajarildi</span></span>
        </div>
        <div class="steps-bar" aria-hidden="true"><span id="steps-bar-fill"></span></div>
        <p class="steps-hint">Bajarilgan qadamni belgilash uchun ustiga bosing</p>
        ${stepsHtml}
        <div class="steps-done" id="steps-done" role="status"></div>
    </section>`;
    const dontCard = `<section class="dont-card" role="note" aria-label="Qilmang">
        <h2 class="dont-title">${svgIcon('ban')}<span>Qilmang!</span></h2>
        <ul class="dont-list">${splitProhibited(item.prohibited).map(p => `<li><span class="dont-x" aria-hidden="true">${svgIcon('x')}</span><span>${p}</span></li>`).join('')}</ul>
    </section>`;
    const tips = (item.tips && item.tips.length)
        ? detailSection('Foydali maslahatlar', `<ul class="dot-list">${item.tips.map(t => `<li>${t}</li>`).join('')}</ul>`) : '';

    let html = '';
    if (severe) {
        // Kritik: 103 -> qadamlar -> Qilmang! -> Alomatlar (yig'iladigan). Qadamlar birinchi ekranda ko'rinadi.
        html += callCard(true);
        html += `<p class="detail-lead">${item.desc}</p>`;
        html += stepsSection;
        html += dontCard;
        if (hasSymptoms) {
            html += `<details class="detail-collapse">
                <summary><span class="detail-h">Alomatlar</span><span class="collapse-count tabular">${item.symptoms.length}</span>${svgIcon('chevron-down', 'collapse-chevron')}</summary>
                ${symptomTags}
            </details>`;
        }
        html += tips;
    } else {
        html += `<div class="safety-row" role="note">${svgIcon('shield-check')}<span><strong>Avval xavfsizlikni tekshiring.</strong> O'zingiz va bemor uchun xavf yo'qligiga ishonch hosil qiling.</span></div>`;
        html += `<p class="detail-lead">${item.desc}</p>`;
        if (hasSymptoms) html += detailSection('Alomatlar', symptomTags);
        html += stepsSection;
        html += dontCard;
        html += tips;
        if (has103) html += callCard(false);
    }

    const share = [plainText(item.title), '', 'Bosqichma-bosqich yordam:']
        .concat(item.steps.map((s, i) => `${i + 1}. ${plainText(s)}`))
        .concat(['', 'Qilmang:'], splitProhibited(item.prohibited).map(p => '✕ ' + plainText(p)))
        .concat(['', "Og'ir holatda: 103 — Tez yordam", 'Birinchi Yordam bot: https://t.me/' + BOT_USERNAME]);

    showDetail(item.title, chips, html, severe
        ? { text: "103 ga qo'ng'iroq", color: '#C9343A', textColor: '#FFFFFF', onClick: dial103 }
        : { text: "AI'dan so'rash", onClick: askAiFromDetail },
        { shareText: share.join('\n'), secondaryAi: severe });
}

// RENDER DISEASES — alifbo harflari bo'yicha guruhlangan inset ro'yxat (4.4-D)
const UZ_LETTER_ORDER = 'ABDEFGHIJKLMNOPQRSTUVXYZ';

function letterRank(letter) {
    const i = UZ_LETTER_ORDER.indexOf(letter);
    return i === -1 ? 100 + letter.charCodeAt(0) : i;
}

// Kategoriya -> rang guruhi (faqat bezak nuqtasi; kategoriya nomi matn sifatida ham yoziladi)
const CAT_HUE = {
    Yurak: 'red', Qon: 'red', Travma: 'red',
    Nafas: 'blue', Tomoq: 'blue', Quloq: 'blue', "Ko'z": 'blue', "Og'iz": 'blue',
    Oshqozon: 'teal', Ichak: 'teal', Jigar: 'teal', Metabolizm: 'teal', Endokrin: 'teal',
    Teriga: 'amber', Tish: 'amber',
    Ruhiy: 'violet', Asab: 'violet', Miya: 'violet',
    Yuqumli: 'green', Infeksiya: 'green', Profilaktika: 'green',
    Tanosil: 'pink', Siydik: 'pink', Buyrak: 'pink',
    Tayanch: 'slate', Umumiy: 'slate'
};

function catDot(cat) {
    const dot = document.createElement('span');
    dot.className = 'cat-dot cat--' + (CAT_HUE[cat] || 'slate');
    dot.setAttribute('aria-hidden', 'true');
    return dot;
}

// Mos kelgan qismni <mark> bilan belgilaydi. Solishtirish normalizeSearch() bilan bir xil (apostroflarsiz).
// Xavfsiz: faqat text node'lar, innerHTML ishlatilmaydi.
function setHighlighted(el, text, q) {
    el.textContent = '';
    let norm = '';
    const map = [];
    for (let i = 0; i < text.length; i++) {
        if (/['ʻʼ‘’`´]/.test(text[i])) continue;
        norm += text[i].toLowerCase();
        map.push(i);
    }
    const at = q ? norm.indexOf(q) : -1;
    if (at === -1) { el.append(text); return; }
    const start = map[at];
    const end = map[at + q.length - 1] + 1;
    const mark = document.createElement('mark');
    mark.textContent = text.slice(start, end);
    el.append(text.slice(0, start), mark, text.slice(end));
}

function prefersReducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

// Alifbo tartibi: o'zbek harflar ketma-ketligi, keyin localeCompare
function compareDiseaseNames(p, r) {
    return letterRank(displayTitle(p.name).charAt(0).toUpperCase()) - letterRank(displayTitle(r.name).charAt(0).toUpperCase())
        || p.name.localeCompare(r.name, 'uz');
}

// Sticky harf sarlavhalari qidiruv paneli ostida to'xtashi uchun panel balandligi
function syncStickyToolsHeight() {
    const tab = document.getElementById('tab-diseases');
    const tools = tab && tab.querySelector('.sticky-tools');
    if (!tools || !tools.offsetHeight) return;
    tab.style.setProperty('--tools-h', tools.offsetHeight + 'px');
    // A–Z panel yuqori chegarasi: qidiruv panelining skrollsiz holatdagi pastki cheti (header va chiplar bilan to'qnashmaydi)
    const content = document.querySelector('.app-content');
    const head = tab.querySelector('.screen-head');
    let bottom = tools.getBoundingClientRect().bottom;
    if (content && content.scrollTop > 0 && head) {
        bottom = head.getBoundingClientRect().bottom + content.scrollTop
            + (parseFloat(getComputedStyle(head).marginBottom) || 0) + tools.offsetHeight;
    }
    tab.style.setProperty('--az-top', Math.round(bottom + 8) + 'px');
    updateAzActive();
}

function renderDiseases(data, opts) {
    opts = opts || {};
    const q = opts.query || '';
    const container = document.getElementById('disease-list-container');
    const empty = document.getElementById('disease-empty');
    container.innerHTML = '';
    if (empty) empty.hidden = data.length !== 0;

    const groups = {};
    data.forEach(item => {
        const letter = (displayTitle(item.name).charAt(0) || '#').toUpperCase();
        (groups[letter] = groups[letter] || []).push(item);
    });
    const letters = Object.keys(groups).sort((x, y) => letterRank(x) - letterRank(y));
    // Filtr (qidiruv yoki kategoriya) faol bo'lsa — harf sarlavhalarisiz bitta ro'yxat
    const flat = !!q || diseaseCategory !== 'all';
    const sections = flat ? (data.length ? [{ letter: null, items: data }] : [])
                          : letters.map(l => ({ letter: l, items: groups[l] }));
    sections.forEach(({ letter, items }) => {
        if (letter) {
            const header = document.createElement('h2');
            header.className = 'letter-header';
            header.setAttribute('data-letter', letter);
            header.textContent = letter;
            container.appendChild(header);
        }

        const group = document.createElement('div');
        group.className = 'inset-group';
        (flat ? items : items.slice().sort(compareDiseaseNames))
            .forEach(item => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'list-row';
                row.innerHTML = `<span class="row-text"><span class="row-title"></span><span class="row-sub"><span class="row-cat"></span></span></span>${svgIcon('chevron-right', 'row-chevron')}`;
                setHighlighted(row.querySelector('.row-title'), item.name, q);
                const sub = row.querySelector('.row-sub');
                sub.insertBefore(catDot(item.cat), sub.firstChild);
                setHighlighted(row.querySelector('.row-cat'), item.cat, q);
                const snippet = opts.snippets && opts.snippets.get(item);
                if (snippet) {
                    // Tavsifdagi alomat orqali topilgan: mos bo'lak kichik matn bilan
                    const m = document.createElement('span');
                    m.className = 'row-match';
                    setHighlighted(m, snippet, q);
                    row.querySelector('.row-text').appendChild(m);
                }
                row.addEventListener('click', () => openDiseaseDetail(item));
                group.appendChild(row);
            });
        container.appendChild(group);
    });

    container.classList.remove('animate-in');
    if (opts.animate && !prefersReducedMotion()) {
        void container.offsetWidth;                       // animatsiyani qayta boshlash
        container.classList.add('animate-in');
        setTimeout(() => container.classList.remove('animate-in'), 400);
    }
    renderAzIndex(letters, !q && diseaseCategory === 'all' && data.length > 0);
}

// ── A–Z tezkor indeks (o'ng chetda). Qidiruv yoki kategoriya faol bo'lsa yashirin. ──
// smooth — bosilganda silliq (prefers-reduced-motion da darhol); sudrab tanlashda (scrub) darhol
let azPending = null;                  // silliq o'tish davomida faol harf o'zgarib-o'zgarib turmaydi

function scrollToLetter(letter, focusRow, smooth) {
    const header = document.querySelector(`#disease-list-container .letter-header[data-letter="${CSS.escape(letter)}"]`);
    const content = document.querySelector('.app-content');
    if (!header || !content) return;
    const tools = document.querySelector('#tab-diseases .sticky-tools');
    const offset = header.getBoundingClientRect().top - content.getBoundingClientRect().top - (tools ? tools.offsetHeight : 0) - 4;
    const target = Math.max(0, Math.min(content.scrollTop + offset, content.scrollHeight - content.clientHeight));
    setAzActive(letter);
    // Skroll manziliga yetguncha (ro'yxat oxirida ham) tanlangan harf faol qoladi
    azPending = Math.abs(target - content.scrollTop) > 1 ? target : null;
    if (smooth && !prefersReducedMotion() && content.scrollTo) content.scrollTo({ top: target, behavior: 'smooth' });
    else content.scrollTop = target;
    if (focusRow) {
        const row = header.nextElementSibling && header.nextElementSibling.querySelector('.list-row');
        if (row) row.focus({ preventScroll: true });
    }
}

function renderAzIndex(letters, visible) {
    const nav = document.getElementById('disease-az');
    if (!nav) return;
    nav.hidden = !visible;
    document.getElementById('tab-diseases').classList.toggle('az-on', visible);
    if (nav.getAttribute('data-letters') === letters.join('')) return;
    nav.setAttribute('data-letters', letters.join(''));
    nav.innerHTML = '';
    letters.forEach(letter => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = letter;
        btn.setAttribute('data-letter', letter);
        btn.setAttribute('aria-label', `${letter} harfiga o'tish`);
        // Klaviatura (detail === 0) — fokus ham guruhning birinchi qatoriga o'tadi.
        // Sichqoncha / barmoq bosishi pointerup da (initAzScrub) bajariladi.
        btn.addEventListener('click', (e) => { if (e.detail === 0) scrollToLetter(letter, true, true); });
        nav.appendChild(btn);
    });
    updateAzActive();
}

// Faol harf: hozir ko'rinib turgan bo'lim (--primary fon). Ro'yxatda yo'q harflar panelda umuman chiqmaydi.
function setAzActive(letter) {
    document.querySelectorAll('#disease-az button').forEach(b => {
        const on = b.getAttribute('data-letter') === letter;
        b.classList.toggle('is-active', on);
        if (on) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
}

function updateAzActive() {
    const nav = document.getElementById('disease-az');
    const content = document.querySelector('.app-content');
    if (!nav || nav.hidden || !content) return;
    if (azPending !== null) {                       // panel orqali o'tish: manzilga yetguncha tanlangan harf qoladi
        if (Math.abs(content.scrollTop - azPending) <= 2) azPending = null;
        return;
    }
    const tools = document.querySelector('#tab-diseases .sticky-tools');
    const line = content.getBoundingClientRect().top + (tools ? tools.offsetHeight : 0) + 8;
    const headers = document.querySelectorAll('#disease-list-container .letter-header');
    let current = headers.length ? headers[0].getAttribute('data-letter') : null;
    headers.forEach(h => { if (h.getBoundingClientRect().top <= line) current = h.getAttribute('data-letter'); });
    if (current) setAzActive(current);
}

// Barmoq / sichqoncha: bosish — tegishli bo'limga silliq o'tish; sudrab o'tish (scrub) — harf almashganda darhol
function initAzScrub() {
    const nav = document.getElementById('disease-az');
    if (!nav) return;
    let active = false, start = null, last = null, moved = false;
    const letterAt = (e) => {
        const el = document.elementFromPoint(e.clientX, e.clientY);
        const btn = el && el.closest && el.closest('#disease-az button');
        return btn ? btn.getAttribute('data-letter') : null;
    };
    nav.addEventListener('pointerdown', (e) => {
        active = true;
        moved = false;
        start = last = letterAt(e);
        try { nav.setPointerCapture(e.pointerId); } catch (err) { /* eski brauzer */ }
        if (start) setAzActive(start);
    });
    nav.addEventListener('pointermove', (e) => {
        if (!active) return;
        const letter = letterAt(e);
        if (!letter || letter === last) return;
        moved = true;
        last = letter;
        scrollToLetter(letter, false, false);
        try { if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged(); } catch (err) { /* yo'q */ }
    });
    nav.addEventListener('pointerup', () => {
        if (active && !moved && start) scrollToLetter(start, false, true);
        active = false;
    });
    nav.addEventListener('pointercancel', () => { active = false; });
    // Faol harf skroll bo'yicha; foydalanuvchi o'zi skroll qilsa silliq o'tish kutilmaydi
    const content = document.querySelector('.app-content');
    if (content) {
        content.addEventListener('scroll', updateAzActive, { passive: true });
        ['wheel', 'touchstart', 'pointerdown', 'keydown'].forEach(ev =>
            content.addEventListener(ev, () => { azPending = null; }, { passive: true }));
    }
}

// OPEN DISEASE DETAILS
function openDiseaseDetail(item) {
    detailSevere = false;
    detailAiContext = { type: 'condition', key: aiDiseaseKey(item.name), label: item.name, prefix: 'Kasallik' };
    const chips = `<span class="chip chip--primary">${item.cat}</span>`;
    let html = detailSection('Kasallik tavsifi', `<p>${item.desc}</p>`);
    html += detailSection('Birinchi yordam va chora', `<div class="aid-card"><p>${item.aid}</p></div>`);
    html += `<p class="detail-note">Har qanday kasallikda o'z-o'zini davolashdan ko'ra, malakali shifokor ko'rigidan o'tish tavsiya etiladi.</p>`;
    const share = [item.name, '', 'Kasallik tavsifi: ' + plainText(item.desc), '', 'Birinchi yordam va chora: ' + plainText(item.aid),
                   '', 'Birinchi Yordam bot: https://t.me/' + BOT_USERNAME].join('\n');
    showDetail(item.name, chips, html, { text: "AI'dan so'rash", onClick: askAiFromDetail }, { shareText: share, secondaryAi: false });
}

// SEARCH + KATEGORIYA CHIPLARI
let diseaseCategory = 'all';

// Tavsifdan mos bo'lakni ajratadi (vergul/nuqta oralig'i, uzun bo'lsa moslik atrofida qisqartiriladi)
// Tavsifda so'z boshidan moslik (so'z o'rtasidagi moslik — masalan "gri" ichida "og'riq" — hisoblanmaydi)
function wordStartRe(q) {
    return new RegExp('(^|[^\\p{L}\\p{N}])' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'u');
}

function descSnippet(desc, q) {
    const re = wordStartRe(q);
    const parts = String(desc || '').split(/[.,;:!?]/).map(s => s.trim()).filter(Boolean);
    const hit = parts.find(s => re.test(normalizeSearch(s)));
    if (!hit) return null;
    if (hit.length <= 70) return hit;
    const at = Math.max(0, normalizeSearch(hit).indexOf(q) - 25);
    return (at > 0 ? '…' : '') + hit.slice(at, at + 64).trim() + '…';
}

// Moslik darajasi: 0 — so'z boshi (prefix), 1 — nom ichida, 2 — kategoriya, 3 — tavsif/alomat (>= 3 belgi, so'z boshidan).
// -1 — mos emas
function diseaseMatchRank(item, q) {
    const name = normalizeSearch(item.name);
    if (name.split(/[\s()\-\/,«»"]+/).some(w => w && w.startsWith(q))) return 0;
    if (name.includes(q)) return 1;
    if (normalizeSearch(item.cat).includes(q)) return 2;
    if (q.length >= 3 && wordStartRe(q).test(normalizeSearch(item.desc))) return 3;
    return -1;
}

function applyDiseaseFilter(animate) {
    const input = document.getElementById('disease-search-input');
    const q = normalizeSearch(input ? input.value.trim() : '');
    const snippets = new Map();
    const ranked = [];
    DISEASES_DATA.forEach(item => {
        if (diseaseCategory !== 'all' && item.cat !== diseaseCategory) return;
        const rank = q ? diseaseMatchRank(item, q) : 0;
        if (rank === -1) return;
        if (rank === 3) snippets.set(item, descSnippet(item.desc, q));
        ranked.push({ item, rank });
    });
    ranked.sort((x, y) => x.rank - y.rank || compareDiseaseNames(x.item, y.item));
    const filtered = ranked.map(r => r.item);
    renderDiseases(filtered, { query: q, animate: !!animate, snippets });
    const count = document.getElementById('disease-count');
    if (count) {
        const filteredOn = !!q || diseaseCategory !== 'all';
        count.hidden = !filteredOn || filtered.length === 0;
        count.textContent = filteredOn ? `${filtered.length} ta natija` : '';
    }
    syncStickyToolsHeight();
}

// Chiplar qatori: o'ng chetda fade (skroll borligi ko'rinadi); oxiriga yetganda fade olinadi
function updateChipFade(bar) {
    bar.classList.toggle('at-end', bar.scrollLeft + bar.clientWidth >= bar.scrollWidth - 2);
}

// Faol chip ko'rinadigan joyga o'zi skroll qiladi (faqat gorizontal)
function revealChip(bar, chip) {
    const b = bar.getBoundingClientRect();
    const c = chip.getBoundingClientRect();
    let dx = 0;
    if (c.right > b.right - 40) dx = c.right - b.right + 48;
    else if (c.left < b.left + 8) dx = c.left - b.left - 16;
    if (!dx) return;
    const left = Math.max(0, Math.min(bar.scrollLeft + dx, bar.scrollWidth - bar.clientWidth));
    bar.classList.toggle('at-end', left >= bar.scrollWidth - bar.clientWidth - 2);   // silliq skroll tugashini kutmaymiz
    if (bar.scrollTo && !prefersReducedMotion()) bar.scrollTo({ left: left, behavior: 'smooth' });
    else bar.scrollLeft = left;
}

function selectDiseaseCategory(cat, focus) {
    const bar = document.getElementById('disease-cats');
    diseaseCategory = cat;
    let chosen = null;
    bar.querySelectorAll('.cat-chip').forEach(c => {
        const on = c.getAttribute('data-cat') === cat;
        c.setAttribute('aria-selected', on ? 'true' : 'false');
        c.tabIndex = on ? 0 : -1;
        if (on) chosen = c;
    });
    if (chosen) {
        if (focus) chosen.focus({ preventScroll: true });
        revealChip(bar, chosen);
    }
    const content = document.querySelector('.app-content');
    applyDiseaseFilter(true);
    if (content) {
        const head = document.querySelector('#tab-diseases .sticky-tools');
        if (head && content.scrollTop > head.offsetTop) content.scrollTop = head.offsetTop;   // ro'yxat boshiga
    }
}

function renderDiseaseCategories() {
    const bar = document.getElementById('disease-cats');
    if (!bar) return;
    const counts = {};
    DISEASES_DATA.forEach(d => { counts[d.cat] = (counts[d.cat] || 0) + 1; });
    const cats = ['all'].concat(Object.keys(counts).sort((x, y) => counts[y] - counts[x] || x.localeCompare(y, 'uz')));
    bar.innerHTML = '';
    cats.forEach(cat => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'cat-chip';
        chip.setAttribute('role', 'tab');
        chip.setAttribute('data-cat', cat);
        chip.setAttribute('aria-selected', cat === diseaseCategory ? 'true' : 'false');
        chip.tabIndex = cat === diseaseCategory ? 0 : -1;
        if (cat !== 'all') chip.appendChild(catDot(cat));
        chip.append(cat === 'all' ? 'Hammasi' : cat);
        chip.addEventListener('click', () => selectDiseaseCategory(cat, false));
        bar.appendChild(chip);
    });
    // Klaviatura: ←/→, Home/End (roving tabindex)
    bar.addEventListener('keydown', (e) => {
        const chips = [...bar.querySelectorAll('.cat-chip')];
        const i = chips.indexOf(document.activeElement);
        if (i === -1) return;
        let j = null;
        if (e.key === 'ArrowRight') j = Math.min(i + 1, chips.length - 1);
        else if (e.key === 'ArrowLeft') j = Math.max(i - 1, 0);
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = chips.length - 1;
        if (j === null) return;
        e.preventDefault();
        selectDiseaseCategory(chips[j].getAttribute('data-cat'), true);
    });
    bar.addEventListener('scroll', () => updateChipFade(bar), { passive: true });
    updateChipFade(bar);
}

function initSearch() {
    const input = document.getElementById('disease-search-input');
    const clearBtn = document.getElementById('search-clear-btn');
    renderDiseaseCategories();
    initAzScrub();
    applyDiseaseFilter(true);

    input.addEventListener('input', () => {
        clearBtn.hidden = input.value.length === 0;
        applyDiseaseFilter(false);
    });

    clearBtn.addEventListener('click', (e) => {
        e.preventDefault();
        input.value = '';
        clearBtn.hidden = true;
        applyDiseaseFilter(false);
        input.focus();
    });

    const ask = document.getElementById('disease-ask-ai');
    if (ask) ask.addEventListener('click', askAiFromSearch);
    // Tab birinchi marta ko'ringanda chiplar o'lchami ma'lum bo'ladi
    document.querySelectorAll('.nav-btn[data-tab="tab-diseases"]').forEach(b =>
        b.addEventListener('click', () => { updateChipFade(document.getElementById('disease-cats')); syncStickyToolsHeight(); }));
    window.addEventListener('resize', syncStickyToolsHeight);
}

// OVERLAY CONTROLS
function initOverlay() {
    const closeBtn = document.getElementById('close-overlay-btn');
    const overlay = document.getElementById('overlay-details');

    closeBtn.addEventListener('click', closeDetail);
    overlay.addEventListener('scroll', updateDetailBar, { passive: true });
    document.getElementById('detail-share-btn').addEventListener('click', shareDetail);
    document.getElementById('detail-ai-btn').addEventListener('click', askAiFromDetail);
    // Klaviatura: Esc — detalni yopadi
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) closeDetail();
    });
}

// CALCULATORS (4.4-E). Formulalar o'zgarmagan; "Hisoblash" — MainButton (Telegram) yoki sahifadagi tugma.
let currentCalc = 'bmi';
const CALC_FIELDS = {
    bmi: ['bmi-weight', 'bmi-height'],
    water: ['water-weight'],
    calorie: ['calorie-weight', 'calorie-height', 'calorie-age']
};

// Ruxsat etilgan oraliqlar (input min/max bilan bir xil) va maydon ostidagi xabar
const CALC_RANGES = {
    'bmi-weight': [20, 300, "Vazn 20–300 kg oralig'ida bo'lsin"],
    'bmi-height': [50, 250, "Bo'y 50–250 sm oralig'ida bo'lsin"],
    'water-weight': [20, 300, "Vazn 20–300 kg oralig'ida bo'lsin"],
    'calorie-weight': [20, 300, "Vazn 20–300 kg oralig'ida bo'lsin"],
    'calorie-height': [50, 250, "Bo'y 50–250 sm oralig'ida bo'lsin"],
    'calorie-age': [1, 120, "Yosh 1–120 oralig'ida bo'lsin"]
};

function fieldValue(id) {
    const el = document.getElementById(id);
    return id === 'calorie-age' ? parseInt(el.value) : parseFloat(el.value);
}

function fieldValid(id) {
    const v = fieldValue(id);
    const r = CALC_RANGES[id];
    return v > 0 && (!r || (v >= r[0] && v <= r[1]));
}

function calcInputValid(type) {
    return CALC_FIELDS[type].every(fieldValid);
}

// Xabar faqat maydon to'ldirilib, noto'g'ri bo'lsa (yozish paytida emas — blur/Enter da)
function showFieldError(id, force) {
    const el = document.getElementById(id);
    const err = document.getElementById(id + '-err');
    if (!err) return;
    const bad = el.value.trim() !== '' && !fieldValid(id);
    const show = bad && (force || !err.hidden);
    err.hidden = !show;
    if (show) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
}

function runCalc() {
    const fn = { bmi: calcBmi, water: calcWater, calorie: calcCalorie }[currentCalc];
    if (fn) fn();
}

// Sog'liq (kalkulyator) ekrani ochiq va detal yopiq bo'lsa — "Hisoblash" tugmasi; aks holda o'zimiznikini olib tashlaymiz
function syncCalcMainButton() {
    const tab = document.getElementById('tab-health');
    const overlay = document.getElementById('overlay-details');
    const onCalc = tab && tab.classList.contains('active') && !(overlay && overlay.classList.contains('active'));
    if (!onCalc) {
        if (MainButtonCtl.owner === 'calc') MainButtonCtl.clear();
        return;
    }
    MainButtonCtl.set({ text: 'Hisoblash', owner: 'calc', onClick: runCalc }, document.getElementById('btn-calculate-' + currentCalc));
    MainButtonCtl.setActive(calcInputValid(currentCalc));
}

function switchCalc(type) {
    if (!CALC_FIELDS[type]) return;
    currentCalc = type;
    document.querySelectorAll('[data-calc]').forEach(b => {
        b.setAttribute('aria-selected', b.getAttribute('data-calc') === type ? 'true' : 'false');
    });
    document.querySelectorAll('.calc-section').forEach(s => s.classList.toggle('active', s.id === 'calc-' + type + '-section'));
    document.querySelectorAll('[data-calc-result]').forEach(r => {
        if (r.getAttribute('data-calc-result') !== type) r.hidden = true;
    });
    syncCalcMainButton();
}

function showCalcResult(id) {
    const card = document.getElementById(id);
    card.hidden = false;
    // Natija ko'rinadigan joyga o'zi skroll qiladi (MainButton paddingi hisobga olinadi)
    try { card.scrollIntoView({ block: 'nearest', behavior: prefersReducedMotion() ? 'auto' : 'smooth' }); } catch (e) { /* eski brauzer */ }
}

const BMI_CHIP = { low: 'chip--warning', ok: 'chip--teal', over: 'chip--warning', obese: 'chip--danger' };

function calcBmi() {
    const weight = parseFloat(document.getElementById('bmi-weight').value);
    const height = parseFloat(document.getElementById('bmi-height').value);

    if (!weight || !height || weight <= 0 || height <= 0) {
        if (tg) tg.showAlert("Iltimos, vazn va bo'y qiymatlarini to'g'ri kiriting!");
        else notify("Iltimos, vazn va bo'y qiymatlarini to'g'ri kiriting!");
        return;
    }

    const heightM = height / 100;
    const bmi = weight / (heightM * heightM);

    document.getElementById('bmi-number').innerText = bmi.toFixed(1);

    // Normal vazn diapazonini hisoblash
    const minW = 18.5 * (heightM * heightM);
    const maxW = 24.9 * (heightM * heightM);
    document.getElementById('bmi-ideal-range').innerText = `${minW.toFixed(1)} - ${maxW.toFixed(1)} kg`;

    let status = '';
    let desc = '';
    let level = 'ok';
    let pointerPos = 0; // % from left

    if (bmi < 18.5) {
        status = "Kam vazn";
        desc = "Sizning tana vazningiz me'yordan past. Sog'lom va to'yimli ovqatlanishga harakat qiling.";
        level = 'low';
        pointerPos = 15;
    } else if (bmi >= 18.5 && bmi < 25) {
        status = "Normal vazn";
        desc = "Sizning vazningiz mutlaqo me'yorda! Faol bo'ling va to'g'ri ovqatlanishda davom eting.";
        level = 'ok';
        pointerPos = 40;
    } else if (bmi >= 25 && bmi < 30) {
        status = "Ortiqcha vazn";
        desc = "Tana vazningiz me'yordan bir oz yuqori. Jismoniy mashqlar va shirinliklarni kamaytirish tavsiya etiladi.";
        level = 'over';
        pointerPos = 65;
    } else {
        status = "Semizlik";
        desc = "Sizda semizlik darajasi aniqlandi. Sog'lig'ingiz uchun shifokor-dietolog bilan maslahatlashishni tavsiya qilamiz.";
        level = 'obese';
        pointerPos = 90;
    }

    const chip = document.getElementById('bmi-status');
    chip.innerText = status;
    chip.className = 'chip ' + BMI_CHIP[level];
    document.getElementById('bmi-description').innerText = desc;
    // Marker shkala bo'ylab joyiga keladi: birinchi ko'rsatishda chap chetdan
    const pointer = document.getElementById('bmi-gauge-pointer');
    if (document.getElementById('bmi-result-card').hidden) {
        pointer.style.left = '0%';
        showCalcResult('bmi-result-card');
        void pointer.offsetWidth;
    } else {
        showCalcResult('bmi-result-card');
    }
    pointer.style.left = `${pointerPos}%`;

    // BMI tarixiga saqlash
    saveHistory('bmi', { bmi: bmi.toFixed(1), weight, height, status: status.replace(/[^a-zA-Z\s']/g, '').trim() });
    renderHistoryLog();
}

function calcWater() {
    const weight = parseFloat(document.getElementById('water-weight').value);

    if (!weight || weight <= 0) {
        if (tg) tg.showAlert("Iltimos, vazningizni to'g'ri kiriting!");
        else notify("Iltimos, vazningizni to'g'ri kiriting!");
        return;
    }

    const minWater = weight * 30; // ml
    const sportWater = minWater + 500;
    const summerWater = minWater + 300;

    document.getElementById('water-value').innerText = `${(minWater / 1000).toFixed(1)} Litr`;
    document.getElementById('water-sport').innerText = `${(sportWater / 1000).toFixed(1)} L`;
    document.getElementById('water-summer').innerText = `${(summerWater / 1000).toFixed(1)} L`;

    showCalcResult('water-result-card');

    // Suv tarixiga saqlash
    saveHistory('water', { liters: (minWater / 1000).toFixed(1), weight });
    renderHistoryLog();
}

function calcCalorie() {
    const gender = document.getElementById('calorie-gender').value;
    const weight = parseFloat(document.getElementById('calorie-weight').value);
    const height = parseFloat(document.getElementById('calorie-height').value);
    const age = parseInt(document.getElementById('calorie-age').value);
    const activity = document.getElementById('calorie-activity').value;

    if (!weight || !height || !age || weight <= 0 || height <= 0 || age <= 0) {
        if (tg) tg.showAlert("Iltimos, barcha maydonlarni to'g'ri to'ldiring!");
        else notify("Iltimos, barcha maydonlarni to'g'ri to'ldiring!");
        return;
    }

    // Mifflin-St Jeor formula
    let bmr = 0;
    if (gender === 'male') {
        bmr = 10 * weight + 6.25 * height - 5 * age + 5;
    } else {
        bmr = 10 * weight + 6.25 * height - 5 * age - 161;
    }

    // TDEE (Total Daily Energy Expenditure)
    let factor = 1.2;
    if (activity === 'moderate') factor = 1.55;
    else if (activity === 'high') factor = 1.9;

    const tdee = bmr * factor;
    const lose = tdee - 500;
    const gain = tdee + 500;

    document.getElementById('calorie-value').innerText = `${Math.round(tdee)} kkal`;
    document.getElementById('calorie-lose').innerText = `${Math.round(lose)} kkal`;
    document.getElementById('calorie-gain').innerText = `${Math.round(gain)} kkal`;

    showCalcResult('calorie-result-card');
}

function initCalculators() {
    document.body.classList.toggle('tg-main', MainButtonCtl.available());
    document.querySelectorAll('[data-calc]').forEach(btn => {
        btn.addEventListener('click', () => switchCalc(btn.getAttribute('data-calc')));
    });
    Object.keys(CALC_FIELDS).forEach(type => {
        const ids = CALC_FIELDS[type];
        ids.forEach((id, i) => {
            const el = document.getElementById(id);
            // Maydon ostidagi xabar (aria-describedby)
            const err = document.createElement('p');
            err.className = 'field-error';
            err.id = id + '-err';
            err.hidden = true;
            err.textContent = CALC_RANGES[id][2];
            el.closest('.field').appendChild(err);
            el.setAttribute('aria-describedby', err.id);
            el.setAttribute('enterkeyhint', i === ids.length - 1 ? 'done' : 'next');

            el.addEventListener('input', () => {
                showFieldError(id, false);
                if (type === currentCalc && MainButtonCtl.owner === 'calc') MainButtonCtl.setActive(calcInputValid(type));
            });
            el.addEventListener('blur', () => showFieldError(id, true));
            // Enter: keyingi maydon; oxirgisida — hisoblash (hammasi to'g'ri bo'lsa), aks holda birinchi xatoga
            el.addEventListener('keydown', (e) => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                showFieldError(id, true);
                if (i < ids.length - 1) { document.getElementById(ids[i + 1]).focus(); return; }
                if (calcInputValid(type)) { currentCalc = type; runCalc(); return; }
                const bad = ids.find(x => !fieldValid(x));
                if (bad) { showFieldError(bad, true); document.getElementById(bad).focus(); }
            });
        });
        // Sahifadagi tugma (brauzer zaxirasi) — MainButton bilan bir xil yo'l
        const btn = document.getElementById('btn-calculate-' + type);
        btn.addEventListener('click', () => { if (!btn.onclick) { currentCalc = type; runCalc(); } });
    });
}

// ═══════════════════════════════════════════════════════════════════
// QUIZ
// ═══════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════
// QUIZ — 65 ta savollik havza, har sessiyada 10 ta tasodifiy
// ═══════════════════════════════════════════════════════════════════

const QUIZ_POOL = [
    { q: "Kuyganda birinchi nima qilish kerak?", options: ["Yog' surish", "Muz qo'yish", "Sovuq suv ostida ushlab turish", "Tish pastasi surtish"], answer: 2 },
    { q: "Qon ketishini to'xtatish uchun qanday bosim o'rnatiladi?", options: ["Yaraning pastki qismiga", "Yaraning yuqori qismiga", "Yara ustiga to'g'ridan-to'g'ri", "Yon tomonga"], answer: 2 },
    { q: "Yurak xurujida bemorni qanday o'tqizish kerak?", options: ["To'liq yotqizish", "Yarim o'tirgan holatda", "Tik turdirish", "Oyoqlarini ko'targan holda yotqizish"], answer: 1 },
    { q: "BMI qanday formulada hisoblanadi?", options: ["Vazn × bo'y", "Vazn / (bo'y²)", "(Vazn + bo'y) / 2", "Vazn - bo'y"], answer: 1 },
    { q: "Normal BMI qiymati qancha?", options: ["10 – 15", "15 – 18.5", "18.5 – 24.9", "25 – 30"], answer: 2 },
    { q: "Tomoqqa narsa tiqilganda qaysi usul qo'llaniladi?", options: ["Geymlix usuli", "CPR usuli", "Turniket usuli", "Shina usuli"], answer: 0 },
    { q: "Tez yordam raqami qancha?", options: ["101", "102", "103", "104"], answer: 2 },
    { q: "Hushidan ketgan bemorning oyoqlari qanday bo'lishi kerak?", options: ["Pastga tushirilgan", "30 sm ko'tarilgan", "Bukib qo'yilgan", "Ikki yon tomonga yozilgan"], answer: 1 },
    { q: "Kislota bilan zaharlanganda qustirish ...", options: ["Foydali", "Zararsiz", "Mutlaqo taqiqlangan", "Ixtiyoriy"], answer: 2 },
    { q: "Issiqlik urganda birinchi navbatda nima qilinadi?", options: ["Bemorga qahva ichirish", "Sovuq vannaga solish", "Soya va salqin joyga olib o'tish", "Gips qo'yish"], answer: 2 },
    { q: "Yong'in xavfsizligi raqami qancha?", options: ["101", "102", "103", "104"], answer: 0 },
    { q: "Turniketni yozda necha soatdan ortiq qoldirish mumkin emas?", options: ["30 daqiqa", "1 soat", "1.5 soat", "3 soat"], answer: 2 },
    { q: "Suyak singanda birinchi nima qilish kerak?", options: ["Suyakni o'z joyiga solish", "Shikastlangan a'zoni harakatsiz qilish", "Issiq kompres qo'yish", "Massaj qilish"], answer: 1 },
    { q: "Insult belgilarida birinchi yordam:", options: ["Bemorni yurgizish", "Yotqizib boshini biroz ko'tarish va 103 chaqirish", "Sovuq suv ichirish", "Dori berish"], answer: 1 },
    { q: "Faollashtirilgan ko'mir har necha kg vazn uchun 1 tabletka beriladi?", options: ["5 kg", "10 kg", "15 kg", "20 kg"], answer: 1 },
    { q: "Noshadir spirti nima uchun ishlatiladi?", options: ["Yaralarni dezinfeksiya qilish", "Hushidan ketgan odamni o'ziga keltirish", "Harorat tushirish", "Og'riq qoldirish"], answer: 1 },
    { q: "Burun qonganda boshni qanday tutish kerak?", options: ["Orqaga eğish", "Oldinga engashtirish", "Yon tomonga burish", "Boshni ko'tarish"], answer: 1 },
    { q: "CPR (yurak-o'pka reanimatsiyasi) qanday bajariladi?", options: ["Ko'krak siqish + sun'iy nafas", "Faqat sun'iy nafas", "Faqat ko'krak siqish", "Orqaga zarba berish"], answer: 0 },
    { q: "Elektr toki ursa birinchi nima qilish kerak?", options: ["Bemorni qo'llar bilan tortish", "Elektr manbaini o'chirish yoki bemorni quruq tayoq bilan itarish", "Suvga yaxshiroq ulash", "Hech narsa qilmay 103 kutish"], answer: 1 },
    { q: "Ilon chaqganda nima QILISH MUMKIN EMAS?", options: ["A'zoni harakatsiz saqlash", "Zaharni og'iz bilan so'rib chiqarish", "103 chaqirish", "Bemorni tinch saqlash"], answer: 1 },
    { q: "Issiqlik urishida tana haroratini qanday tushirish TO'G'RI?", options: ["Muzdek suvli vannaga solish", "Ho'llangan latta bilan artish va salqin joyga o'tkazish", "Sport qilish", "Quyoshda qoldirish"], answer: 1 },
    { q: "Kuygan joyga nima surtish TAQIQLANGAN?", options: ["Steril bog'lam", "Sariyog' yoki tish pastasi", "Sovuq suv", "Toza latta"], answer: 1 },
    { q: "Pufakchali kuyishda pufakchani nima qilish kerak?", options: ["Yorish", "Siqish", "Yormaslik", "Igna bilan teshish"], answer: 2 },
    { q: "Qaysi holat uchun Geymlix usuli qo'llaniladi?", options: ["Qon ketish", "Bo'g'ilish (tomoqqa narsa tiqilish)", "Suyak sinishi", "Kuyish"], answer: 1 },
    { q: "Militsiya raqami qancha?", options: ["101", "102", "103", "1050"], answer: 1 },
    { q: "FVV (Favqulodda vaziyatlar xizmati) raqami qancha?", options: ["101", "102", "103", "1050"], answer: 3 },
    { q: "Ari chaqganda birinchi nima qilish kerak?", options: ["Jarohatni ovqatga bosish", "Nishni pinset bilan chiqarib olish", "Nishni barmoq bilan siqish", "Isitish"], answer: 1 },
    { q: "Miya chayqalishida bemor qanday bo'lishi kerak?", options: ["Tik turishi", "Yugurishi", "Tekis yotishi", "Sakrashi"], answer: 2 },
    { q: "Lat yeyishda (bruise) birinchi chorа:", options: ["Issiq kompres", "Massaj", "Muz qo'yish", "Sport qilish"], answer: 2 },
    { q: "Pay cho'zilganda bo'g'imni nima bilan mahkamlash kerak?", options: ["Ip bilan", "Elastik bint bilan", "Qattiq sim bilan", "Mahkamlash kerak emas"], answer: 1 },
    { q: "Kimyoviy kuyishda yara necha daqiqa suv ostida tutiladi?", options: ["5 daqiqa", "10 daqiqa", "20 daqiqa", "1 daqiqa"], answer: 2 },
    { q: "Zaharlanishda nima uchun bemorni qustirish tavsiya etilmaydi?", options: ["Samarasiz bo'lgani uchun", "Zahar qizilo'ngachni qaytishda yana kuydirishi va nafas yo'liga tushishi mumkinligi uchun", "Qon bosimini tushirib yuborishi uchun", "Bemorni charchatgani uchun"], answer: 1 },
    { q: "It qopganda yarani birinchi nimalar bilan yuvish kerak?", options: ["Faqat suv bilan", "Kir sovun va ko'p suv bilan", "Spirt bilan", "Yog' bilan"], answer: 1 },
    { q: "Qon bosimi tushib ketganda nima ichirish tavsiya etiladi?", options: ["Sovuq suv", "Iliq shirin choy yoki qahva", "Limon suvi", "Dori"], answer: 1 },
    { q: "Hushsiz odamning og'ziga nima quyish TAQIQLANGAN?", options: ["Havo", "Suv yoki dori", "Suv bug'i", "Hech narsa"], answer: 1 },
    { q: "Kimyoviy modda ko'zga chayqalganda nima qilish kerak?", options: ["Ko'zni ishqalash", "Ko'zni kamida 15-20 daqiqa davomida ko'p miqdorda oqib turgan toza suv bilan yuvish", "Ko'zni bog'lab qo'yish", "Ko'zga tomchi tomizish"], answer: 1 },
    { q: "Muzlagan a'zoni qanday isitish kerak?", options: ["Uni qor bilan ishqalash", "Uni issiq suvga solish", "Asta-sekin iliq muhitda isitish va quruq issiq bog'lam qo'yish", "Olovga yaqin tutish"], answer: 2 },
    { q: "Kuchli qon ketayotganda jgut (turniket) qayerga bog'lanadi?", options: ["Yaraning ustiga", "Yaradan 5-7 sm yuqoriroqqa (yurakka yaqinroq)", "Yaradan pastroqqa", "Bo'g'im ustiga"], answer: 1 },
    { q: "Ochiq suyak sinishida birinchi chora nima?", options: ["Suyakni joyiga kiritish", "Yarani tozalab, steril bog'lam qo'yish va a'zoni harakatsizlantirish (shina qo'yish)", "Shinani to'g'ridan-to'g'ri yalang'och suyakka bog'lash", "Singan joyni massaj qilish"], answer: 1 },
    { q: "Quyosh urganda bemorga qanday suyuqlik berish tavsiya etiladi?", options: ["Muzdek gazlangan suv", "Spirtli ichimliklar", "Oddiy yoki sho'rroq salqin suv", "Achchiq qahva"], answer: 2 },
    { q: "Isitma o'ta yuqori bo'lganda bemorga birinchi yordam sifatida nima qilish mumkin?", options: ["Uni qalin ko'rpaga o'rash", "Tanasini iliq suvda namlangan latta bilan artish va ko'p suyuqlik berish", "Muzdek suvli vannaga yotqizish", "Spirt surtib uxlashga yotqizish"], answer: 1 },
    { q: "Gipertonik krizda (qon bosimi keskin ko'tarilganda) bemorga qanday holat berish kerak?", options: ["Boshini pastga qilib yotqizish", "Yarim o'tirgan holat berish", "Tik turgan holda yurgizish", "Oyoqlarini baland ko'tarib yotqizish"], answer: 1 },
    { q: "Ari chaqqanda allergiya belgisi (shish, nafas qisilishi) bo'lsa, nima qilish kerak?", options: ["Oddiygina muz qo'yib kutish", "Zudlik bilan tez yordam chaqirish va antigistamin dori berish", "Chaqilgan joyni kesish", "Loy surtish"], answer: 1 },
    { q: "Ko'krak qafasiga yot jism kirib qolganda (masalan, pichoq yoki mix):", options: ["Uni tezda sug'urib olish kerak", "Uni joyida qoldirib, qimirlamaydigan qilib mahkamlash va shifokor chaqirish", "Jarohatni kattalashtirib tozalash", "Yarani spirt bilan yuvish"], answer: 1 },
    { q: "Bosh jarohatida bemor hushini yo'qotsa, birinchi navbatda nima qilish kerak?", options: ["Uni o'tirg'izish", "Nafas yo'llari ochiqligini tekshirish va yonbosh holatga yotqizish", "Boshini silkitish", "Yuziga muzdek suv sepib turish"], answer: 1 },
    { q: "CPR (yurak massaji) paytida kattalar uchun ko'krak qafasini bosish chuqurligi qancha bo'lishi kerak?", options: ["1-2 sm", "5-6 sm", "8-10 sm", "Bosish shart emas"], answer: 1 },
    { q: "Tikuv ignasi yoki mayda shisha bo'lagi teriga kirganda va uni ko'rib bo'lmaganda:", options: ["Igna bilan terini chuqur kovlash", "O'z holicha qoldirib, tibbiy yordamga murojaat qilish", "Issiq tuzli suvga solish", "Yarani qattiq siqish"], answer: 1 },
    { q: "Quturish kasalligi qanday yuqadi?", options: ["Faqat havo orqali", "Kasal hayvonning so'lagi shikastlangan teriga yoki yara ustiga tushganda (tishlaganda)", "Muloqot paytida ko'z orqali", "Faqat iflos suv ichganda"], answer: 1 },
    { q: "Qon ketganda yaraning ustiga qanday mato qo'yish kerak?", options: ["Rangli jun mato", "Steril doka (bint) yoki imkon qadar eng toza mato", "Quruq barglar", "Gazeta qog'ozi"], answer: 1 },
    { q: "Turniket (jgut) yozilgan qog'ozda nima yozilishi shart?", options: ["Bemoring ismi va yoshi", "Turniket bog'langan aniq vaqt (soat va daqiqa)", "Qon guruhi", "Tez yordam chaqirilgan vaqt"], answer: 1 },
    { q: "Gazdan zaharlangan odamni birinchi navbatda nima qilish kerak?", options: ["Unga suv ichirish", "Zudlik bilan toza havoga olib chiqish", "Yuragiga muz qo'yish", "Uni uxlashga yotqizish"], answer: 1 },
    { q: "Tok urgan odam hushida bo'lsa va tashqi jarohati bo'lmasa:", options: ["Unga darhol ruxsat berish", "Baribir shifokor ko'rigidan o'tkazish (yurak ritmi buzilishi mumkin)", "Unga dori berib yotqizish", "Sovuq suvda yuvintirish"], answer: 1 },
    { q: "Termik kuyishda (issiq suv yoki olovda) kiyim teriga yopishib qolsa:", options: ["Uni kuch bilan yulib olish", "Kiyimni yulmasdan, atrofini kesib olish va shifokorga murojaat qilish", "Ustidan yog' surtish", "Hech narsa qilmaslik"], answer: 1 },
    { q: "Qorin sohasida kuchli o'tkir og'riq bo'lganda (masalan, appenditsit shubhasida) nima qilish mumkin emas?", options: ["Tez yordam chaqirish", "Og'riq qoldiruvchi dori ichish va qoringa issiq narsa qo'yish", "Bemorni tinch holatda yotqizish", "Ovqat va suv bermaslik"], answer: 1 },
    { q: "Sovuq urgan tana a'zosini (masalan, barmoqlarni) uqalash orqali isitish...", options: ["Foydali, qon yurishadi", "Taqiqlanadi, chunki yumshoq to'qimalarga jiddiy shikast yetishi mumkin", "Zararsiz", "Faqat bolalarda mumkin"], answer: 1 },
    { q: "Bola tomoqqa narsa tiqilib ko'karib ketganda nima qilinadi (1 yoshgacha)?", options: ["Oyoqlaridan ko'tarib silkitish", "Qornidan quchoqlab Geymlix qilish", "Uni bilakka yuzini pastga qilib yotqizib, kuraklariga asta 5 marta urish", "Og'ziga suv quyish"], answer: 2 },
    { q: "Yurak xurujida aspirin dori vositasini bemorga qanday bergan ma'qul?", options: ["Butunlay yuttirish", "Chaynashni so'rash (tezroq so'rilishi uchun)", "Suvda eritib ichirish", "Aspirin berish mutlaqo mumkin emas"], answer: 1 },
    { q: "Epilepsiya (tutqanoq) xuruji paytida bemorning og'ziga qoshiq yoki qattiq jism tiqish...", options: ["Taqiqlanadi, tishlari va jag'iga zarar yetishi mumkin", "Tavsiya etiladi, tilini tishlab olmasligi uchun", "Faqat kattalarda ruxsat beriladi", "Zararsiz"], answer: 0 },
    { q: "Burun qonashida paxtani vodorod peroksid bilan ho'llab burunga qo'yish...", options: ["Zararli", "Yordam beradi (qonni to'xtatishga yordam beradi)", "Mutlaqo taqiqlangan", "Faqat shifokor qilishi kerak"], answer: 1 },
    { q: "Quyosh ostida uzoq vaqt bosh kiyimsiz yurish qanday oqibatga olib keladi?", options: ["Grippga", "Quyosh urishiga (issiqlik urishi)", "Gastritga", "Anemiyaga"], answer: 1 },
    { q: "Kattalarda yurak massaji soni va sun'iy nafas nisbati qanday bo'ladi?", options: ["15 ta bosish va 2 ta nafas", "30 ta bosish va 2 ta nafas", "10 ta bosish va 1 ta nafas", "5 ta bosish va 5 ta nafas"], answer: 1 },
    { q: "Kimyoviy modda teriga to'kilsa, suv bilan yuvishdan oldin nima qilish kerak?", options: ["Ustidan kukun sepish", "Quruq salfetka yoki mato bilan moddani ehtiyotkorlik bilan artib tashlash (agar u suv bilan reaksiyaga kirsa)", "Yog' surtish", "Hech narsa qilmasdan darhol suv quyish"], answer: 1 },
    { q: "Jarohatdan ko'piksimon, och qizil rangli qon otilib chiqayotgan bo'lsa, bu qanday qon ketish?", options: ["Venoz qon ketish", "Arterial qon ketish", "Kapillyar qon ketish", "Aralash qon ketish"], answer: 1 },
    { q: "Shikastlangan odamni ko'chirish yoki tashish qachon majburiy hisoblanadi?", options: ["Har qanday holatda darhol", "Faqat u yerda qolish bemor hayotiga xavf tug'dirganda (masalan, yong'in, qulash xavfi)", "Faqat bemor o'zi so'raganda", "Hech qachon mumkin emas"], answer: 1 },
    { q: "Hushidan ketgan odamni yonbosh (xavfsiz) holatga o'tkazishdan maqsad nima?", options: ["Uxlashini osonlashtirish", "Nafas yo'llari til orqaga ketishi yoki qusiq moddalari bilan to'silib qolishini oldini olish", "Og'riqni kamaytirish", "Qon bosimini ko'tarish"], answer: 1 },
];

// Massivni aralashtiruvchi funksiya (Fisher-Yates shuffle)
function shuffleArray(arr) {
    const a = [...arr];
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
}

// Savollar havzasidan 10 tani tasodifiy tanlab, variantlarini ham aralashtirib chiqaradi
function buildRandomQuiz(count = 10) {
    const picked = shuffleArray(QUIZ_POOL).slice(0, count);
    return picked.map(q => {
        // Har bir savol uchun variantlarni indeksi bilan birgalikda olish
        const indexed = q.options.map((opt, idx) => ({ opt, isCorrect: idx === q.answer }));
        const shuffled = shuffleArray(indexed);
        const newCorrect = shuffled.findIndex(o => o.isCorrect);
        return {
            q: q.q,
            options: shuffled.map(o => o.opt),
            answer: newCorrect
        };
    });
}

let QUIZ_QUESTIONS = buildRandomQuiz();
let quizState = { current: 0, score: 0, answered: false };

function initQuiz() {
    updateQuizStats();
    document.getElementById('btn-start-quiz').addEventListener('click', startQuiz);
    document.getElementById('btn-retry-quiz').addEventListener('click', startQuiz);
}

function updateQuizStats() {
    const best = parseInt(SafeStorage.getItem('quiz_best') || '0');
    const attempts = parseInt(SafeStorage.getItem('quiz_attempts') || '0');
    document.getElementById('quiz-best-score').innerText = best;
    document.getElementById('quiz-attempts').innerText = attempts;
}

function showQuizScreen(id) {
    document.querySelectorAll('.quiz-screen').forEach(s => s.classList.remove('active'));
    document.getElementById(id).classList.add('active');
}

function startQuiz() {
    // Har safar yangi tasodifiy savollar va aralash variantlar
    QUIZ_QUESTIONS = buildRandomQuiz(10);
    quizState = { current: 0, score: 0, answered: false };
    showQuizScreen('quiz-question-screen');
    renderQuizQuestion();
}

function renderQuizQuestion() {
    const q = QUIZ_QUESTIONS[quizState.current];
    const total = QUIZ_QUESTIONS.length;
    document.getElementById('quiz-q-num').innerText = `${quizState.current + 1} / ${total}`;
    document.getElementById('quiz-score-live').innerText = `${quizState.score} ball`;
    document.getElementById('quiz-progress-fill').style.width = `${((quizState.current + 1) / total) * 100}%`;
    const bar = document.getElementById('quiz-progress');
    bar.setAttribute('aria-valuemax', String(total));
    bar.setAttribute('aria-valuenow', String(quizState.current + 1));
    document.getElementById('quiz-question-text').innerText = q.q;
    document.getElementById('quiz-feedback').textContent = '';

    const container = document.getElementById('quiz-options-container');
    container.innerHTML = '';
    quizState.answered = false;

    q.options.forEach((opt, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'quiz-option-btn';
        btn.innerHTML = `<span class="quiz-opt-badge" aria-hidden="true"><span class="quiz-opt-letter">${'ABCDEF'[idx]}</span>${svgIcon('check', 'quiz-opt-ok')}${svgIcon('x', 'quiz-opt-bad')}</span><span class="quiz-opt-text"></span>`;
        btn.querySelector('.quiz-opt-text').textContent = opt;
        btn.addEventListener('click', () => handleAnswer(idx, btn));
        container.appendChild(btn);
    });
}

function quizHaptic(type) {
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred(type); } catch (e) { /* eski klient */ }
}

function handleAnswer(idx, btn) {
    if (quizState.answered) return;
    quizState.answered = true;

    const q = QUIZ_QUESTIONS[quizState.current];
    const correct = q.answer;
    const allBtns = document.querySelectorAll('.quiz-option-btn');
    const feedback = document.getElementById('quiz-feedback');

    allBtns.forEach(b => b.disabled = true);

    if (idx === correct) {
        btn.classList.add('correct');
        quizState.score += 10;
        quizHaptic('success');
        feedback.textContent = "To'g'ri!";
    } else {
        btn.classList.add('wrong');
        allBtns[correct].classList.add('correct');
        quizHaptic('error');
        feedback.textContent = `Noto'g'ri. To'g'ri javob: ${q.options[correct]}`;
    }
    document.getElementById('quiz-score-live').innerText = `${quizState.score} ball`;

    setTimeout(() => {
        quizState.current++;
        if (quizState.current < QUIZ_QUESTIONS.length) {
            renderQuizQuestion();
        } else {
            finishQuiz();
        }
    }, 1000);
}

function finishQuiz() {
    const score = quizState.score;
    const best = parseInt(SafeStorage.getItem('quiz_best') || '0');
    const attempts = parseInt(SafeStorage.getItem('quiz_attempts') || '0');
    if (score > best) SafeStorage.setItem('quiz_best', score);
    SafeStorage.setItem('quiz_attempts', attempts + 1);

    const max = QUIZ_QUESTIONS.length * 10;
    let tier = 'low', title = 'Ko\'proq o\'qing!', desc = 'Hali siz uchun o\'rganish vaqti!';
    if (score >= 80) { tier = 'good'; title = 'Barakallo!'; desc = 'Siz juda yaxshi bilasiz!'; }
    else if (score >= 50) { tier = 'ok'; title = 'Yaxshi natija!'; desc = 'Ozgina ko\'proq o\'qisangiz mukammal bo\'ladi!'; }

    const ring = document.getElementById('quiz-ring');
    ring.className = 'quiz-ring quiz-ring--' + tier;
    ring.setAttribute('aria-label', `${max} dan ${score} ball`);
    document.getElementById('quiz-ring-fill').setAttribute('stroke-dasharray', `${Math.round(score / max * 100)} 100`);
    document.getElementById('quiz-result-title').innerText = title;
    document.getElementById('quiz-final-score-num').innerText = score;
    document.getElementById('quiz-result-desc').innerText = desc;
    showQuizScreen('quiz-result-screen');
    updateQuizStats();
}

// ═══════════════════════════════════════════════════════════════════
// HISTORY (LocalStorage + Canvas Chart)
// ═══════════════════════════════════════════════════════════════════

function saveHistory(type, data) {
    const key = `history_${type}`;
    const arr = JSON.parse(SafeStorage.getItem(key) || '[]');
    const now = new Date();
    const dateStr = `${now.getDate()}.${now.getMonth() + 1}.${now.getFullYear()}`;
    arr.push({ date: dateStr, ...data });
    if (arr.length > 30) arr.shift(); // max 30 ta yozuv
    SafeStorage.setItem(key, JSON.stringify(arr));
}

let currentHistory = 'bmi';

function initHistory() {
    document.querySelectorAll('[data-history]').forEach(btn => {
        btn.addEventListener('click', () => switchHistoryTab(btn.getAttribute('data-history')));
    });
    ['bmi', 'water'].forEach(type => {
        document.getElementById(`btn-clear-${type}-history`).addEventListener('click', () => {
            SafeStorage.removeItem(`history_${type}`);
            renderHistoryLog();
        });
    });
    document.querySelectorAll('[data-go-calc]').forEach(btn => {
        btn.addEventListener('click', () => {
            showTab('tab-health');
            switchCalc(btn.getAttribute('data-go-calc'));
            const first = document.getElementById(CALC_FIELDS[currentCalc][0]);
            if (first) first.focus({ preventScroll: true });
        });
    });
    renderHistoryLog();
    // Grafik o'lchami faqat bo'lim ko'ringanda ma'lum — Tarix ochilganda qayta chiziladi
    window.addEventListener('resize', () => drawChart(currentHistory));
}

function switchHistoryTab(type) {
    currentHistory = type;
    document.querySelectorAll('[data-history]').forEach(b => {
        b.setAttribute('aria-selected', b.getAttribute('data-history') === type ? 'true' : 'false');
    });
    document.getElementById('history-bmi').classList.toggle('active', type === 'bmi');
    document.getElementById('history-water').classList.toggle('active', type === 'water');
    drawChart(type);
}

function renderHistoryLog() {
    renderBmiLog();
    renderWaterLog();
    drawChart('bmi');
    drawChart('water');
}

function readHistory(type) {
    try { return JSON.parse(SafeStorage.getItem(`history_${type}`) || '[]'); } catch (e) { return []; }
}

// Log qatori: sana chapda, qiymat o'ngda (tabular). Qiymatlar textContent orqali.
function historyRow(date, value, chip) {
    const row = document.createElement('div');
    row.className = 'list-row history-row';
    row.innerHTML = '<span class="h-date"></span><span class="h-right"><span class="h-val tabular"></span></span>';
    row.querySelector('.h-date').textContent = date;
    row.querySelector('.h-val').textContent = value;
    if (chip) {
        const c = document.createElement('span');
        c.className = 'chip ' + chip.cls;
        c.textContent = chip.text;
        row.querySelector('.h-right').appendChild(c);
    }
    return row;
}

function updateHistoryEmpty(type, count) {
    const empty = document.getElementById(`${type}-chart-empty`);
    const canvas = document.getElementById(`${type}-chart`);
    const log = document.getElementById(`${type}-history-log`);
    const clear = document.getElementById(`btn-clear-${type}-history`);
    empty.hidden = count >= 2;
    canvas.hidden = count < 2;
    // 0 ta — "Hali hisob-kitob yo'q" + kalkulyatorga o'tish; 1 ta — grafik uchun yana bitta natija kerak
    empty.querySelector('.empty-title').hidden = count !== 0;
    empty.querySelector('[data-go-calc]').hidden = count !== 0;
    empty.querySelector('.chart-empty-text').textContent = count === 1
        ? "Grafik ikkinchi natijadan keyin paydo bo'ladi"
        : (type === 'bmi' ? "BMI hisoblaganingizda bu yerda grafik paydo bo'ladi" : "Suv hisoblashlaringiz bu yerda grafik shaklida ko'rinadi");
    log.hidden = count === 0;
    clear.hidden = count === 0;
}

function renderBmiLog() {
    const arr = readHistory('bmi');
    const log = document.getElementById('bmi-history-log');
    log.innerHTML = '';
    updateHistoryEmpty('bmi', arr.length);
    arr.slice().reverse().forEach(entry => {
        const v = parseFloat(entry.bmi);
        const chip = v < 18.5 ? { text: 'Kam', cls: 'chip--warning' }
                   : v < 25 ? { text: 'Normal', cls: 'chip--teal' }
                   : { text: 'Yuqori', cls: 'chip--danger' };
        log.appendChild(historyRow(entry.date, `BMI ${entry.bmi}`, chip));
    });
}

function renderWaterLog() {
    const arr = readHistory('water');
    const log = document.getElementById('water-history-log');
    log.innerHTML = '';
    updateHistoryEmpty('water', arr.length);
    arr.slice().reverse().forEach(entry => {
        log.appendChild(historyRow(entry.date, `${entry.liters} L`, null));
    });
}

// Grafik: bitta rang (--primary), to'r chiziqlari --separator, nuqtalar yo'q (faqat oxirgi qiymat), HiDPI
function drawChart(type) {
    const canvas = document.getElementById(type === 'bmi' ? 'bmi-chart' : 'water-chart');
    if (!canvas) return;
    const arr = readHistory(type);
    const cssW = canvas.parentElement.clientWidth - 32;
    if (arr.length < 2 || cssW <= 0) return;

    const cs = getComputedStyle(document.body);
    const color = cs.getPropertyValue('--primary').trim() || '#0A84C6';
    const grid = cs.getPropertyValue('--line').trim() || 'rgba(15,27,45,0.08)';
    const muted = cs.getPropertyValue('--text-2').trim() || '#5E6B7E';
    const font = cs.getPropertyValue('--font').trim() || 'sans-serif';

    const cssH = 180;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const values = arr.map(e => parseFloat(type === 'bmi' ? e.bmi : e.liters));
    const labels = arr.map(e => e.date);
    let min = Math.min(...values), max = Math.max(...values);
    const span = (max - min) || Math.max(1, max * 0.1);
    min -= span * 0.15; max += span * 0.15;
    const pad = { top: 12, bottom: 26, left: 4, right: 40 };
    const w = cssW - pad.left - pad.right;
    const h = cssH - pad.top - pad.bottom;
    const toX = i => pad.left + (values.length === 1 ? w / 2 : i * w / (values.length - 1));
    const toY = v => pad.top + h - ((v - min) / (max - min)) * h;

    // To'r chiziqlari va o'ng tomonda qiymatlar
    ctx.font = `12px ${font}`;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    for (let k = 0; k <= 3; k++) {
        const v = min + (max - min) * k / 3;
        const y = toY(v);
        ctx.strokeStyle = grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.left, Math.round(y) + 0.5);
        ctx.lineTo(pad.left + w, Math.round(y) + 0.5);
        ctx.stroke();
        ctx.fillStyle = muted;
        ctx.fillText(v.toFixed(1), pad.left + w + 6, y);
    }

    // Chiziq
    ctx.beginPath();
    values.forEach((v, i) => { if (i === 0) ctx.moveTo(toX(i), toY(v)); else ctx.lineTo(toX(i), toY(v)); });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Faqat oxirgi nuqta
    const li = values.length - 1;
    ctx.beginPath();
    ctx.arc(toX(li), toY(values[li]), 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();

    // Sanalar: birinchi va oxirgi
    ctx.fillStyle = muted;
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left';
    ctx.fillText(labels[0], pad.left, cssH - 6);
    ctx.textAlign = 'right';
    ctx.fillText(labels[li], pad.left + w, cssH - 6);

    const unit = type === 'bmi' ? '' : ' L';
    canvas.setAttribute('aria-label', `${type === 'bmi' ? 'BMI' : 'Suv'} grafigi: ${values.length} ta natija, oxirgisi ${values[li]}${unit}`);
}

// ═══════════════════════════════════════════════════════════════════
// BODY MAP FEATURE
// ═══════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════
// BODY MAP FEATURE — Medical Scanner with Front & Back Views
// ═══════════════════════════════════════════════════════════════════

let bodyMapData = null;
let selectedBodyPartKey = null;
let currentBodyView = 'front';

// A'zo ma'lumotlari (body_map_data.json) va bottom sheet. Tana figurasi — bosh ekranda (Stage 2).
async function initBodyMap() {

    // Local fallback in case body_map_data.json fails to load
    const fallbackBodyParts = {
      head: { title: "🧠 Bosh", icon: "🧠", problems: ["Bosh og'rig'i", "Bosh aylanishi", "Migren", "Charchoq"], tip: "Dam olish, yetarli suyuqlik ichish va ekran vaqtini kamaytirish yordam berishi mumkin." },
      neck: { title: "🦴 Bo'yin", icon: "🦴", problems: ["Bo'yin og'rig'i", "Mushak zo'riqishi", "Qotish"], tip: "Yengil mashqlar qilish va issiq dush qabul qilish tavsiya etiladi." },
      chest: { title: "🫁 Ko'krak", icon: "🫁", problems: ["Mushak zo'riqishi", "Ko'krak sohasidagi noqulaylik"], tip: "Chuqur nafas oling va tinchlanishga harakat qiling. Og'riq davom etsa, darhol shifokorga murojaat qiling." },
      abdomen: { title: "🫃 Qorin", icon: "🫃", problems: ["Qorin og'rig'i", "Dam bo'lish", "Hazm noqulayligi"], tip: "Yengil ovqatlaning va gazli ichimliklardan saqlaning." },
      hip: { title: "🦴 Chanoq / Dumba", icon: "🦴", problems: ["Og'riq", "Asab siqilishi", "Mushak zo'riqishi"], tip: "Uzoq o'tirmaslikka va vaqti-vaqti bilan yurishga harakat qiling." },
      thigh: { title: "🦵 Son", icon: "🦵", problems: ["Mushak og'rig'i", "Zo'riqish"], tip: "Yengil massaj va oyoqni balandroq qilib yotish foydali." },
      knee: { title: "🦿 Tizza", icon: "🦿", problems: ["Tizza og'rig'i", "Zo'riqish"], tip: "Tizzaga og'irlik tushirmang va elastik bint bilan o'rab oling." },
      shin: { title: "🦴 Boldir", icon: "🦴", problems: ["Mushak og'rig'i", "Zo'riqish", "Charchoq"], tip: "Issiq vanna yoki yengil massaj qiling." },
      foot: { title: "🦶 Panja / Tovon", icon: "🦶", problems: ["Panja og'rig'i", "Zo'riqish", "Charchoq"], tip: "Poyabzalni yechib, oyoqlarga dam bering." },
      shoulder: { title: "💪 Yelka", icon: "💪", problems: ["Yelka og'rig'i", "Qotish", "Mushak zo'riqishi"], tip: "Yelkani issiq tuting va og'ir narsa ko'tarmang." },
      arm: { title: "🤲 Qo'l", icon: "🤲", problems: ["Qo'l og'rig'i", "Charchoq", "Uvishish"], tip: "Qo'lni bo'sh qo'yib, bilak mashqlarini bajaring." },
      hand: { title: "🖐 Kaft", icon: "🖐", problems: ["Barmoqlar og'rig'i", "Uvishish", "Siqilish"], tip: "Barmoqlarni qisib-yozib mashq qiling." },
      back: { title: "🔙 Bel va Orqa", icon: "🔙", problems: ["Bel og'rig'i", "Qotish", "Zo'riqish"], tip: "Qattiqroq joyda yotish va og'irlik ko'tarmaslik tavsiya etiladi." }
    };

    try {
        const response = await fetch('body_map_data.json?v=' + Date.now());
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        bodyMapData = await response.json();
        console.log("Loaded body map data successfully:", bodyMapData);
    } catch (e) {
        console.warn("Failed to fetch body_map_data.json. Using local fallback.", e);
        bodyMapData = fallbackBodyParts;
    }

    renderBodyFigure();

    const closeBtn = document.getElementById('modal-close');
    if (closeBtn) closeBtn.addEventListener('click', closeBodySheet);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && isBodySheetOpen()) closeBodySheet();
    });
    // Sahifadagi zaxira tugma (Telegram tashqarisida) — MainButton bilan bir xil yo'l (MainButtonCtl.set ulaydi)
}

// ── Tana figurasi (bosh ekran, G 2.4). Yorliq -> body_map_data.json hududlari (ma'lumot to'qilmaydi) ──
const BODY_HOTSPOTS = {
    front: [
        { slot: 1, id: 'bosh', label: 'Bosh', keys: ['head', 'neck'] },
        { slot: 2, id: 'qol', label: "Qo'l", keys: ['arm', 'shoulder', 'hand'] },
        { slot: 3, id: 'kokrak', label: "Ko'krak", keys: ['chest'] },
        { slot: 4, id: 'qorin', label: 'Qorin', keys: ['abdomen'] },
        { slot: 5, id: 'oyoq', label: 'Oyoq', keys: ['foot', 'thigh', 'knee', 'shin'] }
    ],
    back: [
        { slot: 1, id: 'bosh', label: 'Bosh', keys: ['head', 'neck'] },
        { slot: 2, id: 'qol', label: "Qo'l", keys: ['arm', 'shoulder', 'hand'] },
        { slot: 3, id: 'orqa', label: 'Orqa', keys: ['back'] },
        { slot: 4, id: 'bel', label: 'Bel', keys: ['back', 'hip'] },
        { slot: 5, id: 'oyoq', label: 'Oyoq', keys: ['foot', 'thigh', 'knee', 'shin'] }
    ]
};
let selectedHotspotId = null;
let bodySheetHotspot = null;           // sheet yorliq/strelkadan ochilgan bo'lsa — hudud id (AI konteksti: "kokrak")
let selectedPartKeys = new Set();      // ajratilgan maneken qismlari (data-part)
const FIG_MAN = { x: 87.89, y: 2, s: 0.6222 };   // maneken -> figura koordinatalari (index.html dagi transform bilan bir xil)
const FIG_LABEL_Y = { 1: 35, 2: 146, 3: 107, 4: 155, 5: 271 };   // yorliq markazi (G 2.4)
const FIG_LABEL_X = { 1: 76, 2: 76, 3: 274, 4: 274, 5: 274 };    // strelka boshlanishi (yorliq cheti)

function partBaseKey(partKey) {
    return String(partKey || '').replace('left_', '').replace('right_', '');
}

// Joriy ko'rinishdagi maneken qismlari
function viewParts() {
    return [...document.querySelectorAll(`#body-figure .fig-man--${currentBodyView} .body-part`)];
}

// Qism chegarasi figura koordinatalarida (faqat ko'rinadigan shakl, keng bosish zonasi emas)
function partBox(part) {
    let box = null;
    part.querySelectorAll('.part-shape').forEach(shape => {
        const b = shape.getBBox();
        if (!b.width && !b.height) return;
        box = box ? { x1: Math.min(box.x1, b.x), y1: Math.min(box.y1, b.y), x2: Math.max(box.x2, b.x + b.width), y2: Math.max(box.y2, b.y + b.height) }
                  : { x1: b.x, y1: b.y, x2: b.x + b.width, y2: b.y + b.height };
    });
    if (!box) return null;
    const t = (v, o) => o + v * FIG_MAN.s;
    return { x1: t(box.x1, FIG_MAN.x), x2: t(box.x2, FIG_MAN.x), y1: t(box.y1, FIG_MAN.y), y2: t(box.y2, FIG_MAN.y) };
}

// Strelka uchi va nuqta — hududning maneken qismiga (yorliq balandligida, iloji bo'lsa gorizontal)
function placeFigureLeaders() {
    const wrap = document.getElementById('body-figure');
    if (!wrap || !wrap.offsetParent) return;
    const parts = viewParts();
    BODY_HOTSPOTS[currentBodyView].forEach(spot => {
        const y = FIG_LABEL_Y[spot.slot];
        const left = FIG_LABEL_X[spot.slot] < 175;
        const boxes = parts.filter(p => spot.keys.includes(partBaseKey(p.getAttribute('data-part'))))
            .map(partBox).filter(Boolean);
        if (!boxes.length) return;
        let pool = boxes.filter(b => b.y1 <= y && y <= b.y2);
        if (!pool.length) {
            const dist = b => Math.min(Math.abs(b.y1 - y), Math.abs(b.y2 - y));
            const best = Math.min(...boxes.map(dist));
            pool = boxes.filter(b => dist(b) === best);
        }
        const cx = b => (b.x1 + b.x2) / 2;
        const box = pool.reduce((p, b) => (left ? cx(b) < cx(p) : cx(b) > cx(p)) ? b : p);
        const tx = Math.round(cx(box) * 10) / 10;
        const ty = Math.round(Math.min(Math.max(y, box.y1 + 4), box.y2 - 4) * 10) / 10;
        wrap.querySelectorAll(`.fig-lead line[data-slot="${spot.slot}"]`).forEach(l => {
            l.setAttribute('x2', tx);
            l.setAttribute('y2', ty);
        });
        wrap.querySelectorAll(`.fig-halo circle[data-slot="${spot.slot}"], .fig-dot circle[data-slot="${spot.slot}"]`).forEach(c => {
            c.setAttribute('cx', tx);
            c.setAttribute('cy', ty);
        });
    });
}

// Maneken qismi bosilganda — aynan shu qism (masalan "Chap tizza") ma'lumoti; tegishli yorliq ham ajratiladi
function openBodyPartFromFigure(partKey) {
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
    const base = partBaseKey(partKey);
    const spot = BODY_HOTSPOTS[currentBodyView].find(s => s.keys.includes(base));
    selectedHotspotId = spot ? spot.id : null;
    selectedPartKeys = new Set([partKey]);
    openBodyMapModal(partKey);
}

function hotspotKeys(spot) {
    return spot.keys.filter(k => bodyMapData && bodyMapData[k]);
}

function renderBodyFigure() {
    const wrap = document.getElementById('body-figure');
    if (!wrap) return;
    wrap.setAttribute('data-view', currentBodyView);
    BODY_HOTSPOTS[currentBodyView].forEach(spot => {
        const btn = wrap.querySelector(`.fig-label[data-slot="${spot.slot}"]`);
        const off = bodyMapData !== null && hotspotKeys(spot).length === 0;     // ma'lumoti yo'q — yashiriladi
        btn.id = spot.id;
        btn.textContent = spot.label;
        btn.setAttribute('aria-label', `${spot.label} — tana qismi`);
        btn.hidden = off;
        wrap.querySelectorAll(`[data-slot="${spot.slot}"]:not(.fig-label)`).forEach(el => el.classList.toggle('is-off', off));
    });
    placeFigureLeaders();
    markSelectedBodyPart();
}

function openHotspot(spot) {
    const keys = hotspotKeys(spot);
    if (!keys.length) return;
    if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
    // Bir nechta hududning holatlari bitta ro'yxatda (takrorlanmaydi); ma'lumot matni o'zgarmaydi
    const seen = new Set();
    const diseases = [];
    keys.forEach(k => (bodyMapData[k].diseases || []).forEach(d => {
        if (!seen.has(d.name)) { seen.add(d.name); diseases.push(d); }
    }));
    selectedHotspotId = spot.id;
    selectedPartKeys = new Set(viewParts().map(p => p.getAttribute('data-part'))
        .filter(k => spot.keys.includes(partBaseKey(k))));          // hududning maneken qismlari ham ajratiladi
    selectedBodyPartKey = keys[0];          // "Botda davom etish" zaxirasi (tg.sendData / ?start=ai_consult_<kalit>) uchun
    bodySheetHotspot = spot.id;
    _openFullModal(keys[0], { name: spot.label, diseases: diseases });
}

// Tor ekranlarda (<350px) butun blok bir tekis kichrayadi
function fitBodyFigure() {
    const outer = document.getElementById('body-figure-outer');
    const wrap = document.getElementById('body-figure');
    if (!outer || !wrap || !outer.clientWidth) return;
    const scale = Math.min(1, outer.clientWidth / 350);
    wrap.style.transform = scale < 1 ? `scale(${scale})` : '';
    outer.style.height = `${Math.round(340 * scale)}px`;
    placeFigureLeaders();
}

function initBodyFigure() {
    const wrap = document.getElementById('body-figure');
    if (!wrap) return;
    // Yorliq, strelka (keng ko'rinmas chiziq), halqa va nuqta — hudud sheet'i
    wrap.querySelectorAll('.fig-label, .fig-lead line, .fig-halo circle, .fig-dot circle').forEach(el => {
        el.addEventListener('click', () => {
            const spot = BODY_HOTSPOTS[currentBodyView].find(s => String(s.slot) === el.getAttribute('data-slot'));
            if (spot) openHotspot(spot);
        });
    });
    // Tana qismining o'zi — shu qism sheet'i
    wrap.querySelectorAll('.fig-man .body-part').forEach(part => {
        part.addEventListener('click', () => openBodyPartFromFigure(part.getAttribute('data-part')));
    });
    document.querySelectorAll('.fig-views [data-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.getAttribute('data-view');
            if (view === currentBodyView) return;
            currentBodyView = view;
            document.querySelectorAll('.fig-views [data-view]').forEach(b =>
                b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'));
            hideBodySheet();
            renderBodyFigure();
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        });
    });
    renderBodyFigure();
    fitBodyFigure();
    window.addEventListener('resize', fitBodyFigure);
}

function isBodySheetOpen() {
    const sheet = document.getElementById('body-map-modal');
    return !!sheet && !sheet.hidden;
}

// UI ni yashiradi (navigatsiya stekiga tegmaydi)
function hideBodySheet() {
    const sheet = document.getElementById('body-map-modal');
    if (!sheet || sheet.hidden) return;
    sheet.hidden = true;
    document.body.classList.remove('sheet-open');
    if (MainButtonCtl.owner === 'body') MainButtonCtl.clear();
    selectedBodyPartKey = null;
    selectedHotspotId = null;
    bodySheetHotspot = null;
    selectedPartKeys = new Set();
    markSelectedBodyPart();
}

function closeBodySheet() {
    if (!isBodySheetOpen()) return;
    hideBodySheet();
    AppNavigation.pop();
}

// Sheet'dagi "AI'dan so'rash": AI tabi ochiladi, kontekst chipi qo'yiladi, yozish maydoniga fokus. Xabar YUBORILMAYDI.
function openAiChatFromBodySheet() {
    const partKey = selectedBodyPartKey;
    const key = bodySheetHotspot || partBaseKey(partKey);          // server ruxsat etgan kalit: hudud id yoki a'zo kaliti
    const titleEl = document.getElementById('modal-title');
    const label = (titleEl && titleEl.textContent.trim()) || bodyConsultTitle(partKey);
    closeBodySheet();
    openAiChat(key ? { type: 'body_part', key: key, label: label, partKey: partKey } : null);
}

// Eski "AI konsultant" sarlavhasi (body_map_data.json dagi nom, emoji'siz) — botga yuboriladigan title
function bodyConsultTitle(partKey) {
    const partData = bodyMapData && partKey ? bodyMapData[partBaseKey(partKey)] : null;
    return partData ? partData.title.replace(/^[^\w\s\u0400-\u04FF]+/, '').trim() : (partKey || 'bosh');
}

// ESKI yo'l (o'zgarmagan): tg.sendData({action:"ai_consult"}), botga havola va mini app yopiladi.
// Endi faqat zaxira: AI suhbat API'si ishlamasa "Botda davom etish" tugmasi shuni chaqiradi.
function sendAiConsultToBot(title, startKey) {
    if (tg && tg.sendData) {
        try { tg.sendData(JSON.stringify({ action: "ai_consult", title: title })); } catch (e) {}
    }
    if (tg) {
        const url = startKey ? `https://t.me/${BOT_USERNAME}?start=ai_consult_${startKey}` : `https://t.me/${BOT_USERNAME}`;
        tg.openTelegramLink(url);
        tg.close();
    } else {
        notify(`AI konsultant: ${title}\n\nTelegram ilovasi orqali kiring!`);
    }
}

function markSelectedBodyPart() {
    document.querySelectorAll('#body-figure .fig-label').forEach(btn => {
        const on = !!selectedHotspotId && btn.id === selectedHotspotId;
        btn.classList.toggle('selected', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    // Faqat joriy ko'rinish (old/orqa manekenlarida bir xil data-part bor)
    document.querySelectorAll('#body-figure .fig-man .body-part').forEach(part => {
        const inView = !!part.closest(`.fig-man--${currentBodyView}`);
        part.classList.toggle('selected', inView && selectedPartKeys.has(part.getAttribute('data-part')));
    });
}


function openBodyMapModal(partKey) {
    try {
        selectedBodyPartKey = partKey;
        bodySheetHotspot = null;
        if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

        console.log("MODAL OCHISHGA URINISH:", partKey);

        const mapKey = partKey.replace('left_', '').replace('right_', '');

        let data = null;
        if (bodyMapData) {
            if (bodyMapData[partKey]) {
                data = JSON.parse(JSON.stringify(bodyMapData[partKey]));
            } else if (bodyMapData[mapKey]) {
                data = JSON.parse(JSON.stringify(bodyMapData[mapKey]));
                // Set name field if not present
                if (!data.name) {
                    // Remove emoji at the beginning for proper title formatting
                    const cleanTitle = (data.title || mapKey).replace(/^[^\w\s\u0400-\u04FF]+/, '').trim();
                    data.name = cleanTitle;
                }
                // Dynamically add Left/Right prefix to name if needed
                if (partKey.startsWith('left_')) {
                    data.name = "Chap " + data.name.toLowerCase();
                    data.name = data.name.charAt(0).toUpperCase() + data.name.slice(1);
                } else if (partKey.startsWith('right_')) {
                    data.name = "O'ng " + data.name.toLowerCase();
                    data.name = data.name.charAt(0).toUpperCase() + data.name.slice(1);
                }
            }
        }

        if (data) {
            // Ensure name is cleaned of any starting emojis if present
            if (!data.name) {
                data.name = (data.title || partKey).replace(/^[^\w\s\u0400-\u04FF]+/, '').trim();
            }
            _openFullModal(partKey, data);
        } else {
            // Data not loaded yet or missing
            console.error("DATA MISSING FOR:", partKey);
            const statusMsg = bodyMapData ? "topilmadi" : "yuklanmagan";
            console.warn(`A'zo ma'lumoti topilmadi (${partKey}). bodyMapData: ${statusMsg}`);
            notify("Ma'lumotlar yuklanmoqda yoki topilmadi...");
        }
    } catch (err) {
        reportError('openBodyMapModal', err);
    }
}

function _openFullModal(partKey, data) {
    try {
        const sheet = document.getElementById('body-map-modal');
        const titleEl = document.getElementById('modal-title');
        const listEl = document.getElementById('modal-diseases-list');
        if (!sheet) {
            reportError('_openFullModal', new Error('#body-map-modal HTML ichida topilmadi'));
            return;
        }

        if (titleEl) titleEl.textContent = data.name || partKey;

        if (listEl) {
            listEl.innerHTML = '';
            if (data.diseases && data.diseases.length > 0) {
                // Holatlar: yig'iladigan ro'yxat (bir vaqtda bittasi ochiq)
                data.diseases.forEach(d => {
                    const item = document.createElement('details');
                    item.className = 'sheet-item' + (d.urgent ? ' is-urgent' : '');
                    item.innerHTML = `<summary><span class="sheet-item-name"></span>${d.urgent ? `<span class="chip chip--danger">${svgIcon('alert-triangle')}<span>Tezkor</span></span>` : ''}${svgIcon('chevron-down', 'collapse-chevron')}</summary>
                        <p class="sheet-item-desc"></p>${d.tip ? `<p class="sheet-tip">${svgIcon('info')}<span></span></p>` : ''}`;
                    item.querySelector('.sheet-item-name').textContent = d.name;
                    item.querySelector('.sheet-item-desc').textContent = d.desc || '';
                    if (d.tip) item.querySelector('.sheet-tip span').textContent = d.tip;
                    item.addEventListener('toggle', () => {
                        if (!item.open) return;
                        listEl.querySelectorAll('details[open]').forEach(o => { if (o !== item) o.open = false; });
                        if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
                    });
                    listEl.appendChild(item);
                });
            } else if (data.problems && data.problems.length > 0) {
                const ul = document.createElement('ul');
                ul.className = 'sheet-problems';
                data.problems.forEach(p => {
                    const li = document.createElement('li');
                    li.textContent = p;
                    ul.appendChild(li);
                });
                listEl.appendChild(ul);
            }
            if (data.tip && (!data.diseases || data.diseases.length === 0)) {
                const tip = document.createElement('p');
                tip.className = 'sheet-tip';
                tip.innerHTML = `${svgIcon('info')}<span></span>`;
                tip.querySelector('span').textContent = data.tip;
                listEl.appendChild(tip);
            }
        }

        const wasOpen = !sheet.hidden;
        sheet.hidden = false;
        sheet.scrollTop = 0;
        document.body.classList.add('sheet-open');
        markSelectedBodyPart();
        MainButtonCtl.set({ text: "AI'dan so'rash", owner: 'body', onClick: openAiChatFromBodySheet },
                          document.getElementById('ai-consult-btn'));
        // Boshqa a'zo bosilganda sheet yangilanadi — navigatsiya stekiga qayta qo'shilmaydi
        if (!wasOpen) AppNavigation.push({ type: 'body-map-modal', close: closeBodySheet });
    } catch (err) {
        reportError('_openFullModal', err);
    }
}

// Auto init on page load
document.addEventListener('DOMContentLoaded', () => {
    try {
        initBodyMap();
        initWheelOfFortune();
    } catch (e) {
        reportError('DOM Init 2', e);
    }
});

// ═══════════════════════════════════════════════════════════════════
// OMAD BARABANI (Wheel of Fortune) — Luxury Casino-Grade Engine
// ═══════════════════════════════════════════════════════════════════
let isSpinning = false;
let hasSpunThisSession = false;

// Kutish holati: katta tabular taymer (id o'zgarmagan — taymer mantig'i shu elementga yozadi)
function wheelWaitingMarkup() {
    return `<div class="result-icon">${svgIcon('clock')}</div><p class="result-title">Urinish tugadi</p>` +
        `<p class="result-desc">Keyingi bepul aylantirishgacha qolgan vaqt:</p>` +
        `<div class="wheel-countdown tabular" id="wheel-countdown-timer" role="timer">23:59:59</div>`;
}

// Natija kartasidagi emoji o'rniga SVG ikonka
const WHEEL_CARD_ICONS = {
    '🏆': 'crown', '⏳': 'loader', '✅': 'circle-check', '⚠️': 'alert-triangle', 'ℹ️': 'info', '🎉': 'sparkles',
    '💡': 'lightbulb', '🤖': 'bot', '⭐': 'star'
};

function initWheelOfFortune() {
    const openBtn = document.getElementById('btn-open-wheel');
    const closeBtn = document.getElementById('wheel-modal-close');
    const modal = document.getElementById('wheel-modal');
    const spinBtn = document.getElementById('btn-spin-wheel');
    const resultMsg = document.getElementById('wheel-result-msg');
    const canvas = document.getElementById('wheel-canvas');

    if (!openBtn || !closeBtn || !modal || !spinBtn || !canvas) return;

    const urlParams = new URLSearchParams(window.location.search);
    const lastSpin = urlParams.get('last_spin');
    // prize parametri server tomonidan yuborilishi shart (default '1' noto'g'ri)
    const prizeParam = urlParams.get('prize');
    let serverPrize = prizeParam !== null ? parseInt(prizeParam) : null;
    const centerText = spinBtn.querySelector('.wheel-center-text');

    let remainingTimeMs = 0;
    let wheelApiActive = false;   // /api/state muvaffaqiyatli bo'lsa true (server — haqiqat manbai)

    // Get the most recent spin time from either URL parameter or localStorage
    let effectiveLastSpin = lastSpin;
    const localLastSpin = SafeStorage.getItem('last_spin_time');
    if (localLastSpin) {
        if (!effectiveLastSpin) {
            effectiveLastSpin = localLastSpin;
        } else {
            // Compare which one is more recent
            const tParam = new Date(effectiveLastSpin).getTime();
            const tLocal = new Date(localLastSpin).getTime();
            if (!isNaN(tLocal) && (isNaN(tParam) || tLocal > tParam)) {
                effectiveLastSpin = localLastSpin;
            }
        }
    }

    if (effectiveLastSpin) {
        if (effectiveLastSpin.includes('T') || effectiveLastSpin.includes(':')) {
            const lastSpinTime = new Date(effectiveLastSpin).getTime();
            if (!isNaN(lastSpinTime)) {
                const cooldownMs = 24 * 60 * 60 * 1000;
                const elapsedMs = Date.now() - lastSpinTime;
                remainingTimeMs = cooldownMs - elapsedMs;
            }
        } else {
            // Fallback for YYYY-MM-DD
            const nowUz = new Date(Date.now() + (5 * 60 * 60 * 1000) + (new Date().getTimezoneOffset() * 60 * 1000));
            const todayStrUz = nowUz.toISOString().split('T')[0];
            if (effectiveLastSpin === todayStrUz) {
                const tomorrowMidnight = new Date(effectiveLastSpin + 'T23:59:59+05:00').getTime();
                remainingTimeMs = tomorrowMidnight - Date.now();
            }
        }
    }

    let countdownInterval = null;
    function startCountdown(durationMs) {
        if (countdownInterval) clearInterval(countdownInterval);
        const endTime = Date.now() + durationMs;

        function updateTimer() {
            const timeLeft = endTime - Date.now();
            if (timeLeft <= 0) {
                clearInterval(countdownInterval);
                remainingTimeMs = 0;
                spinBtn.disabled = false;
                if (centerText) centerText.textContent = "AYLANTIR";
                resultMsg.classList.add('hidden');
                return;
            }

            const hours = Math.floor(timeLeft / (3600 * 1000));
            const minutes = Math.floor((timeLeft % (3600 * 1000)) / (60 * 1000));
            const seconds = Math.floor((timeLeft % (60 * 1000)) / 1000);

            const timerEl = document.getElementById('wheel-countdown-timer');
            if (timerEl) {
                timerEl.textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            }
        }

        updateTimer();
        countdownInterval = setInterval(updateTimer, 1000);
    }

    if (remainingTimeMs > 0) {
        spinBtn.disabled = true;
        if (centerText) centerText.textContent = "KUTISH";
        resultMsg.innerHTML = wheelWaitingMarkup();
        resultMsg.classList.remove('hidden');
        startCountdown(remainingTimeMs);
    }

    // Query Telegram CloudStorage for cross-device & cookie-independent state
    if (tg && tg.CloudStorage) {
        tg.CloudStorage.getItem('last_spin_time', (err, value) => {
            if (!err && value && !wheelApiActive) {
                const lastSpinTime = new Date(value).getTime();
                if (!isNaN(lastSpinTime)) {
                    const cooldownMs = 24 * 60 * 60 * 1000;
                    const elapsedMs = Date.now() - lastSpinTime;
                    const remaining = cooldownMs - elapsedMs;
                    if (remaining > remainingTimeMs) {
                        remainingTimeMs = remaining;
                        spinBtn.disabled = true;
                        if (centerText) centerText.textContent = "KUTISH";
                        resultMsg.innerHTML = wheelWaitingMarkup();
                        resultMsg.classList.remove('hidden');
                        startCountdown(remaining);
                    }
                }
            }
        });
    }

    const WHEEL_WAITING_HTML = wheelWaitingMarkup();

    function showWheelWaiting(ms) {
        spinBtn.disabled = true;
        if (centerText) centerText.textContent = "KUTISH";
        resultMsg.innerHTML = WHEEL_WAITING_HTML;
        resultMsg.classList.remove('hidden');
        startCountdown(ms);
    }

    function showWheelReady() {
        if (countdownInterval) clearInterval(countdownInterval);
        spinBtn.disabled = false;
        if (centerText) centerText.textContent = "AYLANTIR";
        resultMsg.classList.add('hidden');
    }

    // Server javob bermasa: URL-parametr / localStorage asosidagi avvalgi holat
    function applyLocalWheelState() {
        if (remainingTimeMs > 0 || hasSpunThisSession) {
            showWheelWaiting(remainingTimeMs > 0 ? remainingTimeMs : 24 * 60 * 60 * 1000);
        } else {
            showWheelReady();
        }
    }

    let wheelSyncSeq = 0;
    function syncWheelWithServer() {
        if (!canUseApi() || isSpinning) return;
        const seq = ++wheelSyncSeq;
        if (!spinBtn.disabled) {                 // javob kelguncha tasodifan aylantirib yuborilmasin
            spinBtn.disabled = true;
            if (centerText) centerText.textContent = "...";
        }
        // Umumiy kesh: natija 60 soniyadan eski bo'lsagina qayta so'raladi
        getAppState(60000).then((s) => {
            if (seq !== wheelSyncSeq || isSpinning) return;
            if (!s) {
                wheelApiActive = false;
                applyLocalWheelState();
                return;
            }
            wheelApiActive = true;
            setGlobalScore(s.score);
            serverPrize = (typeof s.prize === 'number') ? s.prize : null;
            const elapsedMs = Date.now() - AppState.ts;     // keshdagi cooldown vaqt o'tgan sari kamayadi
            remainingTimeMs = Math.max(0, (Number(s.cooldown_seconds) || 0) * 1000 - elapsedMs);
            applyLocalWheelState();
        });
    }

    function checkWheelStateAndOpen() {
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        drawWheel();
        if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');

        if (remainingTimeMs > 0 || hasSpunThisSession) {
            spinBtn.disabled = true;
            if (centerText) centerText.textContent = "KUTISH";
            resultMsg.innerHTML = wheelWaitingMarkup();
            resultMsg.classList.remove('hidden');
            const timeToUse = remainingTimeMs > 0 ? remainingTimeMs : 24 * 60 * 60 * 1000;
            startCountdown(timeToUse);
        }
        syncWheelWithServer();
    }

    // Modal open
    openBtn.onclick = () => {
        checkWheelStateAndOpen();
    };

    // Also open when clicking promo card
    const promoCard = document.getElementById('wheel-promo-card');
    if (promoCard) {
        promoCard.onclick = (e) => {
            if (e.target.closest('.wheel-promo-btn') || e.target === openBtn) return;
            checkWheelStateAndOpen();
        };
    }

    // Aylanish tugagan, lekin "Mukofotni olish" bosilmagan sovrin. Oyna yopilganda (X / BackButton) shu sovrin
    // serverdan BIR MARTA olinadi. Ikkinchi marta yopish yoki qayta ochish hech narsa qilmaydi (qiymat null).
    // Server ham idempotent: claim faqat pending_spin_prize bo'lsa va 24 soatlik limit ichida bo'lmasa beriladi.
    let unclaimedPrize = null;

    function claimUnclaimedOnClose() {
        if (unclaimedPrize === null) return;
        const p = unclaimedPrize;
        unclaimedPrize = null;
        if (wheelApiActive) {
            claimSpinViaApi(p, { toast: true });     // fonda; natija toast bilan
        } else {
            openSpinDeepLink(p);                     // ZAXIRA: bot orqali (API yo'q)
        }
    }

    // Wheel modal open — push navigation
    const _wheelOpen = openBtn.onclick;
    function pushWheelNav() {
        AppNavigation.push({
            type: 'wheel-modal',
            close: function () {
                if (!isSpinning) {
                    modal.classList.add('hidden');
                    modal.style.display = 'none';
                    AppNavigation.pop();
                    claimUnclaimedOnClose();
                }
            }
        });
    }

    const _origOpenBtn = openBtn.onclick;
    openBtn.onclick = () => {
        checkWheelStateAndOpen();
        pushWheelNav();
    };

    const promoCard2 = document.getElementById('wheel-promo-card');
    if (promoCard2) {
        const _origPromo = promoCard2.onclick;
        promoCard2.onclick = (e) => {
            if (e.target.closest('.wheel-promo-btn') || e.target === openBtn) return;
            checkWheelStateAndOpen();
            pushWheelNav();
        };
    }

    closeBtn.onclick = () => {
        if (!isSpinning) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
            AppNavigation.pop();
            claimUnclaimedOnClose();
        }
    };

    // Segmentlar — server bilan bir xil sovrin KODLARI (database.SPIN_PRIZES): 1, 2, 3, 5 ball; -2 kun maslahati;
    // -1 +1 bepul AI savol; -3 1 kunlik Premium Pro; 0 = SUPER. Bo'lak sovrin KODI bo'yicha topiladi
    // (ball bo'yicha emas: manfiy kodlar bor). Ikonkalar emoji emas, sprite'dan (icon) chiziladi.
    const segments = [
        { code: 1, text: "+1", label: "ball", tone: 'primary' },
        { code: 2, text: "+2", label: "ball", tone: 'teal' },
        { code: 3, text: "+3", label: "ball", tone: 'neutral' },
        { code: 5, text: "+5", label: "ball", tone: 'primary2' },
        { code: -2, icon: 'lightbulb', label: "Maslahat", tone: 'violet' },
        { code: -1, icon: 'bot', label: "AI savol", tone: 'mint' },
        { code: -3, icon: 'star', label: "1 kun Pro", tone: 'indigo' },
        { code: 0, text: "SUPER", label: "priz", tone: 'warning' }
    ];

    // Sovrin kodi -> turi (server: database.spin_prize_type). 10 — eski barabandan qolgan ball sovrini.
    function prizeTypeOfCode(code) {
        if (code === 0) return 'super';
        if (code === -1) return 'ai';
        if (code === -2) return 'tip';
        if (code === -3) return 'pro_day';
        return 'points';
    }

    // Server javobidagi tur; eski server (prize_type yo'q) bo'lsa is_super bo'yicha
    function claimedPrizeType(r) {
        if (['points', 'tip', 'ai', 'pro_day', 'super'].indexOf(r.prize_type) !== -1) return r.prize_type;
        return r.is_super ? 'super' : 'points';
    }

    // Ranglar mavzuga qarab (matn kontrasti >= 4.5:1)
    function segmentColors(tone) {
        const dark = document.body.classList.contains('dark-mode');
        const map = dark ? {
            primary: ['#1F6FA3', '#FFFFFF'], teal: ['#0F7D75', '#FFFFFF'], neutral: ['#2A3441', '#E8EEF5'],
            primary2: ['#3FA9E8', '#06121C'], violet: ['#7C4DBA', '#FFFFFF'], mint: ['#3BB38B', '#04201A'],
            indigo: ['#5B54D6', '#FFFFFF'], warning: ['#F5A524', '#1A1200']
        } : {
            primary: ['#0872AB', '#FFFFFF'], teal: ['#0B746D', '#FFFFFF'], neutral: ['#E9EEF4', '#0F1B2D'],
            primary2: ['#2B8FCB', '#06121C'], violet: ['#6B3FA0', '#FFFFFF'], mint: ['#BFEBDD', '#06281F'],
            indigo: ['#4338CA', '#FFFFFF'], warning: ['#F5A524', '#1A1200']
        };
        return map[tone];
    }

    // Sprite ikonkasi (<symbol id="i-NAME">, faqat <path>) -> Path2D ro'yxati
    const wheelIconCache = {};
    function wheelIconPaths(name) {
        if (!wheelIconCache[name]) {
            const sym = document.getElementById('i-' + name);
            wheelIconCache[name] = sym
                ? Array.from(sym.querySelectorAll('path')).map((p) => new Path2D(p.getAttribute('d')))
                : [];
        }
        return wheelIconCache[name];
    }

    // 24x24 stroke-ikonkani canvasga chizadi (markaz cx, cy; o'lcham size px). Sektor bilan birga burilgan
    // koordinata tizimida ikonkaning "yuqorisi" g'ildirak chetiga qaraydi (+90 daraja), shunda lampa/yulduz tanish
    // ko'rinishda bo'ladi. Ikonka topilmasa false.
    function drawWheelIcon(ctx, name, cx, cy, size, color) {
        const paths = wheelIconPaths(name);
        if (!paths.length) return false;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(Math.PI / 2);
        ctx.translate(-size / 2, -size / 2);
        ctx.scale(size / 24, size / 24);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        paths.forEach((p) => ctx.stroke(p));
        ctx.restore();
        return true;
    }

    // Matn maxWidth ga sig'maguncha shrift kichraytiriladi (8 bo'lakda joy tor)
    function fitFontPx(ctx, text, weight, maxPx, maxWidth, family) {
        let px = maxPx;
        ctx.font = `${weight} ${px}px ${family}`;
        while (px > 14 && ctx.measureText(text).width > maxWidth) {
            px -= 2;
            ctx.font = `${weight} ${px}px ${family}`;
        }
        return px;
    }

    function drawWheel() {
        const ctx = canvas.getContext('2d');
        const size = canvas.width;
        const r = size / 2;
        const arc = (Math.PI * 2) / segments.length;
        const font = getComputedStyle(document.body).getPropertyValue('--font').trim() || 'sans-serif';

        ctx.clearRect(0, 0, size, size);
        for (let i = 0; i < segments.length; i++) {
            const startAngle = i * arc;
            const seg = segments[i];
            const [bg, fg] = segmentColors(seg.tone);

            ctx.beginPath();
            ctx.moveTo(r, r);
            ctx.arc(r, r, r - 4, startAngle, startAngle + arc);
            ctx.closePath();
            ctx.fillStyle = bg;
            ctx.fill();
            // Ingichka oq ajratgich
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 4;
            ctx.stroke();

            ctx.save();
            ctx.translate(r, r);
            ctx.rotate(startAngle + arc / 2);
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = fg;
            const cx = r * 0.64;
            let drawn = false;
            if (seg.icon) drawn = drawWheelIcon(ctx, seg.icon, cx, -12, 58, fg);
            if (!drawn && seg.text) {
                ctx.font = `800 ${fitFontPx(ctx, seg.text, 800, seg.text.length > 3 ? 40 : 52, 150, font)}px ${font}`;
                ctx.fillText(seg.text, cx, -12);
            }
            ctx.font = `600 ${fitFontPx(ctx, seg.label, 600, 26, 150, font)}px ${font}`;
            ctx.fillText(seg.label, cx, 34);
            ctx.restore();
        }
        // Tashqi chiziq
        ctx.beginPath();
        ctx.arc(r, r, r - 4, 0, Math.PI * 2);
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 6;
        ctx.stroke();
    }

    // Server sovrin kodiga mos bo'laklar indekslari. Eski barabandan qolgan ball sovrini (masalan 10) uchun
    // g'ildirakda bo'lak yo'q: eng katta ball bo'lagida to'xtaydi, karta/ball esa serverdagi qiymat bo'yicha.
    function segmentIndexesFor(code) {
        const exact = [];
        segments.forEach((seg, i) => { if (seg.code === code) exact.push(i); });
        if (exact.length || !(code > 0)) return exact;
        let best = -1;
        segments.forEach((seg, i) => { if (seg.code > 0 && (best < 0 || seg.code > segments[best].code)) best = i; });
        return best < 0 ? [] : [best];
    }

    // Animatsiya tugagach ko'rsatiladigan karta (har sovrin turi uchun alohida). Tugma bosilganda: API ishlayotgan
    // bo'lsa serverda hisobga qo'shiladi, aks holda ZAXIRA yo'l — eski botga deep link.
    function renderSpinConfirmCard(code) {
        const cards = {
            points: { icon: '🎉', title: `+${code} ball yutdingiz!`, desc: "Ballarni hisobingizga qo'shish va saqlash uchun tasdiqlang." },
            tip: { icon: '💡', title: "Kun maslahati", desc: "Bugungi maslahatni ochish uchun tasdiqlang." },
            ai: { icon: '🤖', title: "+1 bepul AI savol", desc: "AI tabida ishlatishingiz mumkin. Hisobingizga qo'shish uchun tasdiqlang." },
            pro_day: { icon: '⭐', title: "1 kunlik Premium Pro yutdingiz!", desc: "Faollashtirish uchun tasdiqlang.", accent: true },
            super: {
                icon: '🏆', title: "SUPER PRIZ!", accent: true,
                desc: ["Siz ", { b: "Super Priz" }, " — 30 kunlik Premium Plus uchun ", { b: "50% chegirma" }, " yutib oldingiz!"]
            }
        };
        const card = cards[prizeTypeOfCode(code)];
        renderWheelCard(card.icon, card.title, card.desc, "Mukofotni olish", () => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('heavy');
            unclaimedPrize = null;
            if (wheelApiActive) {
                claimSpinViaApi(code);
            } else {
                openSpinDeepLink(code);
            }
        }, { btnId: 'btn-confirm-spin', accent: card.accent });
    }

    // ZAXIRA yo'l (API yo'q yoki xato): eski mantiq — botga deep link orqali tasdiqlash.
    // Parametr faqat belgi: sovrin botda baribir serverdagi pending_spin_prize dan olinadi.
    function openSpinDeepLink(code) {
        if (tg) {
            const botUsername = BOT_USERNAME;
            const named = { '0': 'super', '-1': 'ai', '-2': 'tip', '-3': 'proday' };
            const pv = named[String(code)] || code;
            tg.openTelegramLink(`https://t.me/${botUsername}?start=spin_${pv}`);
            tg.close();
        } else {
            notify("Telegram orqali tasdiqlang!");
        }
    }

    // Natija kartasi: matnlar textContent orqali qo'yiladi (server xabari / maslahati HTML sifatida talqin qilinmaydi).
    // desc — satr yoki [satr, {b: "qalin matn"}, ...] ro'yxati. opts: { btnId, accent (oltin ikonka) }.
    function renderWheelCard(icon, title, desc, btnText, onBtn, opts) {
        const o = opts || {};
        resultMsg.replaceChildren();
        const iconEl = document.createElement('div');
        iconEl.className = o.accent ? 'result-icon result-icon--super' : 'result-icon';
        iconEl.innerHTML = svgIcon(WHEEL_CARD_ICONS[icon] || 'info', icon === '⏳' ? 'icon-spin' : '');
        const titleEl = document.createElement('p');
        titleEl.className = 'result-title';
        titleEl.textContent = title;
        const descEl = document.createElement('p');
        descEl.className = 'result-desc';
        (Array.isArray(desc) ? desc : [desc]).forEach((part) => {
            if (part && typeof part === 'object') {
                const b = document.createElement('b');
                b.textContent = part.b;
                descEl.appendChild(b);
            } else {
                descEl.appendChild(document.createTextNode(part === null || part === undefined ? '' : String(part)));
            }
        });
        resultMsg.append(iconEl, titleEl, descEl);
        if (btnText && onBtn) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'result-confirm-btn';
            if (o.btnId) btn.id = o.btnId;
            btn.textContent = btnText;
            btn.onclick = onBtn;
            resultMsg.appendChild(btn);
        }
        resultMsg.classList.remove('hidden');
    }

    function renderSuperPrizeCard() {
        renderWheelCard("🏆", "SUPER PRIZ!", "50% chegirma faollashtirildi.",
            "Premium olish", () => {
                if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('heavy');
                buyPremium('buy_plus_30');      // chegirma server tomonida avtomatik (has_discount)
            }, { accent: true });
    }

    function renderAiPrizeCard() {
        renderWheelCard("🤖", "+1 bepul AI savol", "AI tabida ishlatishingiz mumkin");
    }

    function renderProDayCard(text) {
        renderWheelCard("⭐", "1 kunlik Premium Pro faollashdi!", text || "", null, null, { accent: true });
    }

    // Claim javobidagi Premium holati va AI hisoblagichi (faqat ai / pro_day turlarida keladi) — keshga
    // qo'shimcha /api/state so'rovisiz yoziladi (header nishoni va AI tab sarlavhasi tinglovchilar orqali yangilanadi)
    function applyClaimedState(r) {
        const patch = {};
        ['is_premium', 'premium_type', 'premium_expires_at', 'premium_unlimited', 'premium_days_left',
         'ai_remaining', 'ai_limit', 'ai_bonus'].forEach((k) => {
            if (r[k] !== undefined) patch[k] = r[k];
        });
        if (Object.keys(patch).length) patchAppState(patch);
    }

    // Javob kelmadi: server sovrinni allaqachon bergan bo'lishi mumkin — holatni qayta so'raymiz
    async function recoverSpinClaim(winningCode, prevScore) {
        renderWheelCard("⏳", "Natija tekshirilmoqda...", "");
        const s = await recoverStateAfterClaimFailure();
        if (!s) {                                   // holat ham olinmadi: ESKI zaxira yo'l
            openSpinDeepLink(winningCode);
            return;
        }
        setGlobalScore(s.score);
        if (s.prize === null && Number(s.cooldown_seconds) > 0) {
            // Server sovrinni allaqachon bergan: deep link YO'Q
            const type = prizeTypeOfCode(winningCode);
            if (type === 'super') {
                renderSuperPrizeCard();
                return;
            }
            if (type === 'ai') {
                renderAiPrizeCard();
                return;
            }
            if (type === 'pro_day') {
                renderProDayCard("");
                return;
            }
            if (type === 'tip') {
                renderWheelCard("💡", "Kun maslahati", "Maslahat berildi, lekin ulanish uzilgani uchun matnni ko'rsatib bo'lmadi. Ertaga yangisini oling.");
                return;
            }
            const diff = (typeof prevScore === 'number') ? s.score - prevScore : 0;
            renderWheelCard("✅", "Ball hisobingizga qo'shilgan",
                diff > 0 ? `+${diff} ball hisobingizga qo'shildi` : "Ball hisobingizga qo'shilgan.");
            return;
        }
        // Server hali bermagan (ulanish muammosi). Server ikki marta bermaydi, shuning uchun qayta urinish xavfsiz
        unclaimedPrize = winningCode;                // foydalanuvchi yopib ketsa — yopishda yana bir urinish
        renderWheelCard("⚠️", "Ulanishda xatolik", "Sovrin hali qo'shilmadi. Qayta urinib ko'ring.",
            "Qayta urinish", () => { unclaimedPrize = null; claimSpinViaApi(winningCode); });
    }

    // "Mukofotni olish" bosilganda sovrinni serverda hisobga qo'shadi (botga chiqmasdan, tg.close() yo'q)
    async function claimSpinViaApi(winningCode, opts) {
        const toast = (msg, ms) => { if (opts && opts.toast) showToast(msg, ms); };
        const prevScore = AppState.data ? AppState.data.score : null;
        renderWheelCard("⏳", "Hisobga qo'shilmoqda...", "");
        let r;
        try {
            r = await api('spin/claim');
            if (!r || typeof r.ok !== 'boolean') throw new Error('bad-claim');
        } catch (err) {
            console.warn("[wheel] /api/spin/claim javobi olinmadi, holat tekshiriladi:", err);
            await recoverSpinClaim(winningCode, prevScore);
            return;
        }
        if (typeof r.score === 'number') setGlobalScore(r.score);
        // Serverda cooldown boshlandi: keshni shunga moslaymiz (qayta ochilganda KUTISH ko'rinadi)
        patchAppState({ score: r.score, prize: null, prize_type: null, cooldown_seconds: 24 * 60 * 60 });

        if (!r.ok) {
            renderWheelCard("ℹ️", prizeTypeOfCode(winningCode) === 'points' ? "Ball qo'shilmadi" : "Sovrin qo'shilmadi",
                r.message || "Mukofot allaqachon olingan.");
            toast(r.message || "Mukofot allaqachon olingan.");
            return;
        }
        applyClaimedState(r);
        const type = claimedPrizeType(r);
        if (type === 'super') {
            renderSuperPrizeCard();
            toast("SUPER PRIZ: Premium Plus uchun 50% chegirma faollashtirildi");
        } else if (type === 'tip') {
            const tip = (typeof r.tip === 'string' && r.tip) ? r.tip : (r.message || '');
            renderWheelCard("💡", "Kun maslahati", tip);
            toast("Kun maslahati: " + tip, 2200 + tip.length * 50);       // uzun matn — uzoqroq ko'rinadi
        } else if (type === 'ai') {
            renderAiPrizeCard();
            toast("+1 bepul AI savol hisobingizga qo'shildi");
        } else if (type === 'pro_day') {
            renderProDayCard(r.message);
            toast("1 kunlik Premium Pro faollashdi");
        } else {
            // Ball soni SERVERDAN: javobdagi points, bo'lmasa oldingi/yangi score farqi; matnda server xabari
            // (r.message — server uni allaqachon oddiy matnga aylantirgan). Klientdagi sovrin kodi ko'rsatilmaydi.
            const gained = (typeof r.points === 'number' && r.points > 0) ? r.points
                : ((typeof prevScore === 'number' && typeof r.score === 'number') ? r.score - prevScore : 0);
            renderWheelCard("🎉",
                gained > 0 ? `+${gained} ball yutdingiz!` : "Ball hisobingizga qo'shildi",
                r.message || "✅ Ball hisobingizga qo'shildi");
            toast(gained > 0 ? `+${gained} ball hisobingizga qo'shildi` : "Ball hisobingizga qo'shildi");
        }
    }

    // Spin handler
    spinBtn.onclick = () => {
        if (isSpinning || hasSpunThisSession || remainingTimeMs > 0) return;

        isSpinning = true;
        spinBtn.disabled = true;
        if (centerText) centerText.textContent = "...";
        resultMsg.classList.add('hidden');

        if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

        // Use server-side pre-generated prize
        // XAVFSIZLIK: prize URL da bo'lmasa spin bloklanadi
        if (serverPrize === null) {
            isSpinning = false;
            spinBtn.disabled = false;
            if (centerText) centerText.textContent = "AYLANTIR";
            resultMsg.innerHTML = `<div class="result-icon">${svgIcon('gift')}</div><p class="result-title">Bot orqali kiring</p><p class="result-desc">Omad g‘ildiragini aylantirish uchun botdagi maxsus havola orqali kiring.</p><button type="button" class="result-confirm-btn" id="btn-open-bot-wheel">Bot orqali ochish</button>`;
            resultMsg.classList.remove('hidden');
            const btnBotWheel = document.getElementById('btn-open-bot-wheel');
            if (btnBotWheel) {
                btnBotWheel.onclick = () => {
                    if (tg && tg.openTelegramLink) {
                        const botUsername = BOT_USERNAME;
                        tg.openTelegramLink(`https://t.me/${botUsername}?start=wheel`);
                        tg.close();
                    }
                };
            }
            return;
        }
        const winningCode = serverPrize;
        const eligible = segmentIndexesFor(winningCode);

        // XAVFSIZLIK: server prize frontend da mavjud bo'lmasa blokla
        if (!eligible.length) {
            isSpinning = false;
            spinBtn.disabled = false;
            if (centerText) centerText.textContent = "AYLANTIR";
            resultMsg.innerHTML = `<div class="result-icon">${svgIcon('alert-triangle')}</div><p class="result-title">Texnik xatolik</p><p class="result-desc">Mukofotni olish uchun botga /start yuboring.</p>`;
            resultMsg.classList.remove('hidden');
            return;
        }

        const winIdx = eligible[Math.floor(Math.random() * eligible.length)];
        const segArc = 360 / segments.length;
        const target = 270 - (winIdx * segArc + segArc / 2);
        const finalAngle = 8 * 360 + target;

        const spinMs = prefersReducedMotion() ? 600 : 4000;
        canvas.style.transition = `transform ${spinMs}ms cubic-bezier(.2, .8, .2, 1)`;
        canvas.style.transform = `rotate(${finalAngle}deg)`;

        // Periodic click haptic while spinning
        let spinHapticInterval = setInterval(() => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        }, 300);

        setTimeout(() => clearInterval(spinHapticInterval), Math.max(0, spinMs - 400));

        setTimeout(() => {
            isSpinning = false;
            hasSpunThisSession = true;
            SafeStorage.setItem('last_spin_time', new Date().toISOString());
            if (tg && tg.CloudStorage) {
                tg.CloudStorage.setItem('last_spin_time', new Date().toISOString());
            }

            spinBtn.disabled = true;
            if (centerText) centerText.textContent = "ERTAGA";

            if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');

            // Konfetti — faqat SUPER va 1 kunlik Pro'da
            if (winningCode === 0 || winningCode === -3) fireConfetti();

            unclaimedPrize = winningCode;
            renderSpinConfirmCard(winningCode);
        }, spinMs + 100);
    };

    // Karta yoki oyna o'zgarganda MainButton kartadagi tugmaga moslanadi (bir xil matn va bir xil handler)
    function syncWheelMainButton() {
        const visible = !modal.classList.contains('hidden') && modal.style.display !== 'none';
        const btn = visible && !resultMsg.classList.contains('hidden') ? resultMsg.querySelector('.result-confirm-btn') : null;
        if (!btn || !btn.onclick) {
            if (MainButtonCtl.owner === 'wheel') MainButtonCtl.clear();
            return;
        }
        if (MainButtonCtl.owner === 'wheel' && MainButtonCtl.fallback === btn) return;
        const handler = btn.onclick;
        MainButtonCtl.set({ text: btn.textContent.trim(), owner: 'wheel', onClick: () => handler.call(btn) }, btn);
    }
    new MutationObserver(syncWheelMainButton).observe(modal, {
        subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'style']
    });

    // Auto-open wheel if specified in URL params or start_param
    const page = urlParams.get('page') || (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param);
    if (page === 'wheel') {
        checkWheelStateAndOpen();
        pushWheelNav();
    }
}

// Confetti Particle Explosion Engine
function fireConfetti() {
    const canvas = document.getElementById('wheel-confetti-canvas');
    if (!canvas || prefersReducedMotion()) return;          // kamaytirilgan harakat: konfetti yo'q

    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    const colors = ['#F5A524', '#14A39A', '#0A84C6', '#FFFFFF'];

    for (let i = 0; i < 40; i++) {
        particles.push({
            x: canvas.width / 2,
            y: canvas.height * 0.45,
            vx: (Math.random() - 0.5) * 16,
            vy: (Math.random() - 0.7) * 18,
            size: Math.random() * 8 + 4,
            color: colors[Math.floor(Math.random() * colors.length)],
            rotation: Math.random() * 360,
            rSpeed: (Math.random() - 0.5) * 12,
            opacity: 1,
            gravity: 0.35
        });
    }

    let animationFrame;
    const startTime = Date.now();

    function renderConfetti() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        let activeCount = 0;
        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += p.gravity;
            p.vx *= 0.98;
            p.rotation += p.rSpeed;
            p.opacity -= 0.008;

            if (p.opacity > 0) {
                activeCount++;
                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate((p.rotation * Math.PI) / 180);
                ctx.globalAlpha = Math.max(0, p.opacity);
                ctx.fillStyle = p.color;
                ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
                ctx.restore();
            }
        });

        if (activeCount > 0 && Date.now() - startTime < 4000) {
            animationFrame = requestAnimationFrame(renderConfetti);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            cancelAnimationFrame(animationFrame);
        }
    }

    renderConfetti();
}




// DAILY BONUS LOGIC
document.addEventListener('DOMContentLoaded', () => {
    const btnOpenDailyBonus = document.getElementById('btn-open-daily-bonus');
    const modal = document.getElementById('daily-bonus-modal');
    const btnClose = document.getElementById('daily-bonus-close');
    const btnClaim = document.getElementById('btn-claim-daily-bonus');
    const grid = document.getElementById('daily-bonus-grid');
    const currentScoreEl = document.getElementById('daily-bonus-current-score');
    
    if (!btnOpenDailyBonus || !modal) return;
    
    // Parse URL params
    const urlParams = new URLSearchParams(window.location.search);
    // URL-parametrlar — ZAXIRA qiymatlar; /api/state ishlasa ular serverdan yangilanadi
    let streak = parseInt(urlParams.get('streak') || '1');
    let dailyClaimed = urlParams.get('daily_claimed') === '1';
    let userScore = urlParams.get('score') || '0';
    
    if(currentScoreEl) {
        currentScoreEl.textContent = userScore;
    }
    
    // Render Grid
    function renderGrid() {
        if(!grid) return;
        grid.innerHTML = '';
        const rewards = [1, 2, 3, 3, 3, 3, 20];
        
        for (let i = 1; i <= 7; i++) {
            const isDay7 = i === 7;
            const isCurrent = i === streak;
            const isPast = i < streak || (i === streak && dailyClaimed);
            
            const card = document.createElement('div');
            let classes = ['daily-bonus-card'];
            if(isDay7) classes.push('day-7');
            if(isCurrent && !dailyClaimed) classes.push('active');
            if(isPast) classes.push('claimed');

            card.className = classes.join(' ');
            card.setAttribute('role', 'listitem');
            const state = isPast ? 'olingan' : (isCurrent && !dailyClaimed) ? 'bugun' : 'kutilmoqda';
            card.setAttribute('aria-label', `${i}-kun: ${rewards[i-1]} ball, ${state}`);
            // Belgi: olingan — ✓, 7-kun — sovg'a, qolganlari — kun raqami
            const mark = isPast ? svgIcon('check') : isDay7 ? svgIcon('gift') : `<span class="tabular">${i}</span>`;
            card.innerHTML = `<span class="day-dot" aria-hidden="true">${mark}</span>` +
                             `<span class="day-reward tabular" aria-hidden="true">+${rewards[i-1]}</span>`;
            grid.appendChild(card);
        }
        
        if (dailyClaimed) {
            btnClaim.classList.add('is-claimed');
            btnClaim.setAttribute('aria-disabled', 'true');
            btnClaim.querySelector('.bonus-claim-label').textContent = 'Bugungi bonus olindi';
            btnClaim.onclick = null;
        } else {
            btnClaim.classList.remove('is-claimed');
            btnClaim.removeAttribute('aria-disabled');
            btnClaim.onclick = () => {
                if (AppState.data) {
                    claimBonusViaApi();         // API ishlayapti: mini app ichida
                } else {
                    openClaimDailyDeepLink();   // ZAXIRA: eski mantiq
                }
            };
        }
        syncBonusMainButton();
    }

    // Asosiy amal: Telegram ichida MainButton "Bonusni olish" (kartadagi tugma bilan bir xil handler).
    // Olingan holatda MainButton yo'q — sahifada "Bugungi bonus olindi" ko'rinadi.
    function syncBonusMainButton() {
        const open = !modal.classList.contains('hidden');
        if (!open || dailyClaimed || !btnClaim.onclick) {
            btnClaim.classList.remove('inpage-main');
            if (MainButtonCtl.owner === 'bonus') MainButtonCtl.clear();
            return;
        }
        btnClaim.classList.add('inpage-main');
        const handler = btnClaim.onclick;
        // Zaxira tugma o'z onclick'i bilan qoladi (ichidagi yorliq "Kutilmoqda..." uchun kerak) — fallback berilmaydi
        MainButtonCtl.set({ text: 'Bonusni olish', owner: 'bonus', onClick: () => handler.call(btnClaim) });
        if (bonusLabelBackup === null) btnClaim.querySelector('.bonus-claim-label').textContent = 'Bonusni olish';
    }

    // ZAXIRA yo'l (API yo'q yoki xato): botga deep link orqali olish
    function openClaimDailyDeepLink() {
        if (window.Telegram && window.Telegram.WebApp) {
            const botUsername = BOT_USERNAME;
            window.Telegram.WebApp.openTelegramLink(`https://t.me/${botUsername}?start=claim_daily`);
            window.Telegram.WebApp.close();
        } else {
            notify('Faqat Telegram ichida ishlaydi!');
        }
    }

    // Serverdagi holatni (seriya, bugun olinganmi, ball) interfeysga qo'llaydi
    function applyState(s) {
        streak = Number(s.streak) || 1;
        dailyClaimed = !!s.daily_claimed;
        userScore = s.score;
        if (currentScoreEl) currentScoreEl.textContent = String(s.score);
        renderGrid();
    }

    function showBonusResult(text) {
        let el = document.getElementById('daily-bonus-result');
        if (!el) {
            el = document.createElement('p');
            el.id = 'daily-bonus-result';
            el.className = 'daily-bonus-result';
            btnClaim.insertAdjacentElement('beforebegin', el);
        }
        el.textContent = text;
    }

    // Javob kutilayotganda tugma matni o'zgaradi (server uzoqda: 8 s gacha kutish mumkin)
    let bonusLabelBackup = null;
    function setBonusBusy(busy) {
        const label = btnClaim.querySelector('.bonus-claim-label');
        if (!label) return;
        try {
            if (MainButtonCtl.owner === 'bonus' && tg && tg.MainButton) {
                if (busy && tg.MainButton.showProgress) tg.MainButton.showProgress();
                if (!busy && tg.MainButton.hideProgress) tg.MainButton.hideProgress();
            }
        } catch (e) { /* eski klient */ }
        if (busy) {
            if (bonusLabelBackup === null) bonusLabelBackup = label.textContent;
            label.textContent = 'Kutilmoqda...';
        } else if (bonusLabelBackup !== null) {
            label.textContent = bonusLabelBackup;
            bonusLabelBackup = null;
        }
    }

    function hapticSuccess() {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
        }
    }

    // Javob kelmadi: server bonusni allaqachon bergan bo'lishi mumkin — holatni qayta so'raymiz
    async function recoverBonusClaim(prevScore) {
        const s = await recoverStateAfterClaimFailure();
        bonusClaiming = false;
        setBonusBusy(false);
        if (!s) {                                   // holat ham olinmadi: ESKI zaxira yo'l
            openClaimDailyDeepLink();
            return;
        }
        setGlobalScore(s.score);
        applyState(s);                              // seriya, ball va tugma holati serverdan
        if (s.daily_claimed) {
            // Server bonusni allaqachon bergan: deep link YO'Q
            const diff = (typeof prevScore === 'number') ? s.score - prevScore : 0;
            showBonusResult(diff > 0 ? `+${diff} ball hisobingizga qo'shilgan` : "Bugungi bonus hisobingizga qo'shilgan");
            hapticSuccess();
        } else {
            notify("Ulanishda xatolik. Qayta urinib ko'ring.");
        }
    }

    let bonusClaiming = false;
    async function claimBonusViaApi() {
        if (bonusClaiming) return;
        bonusClaiming = true;
        const prevScore = AppState.data ? AppState.data.score : null;
        setBonusBusy(true);
        let r;
        try {
            r = await api('bonus/claim');
            if (!r || typeof r.ok !== 'boolean') throw new Error('bad-claim');
        } catch (err) {
            console.warn("[bonus] /api/bonus/claim javobi olinmadi, holat tekshiriladi:", err);
            await recoverBonusClaim(prevScore);
            return;
        }
        bonusClaiming = false;
        setBonusBusy(false);
        if (typeof r.score === 'number') {
            userScore = r.score;
            setGlobalScore(r.score);
            if (currentScoreEl) currentScoreEl.textContent = String(r.score);
        }
        if (r.ok) {
            streak = Number(r.streak) || streak;
            dailyClaimed = true;
            patchAppState({ score: r.score, streak: r.streak, daily_claimed: true });
            renderGrid();                                   // tugma "Olindi" holatiga o'tadi
            showBonusResult(`+${r.points} ball, ${r.streak}-kun`);
            hapticSuccess();
        } else {
            notify(r.message || "Bonusni olib bo'lmadi.");
            invalidateAppState();                           // haqiqiy holatni serverdan qayta olamiz
            getAppState(0).then((s) => { if (s) applyState(s); });
        }
    }

    btnOpenDailyBonus.onclick = () => {
        modal.classList.remove('hidden');
        renderGrid();
        document.body.style.overflow = 'hidden';
        // Umumiy kesh: 60 soniyadan eski bo'lsagina qayta so'raladi
        getAppState(60000).then((s) => { if (s) applyState(s); });
    };

    // Mini app ochilganda seriya va "bugun olingan" holati serverdan (menyu tugmasidan ochilganda ham to'g'ri)
    getAppState(60000).then((s) => { if (s) applyState(s); });
    
    btnClose.onclick = () => {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
        syncBonusMainButton();
    };
    
    // Allow clicking outside the modal content to close it
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            btnClose.onclick();
        }
    });
});

// Premium Modal Logic
// Tarif imkoniyatlari — avvalgi kartalardagi matnlar. AI limitlari database.py dagi PRO/PLUS/ULTRA_AI_DAILY_LIMIT
// bilan mos: 15 / 30 / 100. Ultra'dagi "Cheksiz imkoniyatlar" limitga zid — egasi tasdiqlaguncha olib tashlangan
// ("Kuniga 100 AI so'rov" allaqachon birinchi bandda, takrorlanmaydi)
const PREMIUM_FEATURES = {
    buy_pro_7: ["Kuniga 15 AI so'rov", "Ovozli xabar", "Barcha funksiyalar"],
    buy_plus_30: ["Kuniga 30 AI so'rov", "Ustunlik", "Barcha imkoniyatlar"],
    buy_ultra_30: ["Kuniga 100 AI so'rov", "VIP xizmat"]
};

function selectedPremiumPlan() {
    const r = document.querySelector('#premium-modal input[name="premium-plan"]:checked');
    return r ? { plan: r.value, price: r.getAttribute('data-price') } : { plan: 'buy_plus_30', price: '150' };
}

function renderPremiumFeatures() {
    const list = document.getElementById('premium-features');
    if (!list) return;
    const { plan } = selectedPremiumPlan();
    list.innerHTML = '';
    (PREMIUM_FEATURES[plan] || []).forEach(text => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="pm-check" aria-hidden="true">${svgIcon('check')}</span><span></span>`;
        li.lastChild.textContent = text;
        list.appendChild(li);
    });
}

// "★ 150 — Davom etish": Telegram ichida MainButton, tashqarida sahifadagi tugma. Ikkalasi ham buyPremium(plan)
function syncPremiumMainButton() {
    const modal = document.getElementById('premium-modal');
    const open = modal && !modal.classList.contains('hidden');
    if (!open) {
        if (MainButtonCtl.owner === 'premium') MainButtonCtl.clear();
        return;
    }
    const { plan, price } = selectedPremiumPlan();
    MainButtonCtl.set({ text: `★ ${price} — Davom etish`, owner: 'premium', onClick: () => buyPremium(plan) },
                      document.getElementById('premium-continue'));
}

document.addEventListener('DOMContentLoaded', () => {
    const btnOpenPremium = document.getElementById('btn-open-premium');
    const premiumModal = document.getElementById('premium-modal');
    const premiumModalClose = document.getElementById('premium-modal-close');

    if (btnOpenPremium && premiumModal) {
        premiumModal.querySelectorAll('input[name="premium-plan"]').forEach(r => {
            r.addEventListener('change', () => {
                if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
                renderPremiumFeatures();
                syncPremiumMainButton();
            });
        });
        renderPremiumFeatures();

        btnOpenPremium.addEventListener('click', () => {
            premiumModal.classList.remove('hidden');
            premiumModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            syncPremiumMainButton();

            AppNavigation.push({
                type: 'premium-modal',
                close: () => {
                    premiumModal.classList.add('hidden');
                    premiumModal.style.display = 'none';
                    document.body.style.overflow = 'auto';
                    syncPremiumMainButton();
                    AppNavigation.pop();
                }
            });
        });

        if (premiumModalClose) {
            premiumModalClose.addEventListener('click', () => {
                AppNavigation.back();
            });
        }

        premiumModal.addEventListener('click', (e) => {
            if (e.target === premiumModal) {
                AppNavigation.back();
            }
        });
    }
});

// ═══════════════════════════════════════════════════════════════════
// AI SUHBAT TABI (G 4-bosqich): savol shu yerda yoziladi, javob shu yerda chiqadi (/api/ai/chat).
// Tarix faqat xotirada (oxirgi 6 ta), serverda saqlanmaydi. Foydalanuvchi va AI matni FAQAT textContent va DOM
// tugunlari orqali chiziladi — HTML satri bilan render bu bo'limda ATAYLAB yo'q (tests/test_miniapp_ai_chat_e2e.py).
// ═══════════════════════════════════════════════════════════════════
const AI_MSG_MAX = 1000;                 // server bilan bir xil (bot.py: AI_MSG_MAX)
const AI_HISTORY_MAX = 6;                // server: AI_HISTORY_MAX
const AI_TIMEOUT_MS = 45000;             // server AI kutishi 40 s + zaxira
const AI_INFLIGHT_WAIT_S = 5;            // 409 (boshqa oynada javob kutilmoqda) — shuncha soniya kutiladi
const AI_QUICK_TOPICS = ['qon_ketishi', 'kuyish', 'bogilish', 'yurak_xuruji'];     // FIRST_AID_ITEMS kritik mavzulari
const AI_TEXT = {
    busy: "Hozir band, qayta urinib ko'ring.",
    network: "Aloqa yo'q. Internetni tekshirib, qayta urinib ko'ring.",
    forbidden: "Mini appni Telegram ichida oching.",
    server: "Xatolik yuz berdi. Qayta urinib ko'ring.",
    badRequest: "Xabar 1–1000 belgidan iborat bo'lsin.",
    limitPremium: "Bugungi limit tugadi. Yangi so'rovlar ertaga soat 00:00 dan (Toshkent vaqti) beriladi.",
    placeholder: "Holatni yozing…",
    placeholderLocked: "Bepul savolingiz ishlatildi"
};
const aiChat = {
    history: [],          // [{role: 'user' | 'ai', text}] — faqat muvaffaqiyatli almashinuvlar
    sending: false,       // javob kutilmoqda: yuborish o'chiq (ikki marta bosib bo'lmaydi)
    waitUntil: 0,         // "Juda tez yozyapsiz": shu vaqtgacha yuborish o'chiq (ms)
    waitTimer: null,
    context: null,        // { type: 'body_part' | 'condition', key, label, prefix?, partKey? } — birinchi yuborishda
    pending: null,        // javobsiz qolgan oxirgi xabar { text } — "Qayta urinish" uchun
    quota: null,          // { remaining, limit } — /api/state yuklanmagan bo'lsa
    offerShown: false,    // bepul savol ishlatilgan: Premium taklif kartasi, yozish o'chiq
    epoch: 0              // "Yangi suhbat" — eski javob yangi suhbatga tushmaydi
};

function aiEl(tag, cls, text) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = text;
    return el;
}

function aiIcon(name) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS(NS, 'use');
    use.setAttribute('href', '#i-' + name);
    svg.appendChild(use);
    return svg;
}

// Qator ichi: **qalin** / __qalin__ -> <strong>; qolgan * va ` belgilari ekranda xom ko'rinmaydi
function aiStripMarks(text) {
    return String(text).replace(/\*+/g, '').replace(/`+/g, '');
}

function aiAppendInline(parent, text) {
    String(text).split(/(\*\*[^*]+?\*\*|__[^_]+?__)/).forEach((part, i) => {
        if (!part) return;
        if (i % 2 === 1) {
            parent.appendChild(aiEl('strong', null, aiStripMarks(part.slice(2, -2))));
        } else {
            const t = aiStripMarks(part);
            if (t) parent.appendChild(document.createTextNode(t));
        }
    });
}

// AI javobi (oddiy matn) -> DOM: ## sarlavha, "- " / "* " / "1." ro'yxat, bo'sh qator — yangi xatboshi
function aiRenderReply(container, text) {
    const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
    let para = null;
    let list = null;
    lines.forEach(raw => {
        const line = raw.trim();
        if (!line || /^([-*_])(\s*\1){2,}$/.test(line)) { para = null; list = null; return; }   // bo'sh qator / ---
        let m = line.match(/^#{1,6}\s*(.*)$/);
        if (m) {
            para = null; list = null;
            const h = aiEl('p', 'ai-h');
            aiAppendInline(h, m[1].replace(/\s*#+\s*$/, ''));
            container.appendChild(h);
            return;
        }
        m = line.match(/^(?:[-*•+]|(\d{1,2})[.)])\s+(.*)$/);
        if (m) {
            const tag = m[1] ? 'ol' : 'ul';
            para = null;
            if (!list || list.tagName.toLowerCase() !== tag) {
                list = aiEl(tag, 'ai-list');
                const start = m[1] ? parseInt(m[1], 10) : 1;
                if (start > 1) list.start = start;
                container.appendChild(list);
            }
            const li = aiEl('li');
            aiAppendInline(li, m[2]);
            list.appendChild(li);
            return;
        }
        list = null;
        if (para) para.appendChild(document.createElement('br'));
        else { para = aiEl('p'); container.appendChild(para); }
        aiAppendInline(para, line.replace(/^>\s?/, ''));
    });
    if (!container.childNodes.length) container.appendChild(aiEl('p', null, String(text || '')));
}

function aiThread() { return document.getElementById('ai-thread'); }
function aiLog() { return document.getElementById('ai-log'); }

function aiHasMessages() {
    const thread = aiThread();
    return !!thread && thread.querySelectorAll('.ai-msg:not(.ai-greeting):not(.ai-typing)').length > 0;
}

function aiAddMessage(role, who, build, extraCls) {
    const msg = aiEl('div', 'ai-msg ai-msg--' + role + (extraCls ? ' ' + extraCls : ''));
    msg.appendChild(aiEl('span', 'sr-only', who));
    const bubble = aiEl('div', 'ai-bubble');
    build(bubble);
    msg.appendChild(bubble);
    aiThread().appendChild(msg);
    return msg;
}

function aiAddUser(text) {
    return aiAddMessage('user', 'Siz:', b => b.appendChild(aiEl('p', 'ai-user-text', text)));
}

function aiAddReply(text) {
    return aiAddMessage('ai', 'AI:', b => aiRenderReply(b, text));
}

// Xato / limit / "juda tez" — AI pufagi ichida, kerak bo'lsa tugmalar bilan
function aiAddNotice(text, actions) {
    return aiAddMessage('ai', 'AI:', b => {
        b.appendChild(aiEl('p', 'ai-notice-text', text));
        if (!actions || !actions.length) return;
        const row = aiEl('div', 'ai-actions');
        actions.forEach(a => {
            const btn = aiEl('button', 'ai-action' + (a.primary ? ' ai-action--primary' : ''));
            btn.type = 'button';
            btn.setAttribute('data-ai-action', a.id);
            if (a.icon) btn.appendChild(aiIcon(a.icon));
            btn.appendChild(aiEl('span', null, a.label));
            btn.addEventListener('click', () => a.onClick(btn));
            row.appendChild(btn);
        });
        b.appendChild(row);
    }, 'ai-msg--notice');
}

function aiShowTyping() {
    const msg = aiEl('div', 'ai-msg ai-msg--ai ai-typing');
    msg.setAttribute('role', 'status');
    const bubble = aiEl('div', 'ai-bubble');
    bubble.appendChild(aiEl('span', 'sr-only', 'AI javob yozmoqda'));
    for (let i = 0; i < 3; i++) {
        const dot = aiEl('span', 'ai-dot');
        dot.setAttribute('aria-hidden', 'true');
        bubble.appendChild(dot);
    }
    msg.appendChild(bubble);
    aiThread().appendChild(msg);
    return msg;
}

function aiScrollBottom() {
    const log = aiLog();
    if (log) log.scrollTop = log.scrollHeight;
}

// Uzun javob boshidan o'qiladi: element yuqori chetiga suriladi (mumkin bo'lgancha)
function aiScrollTo(el) {
    const log = aiLog();
    if (!log || !el) return;
    log.scrollTop += el.getBoundingClientRect().top - log.getBoundingClientRect().top - 8;
}

function aiIsWaiting() { return aiChat.waitUntil > Date.now(); }
function aiCanSend() { return !aiChat.sending && !aiIsWaiting() && !aiChat.offerShown; }

// Yuborish tugmasi, tezkor chiplar, "Qayta urinish", "Yangi suhbat" holati — bitta joyda
function aiSync() {
    const input = document.getElementById('ai-input');
    const send = document.getElementById('ai-send');
    if (!input || !send) return;
    const locked = aiChat.offerShown;
    const blocked = locked || aiChat.sending || aiIsWaiting();
    input.disabled = locked;
    input.placeholder = locked ? AI_TEXT.placeholderLocked : AI_TEXT.placeholder;
    send.disabled = blocked || !input.value.trim();
    const composer = document.getElementById('ai-composer');
    if (composer) composer.classList.toggle('is-locked', locked);
    const quick = document.getElementById('ai-quick');
    if (quick) {
        quick.hidden = aiHasMessages();
        quick.querySelectorAll('button').forEach(b => { b.disabled = blocked; });
    }
    document.querySelectorAll('#ai-thread [data-ai-action="retry"]').forEach(b => { b.disabled = blocked; });
    const fresh = document.getElementById('ai-new-chat');
    if (fresh) fresh.disabled = aiChat.sending || !aiHasMessages();
    const thread = aiThread();
    if (thread) thread.setAttribute('aria-busy', aiChat.sending ? 'true' : 'false');
}

// Bepul foydalanuvchi: server limiti 1 (jami 1 ta savol). Limit noma'lum bo'lsa — /api/state dagi is_premium
function aiIsFree(limit) {
    if (typeof limit === 'number') return !(limit > 1);
    return AppState.data ? !AppState.data.is_premium : true;
}

// Sarlavhadagi hisoblagich: bepul — "Bepul savol: 1/1" (jami), Premium — "Bugun: 12/15 so'rov"
function renderAiQuota(s) {
    const el = document.getElementById('ai-quota');
    if (!el) return;
    let remaining = null, limit = null, bonus = 0;
    if (s && typeof s.ai_remaining === 'number' && typeof s.ai_limit === 'number') {
        remaining = s.ai_remaining; limit = s.ai_limit; bonus = Number(s.ai_bonus) || 0;
    } else if (aiChat.quota) {
        remaining = aiChat.quota.remaining; limit = aiChat.quota.limit; bonus = aiChat.quota.bonus || 0;
    }
    if (remaining === null) { el.hidden = true; return; }
    // remaining barabandan yutilgan bonusni ham o'z ichiga oladi: oddiy qoldiq alohida, bonus "+ N bonus" bilan
    const base = Math.max(0, remaining - bonus);
    const main = aiIsFree(limit) ? `Bepul savol: ${base}/${limit}` : `Bugun: ${base}/${limit} so'rov`;
    el.textContent = bonus > 0 ? `${main} + ${bonus} bonus` : main;
    el.hidden = false;
}

// Javobdagi remaining/limit -> umumiy holat (hisoblagich va Premium taklif kartasi tinglovchilar orqali yangilanadi)
function aiApplyQuota(remaining, limit, bonus) {
    if (typeof remaining !== 'number' || typeof limit !== 'number') return;
    const b = (typeof bonus === 'number' && bonus > 0) ? Math.min(bonus, remaining) : 0;
    aiChat.quota = { remaining: remaining, limit: limit, bonus: b };
    if (AppState.data) patchAppState({ ai_remaining: remaining, ai_limit: limit, ai_bonus: b });
    else renderAiQuota(null);
    if (remaining === 0 && aiIsFree(limit) && !aiChat.offerShown) showAiPremiumOffer();   // holat eskirgan bo'lsa ham
}

function aiSetContext(ctx) {
    aiChat.context = ctx || null;
    const box = document.getElementById('ai-context');
    const label = document.getElementById('ai-context-label');
    if (!box || !label) return;
    label.textContent = ctx ? `${ctx.prefix || 'Tana qismi'}: ${ctx.label}` : '';
    box.hidden = !ctx;
}

function aiStartWait(seconds) {
    const s = Math.max(1, Math.min(300, Math.round(seconds) || 1));
    aiChat.waitUntil = Date.now() + s * 1000;
    if (aiChat.waitTimer) clearTimeout(aiChat.waitTimer);
    aiChat.waitTimer = setTimeout(() => { aiChat.waitTimer = null; aiChat.waitUntil = 0; aiSync(); }, s * 1000);
    return s;
}

function aiRetryAction() {
    return { id: 'retry', label: 'Qayta urinish', icon: 'rotate-cw', onClick: aiRetry };
}

function aiRetry(btn) {
    if (!aiChat.pending || !aiCanSend()) return;
    const notice = btn && btn.closest('.ai-msg');
    if (notice) notice.remove();
    aiSend(aiChat.pending.text, { retry: true });
}

// Zaxira: API umuman ishlamasa — eski yo'l (tg.sendData ai_consult), suhbat botda davom etadi
function aiContinueInBot() {
    const ctx = aiChat.context;
    if (ctx && ctx.partKey) {
        sendAiConsultToBot(bodyConsultTitle(ctx.partKey), ctx.partKey);
        return;
    }
    const text = aiChat.pending ? aiChat.pending.text : '';
    sendAiConsultToBot(text.slice(0, 100) || 'AI maslahat', null);
}

function aiOpenPremium() {
    const btn = document.getElementById('btn-open-premium');          // mavjud Premium oynasi (tarif -> openInvoice)
    if (btn) btn.click();
}

function aiHandleResult(message, res, failure) {
    if (failure === 'forbidden') { aiAddNotice(AI_TEXT.forbidden); return; }
    const data = res && res.data && typeof res.data === 'object' ? res.data : null;
    if (failure || !data || (!data.ok && !data.error)) {          // tarmoq / nginx: API umuman javob bermadi
        const actions = [aiRetryAction()];
        if (tg && tg.initData) actions.push({ id: 'bot', label: 'Botda davom etish', icon: 'chevron-right', onClick: aiContinueInBot });
        aiAddNotice(AI_TEXT.network, actions);
        return;
    }
    if (data.ok) {
        const reply = typeof data.reply === 'string' ? data.reply.trim() : '';
        if (!reply) { aiAddNotice(AI_TEXT.busy, [aiRetryAction()]); return; }
        aiChat.history.push({ role: 'user', text: message }, { role: 'ai', text: reply.slice(0, AI_MSG_MAX) });
        aiChat.history = aiChat.history.slice(-AI_HISTORY_MAX);
        aiChat.pending = null;
        if (aiChat.context) aiSetContext(null);               // kontekst birinchi yuborishda uzatildi
        const el = aiAddReply(reply);
        aiApplyQuota(data.remaining, data.limit, data.bonus);
        aiScrollTo(el);
        return;
    }
    const err = data.error;
    if (err === 'limit') {
        const limit = typeof data.limit === 'number' ? data.limit : null;
        if (aiIsFree(limit)) {                                  // bepul savol ishlatilgan: Premium taklif kartasi
            aiChat.pending = null;
            aiApplyQuota(0, limit === null ? 1 : limit);
            aiScrollTo(document.getElementById('ai-premium-offer'));
            return;
        }
        if (typeof data.remaining === 'number' && limit !== null) aiApplyQuota(data.remaining, limit);
        const actions = data.offer === 'premium'
            ? [{ id: 'premium', label: 'Premium tariflar', icon: 'crown', primary: true, onClick: aiOpenPremium }] : [];
        aiAddNotice(AI_TEXT.limitPremium, actions);
        return;
    }
    if (err === 'busy' && (data.reason === 'rate' || data.reason === 'inflight' || res.status === 429)) {
        const wait = data.reason === 'inflight' ? AI_INFLIGHT_WAIT_S
            : (Number(data.retry_after) || res.retryAfter || 2);
        const n = aiStartWait(wait);
        aiAddNotice(`Juda tez yozyapsiz. ${n} soniyadan so'ng qayta urinib ko'ring.`, [aiRetryAction()]);
        return;
    }
    if (err === 'forbidden') { aiAddNotice(AI_TEXT.forbidden); return; }
    if (err === 'bad_request') { aiAddNotice(AI_TEXT.badRequest); return; }
    aiAddNotice(err === 'busy' ? AI_TEXT.busy : AI_TEXT.server, [aiRetryAction()]);
}

async function aiSend(text, opts) {
    const o = opts || {};
    const message = String(text || '').trim().slice(0, AI_MSG_MAX);
    if (!message || !aiCanSend()) return;
    const epoch = aiChat.epoch;
    if (!o.retry) aiAddUser(message);
    aiChat.pending = { text: message };
    aiChat.sending = true;
    aiSync();
    const typing = aiShowTyping();
    aiScrollBottom();
    let res = null;
    let failure = null;
    try {
        const body = { message: message, history: aiChat.history.slice(-AI_HISTORY_MAX) };
        if (aiChat.context) body.context = { type: aiChat.context.type, key: aiChat.context.key };
        res = await api('ai/chat', body, { timeoutMs: AI_TIMEOUT_MS, withStatus: true });
    } catch (e) {
        failure = (e && e.message === 'no-initdata') ? 'forbidden' : 'network';
    }
    typing.remove();
    aiChat.sending = false;
    if (epoch === aiChat.epoch) aiHandleResult(message, res, failure);
    aiSync();
}

function aiSubmit() {
    const input = document.getElementById('ai-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text || !aiCanSend()) return;
    input.value = '';
    aiAutosize();
    aiSend(text);
}

function aiNewChat() {
    if (aiChat.sending) return;
    aiChat.epoch++;
    aiChat.history = [];
    aiChat.pending = null;
    aiSetContext(null);
    aiThread().querySelectorAll('.ai-msg:not(.ai-greeting)').forEach(m => m.remove());
    aiSync();
    const log = aiLog();
    if (log) log.scrollTop = 0;
}

// textarea: 1–4 qator (CSS max-height), keyin ichida skroll
function aiAutosize() {
    const input = document.getElementById('ai-input');
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = (input.scrollHeight + (input.offsetHeight - input.clientHeight)) + 'px';
}

function onAiTabShown() {
    aiSync();
    aiAutosize();
    aiScrollBottom();
}

// Tana sheet'i, detal, kasalliklar: AI tabi, kontekst chipi, fokus (avtomatik yuborilmaydi).
// draft — yozish maydoni bo'sh bo'lsa unga qo'yiladigan matn (masalan qidiruv so'rovi)
function openAiChat(context, draft) {
    showTab('tab-ai');
    if (context) aiSetContext(context);
    const input = document.getElementById('ai-input');
    if (input && draft && !input.disabled && !input.value.trim()) {
        input.value = String(draft).slice(0, AI_MSG_MAX);
        aiAutosize();
        aiSync();
    }
    if (input && !input.disabled) {
        try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); }
    }
}

// Klaviatura: yozish paneli klaviatura ustida qoladi, pastki nav yashirinadi (visualViewport / viewportChanged)
function initAiKeyboard() {
    const input = document.getElementById('ai-input');
    const container = document.getElementById('app-container');
    if (!input || !container) return;
    const vv = window.visualViewport || null;
    const height = () => (vv ? vv.height : window.innerHeight);
    let base = height();
    let width = window.innerWidth;
    const update = () => {
        const h = height();
        if (window.innerWidth !== width) { width = window.innerWidth; base = h; }       // ekran burildi
        const focused = document.activeElement === input;
        if (!focused) base = Math.max(base, h);
        const open = focused && document.body.classList.contains('ai-tab-on') && base - h > 120;
        const was = document.body.classList.contains('kb-open');
        document.body.classList.toggle('kb-open', open);
        container.style.height = open ? Math.round(h) + 'px' : '';
        if (open && !was) {
            try { window.scrollTo(0, 0); } catch (e) { /* yo'q */ }
            aiScrollBottom();
        }
    };
    if (vv) vv.addEventListener('resize', update);
    window.addEventListener('resize', update);
    if (tg && tg.onEvent) {
        try { tg.onEvent('viewportChanged', update); } catch (e) { /* eski klient */ }
    }
    input.addEventListener('focus', update);
    input.addEventListener('blur', update);
}

function initAiChat() {
    const input = document.getElementById('ai-input');
    const send = document.getElementById('ai-send');
    if (!input || !send) return;
    const quick = document.getElementById('ai-quick');
    if (quick) {
        AI_QUICK_TOPICS.forEach(id => {
            const item = FIRST_AID_ITEMS.find(i => i.id === id);
            if (!item) return;
            const label = displayTitle(item.title);
            const chip = aiEl('button', 'ai-chip');
            chip.type = 'button';
            chip.setAttribute('data-topic', id);
            chip.appendChild(aiIcon(iconName(item.icon)));
            chip.appendChild(aiEl('span', null, label));
            chip.addEventListener('click', () => aiSend(label));
            quick.appendChild(chip);
        });
    }
    input.addEventListener('input', () => { aiAutosize(); aiSync(); });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {        // Ctrl/Cmd+Enter — yuborish
            e.preventDefault();
            aiSubmit();
        }
    });
    send.addEventListener('click', aiSubmit);
    const fresh = document.getElementById('ai-new-chat');
    if (fresh) fresh.addEventListener('click', aiNewChat);
    const clear = document.getElementById('ai-context-clear');
    if (clear) clear.addEventListener('click', () => {
        aiSetContext(null);
        if (!input.disabled) input.focus();
    });
    initAiKeyboard();
    aiSync();
}

document.addEventListener('DOMContentLoaded', initAiChat);
// ═══ /AI SUHBAT TABI ═══

// ── AI tabi: Premium taklif kartasi (bepul savol ishlatilgach). To'lov — mavjud buyPremium (openInvoice) ──
function aiOfferPlan() {
    const r = document.querySelector('#ai-premium-offer input[name="ai-offer-plan"]:checked');
    return r ? r.value : 'buy_plus_30';
}

function renderAiOfferFeatures() {
    const list = document.getElementById('ai-offer-features');
    if (!list) return;
    list.innerHTML = '';
    (PREMIUM_FEATURES[aiOfferPlan()] || []).forEach(text => {
        const li = document.createElement('li');
        li.innerHTML = `<span class="pm-check" aria-hidden="true">${svgIcon('check')}</span><span></span>`;
        li.lastChild.textContent = text;
        list.appendChild(li);
    });
}

// Ko'rsatiladi: bepul foydalanuvchi va AI kvotasi 0 (bepul savol ishlatilgan). Premium bo'lsa — yo'q.
// Karta ko'rinsa suhbatdagi yozish paneli o'chiriladi (aiSync).
function renderAiOffer(s) {
    const card = document.getElementById('ai-premium-offer');
    if (!card) return;
    const show = !!s && !s.is_premium && s.ai_remaining === 0 && !(s.ai_limit > 1);    // limit > 1 — Premium tarif
    card.hidden = !show;
    aiChat.offerShown = show;
    if (show) renderAiOfferFeatures();
    aiSync();
}

function showAiPremiumOffer() {       // /api/ai/chat "limit" javobida (holat yuklanmagan bo'lsa ham) shu karta
    renderAiOffer({ is_premium: false, ai_remaining: 0 });
}

document.addEventListener('DOMContentLoaded', () => {
    const card = document.getElementById('ai-premium-offer');
    if (!card) return;
    card.querySelectorAll('input[name="ai-offer-plan"]').forEach(r => r.addEventListener('change', () => {
        if (tg && tg.HapticFeedback) tg.HapticFeedback.selectionChanged();
        renderAiOfferFeatures();
    }));
    document.getElementById('ai-offer-buy').addEventListener('click', () => {
        if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
        buyPremium(aiOfferPlan());
    });
    renderAiOfferFeatures();
});

// ZAXIRA yo'l: Premium'ni bot orqali (deep link) sotib olish — eski mantiq o'zgarmagan
function openPremiumDeepLink(plan) {
    var tg = window.Telegram && window.Telegram.WebApp;
    var botUsername = BOT_USERNAME;
    var url = 'https://t.me/' + botUsername + '?start=' + plan;
    if (tg) {
        tg.openTelegramLink(url);
    } else {
        window.open(url, '_blank');
    }
}

// Javob kelguncha (va invoice ochiq turganda) tugmani qayta bosib bo'lmasin
let premiumBuying = false;
let premiumBuyingTimer = null;
function setPremiumBuying(on) {
    premiumBuying = on;
    clearTimeout(premiumBuyingTimer);
    if (on) {
        // Himoya: invoice yopilgani haqida callback kelmasa tugma abadiy qotib qolmasin
        premiumBuyingTimer = setTimeout(() => { premiumBuying = false; }, 120000);
    }
}

// tg.openInvoice natijasi. 'cancelled' — jim yopiladi. tg.close() CHAQIRILMAYDI.
function handleInvoiceStatus(status) {
    if (status === 'paid') {
        // successful_payment botga biroz kechikib kelishi mumkin
        notify("To'lov qabul qilindi! Premium bir necha soniyada faollashadi.");
        invalidateAppState();
    } else if (status === 'failed') {
        notify("To'lov amalga oshmadi. Qayta urinib ko'ring.");
    } else if (status === 'pending') {
        notify("To'lov tekshirilmoqda...");
    }
}

// Premium sotib olish: Mini App ichida Stars invoice (/api/invoice -> tg.openInvoice), botga chiqmasdan.
// Narx va payload FAQAT serverdan keladi (chegirma ham serverda avtomatik).
// ZAXIRA (initData yo'q, openInvoice yo'q, fetch xato/timeout, 5xx/403/429): avvalgi deep link (?start=buy_...).
async function buyPremium(plan) {
    if (premiumBuying) return;
    if (!canUseApi() || !tg || typeof tg.openInvoice !== 'function') {
        openPremiumDeepLink(plan);
        return;
    }
    setPremiumBuying(true);
    let url;
    try {
        const r = await api('invoice', { plan: plan });
        if (!r || typeof r.ok !== 'boolean') throw new Error('bad-invoice');
        if (!r.ok) {
            if (r.error === 'not_eligible') {            // masalan, allaqachon yuqoriroq tarif: server xabari (oddiy matn)
                setPremiumBuying(false);
                notify(r.message || "Bu tarifni sotib olib bo'lmaydi.");
                return;
            }
            throw new Error(r.error || 'invoice-failed');
        }
        if (typeof r.url !== 'string' || !r.url) throw new Error('no-url');
        url = r.url;
    } catch (err) {
        console.warn("[premium] /api/invoice ishlamadi, deep link ishlatiladi:", err);
        setPremiumBuying(false);
        openPremiumDeepLink(plan);
        return;
    }
    try {
        tg.openInvoice(url, (status) => {
            setPremiumBuying(false);
            handleInvoiceStatus(status);
        });
    } catch (err) {
        console.warn("[premium] tg.openInvoice ishlamadi, deep link ishlatiladi:", err);
        setPremiumBuying(false);
        openPremiumDeepLink(plan);
    }
}

