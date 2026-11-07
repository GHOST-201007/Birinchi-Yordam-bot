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

// Mini App -> bot API (/api/...). Foydalanuvchi faqat tekshirilgan initData orqali aniqlanadi.
// initData yo'q bo'lsa yoki so'rov xato bersa istisno ko'tariladi: chaqiruvchi URL-parametr zaxira yo'liga o'tadi.
function canUseApi() {
    return !!(tg && tg.initData);
}

async function api(path, extra) {
    const initData = (tg && tg.initData) || '';
    if (!initData) throw new Error('no-initdata');
    const ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), 8000) : null;
    try {
        const r = await fetch('/api/' + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(Object.assign({ init_data: initData }, extra || {})),
            signal: ctrl ? ctrl.signal : undefined
        });
        if (!r.ok) throw new Error('http-' + r.status);
        return await r.json();
    } finally {
        if (timer) clearTimeout(timer);
    }
}

// /api/state natijasi — butun ilova uchun BITTA nusxa (header, kunlik bonus, baraban).
// Bir vaqtda bir nechta so'rov bo'lsa ham tarmoqqa bitta so'rov ketadi.
const AppState = { data: null, ts: 0, inflight: null };

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
        scoreEl.style.display = 'inline-block';
    }
}

// Mini app ochilganda (menyu tugmasidan ham — URL'da hech narsa bo'lmaydi) ball serverdan olinadi
document.addEventListener('DOMContentLoaded', () => {
    getAppState(60000).then((s) => { if (s) setGlobalScore(s.score); });
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

    function updateBtn() {
        const btn = getBackBtn();
        if (!btn) return;
        if (stack.length > 0) {
            btn.classList.remove('hidden');
        } else {
            btn.classList.add('hidden');
        }
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
            scoreEl.style.display = 'inline-block';
        }
    });
}

// ═══════════════════════════════════════════════════════════════════
// DARK / LIGHT MODE
// ═══════════════════════════════════════════════════════════════════

function initTheme() {
    const saved = SafeStorage.getItem('theme') || 'light';
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        if (saved === 'dark') {
            document.body.classList.add('dark-mode');
            btn.textContent = '☀️';
        } else {
            document.body.classList.remove('dark-mode');
            btn.textContent = '🌙';
        }
    }
}

function bindThemeToggle() {
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.onclick = () => {
            const isDark = document.body.classList.toggle('dark-mode');
            btn.textContent = isDark ? '☀️' : '🌙';
            SafeStorage.setItem('theme', isDark ? 'dark' : 'light');
        };
    }
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
            bindThemeToggle();

            // Safe Telegram User Info Setup inside DOMContentLoaded
            if (tg) {
                const user = tg.initDataUnsafe ? tg.initDataUnsafe.user : null;
                if (user) {
                    const nameEl = document.getElementById('user-name');
                    if (nameEl) nameEl.innerText = `${user.first_name} ${user.last_name || ''}`.trim();

                    const avatarEl = document.getElementById('user-avatar');
                    if (avatarEl && user.photo_url) {
                        const img = document.createElement('img');
                        img.src = user.photo_url;
                        img.alt = '';
                        img.className = 'avatar-img';
                        avatarEl.replaceChildren(img);
                    }
                }
            }

            initTabs();
            renderFirstAidGrid();
            renderDiseases(DISEASES_DATA);
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
function initTabs() {
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');

            navButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));

            btn.classList.add('active');
            document.getElementById(targetTab).classList.add('active');

            // Switching main tabs clears the navigation stack
            AppNavigation.pop();
        });
    });
}

// RENDER FIRST AID CARDS
function renderFirstAidGrid() {
    const grid = document.getElementById('first-aid-grid');
    grid.innerHTML = '';

    FIRST_AID_ITEMS.forEach(item => {
        const card = document.createElement('div');
        card.className = 'first-aid-card';
        card.setAttribute('data-id', item.id);

        card.innerHTML = `
            <div class="card-icon" style="background-color: ${item.bgColor}; color: ${item.color};">
                <i class="fa-solid ${item.icon}"></i>
            </div>
            <h3>${item.title}</h3>
            <p>${item.desc}</p>
        `;

        card.addEventListener('click', () => {
            openFirstAidDetail(item);
        });

        grid.appendChild(card);
    });
}

// OPEN FIRST AID DETAILS
function openFirstAidDetail(item) {
    const overlay = document.getElementById('overlay-details');
    const title = document.getElementById('overlay-title');
    const body = document.getElementById('overlay-body-content');

    title.innerText = item.title;

    // Urgency badge
    const urgencyMap = {
        critical: { label: 'KRITIK', color: '#ff3b30', bg: 'rgba(255,59,48,0.12)' },
        high: { label: 'MUHIM', color: '#ff9500', bg: 'rgba(255,149,0,0.12)' },
        medium: { label: "O'RTA", color: '#007aff', bg: 'rgba(0,122,255,0.12)' }
    };
    const urg = urgencyMap[item.urgency] || urgencyMap.medium;

    // Steps HTML
    let stepsHtml = '';
    item.steps.forEach((step, idx) => {
        stepsHtml += `
            <div class="instruction-step">
                <div class="step-num">${idx + 1}</div>
                <div class="step-text">${step}</div>
            </div>
        `;
    });

    // Symptoms HTML
    let symptomsHtml = '';
    if (item.symptoms && item.symptoms.length) {
        symptomsHtml = `
            <div class="detail-section">
                <div class="detail-section-title"><span class="detail-icon">🩺</span> Alomatlar</div>
                <div class="detail-tags-grid">
                    ${item.symptoms.map(s => `<div class="symptom-tag">${s}</div>`).join('')}
                </div>
            </div>`;
    }

    // When to call 103
    let call103Html = '';
    if (item.whenToCall103 && item.whenToCall103.length) {
        call103Html = `
            <div class="call103-card">
                <div class="call103-header">
                    <span class="call103-icon">📞</span>
                    <span>Qachon <strong>103</strong> chaqirish kerak?</span>
                </div>
                <ul class="call103-list">
                    ${item.whenToCall103.map(c => `<li>${c}</li>`).join('')}
                </ul>
                <a href="tel:103" class="call103-btn">
                    📞 103 — Tez yordam
                </a>
            </div>`;
    }

    // Tips HTML
    let tipsHtml = '';
    if (item.tips && item.tips.length) {
        tipsHtml = `
            <div class="detail-section">
                <div class="detail-section-title"><span class="detail-icon">💡</span> Foydali maslahatlar</div>
                ${item.tips.map(t => `<div class="tip-item"><span class="tip-dot">•</span><span>${t}</span></div>`).join('')}
            </div>`;
    }

    body.innerHTML = `
        <div class="detail-urgency-badge" style="background:${urg.bg}; color:${urg.color};">
            ⚡ ${urg.label} HOLAT
        </div>
        <p class="detail-desc">${item.desc}</p>

        ${symptomsHtml}

        <div class="detail-section">
            <div class="detail-section-title"><span class="detail-icon">🛠️</span> Bosqichma-bosqich yordam</div>
            <div style="margin-top: 10px;">${stepsHtml}</div>
        </div>

        <div class="prohibited-card">
            <div class="prohibited-title">🚫 Mutlaqo taqiqlanadi</div>
            <p>${item.prohibited}</p>
        </div>

        ${tipsHtml}
        ${call103Html}
    `;

    overlay.classList.add('active');
    body.scrollTop = 0;

    // Push navigation state
    AppNavigation.push({
        type: 'firstaid-detail',
        close: function () {
            overlay.classList.remove('active');
            AppNavigation.pop();
        }
    });
}

// RENDER DISEASES
function renderDiseases(data) {
    const container = document.getElementById('disease-list-container');
    container.innerHTML = '';

    if (data.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding: 30px; color: var(--hint-color);">Natija topilmadi 😕</div>`;
        return;
    }

    data.forEach(item => {
        const div = document.createElement('div');
        div.className = 'disease-item';

        div.innerHTML = `
            <div class="disease-info">
                <h4>${item.name}</h4>
                <span>📁 ${item.cat}</span>
            </div>
            <i class="fa-solid fa-chevron-right"></i>
        `;

        div.addEventListener('click', () => {
            openDiseaseDetail(item);
        });

        container.appendChild(div);
    });
}

// OPEN DISEASE DETAILS
function openDiseaseDetail(item) {
    const overlay = document.getElementById('overlay-details');
    const title = document.getElementById('overlay-title');
    const body = document.getElementById('overlay-body-content');

    title.innerText = item.name;

    const catColors = {
        'Infeksiya': '#ff9500', 'Nafas': '#007aff', 'Yurak': '#ff3b30',
        'Oshqozon': '#34c759', 'Asab': '#af52de', 'Ruhiy': '#af52de',
        'Teriga': '#ff9500', "Ko'z": '#007aff', 'Tish': '#34c759',
        'Travma': '#ff3b30', 'Miya': '#ff3b30', 'Buyrak': '#007aff',
        'Tayanch': '#ff9500', 'Endokrin': '#34c759', 'Jigar': '#ff9500'
    };
    const catColor = catColors[item.cat] || '#248bcf';

    body.innerHTML = `
        <div style="display:inline-flex; align-items:center; gap:8px; background:${catColor}20; color:${catColor}; padding:5px 12px; border-radius:20px; font-size:13px; font-weight:600; margin-bottom:14px;">
            📁 ${item.cat}
        </div>

        <div class="detail-section">
            <div class="detail-section-title"><span class="detail-icon">📋</span> Kasallik tavsifi</div>
            <p class="detail-desc-text">${item.desc}</p>
        </div>

        <div class="detail-section">
            <div class="detail-section-title"><span class="detail-icon">💊</span> Birinchi yordam va chora</div>
            <div class="aid-card">
                <p>${item.aid}</p>
            </div>
        </div>

        <div class="tip-item" style="margin-top:12px; padding:12px 14px; background:var(--secondary-bg-color); border-radius:10px;">
            <span>⚠️</span>
            <span style="font-size:13px; color:var(--hint-color);">Har qanday kasallikda o'z-o'zini davolashdan ko'ra, malakali shifokor ko'rigidan o'tish tavsiya etiladi.</span>
        </div>
    `;

    overlay.classList.add('active');
    body.scrollTop = 0;

    // Push navigation state
    AppNavigation.push({
        type: 'disease-detail',
        close: function () {
            overlay.classList.remove('active');
            AppNavigation.pop();
        }
    });
}

// SEARCH FUNCTIONALITY
function initSearch() {
    const input = document.getElementById('disease-search-input');
    const clearBtn = document.getElementById('search-clear-btn');

    input.addEventListener('input', (e) => {
        const val = e.target.value.toLowerCase().trim();

        if (val.length > 0) {
            clearBtn.style.display = 'block';
        } else {
            clearBtn.style.display = 'none';
        }

        const filtered = DISEASES_DATA.filter(item =>
            item.name.toLowerCase().includes(val) ||
            item.cat.toLowerCase().includes(val)
        );

        renderDiseases(filtered);
    });

    clearBtn.addEventListener('click', () => {
        input.value = '';
        clearBtn.style.display = 'none';
        renderDiseases(DISEASES_DATA);
    });
}

// OVERLAY CONTROLS
function initOverlay() {
    const closeBtn = document.getElementById('close-overlay-btn');
    const overlay = document.getElementById('overlay-details');

    closeBtn.addEventListener('click', () => {
        overlay.classList.remove('active');
        AppNavigation.pop();
    });
}

// CALCULATORS CONTROL
function switchCalc(type) {
    const btns = document.querySelectorAll('.calc-tab-btn');
    const sections = document.querySelectorAll('.calc-section');

    btns.forEach(b => b.classList.remove('active'));
    sections.forEach(s => s.classList.remove('active'));

    if (type === 'bmi') {
        btns[0].classList.add('active');
        document.getElementById('calc-bmi-section').classList.add('active');
    } else if (type === 'water') {
        btns[1].classList.add('active');
        document.getElementById('calc-water-section').classList.add('active');
    } else {
        btns[2].classList.add('active');
        document.getElementById('calc-calorie-section').classList.add('active');
    }
}

function initCalculators() {
    // BMI
    const btnBmi = document.getElementById('btn-calculate-bmi');
    btnBmi.addEventListener('click', () => {
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
        let pointerPos = 0; // % from left

        if (bmi < 18.5) {
            status = "Kam vazn ⚠️";
            desc = "Sizning tana vazningiz me'yordan past. Sog'lom va to'yimli ovqatlanishga harakat qiling.";
            pointerPos = 15;
        } else if (bmi >= 18.5 && bmi < 25) {
            status = "Normal vazn ✅";
            desc = "Sizning vazningiz mutlaqo me'yorda! Faol bo'ling va to'g'ri ovqatlanishda davom eting.";
            pointerPos = 40;
        } else if (bmi >= 25 && bmi < 30) {
            status = "Ortiqcha vazn ⚠️";
            desc = "Tana vazningiz me'yordan bir oz yuqori. Jismoniy mashqlar va shirinliklarni kamaytirish tavsiya etiladi.";
            pointerPos = 65;
        } else {
            status = "Semizlik 🚨";
            desc = "Sizda semizlik darajasi aniqlandi. Sog'lig'ingiz uchun shifokor-dietolog bilan maslahatlashishni tavsiya qilamiz.";
            pointerPos = 90;
        }

        document.getElementById('bmi-status').innerText = status;
        document.getElementById('bmi-description').innerText = desc;
        document.getElementById('bmi-gauge-pointer').style.left = `${pointerPos}%`;
        document.getElementById('bmi-result-card').style.display = 'flex';

        // BMI tarixiga saqlash
        saveHistory('bmi', { bmi: bmi.toFixed(1), weight, height, status: status.replace(/[^a-zA-Z\s']/g, '').trim() });
        renderHistoryLog();
    });

    // Water
    const btnWater = document.getElementById('btn-calculate-water');
    btnWater.addEventListener('click', () => {
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

        document.getElementById('water-result-card').style.display = 'flex';

        // Suv tarixiga saqlash
        saveHistory('water', { liters: (minWater / 1000).toFixed(1), weight });
        renderHistoryLog();
    });

    // Calorie
    const btnCalorie = document.getElementById('btn-calculate-calorie');
    btnCalorie.addEventListener('click', () => {
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

        document.getElementById('calorie-result-card').style.display = 'flex';
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
    document.getElementById('quiz-q-num').innerText = `Savol ${quizState.current + 1}/${total}`;
    document.getElementById('quiz-score-live').innerText = `\uD83C\uDFAF ${quizState.score} ball`;
    document.getElementById('quiz-progress-fill').style.width = `${((quizState.current + 1) / total) * 100}%`;
    document.getElementById('quiz-question-text').innerText = q.q;

    const container = document.getElementById('quiz-options-container');
    container.innerHTML = '';
    quizState.answered = false;

    q.options.forEach((opt, idx) => {
        const btn = document.createElement('button');
        btn.className = 'quiz-option-btn';
        btn.innerText = opt;
        btn.addEventListener('click', () => handleAnswer(idx, btn));
        container.appendChild(btn);
    });
}

function handleAnswer(idx, btn) {
    if (quizState.answered) return;
    quizState.answered = true;

    const correct = QUIZ_QUESTIONS[quizState.current].answer;
    const allBtns = document.querySelectorAll('.quiz-option-btn');

    allBtns.forEach(b => b.disabled = true);

    if (idx === correct) {
        btn.classList.add('correct');
        quizState.score += 10;
    } else {
        btn.classList.add('wrong');
        allBtns[correct].classList.add('correct');
    }

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

    let icon = '\uD83D\uDE22', title = 'Ko\'proq o\'qing!', desc = 'Hali siz uchun o\'rganish vaqti!';
    if (score >= 80) { icon = '\uD83C\uDFC6'; title = 'Barakallo!'; desc = 'Siz juda yaxshi bilasiz!'; }
    else if (score >= 50) { icon = '\uD83D\uDCAA'; title = 'Yaxshi natija!'; desc = 'Ozgina ko\'proq o\'qisangiz mukammal bo\'ladi!'; }

    document.getElementById('quiz-result-icon').innerText = icon;
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

function initHistory() {
    renderHistoryLog();
    const btnBmi = document.getElementById('btn-clear-bmi-history');
    if (btnBmi) {
        btnBmi.addEventListener('click', () => {
            SafeStorage.removeItem('history_bmi');
            renderHistoryLog();
        });
    }
    const btnWater = document.getElementById('btn-clear-water-history');
    if (btnWater) {
        btnWater.addEventListener('click', () => {
            SafeStorage.removeItem('history_water');
            renderHistoryLog();
        });
    }
}

function switchHistoryTab(type) {
    document.querySelectorAll('.history-tab-btn').forEach((b, i) => {
        b.classList.toggle('active', (i === 0 && type === 'bmi') || (i === 1 && type === 'water'));
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

function renderBmiLog() {
    const arr = JSON.parse(SafeStorage.getItem('history_bmi') || '[]').slice().reverse();
    const log = document.getElementById('bmi-history-log');
    const empty = document.getElementById('bmi-chart-empty');
    log.innerHTML = '';
    if (arr.length === 0) { empty.style.display = 'flex'; return; }
    empty.style.display = 'none';
    arr.forEach(entry => {
        const badgeClass = parseFloat(entry.bmi) < 18.5 ? 'low' : parseFloat(entry.bmi) < 25 ? 'normal' : 'high';
        const badgeText = parseFloat(entry.bmi) < 18.5 ? 'Kam' : parseFloat(entry.bmi) < 25 ? 'Normal' : 'Yuqori';
        log.innerHTML += `
        <div class="history-log-item">
            <span class="h-date">${entry.date}</span>
            <span class="h-val">BMI: ${entry.bmi}</span>
            <span class="h-badge ${badgeClass}">${badgeText}</span>
        </div>`;
    });
}

function renderWaterLog() {
    const arr = JSON.parse(SafeStorage.getItem('history_water') || '[]').slice().reverse();
    const log = document.getElementById('water-history-log');
    const empty = document.getElementById('water-chart-empty');
    log.innerHTML = '';
    if (arr.length === 0) { empty.style.display = 'flex'; return; }
    empty.style.display = 'none';
    arr.forEach(entry => {
        log.innerHTML += `
        <div class="history-log-item">
            <span class="h-date">${entry.date}</span>
            <span class="h-val">${entry.liters} L</span>
            <span class="h-badge normal">Hisoblandi</span>
        </div>`;
    });
}

function drawChart(type) {
    const canvasId = type === 'bmi' ? 'bmi-chart' : 'water-chart';
    const key = `history_${type}`;
    const arr = JSON.parse(SafeStorage.getItem(key) || '[]');
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');

    canvas.width = canvas.parentElement.clientWidth - 32;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (arr.length < 2) return;

    const values = arr.map(e => parseFloat(type === 'bmi' ? e.bmi : e.liters));
    const labels = arr.map(e => e.date);
    const min = Math.min(...values) * 0.9;
    const max = Math.max(...values) * 1.1;
    const w = canvas.width;
    const h = canvas.height;
    const pad = { top: 16, bottom: 30, left: 10, right: 10 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;

    const xStep = chartW / (values.length - 1);
    const toX = i => pad.left + i * xStep;
    const toY = v => pad.top + chartH - ((v - min) / (max - min || 1)) * chartH;

    // Gradient fill
    const grad = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    grad.addColorStop(0, 'rgba(0,122,255,0.25)');
    grad.addColorStop(1, 'rgba(0,122,255,0.01)');

    ctx.beginPath();
    ctx.moveTo(toX(0), toY(values[0]));
    values.forEach((v, i) => { if (i > 0) ctx.lineTo(toX(i), toY(v)); });
    ctx.lineTo(toX(values.length - 1), h - pad.bottom);
    ctx.lineTo(toX(0), h - pad.bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.moveTo(toX(0), toY(values[0]));
    values.forEach((v, i) => { if (i > 0) ctx.lineTo(toX(i), toY(v)); });
    ctx.strokeStyle = '#007aff';
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Dots and labels
    values.forEach((v, i) => {
        ctx.beginPath();
        ctx.arc(toX(i), toY(v), 4, 0, Math.PI * 2);
        ctx.fillStyle = '#007aff';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Date labels (every 2nd if many)
        if (arr.length <= 7 || i % 2 === 0) {
            ctx.fillStyle = '#888';
            ctx.font = '9px Outfit, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(labels[i], toX(i), h - 6);
        }
    });
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

const FRONT_BODY_SVG = `
<svg viewBox="0 0 280 540" class="human-body-svg">
    <defs>
        <filter id="glowPart" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#14b8a6" flood-opacity="0.7"/>
        </filter>
        <radialGradient id="organGrad" cx="50%" cy="30%" r="70%">
            <stop offset="0%" stop-color="#14b8a6" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#0f766e" stop-opacity="0.15"/>
        </radialGradient>
    </defs>

    <!-- Head / Bosh -->
    <g class="body-part" data-part="head" onclick="openBodyMapModal('head')">
        <rect x="90" y="10" width="100" height="100" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 140 24 C 118 24 106 38 106 62 C 106 82 120 100 134 104 L 146 104 C 160 100 174 82 174 62 C 174 38 162 24 140 24 Z" class="part-shape"/>
        <circle cx="140" cy="62" r="3.5" fill="#5eead4" class="part-pin"/>
        <rect x="122" y="54" width="36" height="16" class="part-label-bg"/>
        <text x="140" y="66" class="part-label">Bosh</text>
    </g>

    <!-- Neck / Bo'yin -->
    <g class="body-part" data-part="neck" onclick="openBodyMapModal('neck')">
        <rect x="110" y="90" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 128 104 L 152 104 L 156 122 L 124 122 Z" class="part-shape"/>
        <circle cx="140" cy="113" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="140" y="116" class="part-label" style="font-size: 8px;">Bo'yin</text>
    </g>

    <!-- Left Shoulder / Chap Yelka -->
    <g class="body-part" data-part="left_shoulder" onclick="openBodyMapModal('left_shoulder')">
        <rect x="60" y="120" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 124 122 L 96 126 C 86 130 80 140 82 152 L 102 150 C 108 138 116 130 124 128 Z" class="part-shape"/>
        <circle cx="90" cy="138" r="3" fill="#5eead4" class="part-pin"/>
        <text x="64" y="142" class="part-label" style="font-size: 8px;">Yelka</text>
    </g>

    <!-- Right Shoulder / O'ng Yelka -->
    <g class="body-part" data-part="right_shoulder" onclick="openBodyMapModal('right_shoulder')">
        <rect x="160" y="120" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 156 122 L 184 126 C 194 130 200 140 198 152 L 178 150 C 172 138 164 130 156 128 Z" class="part-shape"/>
        <circle cx="190" cy="138" r="3" fill="#5eead4" class="part-pin"/>
        <text x="216" y="142" class="part-label" style="font-size: 8px;">Yelka</text>
    </g>

    <!-- Chest / Ko'krak -->
    <g class="body-part" data-part="chest" onclick="openBodyMapModal('chest')">
        <rect x="90" y="124" width="100" height="65" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 104 128 C 120 124 160 124 176 128 C 182 144 180 178 174 188 C 158 192 122 192 106 188 C 100 178 98 144 104 128 Z" class="part-shape"/>
        <circle cx="140" cy="155" r="3.5" fill="#5eead4" class="part-pin"/>
        <rect x="115" y="146" width="50" height="18" class="part-label-bg"/>
        <text x="140" y="159" class="part-label">Ko'krak</text>
    </g>

    <!-- Left Arm / Chap Qo'l -->
    <g class="body-part" data-part="left_arm" onclick="openBodyMapModal('left_arm')">
        <rect x="50" y="150" width="50" height="90" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 80 154 L 98 152 L 90 236 L 72 232 Z" class="part-shape"/>
        <circle cx="82" cy="192" r="3" fill="#5eead4" class="part-pin"/>
        <text x="56" y="196" class="part-label" style="font-size: 8px;">Qo'l</text>
    </g>

    <!-- Right Arm / O'ng Qo'l -->
    <g class="body-part" data-part="right_arm" onclick="openBodyMapModal('right_arm')">
        <rect x="180" y="150" width="50" height="90" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 200 154 L 182 152 L 190 236 L 208 232 Z" class="part-shape"/>
        <circle cx="198" cy="192" r="3" fill="#5eead4" class="part-pin"/>
        <text x="224" y="196" class="part-label" style="font-size: 8px;">Qo'l</text>
    </g>

    <!-- Abdomen / Qorin -->
    <g class="body-part" data-part="abdomen" onclick="openBodyMapModal('abdomen')">
        <rect x="100" y="185" width="80" height="70" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 106 190 C 122 194 158 194 174 190 C 176 216 172 242 168 250 C 154 254 126 254 112 250 C 108 242 104 216 106 190 Z" class="part-shape"/>
        <circle cx="140" cy="218" r="3.5" fill="#5eead4" class="part-pin"/>
        <rect x="120" y="209" width="40" height="18" class="part-label-bg"/>
        <text x="140" y="222" class="part-label">Qorin</text>
    </g>

    <!-- Left Hand / Chap Kaft -->
    <g class="body-part" data-part="left_hand" onclick="openBodyMapModal('left_hand')">
        <rect x="50" y="230" width="45" height="50" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 70 234 L 88 238 C 88 252 82 268 76 270 C 68 268 64 252 70 234 Z" class="part-shape"/>
        <circle cx="76" cy="254" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="54" y="258" class="part-label" style="font-size: 8px;">Kaft</text>
    </g>

    <!-- Right Hand / O'ng Kaft -->
    <g class="body-part" data-part="right_hand" onclick="openBodyMapModal('right_hand')">
        <rect x="185" y="230" width="45" height="50" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 210 234 L 192 238 C 192 252 198 268 204 270 C 212 268 216 252 210 234 Z" class="part-shape"/>
        <circle cx="204" cy="254" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="226" y="258" class="part-label" style="font-size: 8px;">Kaft</text>
    </g>

    <!-- Pelvis / Chanoq -->
    <g class="body-part" data-part="hip" onclick="openBodyMapModal('hip')">
        <rect x="100" y="250" width="80" height="45" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 112 252 C 126 256 154 256 168 252 C 174 274 168 290 156 294 L 124 294 C 112 290 106 274 112 252 Z" class="part-shape"/>
        <circle cx="140" cy="272" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="118" y="264" width="44" height="16" class="part-label-bg"/>
        <text x="140" y="276" class="part-label" style="font-size: 8.5px;">Chanoq</text>
    </g>

    <!-- Left Thigh / Chap Son -->
    <g class="body-part" data-part="left_thigh" onclick="openBodyMapModal('left_thigh')">
        <rect x="100" y="290" width="40" height="95" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 110 296 L 136 296 L 132 376 L 108 376 C 104 350 106 320 110 296 Z" class="part-shape"/>
        <circle cx="120" cy="336" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="106" y="328" width="28" height="16" class="part-label-bg"/>
        <text x="120" y="340" class="part-label" style="font-size: 8px;">Son</text>
    </g>

    <!-- Right Thigh / O'ng Son -->
    <g class="body-part" data-part="right_thigh" onclick="openBodyMapModal('right_thigh')">
        <rect x="140" y="290" width="40" height="95" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 144 296 L 170 296 C 174 320 176 350 172 376 L 148 376 L 144 296 Z" class="part-shape"/>
        <circle cx="160" cy="336" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="146" y="328" width="28" height="16" class="part-label-bg"/>
        <text x="160" y="340" class="part-label" style="font-size: 8px;">Son</text>
    </g>

    <!-- Left Knee / Chap Tizza -->
    <g class="body-part" data-part="left_knee" onclick="openBodyMapModal('left_knee')">
        <rect x="100" y="380" width="40" height="30" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <ellipse cx="120" cy="392" rx="13" ry="11" class="part-shape"/>
        <circle cx="120" cy="392" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="120" y="395" class="part-label" style="font-size: 8px;">Tizza</text>
    </g>

    <!-- Right Knee / O'ng Tizza -->
    <g class="body-part" data-part="right_knee" onclick="openBodyMapModal('right_knee')">
        <rect x="140" y="380" width="40" height="30" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <ellipse cx="160" cy="392" rx="13" ry="11" class="part-shape"/>
        <circle cx="160" cy="392" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="160" y="395" class="part-label" style="font-size: 8px;">Tizza</text>
    </g>

    <!-- Left Shin / Chap Boldir -->
    <g class="body-part" data-part="left_shin" onclick="openBodyMapModal('left_shin')">
        <rect x="100" y="405" width="40" height="75" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 108 406 L 132 406 L 126 476 L 112 476 Z" class="part-shape"/>
        <circle cx="119" cy="440" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="103" y="432" width="32" height="16" class="part-label-bg"/>
        <text x="119" y="444" class="part-label" style="font-size: 8px;">Boldir</text>
    </g>

    <!-- Right Shin / O'ng Boldir -->
    <g class="body-part" data-part="right_shin" onclick="openBodyMapModal('right_shin')">
        <rect x="140" y="405" width="40" height="75" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 148 406 L 172 406 L 168 476 L 154 476 Z" class="part-shape"/>
        <circle cx="161" cy="440" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="145" y="432" width="32" height="16" class="part-label-bg"/>
        <text x="161" y="444" class="part-label" style="font-size: 8px;">Boldir</text>
    </g>

    <!-- Left Foot / Chap Panja -->
    <g class="body-part" data-part="left_foot" onclick="openBodyMapModal('left_foot')">
        <rect x="90" y="475" width="45" height="35" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 110 478 L 128 478 L 132 506 L 98 506 Z" class="part-shape"/>
        <circle cx="114" cy="494" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="114" y="497" class="part-label" style="font-size: 8px;">Panja</text>
    </g>

    <!-- Right Foot / O'ng Panja -->
    <g class="body-part" data-part="right_foot" onclick="openBodyMapModal('right_foot')">
        <rect x="145" y="475" width="45" height="35" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 152 478 L 170 478 L 182 506 L 148 506 Z" class="part-shape"/>
        <circle cx="166" cy="494" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="166" y="497" class="part-label" style="font-size: 8px;">Panja</text>
    </g>
</svg>
`;


const BACK_BODY_SVG = `
<svg viewBox="0 0 280 540" class="human-body-svg">
    <!-- Head Back / Bosh ensa -->
    <g class="body-part" data-part="head" onclick="openBodyMapModal('head')">
        <rect x="90" y="10" width="100" height="100" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 140 24 C 118 24 106 38 106 62 C 106 82 120 100 134 104 L 146 104 C 160 100 174 82 174 62 C 174 38 162 24 140 24 Z" class="part-shape"/>
        <circle cx="140" cy="62" r="3.5" fill="#5eead4" class="part-pin"/>
        <rect x="115" y="54" width="50" height="16" class="part-label-bg"/>
        <text x="140" y="66" class="part-label">Ensa / Bosh</text>
    </g>

    <!-- Neck Back / Bo'yin -->
    <g class="body-part" data-part="neck" onclick="openBodyMapModal('neck')">
        <rect x="110" y="90" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 128 104 L 152 104 L 156 122 L 124 122 Z" class="part-shape"/>
        <circle cx="140" cy="113" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="140" y="116" class="part-label" style="font-size: 8px;">Bo'yin</text>
    </g>

    <!-- Left Shoulder Back -->
    <g class="body-part" data-part="left_shoulder" onclick="openBodyMapModal('left_shoulder')">
        <rect x="60" y="120" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 124 122 L 96 126 C 86 130 80 140 82 152 L 102 150 C 108 138 116 130 124 128 Z" class="part-shape"/>
        <circle cx="90" cy="138" r="3" fill="#5eead4" class="part-pin"/>
        <text x="64" y="142" class="part-label" style="font-size: 8px;">Yelka</text>
    </g>

    <!-- Right Shoulder Back -->
    <g class="body-part" data-part="right_shoulder" onclick="openBodyMapModal('right_shoulder')">
        <rect x="160" y="120" width="60" height="40" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 156 122 L 184 126 C 194 130 200 140 198 152 L 178 150 C 172 138 164 130 156 128 Z" class="part-shape"/>
        <circle cx="190" cy="138" r="3" fill="#5eead4" class="part-pin"/>
        <text x="216" y="142" class="part-label" style="font-size: 8px;">Yelka</text>
    </g>

    <!-- Spine / Bel va Orqa -->
    <g class="body-part" data-part="back" onclick="openBodyMapModal('back')">
        <rect x="90" y="120" width="100" height="135" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 104 128 C 120 124 160 124 176 128 C 182 156 178 220 172 250 C 156 254 124 254 108 250 C 102 220 98 156 104 128 Z" class="part-shape" style="fill: #115e59; stroke: #2dd4bf; stroke-width: 2;"/>
        <line x1="140" y1="128" x2="140" y2="250" stroke="#5eead4" stroke-width="2" stroke-dasharray="3 3"/>
        <circle cx="140" cy="180" r="4.5" fill="#fde047" class="part-pin"/>
        <rect x="110" y="170" width="60" height="20" class="part-label-bg" style="fill: rgba(15,23,42,0.9); stroke: #fde047; stroke-width: 1.5;"/>
        <text x="140" y="184" class="part-label" style="fill: #fde047; font-size: 11px;">🔙 Bel / Orqa</text>
    </g>

    <!-- Left Arm Back -->
    <g class="body-part" data-part="left_arm" onclick="openBodyMapModal('left_arm')">
        <rect x="50" y="150" width="50" height="90" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 80 154 L 98 152 L 90 236 L 72 232 Z" class="part-shape"/>
        <circle cx="82" cy="192" r="3" fill="#5eead4" class="part-pin"/>
        <text x="56" y="196" class="part-label" style="font-size: 8px;">Qo'l</text>
    </g>

    <!-- Right Arm Back -->
    <g class="body-part" data-part="right_arm" onclick="openBodyMapModal('right_arm')">
        <rect x="180" y="150" width="50" height="90" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 200 154 L 182 152 L 190 236 L 208 232 Z" class="part-shape"/>
        <circle cx="198" cy="192" r="3" fill="#5eead4" class="part-pin"/>
        <text x="224" y="196" class="part-label" style="font-size: 8px;">Qo'l</text>
    </g>

    <!-- Left Hand Back -->
    <g class="body-part" data-part="left_hand" onclick="openBodyMapModal('left_hand')">
        <rect x="50" y="230" width="45" height="50" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 70 234 L 88 238 C 88 252 82 268 76 270 C 68 268 64 252 70 234 Z" class="part-shape"/>
        <circle cx="76" cy="254" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="54" y="258" class="part-label" style="font-size: 8px;">Kaft</text>
    </g>

    <!-- Right Hand Back -->
    <g class="body-part" data-part="right_hand" onclick="openBodyMapModal('right_hand')">
        <rect x="185" y="230" width="45" height="50" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 210 234 L 192 238 C 192 252 198 268 204 270 C 212 268 216 252 210 234 Z" class="part-shape"/>
        <circle cx="204" cy="254" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="226" y="258" class="part-label" style="font-size: 8px;">Kaft</text>
    </g>

    <!-- Pelvis / Dumba -->
    <g class="body-part" data-part="hip" onclick="openBodyMapModal('hip')">
        <rect x="100" y="250" width="80" height="45" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 112 252 C 126 256 154 256 168 252 C 174 274 168 290 156 294 L 124 294 C 112 290 106 274 112 252 Z" class="part-shape"/>
        <circle cx="140" cy="272" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="118" y="264" width="44" height="16" class="part-label-bg"/>
        <text x="140" y="276" class="part-label" style="font-size: 8.5px;">Dumba</text>
    </g>

    <!-- Left Thigh Back -->
    <g class="body-part" data-part="left_thigh" onclick="openBodyMapModal('left_thigh')">
        <rect x="100" y="290" width="40" height="95" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 110 296 L 136 296 L 132 376 L 108 376 C 104 350 106 320 110 296 Z" class="part-shape"/>
        <circle cx="120" cy="336" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="106" y="328" width="28" height="16" class="part-label-bg"/>
        <text x="120" y="340" class="part-label" style="font-size: 8px;">Son</text>
    </g>

    <!-- Right Thigh Back -->
    <g class="body-part" data-part="right_thigh" onclick="openBodyMapModal('right_thigh')">
        <rect x="140" y="290" width="40" height="95" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 144 296 L 170 296 C 174 320 176 350 172 376 L 148 376 L 144 296 Z" class="part-shape"/>
        <circle cx="160" cy="336" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="146" y="328" width="28" height="16" class="part-label-bg"/>
        <text x="160" y="340" class="part-label" style="font-size: 8px;">Son</text>
    </g>

    <!-- Left Knee Back -->
    <g class="body-part" data-part="left_knee" onclick="openBodyMapModal('left_knee')">
        <rect x="100" y="380" width="40" height="30" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <ellipse cx="120" cy="392" rx="13" ry="11" class="part-shape"/>
        <circle cx="120" cy="392" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="120" y="395" class="part-label" style="font-size: 8px;">Tizza</text>
    </g>

    <!-- Right Knee Back -->
    <g class="body-part" data-part="right_knee" onclick="openBodyMapModal('right_knee')">
        <rect x="140" y="380" width="40" height="30" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <ellipse cx="160" cy="392" rx="13" ry="11" class="part-shape"/>
        <circle cx="160" cy="392" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="160" y="395" class="part-label" style="font-size: 8px;">Tizza</text>
    </g>

    <!-- Left Shin Back -->
    <g class="body-part" data-part="left_shin" onclick="openBodyMapModal('left_shin')">
        <rect x="100" y="405" width="40" height="75" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 108 406 L 132 406 L 126 476 L 112 476 Z" class="part-shape"/>
        <circle cx="119" cy="440" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="103" y="432" width="32" height="16" class="part-label-bg"/>
        <text x="119" y="444" class="part-label" style="font-size: 8px;">Boldir</text>
    </g>

    <!-- Right Shin Back -->
    <g class="body-part" data-part="right_shin" onclick="openBodyMapModal('right_shin')">
        <rect x="140" y="405" width="40" height="75" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 148 406 L 172 406 L 168 476 L 154 476 Z" class="part-shape"/>
        <circle cx="161" cy="440" r="3" fill="#5eead4" class="part-pin"/>
        <rect x="145" y="432" width="32" height="16" class="part-label-bg"/>
        <text x="161" y="444" class="part-label" style="font-size: 8px;">Boldir</text>
    </g>

    <!-- Left Foot Back -->
    <g class="body-part" data-part="left_foot" onclick="openBodyMapModal('left_foot')">
        <rect x="90" y="475" width="45" height="35" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 110 478 L 128 478 L 132 506 L 98 506 Z" class="part-shape"/>
        <circle cx="114" cy="494" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="114" y="497" class="part-label" style="font-size: 8px;">Tovon</text>
    </g>

    <!-- Right Foot Back -->
    <g class="body-part" data-part="right_foot" onclick="openBodyMapModal('right_foot')">
        <rect x="145" y="475" width="45" height="35" fill="transparent" class="fat-hotspot" style="cursor:pointer;" />
        <path d="M 152 478 L 170 478 L 182 506 L 148 506 Z" class="part-shape"/>
        <circle cx="166" cy="494" r="2.5" fill="#5eead4" class="part-pin"/>
        <text x="166" y="497" class="part-label" style="font-size: 8px;">Tovon</text>
    </g>
</svg>
`;

async function initBodyMap() {
    const container = document.getElementById('body-map-container');
    if (!container) return;

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

    renderBodyMap(currentBodyView);
    populateQuickChips();

    // View Switcher Buttons
    const btnFront = document.getElementById('btn-view-front');
    const btnBack = document.getElementById('btn-view-back');
    const hudViewTag = document.getElementById('scanner-current-view');

    if (btnFront && btnBack) {
        btnFront.onclick = () => {
            if (currentBodyView === 'front') return;
            currentBodyView = 'front';
            btnFront.classList.add('active');
            btnBack.classList.remove('active');
            if (hudViewTag) hudViewTag.textContent = "OLDI TARAFI";
            renderBodyMap('front');
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        };

        btnBack.onclick = () => {
            if (currentBodyView === 'back') return;
            currentBodyView = 'back';
            btnBack.classList.add('active');
            btnFront.classList.remove('active');
            if (hudViewTag) hudViewTag.textContent = "ORQA TARAFI (BEL)";
            renderBodyMap('back');
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        };
    }

    // Modal Close
    const closeBtn = document.getElementById('modal-close');
    const modal = document.getElementById('body-map-modal');
    if (closeBtn && modal) {
        function closeBodyMapModal() {
            modal.classList.add('hidden');
            modal.style.display = 'none';
            AppNavigation.pop();
        }
        closeBtn.onclick = closeBodyMapModal;
        window.onclick = (e) => {
            if (e.target === modal) {
                closeBodyMapModal();
            }
        };
    }

    // AI Consult Button
    const aiBtn = document.getElementById('ai-consult-btn');
    if (aiBtn) {
        aiBtn.onclick = () => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');

            aiBtn.disabled = true;
            const originalContent = aiBtn.innerHTML;
            aiBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> ? Ulanmoqda...';

            setTimeout(() => {
                aiBtn.disabled = false;
                aiBtn.innerHTML = originalContent;
                if (tg && tg.sendData) {
                    try {
                        const pData = bodyMapData && selectedBodyPartKey ? bodyMapData[selectedBodyPartKey.replace('left_', '').replace('right_', '')] : null;
                        const pLabel = pData ? pData.title.replace(/^[^\w\s\u0400-\u04FF]+/, '').trim() : (selectedBodyPartKey || 'bosh');
                        tg.sendData(JSON.stringify({ action: "ai_consult", title: pLabel }));
                    } catch (e) {}
                }

                // Close modal first
            const modal = document.getElementById('body-map-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.style.display = 'none';
            }

            // Build part label for bot message
            const partData = bodyMapData && selectedBodyPartKey ? bodyMapData[selectedBodyPartKey.replace('left_', '').replace('right_', '')] : null;
            const partLabel = partData ? partData.title.replace(/^[^\w\s\u0400-\u04FF]+/, '').trim() : (selectedBodyPartKey || 'bosh');

            if (tg) {
                const botUsername = "Birinchiyordam1Bot";
                const url = `https://t.me/${botUsername}?start=ai_consult_${selectedBodyPartKey || 'head'}`;
                tg.openTelegramLink(url);
                tg.close();
            } else {
                notify(`AI konsultant: Tana qismi — ${partLabel}\n\nTelegram ilovasi orqali kiring!`);
            }
            }, 300);
        };
    }
}


function hasBodyPartClass(target) {
    if (!target) return false;
    let cls = '';
    if (target.getAttribute) {
        const val = target.getAttribute('class');
        if (val) {
            cls = (typeof val === 'object' && val !== null && val.baseVal !== undefined) ? val.baseVal : val;
        }
    }
    if (!cls && target.className) {
        cls = (typeof target.className === 'object' && target.className.baseVal !== undefined) ? target.className.baseVal : target.className;
    }
    if (typeof cls !== 'string') return false;
    return cls.split(/\s+/).indexOf('body-part') !== -1;
}

function renderBodyMap(view) {
    const container = document.getElementById('body-map-container');
    if (!container) return;

    container.innerHTML = (view === 'back') ? BACK_BODY_SVG : FRONT_BODY_SVG;

    const parts = container.querySelectorAll('.body-part');
    parts.forEach(function(partEl) {
        const partKey = partEl.getAttribute('data-part');
        if (!partKey) return;

        const triggerModal = (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log("BODY PART CLICKED:", partKey); // As requested for debugging
            try {
                if (tg && tg.HapticFeedback) {
                    tg.HapticFeedback.selectionChanged();
                }
            } catch (hapticErr) {
                console.warn("Haptic failed:", hapticErr);
            }
            openBodyMapModal(partKey);
        };

        // Desktop click
        partEl.onclick = triggerModal;

        // Mobile touchend (more responsive on touch screens)
        partEl.addEventListener('touchend', triggerModal, { passive: false });

        // Make cursor pointer visible
        partEl.style.cursor = 'pointer';
    });
}

function populateQuickChips() {
    const chipsContainer = document.getElementById('body-quick-chips');
    if (!chipsContainer || !bodyMapData) return;

    const chipsList = [
        { key: 'head', icon: '🧠', name: 'Bosh' },
        { key: 'neck', icon: '🦴', name: "Bo'yin" },
        { key: 'chest', icon: '🫁', name: "Ko'krak" },
        { key: 'abdomen', icon: '🫃', name: 'Qorin' },
        { key: 'back', icon: '🔙', name: 'Bel va Orqa' },
        { key: 'shoulder', icon: '💪', name: 'Yelka' },
        { key: 'arm', icon: '🤲', name: "Qo'l" },
        { key: 'knee', icon: '🦿', name: 'Tizza' },
        { key: 'foot', icon: '🦶', name: 'Panja' }
    ];

    chipsContainer.innerHTML = '';
    chipsList.forEach(item => {
        const btn = document.createElement('button');
        btn.className = 'quick-chip';
        btn.innerHTML = `<span>${item.icon}</span><span>${item.name}</span>`;
        btn.onclick = () => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
            openBodyMapModal(item.key);
        };
        chipsContainer.appendChild(btn);
    });
}

function openBodyMapModal(partKey) {
    try {
        selectedBodyPartKey = partKey;
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
        const modal = document.getElementById('body-map-modal');
        const titleEl = document.getElementById('modal-title');
        const listEl = document.getElementById('modal-diseases-list');
        const iconEl = document.getElementById('modal-organ-icon');

        if (!modal) {
            reportError('_openFullModal', new Error('#body-map-modal oynasi HTML ichida topilmadi'));
            return;
        }

        // Set title and icon
        if (titleEl) titleEl.innerText = data.name || partKey;
        if (iconEl) iconEl.innerText = data.icon || '🩺';

        // Build disease list with tips and urgent badges
        if (listEl) {
            listEl.innerHTML = '';
            
            // 1. Render diseases list (from JSON)
            if (data.diseases && data.diseases.length > 0) {
                data.diseases.forEach(d => {
                    const li = document.createElement('li');
                    li.className = 'disease-item' + (d.urgent ? ' disease-urgent' : '');
                    
                    li.innerHTML = `
                        <div class="disease-item-header" style="cursor: pointer;">
                            <strong>${d.name}</strong>
                            ${d.urgent ? '<span class="urgent-badge"><i class="fa-solid fa-triangle-exclamation"></i> Tezkor</span>' : ''}
                            <i class="fa-solid fa-chevron-down toggle-icon" style="color: var(--hint-color); transition: transform 0.2s; font-size: 12px;"></i>
                        </div>
                        <div class="disease-details-content" style="max-height: 0; overflow: hidden; transition: max-height 0.3s ease-out;">
                            <p class="disease-desc" style="margin-top: 8px; margin-bottom: 8px;">${d.desc || ''}</p>
                            ${d.tip ? `
                            <div class="disease-tip">
                                <span class="tip-icon">💡</span>
                                <span>${d.tip}</span>
                            </div>` : ''}
                        </div>
                    `;
                    
                    const header = li.querySelector('.disease-item-header');
                    const content = li.querySelector('.disease-details-content');
                    const icon = li.querySelector('.toggle-icon');
                    
                    header.onclick = (e) => {
                        e.stopPropagation();
                        const isExpanded = content.style.maxHeight !== '0px' && content.style.maxHeight !== '';
                        
                        // Close all other expanded items in the list for a clean accordion look
                        const allContents = listEl.querySelectorAll('.disease-details-content');
                        const allIcons = listEl.querySelectorAll('.toggle-icon');
                        allContents.forEach((c, idx) => {
                            c.style.maxHeight = '0px';
                            if (allIcons[idx]) allIcons[idx].style.transform = 'rotate(0deg)';
                        });
                        
                        if (!isExpanded) {
                            content.style.maxHeight = content.scrollHeight + 'px';
                            icon.style.transform = 'rotate(180deg)';
                            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
                        } else {
                            content.style.maxHeight = '0px';
                            icon.style.transform = 'rotate(0deg)';
                            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
                        }
                    };
                    
                    listEl.appendChild(li);
                });
            }
            // 2. Fallback to problems list (from old hardcoded dictionary)
            else if (data.problems && data.problems.length > 0) {
                data.problems.forEach(p => {
                    const li = document.createElement('li');
                    li.className = 'disease-item';
                    li.style.padding = '12px 14px';
                    li.innerHTML = `
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div style="width: 6px; height: 6px; border-radius: 50%; background: #14b8a6;"></div>
                            <span style="font-weight: 600; font-size: 14px;">${p}</span>
                        </div>
                    `;
                    listEl.appendChild(li);
                });
            }
            
            // 3. Render Tip at the bottom (if not already handled inside individual diseases)
            if (data.tip && (!data.diseases || data.diseases.length === 0)) {
                const tipLi = document.createElement('li');
                tipLi.style.listStyle = 'none';
                tipLi.style.marginTop = '16px';
                tipLi.innerHTML = `
                    <div style="font-size: 13px; color: var(--hint-color); margin-bottom: 6px;">Qisqa tavsiya:</div>
                    <div style="background: rgba(20,184,166,0.1); border-left: 3px solid #14b8a6; padding: 12px; border-radius: 4px 8px 8px 4px; font-size: 14px; line-height: 1.4;">
                        ${data.tip}
                    </div>
                `;
                listEl.appendChild(tipLi);
            }
        }

        // Animate in
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        // Trigger reflow for animation
        const mc = modal.querySelector('.body-disease-modal');
        if (mc) {
            mc.style.animation = 'none';
            mc.offsetHeight; // reflow
            mc.style.animation = '';
        }

        // Push navigation state for body map modal
        AppNavigation.push({
            type: 'body-map-modal',
            close: function () {
                modal.classList.add('hidden');
                modal.style.display = 'none';
                AppNavigation.pop();
            }
        });
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

function initWheelOfFortune() {
    const openBtn = document.getElementById('btn-open-wheel');
    const closeBtn = document.getElementById('wheel-modal-close');
    const modal = document.getElementById('wheel-modal');
    const spinBtn = document.getElementById('btn-spin-wheel');
    const resultMsg = document.getElementById('wheel-result-msg');
    const canvas = document.getElementById('wheel-canvas');

    if (!openBtn || !closeBtn || !modal || !spinBtn || !canvas) return;

    generateLedLights();

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
        resultMsg.innerHTML = '<div class="result-icon">🕒</div><p class="result-title">Urinish tugadi</p><p class="result-desc">Keyingi bepul aylantirishgacha qolgan vaqt:</p><div class="wheel-countdown" id="wheel-countdown-timer" style="font-size: 24px; font-weight: 800; color: #fde047; margin: 10px 0; letter-spacing: 1px;">23:59:59</div>';
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
                        resultMsg.innerHTML = '<div class="result-icon">🕒</div><p class="result-title">Urinish tugadi</p><p class="result-desc">Keyingi bepul aylantirishgacha qolgan vaqt:</p><div class="wheel-countdown" id="wheel-countdown-timer" style="font-size: 24px; font-weight: 800; color: #fde047; margin: 10px 0; letter-spacing: 1px;">23:59:59</div>';
                        resultMsg.classList.remove('hidden');
                        startCountdown(remaining);
                    }
                }
            }
        });
    }

    const WHEEL_WAITING_HTML = '<div class="result-icon">🕒</div><p class="result-title">Urinish tugadi</p><p class="result-desc">Keyingi bepul aylantirishgacha qolgan vaqt:</p><div class="wheel-countdown" id="wheel-countdown-timer" style="font-size: 24px; font-weight: 800; color: #fde047; margin: 10px 0; letter-spacing: 1px;">23:59:59</div>';

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
            resultMsg.innerHTML = '<div class="result-icon">🕒</div><p class="result-title">Urinish tugadi</p><p class="result-desc">Keyingi bepul aylantirishgacha qolgan vaqt:</p><div class="wheel-countdown" id="wheel-countdown-timer" style="font-size: 24px; font-weight: 800; color: #fde047; margin: 10px 0; letter-spacing: 1px;">23:59:59</div>';
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
        }
    };

    // Segments — vibrant luxury palette
    const segments = [
        { text: "+1", label: "ball", points: 1, bg: "#0d9488", emoji: "💊" },
        { text: "+3", label: "ball", points: 3, bg: "#0284c7", emoji: "💉" },
        { text: "+5", label: "ball", points: 5, bg: "#0f766e", emoji: "🩺" },
        { text: "+1", label: "ball", points: 1, bg: "#10b981", emoji: "🧬" },
        { text: "+10", label: "ball", points: 10, bg: "#d97706", emoji: "⭐" },
        { text: "SUPER", label: "PRIZ", points: 0, bg: "#dc2626", emoji: "🏆" },
        { text: "+1", label: "ball", points: 1, bg: "#0284c7", emoji: "💊" },
        { text: "+3", label: "ball", points: 3, bg: "#10b981", emoji: "💉" },
        { text: "+5", label: "ball", points: 5, bg: "#0d9488", emoji: "🩺" },
        { text: "+10", label: "ball", points: 10, bg: "#d97706", emoji: "⭐" }
    ];

    function drawWheel() {
        const ctx = canvas.getContext('2d');
        const size = canvas.width;
        const r = size / 2;
        const arc = (Math.PI * 2) / segments.length;

        ctx.clearRect(0, 0, size, size);

        for (let i = 0; i < segments.length; i++) {
            const startAngle = i * arc;
            const endAngle = startAngle + arc;
            const seg = segments[i];

            // Segment fill with radial gradient
            const grad = ctx.createRadialGradient(r, r, 0, r, r, r);
            grad.addColorStop(0, lightenColor(seg.bg, 25));
            grad.addColorStop(0.85, seg.bg);
            grad.addColorStop(1, darkenColor(seg.bg, 20));

            ctx.beginPath();
            ctx.moveTo(r, r);
            ctx.arc(r, r, r - 2, startAngle, endAngle);
            ctx.closePath();
            ctx.fillStyle = grad;
            ctx.fill();

            // Segment borders
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Text and emoji inside segment
            ctx.save();
            ctx.translate(r, r);
            ctx.rotate(startAngle + arc / 2);

            // Emoji
            ctx.font = '20px serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(seg.emoji, r * 0.65, 0);

            // Points text
            ctx.font = "bold 16px 'Outfit', sans-serif";
            ctx.fillStyle = '#ffffff';
            ctx.shadowColor = 'rgba(0,0,0,0.5)';
            ctx.shadowBlur = 4;
            ctx.textAlign = 'center';
            ctx.fillText(seg.text, r * 0.40, -5);

            // Label text
            ctx.font = "600 9px 'Outfit', sans-serif";
            ctx.fillStyle = 'rgba(255,255,255,0.9)';
            ctx.fillText(seg.label, r * 0.40, 9);

            ctx.restore();
        }

        // Center shadow ring
        ctx.save();
        ctx.beginPath();
        ctx.arc(r, r, 42, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(0,0,0,0.25)';
        ctx.fill();
        ctx.restore();
    }

    function lightenColor(hex, percent) {
        const num = parseInt(hex.replace('#', ''), 16);
        const amt = Math.round(2.55 * percent);
        const R = Math.min(255, (num >> 16) + amt);
        const G = Math.min(255, ((num >> 8) & 0x00FF) + amt);
        const B = Math.min(255, (num & 0x0000FF) + amt);
        return `rgb(${R},${G},${B})`;
    }

    function darkenColor(hex, percent) {
        const num = parseInt(hex.replace('#', ''), 16);
        const amt = Math.round(2.55 * percent);
        const R = Math.max(0, (num >> 16) - amt);
        const G = Math.max(0, ((num >> 8) & 0x00FF) - amt);
        const B = Math.max(0, (num & 0x0000FF) - amt);
        return `rgb(${R},${G},${B})`;
    }

    function generateLedLights() {
        const container = document.getElementById('wheel-led-lights');
        if (!container || container.children.length > 0) return;

        const count = 16;
        const radius = 146; // px from center
        const center = 152;

        for (let i = 0; i < count; i++) {
            const angle = (i * 360 / count) * (Math.PI / 180);
            const x = center + radius * Math.cos(angle);
            const y = center + radius * Math.sin(angle);

            const led = document.createElement('div');
            led.className = 'wheel-led';
            led.style.left = `${x}px`;
            led.style.top = `${y}px`;
            led.style.animationDelay = `${(i % 2) * 0.6}s`;
            container.appendChild(led);
        }
    }

    // Animatsiya tugagach ko'rsatiladigan karta. Tugma bosilganda: API ishlayotgan bo'lsa serverda hisobga qo'shiladi,
    // aks holda ZAXIRA yo'l — eski botga deep link.
    function renderSpinConfirmCard(winningPoints) {
        let icon, title, desc, btnText;
        if (winningPoints === 0) {
            icon = "🏆";
            title = "SUPER PRIZ!";
            desc = "Siz <b>Super Priz</b> — 30 kunlik Premium Plus uchun <b>50% chegirma</b> yutib oldingiz!";
            btnText = "Prizni Tasdiqlash 🎁";
        } else {
            icon = "🎉";
            title = `+${winningPoints} ball yutdingiz!`;
            desc = "Ballarni hisobingizga qo'shish va saqlash uchun tasdiqlang.";
            btnText = "Hisobga qo'shish ✅";
        }

        resultMsg.innerHTML = `
            <div class="result-icon">${icon}</div>
            <p class="result-title">${title}</p>
            <p class="result-desc">${desc}</p>
            <button class="result-confirm-btn" id="btn-confirm-spin">${btnText}</button>
        `;
        resultMsg.classList.remove('hidden');

        document.getElementById('btn-confirm-spin').onclick = () => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('heavy');
            if (wheelApiActive) {
                claimSpinViaApi(winningPoints);
            } else {
                openSpinDeepLink(winningPoints);
            }
        };
    }

    // ZAXIRA yo'l (API yo'q yoki xato): eski mantiq — botga deep link orqali tasdiqlash
    function openSpinDeepLink(winningPoints) {
        if (tg) {
            const botUsername = "Birinchiyordam1Bot";
            const pv = (winningPoints === 0) ? "super" : winningPoints;
            tg.openTelegramLink(`https://t.me/${botUsername}?start=spin_${pv}`);
            tg.close();
        } else {
            notify("Telegram orqali tasdiqlang!");
        }
    }

    // Natija kartasi: matnlar textContent orqali qo'yiladi (server xabari HTML sifatida talqin qilinmaydi)
    function renderWheelCard(icon, title, desc, btnText, onBtn) {
        resultMsg.replaceChildren();
        const iconEl = document.createElement('div');
        iconEl.className = 'result-icon';
        iconEl.textContent = icon;
        const titleEl = document.createElement('p');
        titleEl.className = 'result-title';
        titleEl.textContent = title;
        const descEl = document.createElement('p');
        descEl.className = 'result-desc';
        descEl.textContent = desc;
        resultMsg.append(iconEl, titleEl, descEl);
        if (btnText && onBtn) {
            const btn = document.createElement('button');
            btn.className = 'result-confirm-btn';
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
                if (tg && tg.openTelegramLink) {
                    tg.openTelegramLink(`https://t.me/${BOT_USERNAME}?start=buy_plus_30`);
                }
            });
    }

    // Javob kelmadi: server ballni allaqachon bergan bo'lishi mumkin — holatni qayta so'raymiz
    async function recoverSpinClaim(winningPoints, prevScore) {
        renderWheelCard("⏳", "Natija tekshirilmoqda...", "");
        const s = await recoverStateAfterClaimFailure();
        if (!s) {                                   // holat ham olinmadi: ESKI zaxira yo'l
            openSpinDeepLink(winningPoints);
            return;
        }
        setGlobalScore(s.score);
        if (s.prize === null && Number(s.cooldown_seconds) > 0) {
            // Server ballni allaqachon bergan: deep link YO'Q
            if (winningPoints === 0) {
                renderSuperPrizeCard();
                return;
            }
            const diff = (typeof prevScore === 'number') ? s.score - prevScore : 0;
            renderWheelCard("✅", "Ball hisobingizga qo'shilgan",
                diff > 0 ? `+${diff} ball hisobingizga qo'shildi` : "Ball hisobingizga qo'shilgan.");
            return;
        }
        // Server hali bermagan (ulanish muammosi). Server ikki marta bermaydi, shuning uchun qayta urinish xavfsiz
        renderWheelCard("⚠️", "Ulanishda xatolik", "Ball hali qo'shilmadi. Qayta urinib ko'ring.",
            "Qayta urinish", () => claimSpinViaApi(winningPoints));
    }

    // "Hisobga qo'shish" bosilganda ballni serverda hisobga qo'shadi (botga chiqmasdan, tg.close() yo'q)
    async function claimSpinViaApi(winningPoints) {
        const prevScore = AppState.data ? AppState.data.score : null;
        renderWheelCard("⏳", "Hisobga qo'shilmoqda...", "");
        let r;
        try {
            r = await api('spin/claim');
            if (!r || typeof r.ok !== 'boolean') throw new Error('bad-claim');
        } catch (err) {
            console.warn("[wheel] /api/spin/claim javobi olinmadi, holat tekshiriladi:", err);
            await recoverSpinClaim(winningPoints, prevScore);
            return;
        }
        if (typeof r.score === 'number') setGlobalScore(r.score);
        // Serverda cooldown boshlandi: keshni shunga moslaymiz (qayta ochilganda KUTISH ko'rinadi)
        patchAppState({ score: r.score, prize: null, cooldown_seconds: 24 * 60 * 60 });

        if (!r.ok) {
            renderWheelCard("ℹ️", "Ball qo'shilmadi", r.message || "Mukofot allaqachon olingan.");
            return;
        }
        if (r.is_super) {
            renderSuperPrizeCard();
        } else {
            // Ball soni SERVERDAN: sarlavhada oldingi/yangi score farqi, matnda server xabari (r.message — server
            // uni allaqachon oddiy matnga aylantirgan). Klientdagi winningPoints ko'rsatilmaydi. renderWheelCard textContent ishlatadi.
            const gained = (typeof prevScore === 'number' && typeof r.score === 'number') ? r.score - prevScore : 0;
            renderWheelCard("🎉",
                gained > 0 ? `+${gained} ball yutdingiz!` : "Ball hisobingizga qo'shildi",
                r.message || "✅ Ball hisobingizga qo'shildi");
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
            resultMsg.innerHTML = '<div class="result-icon">🎁</div><p class="result-title">Bot orqali kiring</p><p class="result-desc">Omad g‘ildiragini aylantirish uchun botdagi maxsus havola orqali kiring.</p><button class="result-confirm-btn" id="btn-open-bot-wheel" style="margin-top:12px;">🎡 Bot orqali ochish</button>';
            resultMsg.classList.remove('hidden');
            const btnBotWheel = document.getElementById('btn-open-bot-wheel');
            if (btnBotWheel) {
                btnBotWheel.onclick = () => {
                    if (tg && tg.openTelegramLink) {
                        const botUsername = "Birinchiyordam1Bot";
                        tg.openTelegramLink(`https://t.me/${botUsername}?start=wheel`);
                        tg.close();
                    }
                };
            }
            return;
        }
        const winningPoints = serverPrize;

        const eligible = [];
        for (let i = 0; i < segments.length; i++) {
            if (segments[i].points === winningPoints) eligible.push(i);
        }

        // XAVFSIZLIK: server prize frontend da mavjud bo'lmasa blokla
        if (!eligible.length) {
            isSpinning = false;
            spinBtn.disabled = false;
            if (centerText) centerText.textContent = "AYLANTIR";
            resultMsg.innerHTML = `<div class="result-icon">⚠️</div><p class="result-title">Texnik xatolik</p><p class="result-desc">Mukofotni olish uchun botga /start yuboring.</p>`;
            resultMsg.classList.remove('hidden');
            return;
        }

        const winIdx = eligible[Math.floor(Math.random() * eligible.length)];
        const segArc = 360 / segments.length;
        const target = 270 - (winIdx * segArc + segArc / 2);
        const finalAngle = 8 * 360 + target;

        canvas.style.transition = 'transform 5.2s cubic-bezier(0.12, 0.7, 0.1, 1)';
        canvas.style.transform = `rotate(${finalAngle}deg)`;

        // Periodic click haptic while spinning
        let spinHapticInterval = setInterval(() => {
            if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        }, 300);

        setTimeout(() => clearInterval(spinHapticInterval), 4000);

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

            // Fire Confetti!
            fireConfetti();

            renderSpinConfirmCard(winningPoints);
        }, 5300);
    };

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
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const particles = [];
    const colors = ['#fde047', '#14b8a6', '#38bdf8', '#f43f5e', '#a855f7', '#22c55e', '#ffffff'];

    for (let i = 0; i < 90; i++) {
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
            
            let iconClass = 'fa-solid fa-star star-icon';
            if (isDay7) iconClass = 'fa-solid fa-gift star-icon';
            
            card.innerHTML = `
                <i class="fa-solid fa-circle-check check-icon"></i>
                <div class="day-label">${i}-kun</div>
                <i class="${iconClass}"></i>
                <div class="points-label">${rewards[i-1]} ball</div>
                ${isDay7 ? '<div class="big-bonus-label">Katta bonus!</div>' : ''}
            `;
            grid.appendChild(card);
        }
        
        if (dailyClaimed) {
            btnClaim.style.opacity = '0.5';
            btnClaim.style.cursor = 'not-allowed';
            btnClaim.querySelector('.wheel-center-text').textContent = '✅ Bugungi bonus olindi';
            btnClaim.onclick = null;
        } else {
            btnClaim.onclick = () => {
                if (AppState.data) {
                    claimBonusViaApi();         // API ishlayapti: mini app ichida
                } else {
                    openClaimDailyDeepLink();   // ZAXIRA: eski mantiq
                }
            };
        }
    }

    // ZAXIRA yo'l (API yo'q yoki xato): botga deep link orqali olish
    function openClaimDailyDeepLink() {
        if (window.Telegram && window.Telegram.WebApp) {
            const botUsername = "Birinchiyordam1Bot";
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
        const label = btnClaim.querySelector('.wheel-center-text');
        if (!label) return;
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
        renderGrid();
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        // Umumiy kesh: 60 soniyadan eski bo'lsagina qayta so'raladi
        getAppState(60000).then((s) => { if (s) applyState(s); });
    };

    // Mini app ochilganda seriya va "bugun olingan" holati serverdan (menyu tugmasidan ochilganda ham to'g'ri)
    getAppState(60000).then((s) => { if (s) applyState(s); });
    
    btnClose.onclick = () => {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    };
    
    // Allow clicking outside the modal content to close it
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            btnClose.onclick();
        }
    });
});

// Premium Modal Logic
document.addEventListener('DOMContentLoaded', () => {
    const btnOpenPremium = document.getElementById('btn-open-premium');
    const premiumModal = document.getElementById('premium-modal');
    const premiumModalClose = document.getElementById('premium-modal-close');

    if (btnOpenPremium && premiumModal) {
        btnOpenPremium.addEventListener('click', () => {
            premiumModal.classList.remove('hidden');
            premiumModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
            
            AppNavigation.push({
                type: 'premium-modal',
                close: () => {
                    premiumModal.classList.add('hidden');
                    premiumModal.style.display = 'none';
                    document.body.style.overflow = 'auto';
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

// Global helper: buy premium via Telegram deep link
function buyPremium(plan) {
    var tg = window.Telegram && window.Telegram.WebApp;
    var botUsername = 'Birinchiyordam1Bot';
    var url = 'https://t.me/' + botUsername + '?start=' + plan;
    if (tg) {
        tg.openTelegramLink(url);
    } else {
        window.open(url, '_blank');
    }
}

