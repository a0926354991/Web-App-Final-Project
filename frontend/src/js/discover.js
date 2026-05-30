// 課程探索表格 + 搜尋 + 篩選 + 分頁 + 適合度欄位 annotate / 排序。
import { PAGE_SIZE, API_BASE } from './config.js';
import { discoverState, compareState, historyState } from './state.js';
import { getToken, fetchDepartments, fetchCourses, fetchBatchFits } from './api.js';
import { courseId, escapeHtml, escapeAttr, skeletonRowsHTML, renderFitBadge } from './utils.js';
import { openDrawer } from './drawer.js';
import { openHistoryModal } from './history.js';
import { toggleCompare } from './compare.js';

const els = {
    searchInput: document.getElementById('search-input'),
    filterDept: document.getElementById('filter-dept'),
    filterCredits: document.getElementById('filter-credits'),
    filterSemesterTabs: document.getElementById('filter-semester-tabs'),
    filterNoPeriod1: document.getElementById('filter-no-period1'),
    filterMinSweetness: document.getElementById('filter-min-sweetness'),
    filterMaxLoading: document.getElementById('filter-max-loading'),
    searchBtn: document.getElementById('search-btn'),
    resultsBody: document.getElementById('results-body'),
    resultsMeta: document.getElementById('results-meta'),
    pagination: document.getElementById('pagination'),
    pagePrev: document.getElementById('page-prev'),
    pageNext: document.getElementById('page-next'),
    pageInfo: document.getElementById('page-info'),
    fitHeader: document.getElementById('fit-header'),
};

export async function initDiscoverView() {
    discoverState.initialized = true;

    try {
        const depts = await fetchDepartments();
        depts.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.name;
            opt.textContent = d.code ? `${d.code}  ${d.name}` : d.name;
            els.filterDept.appendChild(opt);
        });
    } catch (err) {
        console.error('載入系所清單失敗:', err);
        els.resultsMeta.textContent = `無法連線到 API server (${API_BASE})。請確認後端有啟動。`;
    }

    els.filterSemesterTabs.querySelectorAll('.semester-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            els.filterSemesterTabs.querySelectorAll('.semester-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            discoverState.offset = 0;
            searchCourses();
        });
    });

    els.searchBtn.addEventListener('click', () => { discoverState.offset = 0; searchCourses(); });
    els.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { discoverState.offset = 0; searchCourses(); }
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

    els.fitHeader.addEventListener('click', () => {
        discoverState.resultsSortDirection =
            discoverState.resultsSortDirection === 'desc' ? 'asc' : 'desc';
        sortResultsByFit();
    });

    await searchCourses();
}

export async function searchCourses({ keepParams = false } = {}) {
    if (!keepParams) {
        const activeSemBtn = els.filterSemesterTabs.querySelector('.semester-tab.active');
        discoverState.currentParams = {
            q: els.searchInput.value.trim(),
            dept: els.filterDept.value,
            credits: els.filterCredits.value,
            semester: activeSemBtn ? activeSemBtn.dataset.sem : '',
            no_period1: els.filterNoPeriod1.checked,
            min_sweetness: els.filterMinSweetness.value,
            max_loading: els.filterMaxLoading.value,
        };
    }

    const params = new URLSearchParams();
    const { q, dept, credits, semester, no_period1, min_sweetness, max_loading } = discoverState.currentParams;
    if (q) params.set('q', q);
    if (dept) params.set('dept', dept);
    if (credits) params.set('credits', credits);
    if (semester) params.set('semester', semester);
    if (no_period1) params.set('no_period1', 'true');
    if (min_sweetness) params.set('min_sweetness', min_sweetness);
    if (max_loading) params.set('max_loading', max_loading);
    params.set('limit', PAGE_SIZE);
    params.set('offset', discoverState.offset);

    els.resultsBody.innerHTML = skeletonRowsHTML(10, 6);
    els.pagination.hidden = true;

    try {
        const data = await fetchCourses(params);
        discoverState.total = data.total;
        renderResults(data.items);
        renderMeta();
        renderPagination();
        els.fitHeader.hidden = true;
        if (getToken()) annotateResultsWithFit(data.items);
    } catch (err) {
        console.error(err);
        els.resultsBody.innerHTML = '<tr><td colspan="11" class="empty-row">搜尋失敗,請確認 API server 是否啟動</td></tr>';
    }
}

function renderResults(items) {
    if (items.length === 0) {
        const hint = (els.searchInput.value || els.filterDept.value || els.filterCredits.value)
            ? '<tr><td colspan="11" class="empty-row">沒有符合條件的課程 — 試試減少篩選或換個關鍵字</td></tr>'
            : '<tr><td colspan="11" class="empty-row">沒有資料 — 確認後端有跑起來?</td></tr>';
        els.resultsBody.innerHTML = hint;
        return;
    }
    els.resultsBody.innerHTML = items.map(c => {
        const id = courseId(c);
        const inHist = historyState.idSet.has(id);
        const btnHtml = getToken() ? `
            <button class="btn-add-history ${inHist ? 'in-history' : ''}" data-id="${escapeAttr(id)}" data-name="${escapeAttr(c.course_name)}">
                ${inHist ? '<i class="fas fa-check"></i> 已修' : '<i class="fas fa-plus"></i> 加入歷史'}
            </button>` : '';
        const checked = compareState.ids.has(id) ? 'checked' : '';
        return `
        <tr data-id="${escapeAttr(id)}">
            <td class="check-cell"><input type="checkbox" class="compare-check" data-id="${escapeAttr(id)}" ${checked}></td>
            <td>${escapeHtml(c.semester)}</td>
            <td>${escapeHtml(c.course_code)}</td>
            <td>${escapeHtml(c.course_name)}</td>
            <td><a href="#" class="teacher-link" data-teacher="${escapeAttr(c.teacher)}">${escapeHtml(c.teacher)}</a></td>
            <td>${escapeHtml(c.department)}</td>
            <td>${escapeHtml(c.credits)}</td>
            <td>${escapeHtml(c.schedule_time) || '—'}</td>
            <td class="loc-col">${escapeHtml(c.location) || '—'}</td>
            <td class="action-cell">${btnHtml}</td>
        </tr>
        `;
    }).join('');

    els.resultsBody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.btn-add-history')
                || e.target.closest('.teacher-link')
                || e.target.closest('.compare-check')) return;
            els.resultsBody.querySelectorAll('tr').forEach(r => r.classList.remove('active'));
            row.classList.add('active');
            openDrawer(row.dataset.id);
        });
    });

    els.resultsBody.querySelectorAll('.compare-check').forEach(cb => {
        cb.addEventListener('change', (e) => {
            e.stopPropagation();
            toggleCompare(cb.dataset.id, cb.checked);
        });
    });

    els.resultsBody.querySelectorAll('.btn-add-history:not(.in-history)').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openHistoryModal(btn.dataset.id, btn.dataset.name);
        });
    });
}

function renderMeta() {
    const t = discoverState.total;
    const from = t === 0 ? 0 : discoverState.offset + 1;
    const to = Math.min(discoverState.offset + PAGE_SIZE, t);
    els.resultsMeta.textContent = `共 ${t} 筆,顯示 ${from}–${to}`;
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

async function annotateResultsWithFit(courseItems) {
    if (!getToken() || courseItems.length === 0) return;
    try {
        const fits = await fetchBatchFits(
            courseItems.map(c => ({ semester: c.semester, serial_no: c.serial_no }))
        );
        els.fitHeader.hidden = false;
        els.resultsBody.querySelectorAll('tr').forEach(row => {
            const id = row.dataset.id;
            if (!id) return;
            const f = fits[id];
            if (!f) return;
            const actionCell = row.querySelector('.action-cell');
            const cell = document.createElement('td');
            cell.dataset.fit = f.total;
            cell.innerHTML = renderFitBadge(f.total);
            row.insertBefore(cell, actionCell);
        });
        sortResultsByFit();
    } catch (err) {
        console.warn('annotateResultsWithFit failed', err);
    }
}

function sortResultsByFit() {
    const rows = [...els.resultsBody.querySelectorAll('tr[data-id]')];
    rows.sort((a, b) => {
        const av = Number(a.querySelector('[data-fit]')?.dataset.fit ?? -1);
        const bv = Number(b.querySelector('[data-fit]')?.dataset.fit ?? -1);
        return discoverState.resultsSortDirection === 'desc' ? bv - av : av - bv;
    });
    rows.forEach(r => els.resultsBody.appendChild(r));
}

// 讓 history modal 新增完後可以重繪表格按鈕狀態
export function isDiscoverViewVisible() {
    return !document.getElementById('view-discover').hidden;
}
