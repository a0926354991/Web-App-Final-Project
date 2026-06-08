// 課程比較 Modal — 2-3 門課並排,含衝堂偵測。
import { MAX_COMPARE, WEEKDAY_LABELS } from './config.js';
import { compareState } from './state.js';
import { getToken, fetchCourse, fetchBatchFits, fetchSubstitutes } from './api.js';
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
    updateCompareUrl();
}

function updateCompareUrl() {
    const url = new URL(window.location);
    if (compareState.ids.size > 0) {
        url.searchParams.set('compare', Array.from(compareState.ids).join(','));
    } else {
        url.searchParams.delete('compare');
    }
    history.replaceState(null, '', url);
}

function clearCompare() {
    compareState.ids.clear();
    updateCompareFab();
    document.querySelectorAll('#results-body .compare-check').forEach(cb => { cb.checked = false; });
}

// 從比較移除單一課程:同步取消探索頁該列的勾選,更新 FAB / URL,
// 還有剩課就重渲染比較表,沒了就關掉 Modal。
function removeFromCompare(id) {
    compareState.ids.delete(id);
    const cb = document.querySelector(`#results-body .compare-check[data-id="${id}"]`);
    if (cb) cb.checked = false;
    updateCompareFab();
    if (compareState.ids.size === 0) {
        closeCompareModal();
    } else {
        openCompareModal();  // 重抓剩下的課重渲染
    }
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

        // 每欄的「移除此課」✕ 按鈕
        compareBody.querySelectorAll('[data-remove-id]').forEach(btn => {
            btn.addEventListener('click', () => removeFromCompare(btn.dataset.removeId));
        });

        // 「AI 找替代」按鈕
        compareBody.querySelectorAll('[data-sub-id]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.subId;
                const slot = document.getElementById('ai-substitutes-result');
                compareBody.querySelectorAll('[data-sub-id]').forEach(b => { b.disabled = true; });
                slot.innerHTML = '<div style="margin-top:10px;color:#666">AI 思考中…</div>';
                try {
                    const resp = await fetchSubstitutes(id, 5);
                    if (!resp || (!resp.candidates && !resp.explanation)) {
                        slot.innerHTML = '<div style="margin-top:10px;color:#999">沒有合適的替代課程</div>';
                        return;
                    }
                    const candHtml = (resp.candidates || []).map(c => `
                        <div style="padding:6px 0;border-bottom:1px solid #eee">
                            <strong>${escapeHtml(c.course_name)}</strong>
                            <span style="color:#888;font-size:0.85rem"> · ${escapeHtml(c.teacher || '')} · ${escapeHtml(c.department || '')}</span>
                        </div>
                    `).join('');
                    slot.innerHTML = `
                        <div class="ai-summary-box" style="margin-top:10px">
                            <div class="ai-summary-label"><i class="fas fa-robot"></i> AI 替代建議</div>
                            ${resp.explanation ? `<div class="ai-summary-text" style="white-space:pre-wrap;margin-bottom:8px">${escapeHtml(resp.explanation)}</div>` : ''}
                            ${candHtml}
                        </div>`;
                } catch (err) {
                    slot.innerHTML = '<div style="margin-top:10px;color:#c33">替代查詢失敗</div>';
                } finally {
                    compareBody.querySelectorAll('[data-sub-id]').forEach(b => { b.disabled = false; });
                }
            });
        });
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
    let conflictBanner = '';
    if (conflicts.length > 0) {
        // 給每個衝堂的第二門課加個 AI 找替代按鈕
        const subBtns = getToken() ? courses.map(c => `
            <button class="ai-btn" data-sub-id="${escapeAttr(courseId(c))}" data-sub-name="${escapeAttr(c.course_name)}">
                <i class="fas fa-robot"></i> AI 找「${escapeHtml(c.course_name)}」的替代
            </button>
        `).join('') : '';
        conflictBanner = `
            <div class="schedule-conflict-banner" style="margin-bottom: 14px">
                <i class="fas fa-exclamation-triangle"></i>
                <div>
                    <strong>衝堂警告:</strong>
                    ${conflicts.map(c => `${escapeHtml(c.a)} ↔ ${escapeHtml(c.b)} (${c.slots.join(', ')})`).join('; ')}
                    <div style="margin-top:8px">${subBtns}</div>
                    <div id="ai-substitutes-result"></div>
                </div>
            </div>
        `;
    }

    const cols = courses.map(c => `
        <th class="course-header course-col">
            <button class="compare-remove-col" data-remove-id="${escapeAttr(courseId(c))}"
                    title="從比較移除此課" aria-label="移除 ${escapeAttr(c.course_name)}">
                <i class="fas fa-times"></i>
            </button>
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

export async function loadCompareFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const compareParam = params.get('compare');
    if (!compareParam) return;

    const ids = [...new Set(compareParam.split(','))].slice(0, MAX_COMPARE);
    if (ids.length === 0) return;

    let validCount = 0;
    let anyInvalid = false;

    // Load courses to check validity
    const checks = await Promise.all(ids.map(id => fetchCourse(id).catch(() => null)));
    
    checks.forEach((course, index) => {
        if (course) {
            compareState.ids.add(ids[index]);
            validCount++;
        } else {
            anyInvalid = true;
        }
    });

    if (anyInvalid) {
        toast('連結中部分課程無法找到', 'warn');
    }

    if (validCount > 0) {
        updateCompareFab();
        openCompareModal();
    }
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
