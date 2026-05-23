// 課程比較 Modal — 2-3 門課並排,含衝堂偵測。
import { MAX_COMPARE, WEEKDAY_LABELS } from './config.js';
import { compareState } from './state.js';
import { getToken, fetchCourse, fetchBatchFits } from './api.js';
import { courseId, parseCourseId, escapeHtml, escapeAttr, drawerSkeletonHTML, toast } from './utils.js';

const compareFab = document.getElementById('compare-fab');
const compareCountEl = document.getElementById('compare-count');
const compareModal = document.getElementById('compare-modal');
const compareBody = document.getElementById('compare-modal-body');

export function toggleCompare(id, checked) {
    if (checked) {
        if (compareState.ids.size >= MAX_COMPARE) {
            toast(`最多比較 ${MAX_COMPARE} 門課`, 'warn');
            const cb = document.querySelector(`#results-body .compare-check[data-id="${id}"]`);
            if (cb) cb.checked = false;
            return;
        }
        compareState.ids.add(id);
    } else {
        compareState.ids.delete(id);
    }
    updateCompareFab();
}

function updateCompareFab() {
    const n = compareState.ids.size;
    compareFab.hidden = n === 0;
    compareCountEl.textContent = n;
}

function clearCompare() {
    compareState.ids.clear();
    updateCompareFab();
    document.querySelectorAll('#results-body .compare-check').forEach(cb => { cb.checked = false; });
}

export function closeCompareModal() { compareModal.hidden = true; }

async function openCompareModal() {
    if (compareState.ids.size === 0) return;
    compareModal.hidden = false;
    compareBody.innerHTML = drawerSkeletonHTML();

    const ids = [...compareState.ids];
    try {
        const courses = await Promise.all(ids.map(id => fetchCourse(id)));
        let fits = {};
        if (getToken()) {
            fits = await fetchBatchFits(ids.map(id => parseCourseId(id))).catch(() => ({}));
        }
        compareBody.innerHTML = renderCompareTable(courses, fits);
    } catch (err) {
        console.error(err);
        compareBody.innerHTML = '<p class="drawer-empty">載入失敗</p>';
    }
}

function detectCompareConflict(courses) {
    const conflicts = [];
    for (let i = 0; i < courses.length; i++) {
        for (let j = i + 1; j < courses.length; j++) {
            const a = new Set((courses[i].slots || []).map(s => s.join('-')));
            const overlap = (courses[j].slots || []).filter(s => a.has(s.join('-')));
            if (overlap.length > 0) {
                conflicts.push({
                    a: courses[i].course_name,
                    b: courses[j].course_name,
                    slots: overlap.map(([wd, p]) => `週${WEEKDAY_LABELS[wd-1]}${p}`),
                });
            }
        }
    }
    return conflicts;
}

function renderCompareTable(courses, fits) {
    const conflicts = detectCompareConflict(courses);
    const conflictBanner = conflicts.length === 0 ? '' : `
        <div class="schedule-conflict-banner" style="margin-bottom: 14px">
            <i class="fas fa-exclamation-triangle"></i>
            <div>
                <strong>衝堂警告:</strong>
                ${conflicts.map(c => `${escapeHtml(c.a)} ↔ ${escapeHtml(c.b)} (${c.slots.join(', ')})`).join('; ')}
            </div>
        </div>
    `;

    const cols = courses.map(c => `
        <th class="course-header course-col">
            <span class="compare-course-name">${escapeHtml(c.course_name)}</span>
            <span class="compare-course-meta">${escapeHtml(c.course_code)} · ${escapeHtml(c.semester)} · 流水號 ${escapeHtml(c.serial_no)}</span>
        </th>
    `).join('');

    const row = (label, cellFn) => `
        <tr>
            <th class="label-col">${label}</th>
            ${courses.map(c => `<td class="course-col">${cellFn(c)}</td>`).join('')}
        </tr>
    `;

    const fitRow = (label, key) => {
        if (!getToken()) return '';
        return `
            <tr>
                <th class="label-col">${label}</th>
                ${courses.map(c => {
                    const f = fits[courseId(c)];
                    return `<td class="course-col">${f ? f[key].toFixed(0) : '—'}</td>`;
                }).join('')}
            </tr>
        `;
    };

    const fitTotal = getToken() ? `
        <tr>
            <th class="label-col">適合度</th>
            ${courses.map(c => {
                const f = fits[courseId(c)];
                return `<td class="course-col">${f ? `<span class="compare-fit-total">${f.total.toFixed(0)}%</span>` : '—'}</td>`;
            }).join('')}
        </tr>
    ` : '';

    const explanationRow = getToken() ? `
        <tr>
            <th class="label-col">推薦理由</th>
            ${courses.map(c => {
                const f = fits[courseId(c)];
                return `<td class="course-col" style="font-size:0.8rem;color:#555;font-style:italic">${f ? escapeHtml(f.explanation || '') : '—'}</td>`;
            }).join('')}
        </tr>
    ` : '';

    return `
        ${conflictBanner}
        <table class="compare-table">
            <thead>
                <tr><th class="label-col"></th>${cols}</tr>
            </thead>
            <tbody>
                ${row('教師', c => `<a href="#" class="teacher-link" data-teacher="${escapeAttr(c.teacher)}">${escapeHtml(c.teacher) || '—'}</a>`)}
                ${row('系所', c => escapeHtml(c.department) || '—')}
                ${row('學分', c => escapeHtml(c.credits) || '—')}
                ${row('必選修', c => escapeHtml(c.req_type) || '—')}
                ${row('授課語言', c => escapeHtml(c.language) || '—')}
                ${row('上課時段', c => {
                    const slots = c.slots || [];
                    if (!slots.length) return escapeHtml(c.schedule_time) || '—';
                    return slots.map(([wd, p]) => `週${WEEKDAY_LABELS[wd-1]}${p}`).join(', ');
                })}
                ${row('上課地點', c => escapeHtml(c.location) || '—')}
                ${fitTotal}
                ${fitRow('PTT 推薦', 'recommendation')}
                ${fitRow('甜度匹配', 'sweetness')}
                ${fitRow('loading 匹配', 'loading')}
                ${fitRow('興趣命中', 'interest')}
                ${fitRow('能力匹配', 'ability')}
                ${getToken() ? row('PTT 樣本', c => `${(fits[courseId(c)]?.n_reviews ?? 0)} 篇`) : ''}
                ${explanationRow}
                ${row('評量方式', c => `<div class="compare-text">${escapeHtml(c.grading) || '—'}</div>`)}
                ${row('課程要求', c => `<div class="compare-text">${escapeHtml(c.requirements) || '—'}</div>`)}
            </tbody>
        </table>
    `;
}

export function initCompare() {
    document.getElementById('compare-clear').addEventListener('click', (e) => {
        e.stopPropagation();
        clearCompare();
    });
    compareFab.addEventListener('click', openCompareModal);
    document.getElementById('compare-modal-close').addEventListener('click', closeCompareModal);
    compareModal.addEventListener('click', (e) => {
        if (e.target === compareModal) closeCompareModal();
    });
}
