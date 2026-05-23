// 純函數小工具 — escape / courseId / toast / skeleton / fit badge / PDF export
import { TOAST_ICONS } from './config.js';

// ------- XSS escape -------
export function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function escapeAttr(s) {
    return escapeHtml(s);
}

// ------- Course ID (composite key semester__serial_no) -------
export function courseId(c) {
    if (!c) return '';
    if (typeof c === 'string') return c;
    return `${c.semester}__${c.serial_no}`;
}

export function parseCourseId(id) {
    const idx = (id || '').indexOf('__');
    if (idx < 0) return { semester: '', serial_no: id || '' };
    return { semester: id.slice(0, idx), serial_no: id.slice(idx + 2) };
}

export function courseUrlPath(c) {
    const { semester, serial_no } = typeof c === 'string' ? parseCourseId(c) : c;
    return `${encodeURIComponent(semester)}/${encodeURIComponent(serial_no)}`;
}

// ------- Toast -------
export function toast(message, type = 'info', durationMs = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<i class="fas ${TOAST_ICONS[type] || 'fa-info-circle'}"></i><span>${message}</span>`;
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
        el.classList.remove('show');
        setTimeout(() => el.remove(), 250);
    }, durationMs);
}

// ------- Loading skeleton -------
export function skeletonRowsHTML(cols, n = 6) {
    const td = `<td><span class="skeleton skeleton-text"></span></td>`;
    return Array.from({ length: n }, () =>
        `<tr class="skeleton-row">${td.repeat(cols)}</tr>`
    ).join('');
}

export function drawerSkeletonHTML() {
    return `
        <div class="drawer-skeleton">
            <span class="skeleton block sk-title"></span>
            <span class="skeleton block sk-block"></span>
            <span class="skeleton block sk-block" style="height: 60px;"></span>
            <span class="skeleton block sk-block" style="height: 120px;"></span>
            <span class="skeleton block sk-block" style="height: 80px;"></span>
        </div>
    `;
}

// ------- Fit badge -------
export function fitClass(score) {
    if (score >= 75) return 'fit-high';
    if (score >= 55) return 'fit-mid';
    return 'fit-low';
}

export function renderFitBadge(score) {
    return `<span class="fit-badge ${fitClass(score)}">${score.toFixed(0)}</span>`;
}

export function lowSampleBadge(n) {
    if (n === 0) return ' <span class="low-sample-warn" title="無 PTT 評價,前 3 項分數用中性 50"><i class="fas fa-exclamation-circle"></i> 無評價</span>';
    if (n <= 2) return ' <span class="low-sample-warn" title="PTT 樣本少,分數僅供參考"><i class="fas fa-exclamation-circle"></i> 樣本少</span>';
    return '';
}

// ------- PDF export (用瀏覽器列印) -------
export function exportToPDF(viewId) {
    document.body.classList.add('printing');
    document.body.dataset.printingView = viewId;
    window.print();
    document.body.classList.remove('printing');
    delete document.body.dataset.printingView;
}

// ------- Focus search input (鍵盤快捷鍵用) -------
export function focusSearchInput() {
    const discoverNav = document.querySelector('.sidebar-item[data-target="discover"]');
    if (discoverNav && !discoverNav.classList.contains('active')) {
        discoverNav.click();
    }
    const input = document.getElementById('search-input');
    if (input) {
        input.focus();
        input.select();
    }
}
