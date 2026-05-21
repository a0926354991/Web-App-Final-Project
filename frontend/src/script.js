// ==========================================================================
// 設定
// ==========================================================================
const API_BASE = 'http://localhost:8000';
const PAGE_SIZE = 20;
const TOKEN_KEY = 'ntu_app_token';

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

function authHeaders() {
    const t = getToken();
    return t ? { 'Authorization': `Bearer ${t}` } : {};
}

// ==========================================================================
// Sidebar 開關 (漢堡選單)
// ==========================================================================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 992;
    if (isMobile) {
        sidebar.classList.toggle('mobile-open');
    } else {
        sidebar.classList.toggle('desktop-collapsed');
    }
}

document.querySelector('.main-content').addEventListener('click', () => {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 992 && sidebar.classList.contains('mobile-open')) {
        sidebar.classList.remove('mobile-open');
    }
});

// ==========================================================================
// View 切換 (router 雛形)
// ==========================================================================
const sidebarItems = document.querySelectorAll('.sidebar-item');
sidebarItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const target = item.dataset.target;
        if (!target) return;

        sidebarItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        document.querySelectorAll('.view').forEach(v => v.hidden = true);
        const view = document.getElementById(`view-${target}`);
        if (view) view.hidden = false;

        if (target === 'discover' && !discoverState.initialized) {
            initDiscoverView();
        }
        if (target === 'userinfo') {
            renderProfileView();
        }
        if (target === 'history') {
            renderHistoryView();
        }
        if (target === 'fit') {
            renderFitAnalysisView();
        }

        if (window.innerWidth <= 992) {
            document.getElementById('sidebar').classList.remove('mobile-open');
        }
    });
});

// ==========================================================================
// 儀表板雷達圖 (dashboard) — 預設值,登入後會由 profile 覆寫
// ==========================================================================
const DEFAULT_ABILITIES = [50, 50, 50, 50, 50];
const ABILITY_LABELS = ['數理邏輯', '文字表達', '程式實作', '人文素養', '團隊協作'];

const radarCtx = document.getElementById('radarChart').getContext('2d');
const radarChart = new Chart(radarCtx, {
    type: 'radar',
    data: {
        labels: ABILITY_LABELS,
        datasets: [{
            label: '目前能力值',
            data: DEFAULT_ABILITIES,
            backgroundColor: 'rgba(33, 150, 243, 0.2)',
            borderColor: 'rgba(33, 150, 243, 1)',
            borderWidth: 2,
            pointBackgroundColor: 'rgba(33, 150, 243, 1)',
            pointBorderColor: '#fff',
            pointRadius: 4,
            pointHoverRadius: 6,
        }],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            r: {
                angleLines: { color: 'rgba(0,0,0,0.1)' },
                grid: { color: 'rgba(0,0,0,0.05)' },
                suggestedMin: 0,
                suggestedMax: 100,
                ticks: { stepSize: 20, color: '#888', backdropColor: 'transparent' },
                pointLabels: {
                    font: { size: 14, family: '"Microsoft JhengHei", Arial, sans-serif' },
                    color: '#444',
                },
            },
        },
        plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: 'rgba(0, 0, 0, 0.8)', padding: 10, bodyFont: { size: 14 } },
        },
    },
});

function updateRadarFromProfile(p) {
    radarChart.data.datasets[0].data = [
        p.ability_logic,
        p.ability_writing,
        p.ability_coding,
        p.ability_humanities,
        p.ability_teamwork,
    ];
    radarChart.update();
}

// ==========================================================================
// 課程探索 (course discovery)
// ==========================================================================
const discoverState = {
    initialized: false,
    offset: 0,
    total: 0,
    currentParams: {},
};

const els = {
    searchInput: document.getElementById('search-input'),
    filterDept: document.getElementById('filter-dept'),
    filterCredits: document.getElementById('filter-credits'),
    searchBtn: document.getElementById('search-btn'),
    resultsBody: document.getElementById('results-body'),
    resultsMeta: document.getElementById('results-meta'),
    pagination: document.getElementById('pagination'),
    pagePrev: document.getElementById('page-prev'),
    pageNext: document.getElementById('page-next'),
    pageInfo: document.getElementById('page-info'),
};

async function initDiscoverView() {
    discoverState.initialized = true;

    try {
        const depts = await fetch(`${API_BASE}/departments`).then(r => r.json());
        depts.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.textContent = d;
            els.filterDept.appendChild(opt);
        });
    } catch (err) {
        console.error('載入系所清單失敗:', err);
        els.resultsMeta.textContent = '無法連線到 API server (預期：http://localhost:8000)。請確認後端有啟動。';
    }

    els.searchBtn.addEventListener('click', () => {
        discoverState.offset = 0;
        searchCourses();
    });

    els.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            discoverState.offset = 0;
            searchCourses();
        }
    });

    els.pagePrev.addEventListener('click', () => {
        if (discoverState.offset >= PAGE_SIZE) {
            discoverState.offset -= PAGE_SIZE;
            searchCourses({ keepParams: true });
        }
    });

    els.pageNext.addEventListener('click', () => {
        if (discoverState.offset + PAGE_SIZE < discoverState.total) {
            discoverState.offset += PAGE_SIZE;
            searchCourses({ keepParams: true });
        }
    });

    await searchCourses();
}

async function searchCourses({ keepParams = false } = {}) {
    if (!keepParams) {
        discoverState.currentParams = {
            q: els.searchInput.value.trim(),
            dept: els.filterDept.value,
            credits: els.filterCredits.value,
        };
    }

    const params = new URLSearchParams();
    const { q, dept, credits } = discoverState.currentParams;
    if (q) params.set('q', q);
    if (dept) params.set('dept', dept);
    if (credits) params.set('credits', credits);
    params.set('limit', PAGE_SIZE);
    params.set('offset', discoverState.offset);

    els.resultsBody.innerHTML = '<tr><td colspan="6" class="empty-row">載入中…</td></tr>';
    els.pagination.hidden = true;

    try {
        const data = await fetch(`${API_BASE}/courses?${params}`).then(r => r.json());
        discoverState.total = data.total;
        renderResults(data.items);
        renderMeta();
        renderPagination();
        document.getElementById('fit-header').hidden = true;
        if (getToken()) {
            annotateResultsWithFit(data.items.map(c => c.serial_no));
        }
    } catch (err) {
        console.error(err);
        els.resultsBody.innerHTML = '<tr><td colspan="6" class="empty-row">搜尋失敗，請確認 API server 是否啟動</td></tr>';
    }
}

function renderResults(items) {
    if (items.length === 0) {
        els.resultsBody.innerHTML = '<tr><td colspan="7" class="empty-row">沒有符合條件的課程</td></tr>';
        return;
    }
    els.resultsBody.innerHTML = items.map(c => {
        const inHist = historyState.serialSet.has(c.serial_no);
        const btnHtml = getToken() ? `
            <button class="btn-add-history ${inHist ? 'in-history' : ''}" data-serial="${escapeAttr(c.serial_no)}" data-name="${escapeAttr(c.course_name)}">
                ${inHist ? '<i class="fas fa-check"></i> 已修' : '<i class="fas fa-plus"></i> 加入歷史'}
            </button>` : '';
        return `
        <tr data-serial="${escapeAttr(c.serial_no)}">
            <td>${escapeHtml(c.course_code)}</td>
            <td>${escapeHtml(c.course_name)}</td>
            <td>${escapeHtml(c.teacher)}</td>
            <td>${escapeHtml(c.department)}</td>
            <td>${escapeHtml(c.credits)}</td>
            <td>${escapeHtml(c.schedule_time) || '—'}</td>
            <td class="action-cell">${btnHtml}</td>
        </tr>
    `;
    }).join('');

    els.resultsBody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.btn-add-history')) return;
            els.resultsBody.querySelectorAll('tr').forEach(r => r.classList.remove('active'));
            row.classList.add('active');
            openDrawer(row.dataset.serial);
        });
    });

    els.resultsBody.querySelectorAll('.btn-add-history:not(.in-history)').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openHistoryModal(btn.dataset.serial, btn.dataset.name);
        });
    });
}

function renderMeta() {
    const t = discoverState.total;
    const from = t === 0 ? 0 : discoverState.offset + 1;
    const to = Math.min(discoverState.offset + PAGE_SIZE, t);
    els.resultsMeta.textContent = `共 ${t} 筆，顯示 ${from}–${to}`;
}

function renderPagination() {
    if (discoverState.total <= PAGE_SIZE) {
        els.pagination.hidden = true;
        return;
    }
    els.pagination.hidden = false;
    const page = Math.floor(discoverState.offset / PAGE_SIZE) + 1;
    const totalPages = Math.ceil(discoverState.total / PAGE_SIZE);
    els.pageInfo.textContent = `第 ${page} / ${totalPages} 頁`;
    els.pagePrev.disabled = discoverState.offset === 0;
    els.pageNext.disabled = discoverState.offset + PAGE_SIZE >= discoverState.total;
}

// ==========================================================================
// 課程詳情抽屜 (drawer)
// ==========================================================================
const drawer = document.getElementById('detail-drawer');
const drawerOverlay = document.getElementById('drawer-overlay');
const drawerBody = document.getElementById('drawer-body');
const drawerTitle = document.getElementById('drawer-title');

document.getElementById('drawer-close').addEventListener('click', closeDrawer);
drawerOverlay.addEventListener('click', closeDrawer);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeDrawer();
        closeAuthModal();
        closeHistoryModal();
    }
});

function closeDrawer() {
    drawer.classList.remove('open');
    drawerOverlay.classList.remove('open');
}

async function openDrawer(serialNo) {
    drawer.classList.add('open');
    drawerOverlay.classList.add('open');
    drawerTitle.textContent = '載入中…';
    drawerBody.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> 載入課程資料…</div>';

    try {
        const [detail, reviewsResp, fit] = await Promise.all([
            fetch(`${API_BASE}/courses/${encodeURIComponent(serialNo)}`).then(r => r.json()),
            fetch(`${API_BASE}/courses/${encodeURIComponent(serialNo)}/reviews`).then(r => r.json()),
            loadDrawerFit(serialNo),
        ]);
        drawerTitle.textContent = detail.course_name;
        drawerBody.innerHTML = renderFitBox(fit) + renderDrawerContent(detail, reviewsResp.items);
        const addBtn = document.getElementById('drawer-add-history-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                openHistoryModal(detail.serial_no, detail.course_name);
            });
        }
    } catch (err) {
        console.error(err);
        drawerBody.innerHTML = '<p class="drawer-empty">載入失敗</p>';
    }
}

let currentDrawerSerial = null;

function renderDrawerContent(d, reviews) {
    currentDrawerSerial = d.serial_no;
    const reviewsHtml = reviews.length === 0
        ? '<p class="drawer-empty" style="margin-top: 10px;">尚無 PTT 評價</p>'
        : reviews.map(r => `
            <div class="review-item">
                <div class="review-meta">
                    ${r.recommendation ? `<span class="badge rec">推薦 ${escapeHtml(r.recommendation)}/5</span>` : ''}
                    ${r.sweetness ? `<span class="badge">甜 ${escapeHtml(r.sweetness)}</span>` : ''}
                    ${r.workload ? `<span class="badge">涼 ${escapeHtml(r.workload)}</span>` : ''}
                    ${r.year_term ? `<span class="badge">${escapeHtml(r.year_term)}</span>` : ''}
                    ${r.post_tag ? `<span class="badge">${escapeHtml(r.post_tag)}</span>` : ''}
                </div>
                <div class="review-summary">${escapeHtml(r.summary) || '(無摘要)'}</div>
                <a class="review-link" href="${escapeAttr(r.post_url)}" target="_blank" rel="noopener">
                    <i class="fas fa-external-link-alt"></i> 看原文
                </a>
            </div>
        `).join('');

    const inHist = historyState.serialSet.has(d.serial_no);
    const addBtn = getToken() ? `
        <button class="drawer-add-history-btn ${inHist ? 'in-history' : ''}" id="drawer-add-history-btn" ${inHist ? 'disabled' : ''}>
            ${inHist ? '<i class="fas fa-check"></i> 已在修課歷史中' : '<i class="fas fa-plus"></i> 加入修課歷史'}
        </button>` : '';

    return `
        <div class="drawer-section">
            <div class="course-name-big">${escapeHtml(d.course_name)}</div>
            <div class="course-meta-row"><strong>課號</strong> ${escapeHtml(d.course_code)}　|　<strong>流水號</strong> ${escapeHtml(d.serial_no)}</div>
            <div class="course-meta-row"><strong>教師</strong> ${escapeHtml(d.teacher) || '—'}</div>
            <div class="course-meta-row"><strong>系所</strong> ${escapeHtml(d.department) || '—'}</div>
            <div class="course-meta-row"><strong>學分</strong> ${escapeHtml(d.credits) || '—'}　|　<strong>必選修</strong> ${escapeHtml(d.req_type) || '—'}</div>
            <div class="course-meta-row"><strong>時間</strong> ${escapeHtml(d.schedule_time) || '—'}　|　<strong>地點</strong> ${escapeHtml(d.location) || '—'}</div>
            <div class="course-meta-row"><strong>語言</strong> ${escapeHtml(d.language) || '—'}</div>
            ${addBtn}
        </div>

        ${d.overview ? `
        <div class="drawer-section">
            <h3>課程概述</h3>
            <div class="course-text">${escapeHtml(d.overview)}</div>
        </div>` : ''}

        ${d.objectives ? `
        <div class="drawer-section">
            <h3>課程目標</h3>
            <div class="course-text">${escapeHtml(d.objectives)}</div>
        </div>` : ''}

        ${d.grading ? `
        <div class="drawer-section">
            <h3>評量方式</h3>
            <div class="course-text">${escapeHtml(d.grading)}</div>
        </div>` : ''}

        <div class="drawer-section">
            <h3>PTT 評價 (${reviews.length})</h3>
            ${reviewsHtml}
        </div>

        ${d.detail_url ? `
        <div class="drawer-section">
            <a class="review-link" href="${escapeAttr(d.detail_url)}" target="_blank" rel="noopener">
                <i class="fas fa-external-link-alt"></i> 課程網原始頁面
            </a>
        </div>` : ''}
    `;
}

// ==========================================================================
// Auth：登入 / 註冊 modal + UI 狀態
// ==========================================================================
const authEls = {
    overlay: document.getElementById('auth-modal-overlay'),
    title: document.getElementById('auth-title'),
    form: document.getElementById('auth-form'),
    username: document.getElementById('auth-username'),
    password: document.getElementById('auth-password'),
    error: document.getElementById('auth-error'),
    submit: document.getElementById('auth-submit'),
    close: document.getElementById('auth-modal-close'),
    switchLabel: document.getElementById('auth-switch-label'),
    switchLink: document.getElementById('auth-switch-link'),
    btnLogin: document.getElementById('btn-login'),
    btnLogout: document.getElementById('btn-logout'),
    headerAvatar: document.getElementById('header-avatar'),
    headerUsername: document.getElementById('header-username'),
    sidebarAvatar: document.getElementById('sidebar-avatar'),
    sidebarUsername: document.getElementById('sidebar-username'),
    sidebarUserid: document.getElementById('sidebar-userid'),
    sidebarStatusDot: document.getElementById('sidebar-status-dot'),
    sidebarStatusText: document.getElementById('sidebar-status-text'),
};

let authMode = 'login';  // 'login' | 'register'

function openAuthModal(mode = 'login') {
    authMode = mode;
    renderAuthMode();
    authEls.overlay.hidden = false;
    authEls.username.value = '';
    authEls.password.value = '';
    authEls.error.hidden = true;
    setTimeout(() => authEls.username.focus(), 50);
}

function closeAuthModal() {
    authEls.overlay.hidden = true;
}

function renderAuthMode() {
    if (authMode === 'login') {
        authEls.title.textContent = '登入 Login';
        authEls.submit.textContent = '登入';
        authEls.switchLabel.textContent = '還沒有帳號？';
        authEls.switchLink.textContent = '註冊';
        authEls.password.autocomplete = 'current-password';
    } else {
        authEls.title.textContent = '註冊 Register';
        authEls.submit.textContent = '建立帳號';
        authEls.switchLabel.textContent = '已經有帳號？';
        authEls.switchLink.textContent = '登入';
        authEls.password.autocomplete = 'new-password';
    }
}

function showAuthError(msg) {
    authEls.error.textContent = msg;
    authEls.error.hidden = false;
}

authEls.btnLogin.addEventListener('click', (e) => { e.preventDefault(); openAuthModal('login'); });
authEls.btnLogout.addEventListener('click', (e) => { e.preventDefault(); doLogout(); });
authEls.close.addEventListener('click', closeAuthModal);
authEls.overlay.addEventListener('click', (e) => {
    if (e.target === authEls.overlay) closeAuthModal();
});
authEls.switchLink.addEventListener('click', (e) => {
    e.preventDefault();
    openAuthModal(authMode === 'login' ? 'register' : 'login');
});

authEls.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = authEls.username.value.trim();
    const password = authEls.password.value;
    if (!username || !password) {
        showAuthError('請填寫帳號與密碼');
        return;
    }

    authEls.submit.disabled = true;
    authEls.error.hidden = true;
    try {
        const endpoint = authMode === 'login' ? '/auth/login' : '/auth/register';
        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showAuthError(err.detail || `${res.status} 錯誤`);
            return;
        }
        const data = await res.json();
        setToken(data.token);
        applyLoggedInUI(data.user);
        closeAuthModal();
    } catch (err) {
        console.error(err);
        showAuthError('連線失敗，請確認 API server 是否啟動');
    } finally {
        authEls.submit.disabled = false;
    }
});

async function doLogout() {
    const token = getToken();
    if (token) {
        try {
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: authHeaders(),
            });
        } catch (err) {
            console.warn('logout request failed, clearing locally', err);
        }
    }
    clearToken();
    applyLoggedOutUI();
}

async function applyLoggedInUI(user) {
    const name = user.username;
    const avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=002D62&color=ffffff`;
    authEls.headerAvatar.src = avatarUrl;
    authEls.headerUsername.textContent = `${name} 已登入`;
    authEls.sidebarAvatar.src = avatarUrl;
    authEls.sidebarUsername.textContent = name;
    authEls.sidebarUserid.textContent = `ID: ${user.id}`;
    authEls.sidebarStatusDot.className = 'status-dot online';
    authEls.sidebarStatusText.textContent = '已登入 Online';
    authEls.btnLogin.hidden = true;
    authEls.btnLogout.hidden = false;

    const p = await loadProfile();
    if (p) updateRadarFromProfile(p);
    await loadHistory();
    loadDashboardRecommendations();
}

function applyLoggedOutUI() {
    const avatarUrl = 'https://ui-avatars.com/api/?name=未登入&background=cccccc&color=000000';
    authEls.headerAvatar.src = avatarUrl;
    authEls.headerUsername.textContent = '未登入,請先登入';
    authEls.sidebarAvatar.src = avatarUrl;
    authEls.sidebarUsername.textContent = '未登入';
    authEls.sidebarUserid.textContent = '等待登入後顯示';
    authEls.sidebarStatusDot.className = 'status-dot waiting';
    authEls.sidebarStatusText.textContent = '等待登入 Waiting for login';
    authEls.btnLogin.hidden = false;
    authEls.btnLogout.hidden = true;

    radarChart.data.datasets[0].data = DEFAULT_ABILITIES;
    radarChart.update();
    profileState.loaded = false;
    historyState.items = [];
    historyState.serialSet = new Set();
    historyState.loaded = false;
    loadDashboardRecommendations();
}

async function bootstrapAuth() {
    const token = getToken();
    if (!token) {
        applyLoggedOutUI();
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeaders() });
        if (res.ok) {
            const user = await res.json();
            applyLoggedInUI(user);
        } else {
            clearToken();
            applyLoggedOutUI();
        }
    } catch (err) {
        console.warn('auth bootstrap failed', err);
        applyLoggedOutUI();
    }
}

bootstrapAuth();

// ==========================================================================
// 使用者資訊輸入頁 (profile)
// ==========================================================================
const ABILITY_FIELDS = [
    { key: 'ability_logic', label: '數理邏輯' },
    { key: 'ability_writing', label: '文字表達' },
    { key: 'ability_coding', label: '程式實作' },
    { key: 'ability_humanities', label: '人文素養' },
    { key: 'ability_teamwork', label: '團隊協作' },
];
const PREF_FIELDS = [
    { key: 'pref_sweetness', label: '甜度偏好', hint: '高 = 重視給分甜' },
    { key: 'pref_loading', label: 'loading 偏好', hint: '高 = 喜歡扎實' },
];
const INTEREST_OPTIONS = [
    'AI', '程式', '金融', '商管', '設計', '人文', '語言',
    '自然科學', '社會科學', '醫學', '法律', '體育', '藝術',
];

const profileEls = {
    form: document.getElementById('profile-form'),
    needLogin: document.getElementById('profile-need-login'),
    abilityGroup: document.getElementById('ability-group'),
    prefGroup: document.getElementById('pref-group'),
    interestTags: document.getElementById('interest-tags'),
    save: document.getElementById('profile-save'),
    saved: document.getElementById('profile-saved'),
};

let profileState = {
    loaded: false,
    selectedInterests: new Set(),
};

function buildSliderRow(field, value, hint) {
    const row = document.createElement('div');
    row.className = 'slider-row';
    row.innerHTML = `
        <label for="slider-${field.key}">${field.label}${hint ? `<br><span style="font-size:0.75rem;color:#888">${hint}</span>` : ''}</label>
        <input type="range" id="slider-${field.key}" name="${field.key}" min="0" max="100" value="${value}">
        <span class="slider-value" id="value-${field.key}">${value}</span>
    `;
    const input = row.querySelector('input');
    const valSpan = row.querySelector('.slider-value');
    input.addEventListener('input', () => { valSpan.textContent = input.value; });
    return row;
}

function buildInterestTags(selected) {
    profileEls.interestTags.innerHTML = '';
    profileState.selectedInterests = new Set(selected);
    INTEREST_OPTIONS.forEach(name => {
        const tag = document.createElement('span');
        tag.className = 'interest-tag' + (profileState.selectedInterests.has(name) ? ' selected' : '');
        tag.textContent = name;
        tag.addEventListener('click', () => {
            if (profileState.selectedInterests.has(name)) {
                profileState.selectedInterests.delete(name);
                tag.classList.remove('selected');
            } else {
                profileState.selectedInterests.add(name);
                tag.classList.add('selected');
            }
        });
        profileEls.interestTags.appendChild(tag);
    });
}

function renderProfileForm(profile) {
    profileEls.abilityGroup.innerHTML = '';
    ABILITY_FIELDS.forEach(f => {
        profileEls.abilityGroup.appendChild(buildSliderRow(f, profile[f.key]));
    });
    profileEls.prefGroup.innerHTML = '';
    PREF_FIELDS.forEach(f => {
        profileEls.prefGroup.appendChild(buildSliderRow(f, profile[f.key], f.hint));
    });
    buildInterestTags(profile.interests || []);
    profileState.loaded = true;
}

async function loadProfile() {
    if (!getToken()) return null;
    try {
        const res = await fetch(`${API_BASE}/me/profile`, { headers: authHeaders() });
        if (!res.ok) return null;
        return await res.json();
    } catch (err) {
        console.warn('loadProfile failed', err);
        return null;
    }
}

async function renderProfileView() {
    if (!getToken()) {
        profileEls.form.hidden = true;
        profileEls.needLogin.hidden = false;
        return;
    }
    profileEls.needLogin.hidden = true;
    profileEls.form.hidden = false;
    if (!profileState.loaded) {
        const p = await loadProfile();
        if (p) renderProfileForm(p);
    }
}

profileEls.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!getToken()) return;

    const body = { interests: [...profileState.selectedInterests] };
    [...ABILITY_FIELDS, ...PREF_FIELDS].forEach(f => {
        body[f.key] = Number(document.getElementById(`slider-${f.key}`).value);
    });

    profileEls.save.disabled = true;
    profileEls.saved.hidden = true;
    try {
        const res = await fetch(`${API_BASE}/me/profile`, {
            method: 'PUT',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const saved = await res.json();
        updateRadarFromProfile(saved);
        profileEls.saved.hidden = false;
        setTimeout(() => { profileEls.saved.hidden = true; }, 2500);
    } catch (err) {
        console.error(err);
        alert('儲存失敗,請稍後再試');
    } finally {
        profileEls.save.disabled = false;
    }
});

// ==========================================================================
// 修課歷史 (history)
// ==========================================================================
const historyState = {
    items: [],
    serialSet: new Set(),
    loaded: false,
};

const historyEls = {
    needLogin: document.getElementById('history-need-login'),
    content: document.getElementById('history-content'),
    meta: document.getElementById('history-meta'),
    body: document.getElementById('history-body'),
    // modal
    overlay: document.getElementById('history-modal-overlay'),
    close: document.getElementById('history-modal-close'),
    course: document.getElementById('history-modal-course'),
    form: document.getElementById('history-form'),
    semester: document.getElementById('history-semester'),
    grade: document.getElementById('history-grade'),
    notes: document.getElementById('history-notes'),
    error: document.getElementById('history-error'),
    submit: document.getElementById('history-submit'),
};

let pendingHistorySerial = null;

async function loadHistory() {
    if (!getToken()) {
        historyState.items = [];
        historyState.serialSet = new Set();
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/me/history`, { headers: authHeaders() });
        if (!res.ok) return;
        historyState.items = await res.json();
        historyState.serialSet = new Set(historyState.items.map(i => i.serial_no));
        historyState.loaded = true;
    } catch (err) {
        console.warn('loadHistory failed', err);
    }
}

async function renderHistoryView() {
    if (!getToken()) {
        historyEls.content.hidden = true;
        historyEls.needLogin.hidden = false;
        return;
    }
    historyEls.needLogin.hidden = true;
    historyEls.content.hidden = false;

    if (!historyState.loaded) {
        historyEls.meta.textContent = '載入中…';
        await loadHistory();
    }
    renderHistoryTable();
}

function renderHistoryTable() {
    const items = historyState.items;
    historyEls.meta.textContent = `共 ${items.length} 筆`;
    if (items.length === 0) {
        historyEls.body.innerHTML = '<tr><td colspan="8" class="empty-row">尚未加入任何課程 — 到「課程探索」加幾門吧</td></tr>';
        return;
    }
    historyEls.body.innerHTML = items.map(h => `
        <tr>
            <td>${escapeHtml(h.semester)}</td>
            <td>${escapeHtml(h.course_code)}</td>
            <td>${escapeHtml(h.course_name)}</td>
            <td>${escapeHtml(h.teacher)}</td>
            <td>${escapeHtml(h.credits)}</td>
            <td>${escapeHtml(h.grade) || '—'}</td>
            <td>${escapeHtml(h.notes) || ''}</td>
            <td class="action-cell">
                <button class="btn-delete-row" data-id="${h.id}" title="刪除"><i class="fas fa-trash"></i></button>
            </td>
        </tr>
    `).join('');

    historyEls.body.querySelectorAll('.btn-delete-row').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('確定要刪除這筆紀錄?')) return;
            const id = btn.dataset.id;
            try {
                const res = await fetch(`${API_BASE}/me/history/${id}`, {
                    method: 'DELETE',
                    headers: authHeaders(),
                });
                if (!res.ok) throw new Error(`${res.status}`);
                await loadHistory();
                renderHistoryTable();
            } catch (err) {
                console.error(err);
                alert('刪除失敗');
            }
        });
    });
}

function openHistoryModal(serialNo, courseName) {
    if (!getToken()) {
        openAuthModal('login');
        return;
    }
    pendingHistorySerial = serialNo;
    historyEls.course.textContent = `${courseName} (流水號 ${serialNo})`;
    historyEls.semester.value = '';
    historyEls.grade.value = '';
    historyEls.notes.value = '';
    historyEls.error.hidden = true;
    historyEls.overlay.hidden = false;
    setTimeout(() => historyEls.semester.focus(), 50);
}

function closeHistoryModal() {
    historyEls.overlay.hidden = true;
    pendingHistorySerial = null;
}

historyEls.close.addEventListener('click', closeHistoryModal);
historyEls.overlay.addEventListener('click', (e) => {
    if (e.target === historyEls.overlay) closeHistoryModal();
});

historyEls.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!pendingHistorySerial) return;
    const semester = historyEls.semester.value.trim();
    if (!semester) {
        historyEls.error.textContent = '請填寫學期';
        historyEls.error.hidden = false;
        return;
    }
    historyEls.submit.disabled = true;
    historyEls.error.hidden = true;
    try {
        const res = await fetch(`${API_BASE}/me/history`, {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({
                serial_no: pendingHistorySerial,
                semester,
                grade: historyEls.grade.value || null,
                notes: historyEls.notes.value || null,
            }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `${res.status}`);
        }
        await loadHistory();
        // 重繪探索表格的按鈕狀態
        if (discoverState.total > 0 && !document.getElementById('view-discover').hidden) {
            searchCourses({ keepParams: true });
        }
        closeHistoryModal();
    } catch (err) {
        console.error(err);
        historyEls.error.textContent = `加入失敗:${err.message}`;
        historyEls.error.hidden = false;
    } finally {
        historyEls.submit.disabled = false;
    }
});

// ==========================================================================
// 適合度 (fit analysis)
// ==========================================================================
function fitClass(score) {
    if (score >= 75) return 'fit-high';
    if (score >= 55) return 'fit-mid';
    return 'fit-low';
}

function renderFitBadge(score) {
    return `<span class="fit-badge ${fitClass(score)}">${score.toFixed(0)}</span>`;
}

// ---- Dashboard 「為您推薦」 ----
async function loadDashboardRecommendations() {
    const listEl = document.getElementById('dashboard-recommend-list');
    if (!getToken()) {
        listEl.innerHTML = `
            <div class="course-card placeholder-mini">
                <p style="color:#999;text-align:center;margin:20px 0">登入後顯示個性化推薦</p>
            </div>`;
        return;
    }
    listEl.innerHTML = `<div class="course-card placeholder-mini">
        <p style="color:#999;text-align:center;margin:20px 0">載入中…</p>
    </div>`;
    try {
        const items = await fetch(`${API_BASE}/me/recommendations?limit=5`, {
            headers: authHeaders(),
        }).then(r => r.ok ? r.json() : []);
        if (items.length === 0) {
            listEl.innerHTML = `<div class="course-card placeholder-mini">
                <p style="color:#999;text-align:center;margin:20px 0">沒有可推薦的課程</p>
            </div>`;
            return;
        }
        listEl.innerHTML = items.map(it => `
            <div class="course-card" data-serial="${escapeAttr(it.serial_no)}">
                <div class="course-card-tag fit-tag">適合度 ${it.fit.total.toFixed(0)}%</div>
                <div class="course-card-subtags">
                    <span class="tag">推薦 ${it.fit.recommendation.toFixed(0)}</span>
                    <span class="tag">甜 ${it.fit.sweetness.toFixed(0)}</span>
                    <span class="tag">loading ${it.fit.loading.toFixed(0)}</span>
                    <span class="tag">興趣 ${it.fit.interest.toFixed(0)}</span>
                    <span class="tag">能力 ${it.fit.ability.toFixed(0)}</span>
                </div>
                <div class="course-card-details">
                    <span><i class="fas fa-book"></i> ${escapeHtml(it.course_name)}</span>
                    <span><i class="fas fa-user"></i> ${escapeHtml(it.teacher)}</span>
                    <span><i class="fas fa-clock"></i> ${escapeHtml(it.credits)} 學分</span>
                </div>
            </div>
        `).join('');
        listEl.querySelectorAll('.course-card').forEach(card => {
            card.addEventListener('click', () => openDrawer(card.dataset.serial));
        });
    } catch (err) {
        console.warn('loadDashboardRecommendations failed', err);
    }
}

// ---- 探索頁:批次拿 fit 分數,塞回表格 ----
async function annotateResultsWithFit(serialNos) {
    if (!getToken() || serialNos.length === 0) return;
    try {
        const fits = await fetch(`${API_BASE}/me/fits`, {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(serialNos),
        }).then(r => r.ok ? r.json() : {});
        document.getElementById('fit-header').hidden = false;
        els.resultsBody.querySelectorAll('tr').forEach(row => {
            const s = row.dataset.serial;
            if (!s) return;
            const f = fits[s];
            if (!f) return;
            // 找到 actions cell 前一格插入
            const actionCell = row.querySelector('.action-cell');
            const cell = document.createElement('td');
            cell.dataset.fit = f.total;
            cell.innerHTML = renderFitBadge(f.total);
            row.insertBefore(cell, actionCell);
        });
        // 預設按 fit 降序排
        sortResultsByFit();
    } catch (err) {
        console.warn('annotateResultsWithFit failed', err);
    }
}

let resultsSortDirection = 'desc';
function sortResultsByFit() {
    const rows = [...els.resultsBody.querySelectorAll('tr[data-serial]')];
    rows.sort((a, b) => {
        const av = Number(a.querySelector('[data-fit]')?.dataset.fit ?? -1);
        const bv = Number(b.querySelector('[data-fit]')?.dataset.fit ?? -1);
        return resultsSortDirection === 'desc' ? bv - av : av - bv;
    });
    rows.forEach(r => els.resultsBody.appendChild(r));
}

document.getElementById('fit-header').addEventListener('click', () => {
    resultsSortDirection = resultsSortDirection === 'desc' ? 'asc' : 'desc';
    sortResultsByFit();
});

// ---- Drawer 內的 fit 顯示 ----
async function loadDrawerFit(serialNo) {
    if (!getToken()) return null;
    try {
        const res = await fetch(`${API_BASE}/me/fit/${encodeURIComponent(serialNo)}`, {
            headers: authHeaders(),
        });
        if (!res.ok) return null;
        return await res.json();
    } catch (err) {
        return null;
    }
}

function renderFitBox(fit) {
    if (!fit) return '';
    return `
        <div class="drawer-fit-box">
            <div class="drawer-fit-total">適合度 ${fit.total.toFixed(0)}%</div>
            <div class="drawer-fit-breakdown">
                <span><strong>PTT 推薦</strong>${fit.recommendation.toFixed(0)}</span>
                <span><strong>甜度匹配</strong>${fit.sweetness.toFixed(0)}</span>
                <span><strong>Loading 匹配</strong>${fit.loading.toFixed(0)}</span>
                <span><strong>興趣命中</strong>${fit.interest.toFixed(0)}</span>
                <span><strong>能力匹配</strong>${fit.ability.toFixed(0)}</span>
                <span><strong>PTT 樣本</strong>${fit.n_reviews} 篇</span>
            </div>
            ${fit.n_reviews === 0 ? '<p style="font-size:0.78rem;color:#888;margin:6px 0 0 0">(無 PTT 評價,前 3 項用中性 50)</p>' : ''}
        </div>
    `;
}

// ---- 適合度分析 tab ----
async function renderFitAnalysisView() {
    const needLogin = document.getElementById('fit-need-login');
    const content = document.getElementById('fit-content');
    if (!getToken()) {
        content.hidden = true;
        needLogin.hidden = false;
        return;
    }
    needLogin.hidden = true;
    content.hidden = false;

    // 偏好摘要
    const summary = document.getElementById('fit-profile-summary');
    const p = await loadProfile();
    if (p) {
        summary.innerHTML = `
            <div class="fit-summary-grid">
                <div class="fit-summary-tile"><div class="tile-label">甜度偏好</div><div class="tile-value">${p.pref_sweetness}/100</div></div>
                <div class="fit-summary-tile"><div class="tile-label">Loading 偏好</div><div class="tile-value">${p.pref_loading}/100</div></div>
                <div class="fit-summary-tile"><div class="tile-label">興趣領域</div><div class="tile-value">${p.interests.length > 0 ? p.interests.map(escapeHtml).join('、') : '未填'}</div></div>
            </div>`;
    }

    // Top 20 推薦
    const listEl = document.getElementById('fit-list');
    listEl.innerHTML = '載入中…';
    try {
        const items = await fetch(`${API_BASE}/me/recommendations?limit=20`, {
            headers: authHeaders(),
        }).then(r => r.ok ? r.json() : []);
        if (items.length === 0) {
            listEl.innerHTML = '<p style="color:#999">沒有可推薦的課程</p>';
            return;
        }
        listEl.innerHTML = items.map((it, i) => `
            <div class="fit-list-item" data-serial="${escapeAttr(it.serial_no)}">
                <div class="fit-rank">#${i + 1}</div>
                <div class="fit-item-main">
                    <div class="fit-item-title">${escapeHtml(it.course_name)} <span style="color:#888;font-weight:normal;font-size:0.85rem">${escapeHtml(it.course_code)}</span></div>
                    <div class="fit-item-meta">${escapeHtml(it.teacher)} · ${escapeHtml(it.credits)} 學分 · PTT ${it.fit.n_reviews} 篇評價</div>
                    <div class="fit-bars">
                        <span class="fit-bar-pill">推薦 <strong>${it.fit.recommendation.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">甜 <strong>${it.fit.sweetness.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">loading <strong>${it.fit.loading.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">興趣 <strong>${it.fit.interest.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">能力 <strong>${it.fit.ability.toFixed(0)}</strong></span>
                    </div>
                </div>
                <div class="fit-total-big">${it.fit.total.toFixed(0)}<span style="font-size:0.7em;color:#888">/100</span></div>
            </div>
        `).join('');
        listEl.querySelectorAll('.fit-list-item').forEach(el => {
            el.addEventListener('click', () => openDrawer(el.dataset.serial));
        });
    } catch (err) {
        console.error(err);
        listEl.innerHTML = '<p style="color:#df3d31">載入失敗</p>';
    }
}

// ==========================================================================
// 小工具:防 XSS
// ==========================================================================
function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(s) {
    return escapeHtml(s);
}
