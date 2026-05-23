// 修課歷史 view + 「加入歷史」modal。
import { historyState, authState, discoverState } from './state.js';
import { getToken, fetchHistory, addHistory as apiAddHistory, deleteHistory } from './api.js';
import { courseId, parseCourseId, escapeHtml, skeletonRowsHTML, toast, exportToPDF } from './utils.js';
import { openAuthModal } from './auth.js';
import { searchCourses, isDiscoverViewVisible } from './discover.js';

const els = {
    needLogin: document.getElementById('history-need-login'),
    content: document.getElementById('history-content'),
    meta: document.getElementById('history-meta'),
    body: document.getElementById('history-body'),
    overlay: document.getElementById('history-modal-overlay'),
    close: document.getElementById('history-modal-close'),
    course: document.getElementById('history-modal-course'),
    form: document.getElementById('history-form'),
    grade: document.getElementById('history-grade'),
    notes: document.getElementById('history-notes'),
    error: document.getElementById('history-error'),
    submit: document.getElementById('history-submit'),
};

export async function loadHistory() {
    if (!getToken()) {
        historyState.items = [];
        historyState.idSet = new Set();
        return;
    }
    try {
        historyState.items = await fetchHistory();
        historyState.idSet = new Set(historyState.items.map(i => courseId(i)));
        historyState.loaded = true;
    } catch (err) {
        console.warn('loadHistory failed', err);
    }
}

export async function renderHistoryView() {
    if (!getToken()) {
        els.content.hidden = true;
        els.needLogin.hidden = false;
        return;
    }
    els.needLogin.hidden = true;
    els.content.hidden = false;

    if (!historyState.loaded) {
        els.meta.textContent = '載入中…';
        els.body.innerHTML = skeletonRowsHTML(8, 5);
        await loadHistory();
    }
    renderHistoryTable();
}

function renderHistoryTable() {
    const items = historyState.items;
    els.meta.textContent = `共 ${items.length} 筆`;
    if (items.length === 0) {
        els.body.innerHTML = '<tr><td colspan="8" class="empty-row">尚未加入任何課程 — 到「課程探索」加幾門吧</td></tr>';
        return;
    }
    els.body.innerHTML = items.map(h => `
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

    els.body.querySelectorAll('.btn-delete-row').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('確定要刪除這筆紀錄?')) return;
            const id = btn.dataset.id;
            try {
                await deleteHistory(id);
                await loadHistory();
                renderHistoryTable();
            } catch (err) {
                console.error(err);
                toast('刪除失敗', 'error');
            }
        });
    });
}

export function openHistoryModal(id, courseName) {
    if (!getToken()) {
        openAuthModal('login');
        return;
    }
    authState.pendingHistoryId = id;
    const { semester, serial_no } = parseCourseId(id);
    els.course.textContent = `${courseName} (${semester} · 流水號 ${serial_no})`;
    els.grade.value = '';
    els.notes.value = '';
    els.error.hidden = true;
    els.overlay.hidden = false;
    setTimeout(() => els.grade.focus(), 50);
}

export function closeHistoryModal() {
    els.overlay.hidden = true;
    authState.pendingHistoryId = null;
}

export function initHistory() {
    els.close.addEventListener('click', closeHistoryModal);
    els.overlay.addEventListener('click', (e) => {
        if (e.target === els.overlay) closeHistoryModal();
    });

    els.form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!authState.pendingHistoryId) return;
        const { semester, serial_no } = parseCourseId(authState.pendingHistoryId);
        els.submit.disabled = true;
        els.error.hidden = true;
        try {
            await apiAddHistory({
                semester,
                serial_no,
                grade: els.grade.value || null,
                notes: els.notes.value || null,
            });
            await loadHistory();
            // 重繪探索表格按鈕狀態
            if (discoverState.total > 0 && isDiscoverViewVisible()) {
                searchCourses({ keepParams: true });
            }
            closeHistoryModal();
        } catch (err) {
            console.error(err);
            els.error.textContent = `加入失敗:${err.detail || err.message}`;
            els.error.hidden = false;
        } finally {
            els.submit.disabled = false;
        }
    });

    document.getElementById('history-export').addEventListener('click', () => exportToPDF('view-history'));
}
