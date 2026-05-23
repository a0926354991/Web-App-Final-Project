// 登入 / 註冊 / 登出 + Header / Sidebar 使用者區塊狀態 + bootstrap。
import { authState, historyState, wishlistState, profileState } from './state.js';
import { getToken, setToken, clearToken, apiLogin, apiRegister, apiLogout, apiMe, fetchProfile } from './api.js';
import { updateRadarFromProfile, resetRadarToDefault } from './dashboard.js';
import { loadHistory } from './history.js';
import { loadWishlist } from './wishlist.js';
import { loadDashboardRecommendations } from './fit.js';

const els = {
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

export function openAuthModal(mode = 'login') {
    authState.mode = mode;
    renderAuthMode();
    els.overlay.hidden = false;
    els.username.value = '';
    els.password.value = '';
    els.error.hidden = true;
    setTimeout(() => els.username.focus(), 50);
}

export function closeAuthModal() {
    els.overlay.hidden = true;
}

function renderAuthMode() {
    if (authState.mode === 'login') {
        els.title.textContent = '登入 Login';
        els.submit.textContent = '登入';
        els.switchLabel.textContent = '還沒有帳號？';
        els.switchLink.textContent = '註冊';
        els.password.autocomplete = 'current-password';
    } else {
        els.title.textContent = '註冊 Register';
        els.submit.textContent = '建立帳號';
        els.switchLabel.textContent = '已經有帳號？';
        els.switchLink.textContent = '登入';
        els.password.autocomplete = 'new-password';
    }
}

function showAuthError(msg) {
    els.error.textContent = msg;
    els.error.hidden = false;
}

async function updateLoggedOutHints() {
    const hint = document.getElementById('discover-logged-out-hint');
    if (hint) hint.hidden = !!getToken();
}

export async function applyLoggedInUI(user) {
    const name = user.username;
    const avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=002D62&color=ffffff`;
    els.headerAvatar.src = avatarUrl;
    els.headerUsername.textContent = `${name} 已登入`;
    els.sidebarAvatar.src = avatarUrl;
    els.sidebarUsername.textContent = name;
    els.sidebarUserid.textContent = `ID: ${user.id}`;
    els.sidebarStatusDot.className = 'status-dot online';
    els.sidebarStatusText.textContent = '已登入 Online';
    els.btnLogin.hidden = true;
    els.btnLogout.hidden = false;
    updateLoggedOutHints();

    const p = await fetchProfile().catch(() => null);
    if (p) updateRadarFromProfile(p);
    await loadHistory();
    await loadWishlist();
    loadDashboardRecommendations();
}

export function applyLoggedOutUI() {
    const avatarUrl = 'https://ui-avatars.com/api/?name=未登入&background=cccccc&color=000000';
    els.headerAvatar.src = avatarUrl;
    els.headerUsername.textContent = '未登入,請先登入';
    els.sidebarAvatar.src = avatarUrl;
    els.sidebarUsername.textContent = '未登入';
    els.sidebarUserid.textContent = '等待登入後顯示';
    els.sidebarStatusDot.className = 'status-dot waiting';
    els.sidebarStatusText.textContent = '等待登入 Waiting for login';
    els.btnLogin.hidden = false;
    els.btnLogout.hidden = true;

    resetRadarToDefault();
    profileState.loaded = false;
    historyState.items = [];
    historyState.idSet = new Set();
    historyState.loaded = false;
    wishlistState.items = [];
    wishlistState.idSet = new Set();
    wishlistState.loaded = false;
    loadDashboardRecommendations();
    updateLoggedOutHints();
}

export async function doLogout() {
    if (getToken()) {
        try { await apiLogout(); } catch (e) { console.warn('logout request failed', e); }
    }
    clearToken();
    applyLoggedOutUI();
}

export async function bootstrapAuth() {
    const token = getToken();
    if (!token) { applyLoggedOutUI(); return; }
    try {
        const user = await apiMe();
        applyLoggedInUI(user);
    } catch (err) {
        clearToken();
        applyLoggedOutUI();
    }
}

export function initAuth() {
    els.btnLogin.addEventListener('click', (e) => { e.preventDefault(); openAuthModal('login'); });
    const discoverLoginLink = document.getElementById('discover-login-link');
    if (discoverLoginLink) {
        discoverLoginLink.addEventListener('click', (e) => { e.preventDefault(); openAuthModal('login'); });
    }
    els.btnLogout.addEventListener('click', (e) => { e.preventDefault(); doLogout(); });
    els.close.addEventListener('click', closeAuthModal);
    els.overlay.addEventListener('click', (e) => {
        if (e.target === els.overlay) closeAuthModal();
    });
    els.switchLink.addEventListener('click', (e) => {
        e.preventDefault();
        openAuthModal(authState.mode === 'login' ? 'register' : 'login');
    });

    els.form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = els.username.value.trim();
        const password = els.password.value;
        if (!username || !password) { showAuthError('請填寫帳號與密碼'); return; }

        els.submit.disabled = true;
        els.error.hidden = true;
        try {
            const data = authState.mode === 'login'
                ? await apiLogin(username, password)
                : await apiRegister(username, password);
            setToken(data.token);
            // 登入後立刻清掉密碼欄,避免留在 DOM
            els.password.value = '';
            applyLoggedInUI(data.user);
            closeAuthModal();
        } catch (err) {
            showAuthError(err.detail || err.message || '連線失敗');
        } finally {
            els.submit.disabled = false;
        }
    });
}
