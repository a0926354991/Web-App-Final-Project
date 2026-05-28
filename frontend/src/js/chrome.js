// Chrome:深色模式 / 側邊欄 / view 切換 / 鍵盤快捷鍵。
import { THEME_KEY } from './config.js';
import { focusSearchInput } from './utils.js';
import { updateChartThemeFromBody } from './dashboard.js';
import { renderProfileView } from './profile.js';
import { renderHistoryView } from './history.js';
import { renderFitAnalysisView } from './fit.js';
import { renderScheduleView } from './schedule.js';
import { renderWishlistView } from './wishlist.js';
import { initDiscoverView } from './discover.js';
import { discoverState } from './state.js';
import { closeDrawer } from './drawer.js';
import { closeAuthModal } from './auth.js';
import { closeHistoryModal } from './history.js';
import { closeCompareModal } from './compare.js';

// ------- 主題 -------
// 'tech' = 全站科技深色 (theme-dark 深色基礎 + tech-skin 漸層/玻璃/霓虹增強),為預設。
// 'light' = 原本的亮色。toggle 在 tech ↔ light 之間切。
export function applyTheme(name) {
    const tech = name !== 'light';  // 預設 / 非 light 一律走科技風
    document.body.classList.toggle('theme-dark', tech);
    document.body.classList.toggle('tech-skin', tech);
    const icon = document.querySelector('#theme-toggle i');
    if (icon) icon.className = tech ? 'fas fa-sun' : 'fas fa-moon';
    updateChartThemeFromBody();
}

// ------- Sidebar -------
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 992;
    if (isMobile) {
        sidebar.classList.toggle('mobile-open');
    } else {
        sidebar.classList.toggle('desktop-collapsed');
    }
}

// ------- View 切換 (router 雛形) -------
function setupRouter() {
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

            if (target === 'discover' && !discoverState.initialized) initDiscoverView();
            if (target === 'userinfo') renderProfileView();
            if (target === 'history') renderHistoryView();
            if (target === 'fit') renderFitAnalysisView();
            if (target === 'schedule') renderScheduleView();
            if (target === 'wishlist') renderWishlistView();

            if (window.innerWidth <= 992) {
                document.getElementById('sidebar').classList.remove('mobile-open');
            }
        });
    });
}

// ------- 鍵盤快捷鍵 -------
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Esc: 關閉抽屜 / modal
        if (e.key === 'Escape') {
            closeDrawer();
            closeAuthModal();
            closeHistoryModal();
            closeCompareModal();
            if (document.activeElement && document.activeElement.blur) {
                document.activeElement.blur();
            }
            return;
        }

        // Cmd/Ctrl + K
        if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            focusSearchInput();
            return;
        }

        // 不在輸入框內時的快捷鍵
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
            || e.target.isContentEditable) {
            return;
        }
        if (e.key === '/') {
            e.preventDefault();
            focusSearchInput();
        }
    });
}

// ------- Entry -------
export function initChrome() {
    // theme — 預設科技風 (tech),使用者可切回 light
    applyTheme(localStorage.getItem(THEME_KEY) || 'tech');
    document.getElementById('theme-toggle').addEventListener('click', () => {
        const next = document.body.classList.contains('tech-skin') ? 'light' : 'tech';
        localStorage.setItem(THEME_KEY, next);
        applyTheme(next);
    });

    // sidebar
    document.querySelector('.hamburger').addEventListener('click', toggleSidebar);
    document.querySelector('.main-content').addEventListener('click', () => {
        const sidebar = document.getElementById('sidebar');
        if (window.innerWidth <= 992 && sidebar.classList.contains('mobile-open')) {
            sidebar.classList.remove('mobile-open');
        }
    });

    setupRouter();
    setupKeyboardShortcuts();

    // 全域 data-goto 委派(任意位置的 [data-goto=tab] 連結 → 切換到該 tab)
    document.addEventListener('click', (e) => {
        const link = e.target.closest('[data-goto]');
        if (!link) return;
        e.preventDefault();
        const target = link.dataset.goto;
        const item = document.querySelector(`.sidebar-item[data-target="${target}"]`);
        if (item) item.click();
    });
}
