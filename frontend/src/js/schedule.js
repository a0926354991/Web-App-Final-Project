// 我的課表 — localStorage 持久化 + 衝堂偵測 + 視覺化週課表 + PDF 匯出。
import { SCHEDULE_KEY, WEEKDAY_LABELS, PERIOD_ORDER } from './config.js';
import { fetchCourse } from './api.js';
import { courseId, escapeHtml, escapeAttr, toast, exportToPDF } from './utils.js';
import { openDrawer } from './drawer.js';

// 結構: { "{semester}__{serial_no}": { semester, serial_no, course_name, teacher, slots } }
function getSchedule() {
    try { return JSON.parse(localStorage.getItem(SCHEDULE_KEY) || '{}'); }
    catch (e) { return {}; }
}
function saveSchedule(s) {
    localStorage.setItem(SCHEDULE_KEY, JSON.stringify(s));
}
export function inSchedule(id) { return id in getSchedule(); }

function addToSchedule(course) {
    const s = getSchedule();
    s[courseId(course)] = {
        semester: course.semester,
        serial_no: course.serial_no,
        course_name: course.course_name,
        teacher: course.teacher,
        course_code: course.course_code,
        slots: course.slots || [],
    };
    saveSchedule(s);
}

function removeFromSchedule(id) {
    const s = getSchedule();
    delete s[id];
    saveSchedule(s);
}

export function renderScheduleView() {
    const sched = getSchedule();
    const ids = Object.keys(sched);
    const summaryEl = document.getElementById('schedule-summary');
    const conflictEl = document.getElementById('schedule-conflicts');
    const gridEl = document.getElementById('schedule-grid');
    const listCard = document.getElementById('schedule-list-card');
    const listEl = document.getElementById('schedule-course-list');

    summaryEl.textContent = ids.length === 0
        ? '尚未加入任何課程 — 到課程探索/推薦頁點「加入課表」'
        : `已加入 ${ids.length} 門課`;

    const cellMap = {};
    ids.forEach(id => {
        const c = sched[id];
        (c.slots || []).forEach(([wd, p]) => {
            const key = `${wd}-${p}`;
            (cellMap[key] = cellMap[key] || []).push({ id, ...c });
        });
    });

    const conflictKeys = Object.entries(cellMap).filter(([_, list]) => list.length > 1);
    if (conflictKeys.length > 0) {
        conflictEl.hidden = false;
        const msgs = conflictKeys.map(([key, list]) => {
            const [wd, p] = key.split('-');
            const names = list.map(c => c.course_name).join(' / ');
            return `週${WEEKDAY_LABELS[wd-1]} 第${p}節:${names}`;
        });
        conflictEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i> 衝堂:` + msgs.join('; ');
    } else {
        conflictEl.hidden = true;
    }

    const cells = ['<div class="header"></div>'];
    for (let wd = 1; wd <= 7; wd++) {
        cells.push(`<div class="header">週${WEEKDAY_LABELS[wd-1]}</div>`);
    }
    PERIOD_ORDER.forEach(p => {
        cells.push(`<div class="period-label">${p}</div>`);
        for (let wd = 1; wd <= 7; wd++) {
            const list = cellMap[`${wd}-${p}`] || [];
            const conflict = list.length > 1 ? ' conflict' : '';
            const inner = list.map(c => `
                <div class="cell-course" data-id="${escapeAttr(c.id)}" title="${escapeAttr(c.teacher)}">
                    ${escapeHtml(c.course_name)}
                </div>
            `).join('');
            cells.push(`<div class="cell${conflict}">${inner}</div>`);
        }
    });
    gridEl.innerHTML = cells.join('');

    if (ids.length > 0) {
        listCard.hidden = false;
        listEl.innerHTML = ids.map(id => {
            const c = sched[id];
            const slotText = (c.slots && c.slots.length)
                ? c.slots.map(([wd, p]) => `週${WEEKDAY_LABELS[wd-1]}${p}`).join(', ')
                : '無排定時段';
            return `
                <div class="schedule-course-item" data-id="${escapeAttr(id)}">
                    <div>
                        <div><strong>${escapeHtml(c.course_name)}</strong> <span style="color:#888">${escapeHtml(c.course_code || '')} · ${escapeHtml(c.semester || '')}</span></div>
                        <div class="meta">${escapeHtml(c.teacher || '')} · ${slotText}</div>
                    </div>
                    <button class="btn-remove-schedule" data-id="${escapeAttr(id)}" title="移除"><i class="fas fa-trash"></i></button>
                </div>
            `;
        }).join('');
    } else {
        listCard.hidden = true;
    }

    gridEl.querySelectorAll('.cell-course').forEach(el => {
        el.addEventListener('click', () => openDrawer(el.dataset.id));
    });
    listEl.querySelectorAll('.schedule-course-item').forEach(el => {
        el.addEventListener('click', (e) => {
            if (e.target.closest('.btn-remove-schedule')) return;
            openDrawer(el.dataset.id);
        });
    });
    listEl.querySelectorAll('.btn-remove-schedule').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeFromSchedule(btn.dataset.id);
            renderScheduleView();
            refreshScheduleButtons();
        });
    });
}

export function scheduleToggleBtn(course) {
    const id = courseId(course);
    const has = inSchedule(id);
    return `<button class="btn-toggle-schedule ${has ? 'in-schedule' : ''}" data-schedule-toggle="${escapeAttr(id)}">
        ${has ? '<i class="fas fa-check"></i> 已在課表' : '<i class="fas fa-calendar-plus"></i> 加入課表'}
    </button>`;
}

function refreshScheduleButtons() {
    document.querySelectorAll('[data-schedule-toggle]').forEach(btn => {
        const has = inSchedule(btn.dataset.scheduleToggle);
        btn.classList.toggle('in-schedule', has);
        btn.innerHTML = has ? '<i class="fas fa-check"></i> 已在課表' : '<i class="fas fa-calendar-plus"></i> 加入課表';
    });
}

export function initSchedule() {
    document.getElementById('schedule-clear').addEventListener('click', () => {
        if (!confirm('確定清空課表?')) return;
        localStorage.removeItem(SCHEDULE_KEY);
        renderScheduleView();
        refreshScheduleButtons();
    });

    document.getElementById('schedule-export').addEventListener('click', () => exportToPDF('view-schedule'));

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-schedule-toggle]');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const id = btn.dataset.scheduleToggle;
        if (inSchedule(id)) {
            removeFromSchedule(id);
        } else {
            try {
                const c = await fetchCourse(id);
                addToSchedule(c);
            } catch (err) {
                toast('載入課程資料失敗', 'error');
                return;
            }
        }
        refreshScheduleButtons();
    });
}
