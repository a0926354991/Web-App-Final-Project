// 我的課表 — localStorage 持久化 + 衝堂偵測 + 視覺化週課表 + PDF 匯出。
import { SCHEDULE_KEY, WEEKDAY_LABELS, PERIOD_ORDER } from './config.js';
import { fetchCourse, fetchScheduleBalance, getToken } from './api.js';
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
        location: course.location || '',
        slots: course.slots || [],
    };
    saveSchedule(s);
}

function removeFromSchedule(id) {
    const s = getSchedule();
    delete s[id];
    saveSchedule(s);
}

function addSlotToCourse(id, weekday, period) {
    const s = getSchedule();
    if (!s[id]) return;
    s[id].slots = s[id].slots || [];
    const exists = s[id].slots.some(([w, p]) => String(w) === String(weekday) && String(p) === String(period));
    if (!exists) {
        s[id].slots.push([Number(weekday), String(period)]);
    }
    saveSchedule(s);
}

function removeSlotFromCourse(id, weekday, period) {
    const s = getSchedule();
    if (!s[id] || !s[id].slots) return;
    s[id].slots = s[id].slots.filter(([w, p]) => !(String(w) === String(weekday) && String(p) === String(period)));
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
            const inner = list.map(c => {
                const titleParts = [c.teacher, c.location].filter(Boolean).join(' · ');
                return `
                <div class="cell-course" data-id="${escapeAttr(c.id)}" title="${escapeAttr(titleParts)}">
                    ${escapeHtml(c.course_name)}
                    ${c.location ? `<span class="cell-course-loc">${escapeHtml(c.location)}</span>` : ''}
                </div>
            `;
            }).join('');
            cells.push(`<div class="cell${conflict}">${inner}</div>`);
        }
    });
    gridEl.innerHTML = cells.join('');

    if (ids.length > 0) {
        listCard.hidden = false;
        const wdOptions = WEEKDAY_LABELS.map((lbl, i) => `<option value="${i+1}">週${lbl}</option>`).join('');
        const pOptions = PERIOD_ORDER.map(p => `<option value="${p}">第 ${p} 節</option>`).join('');
        listEl.innerHTML = ids.map(id => {
            const c = sched[id];
            const slots = c.slots || [];
            const slotChips = slots.length === 0
                ? '<span style="color:#c80">無排定時段(請手動加)</span>'
                : slots.map(([wd, p]) => `
                    <span class="slot-chip">
                        週${WEEKDAY_LABELS[wd-1]}${p}
                        <button class="slot-chip-x" data-rm-slot data-id="${escapeAttr(id)}" data-wd="${wd}" data-p="${escapeAttr(p)}" title="移除此時段">×</button>
                    </span>
                `).join('');
            return `
                <div class="schedule-course-item" data-id="${escapeAttr(id)}">
                    <div style="flex:1">
                        <div><strong>${escapeHtml(c.course_name)}</strong> <span style="color:#888">${escapeHtml(c.course_code || '')} · ${escapeHtml(c.semester || '')}</span></div>
                        <div class="meta">${escapeHtml(c.teacher || '')}${c.location ? ` · <i class="fas fa-location-dot"></i> ${escapeHtml(c.location)}` : ''}</div>
                        <div class="slot-row">
                            ${slotChips}
                            <span class="slot-add-inline" data-id="${escapeAttr(id)}">
                                <select class="slot-add-wd">${wdOptions}</select>
                                <select class="slot-add-p">${pOptions}</select>
                                <button class="btn-add-slot" data-id="${escapeAttr(id)}">+ 加時段</button>
                            </span>
                        </div>
                    </div>
                    <button class="btn-remove-schedule" data-id="${escapeAttr(id)}" title="移除整門課"><i class="fas fa-trash"></i></button>
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
            if (e.target.closest('.slot-row')) return;  // 點時段區域不開 drawer
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
    listEl.querySelectorAll('.btn-add-slot').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            const wrap = btn.closest('.slot-add-inline');
            const wd = wrap.querySelector('.slot-add-wd').value;
            const p = wrap.querySelector('.slot-add-p').value;
            addSlotToCourse(id, wd, p);
            renderScheduleView();
        });
    });
    listEl.querySelectorAll('[data-rm-slot]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeSlotFromCourse(btn.dataset.id, btn.dataset.wd, btn.dataset.p);
            renderScheduleView();
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

// 課表美感健檢 — 純前端分析 slots,給趣味分數 + 吐槽。
function analyzeScheduleVibe() {
    const sched = getSchedule();
    const courses = Object.values(sched);
    const allSlots = courses.flatMap(c => c.slots || []);
    if (allSlots.length === 0) {
        return { score: null, msg: '課表是空的,先加幾門課再來健檢 🫥' };
    }

    // 各項指標
    const byDay = {};       // weekday → [periods]
    let earlyBird = 0;      // 早八 (第 1 節) 次數
    allSlots.forEach(([wd, p]) => {
        (byDay[wd] = byDay[wd] || []).push(p);
        if (String(p) === '1') earlyBird++;
    });
    const daysWithClass = Object.keys(byDay).length;
    const maxPerDay = Math.max(...Object.values(byDay).map(ps => ps.length));
    const totalSlots = allSlots.length;
    const freeDays = 5 - Object.keys(byDay).filter(wd => Number(wd) <= 5).length; // 平日空堂天

    // 評分 (100 起扣)
    let score = 100;
    const roasts = [];
    if (earlyBird >= 3) { score -= 25; roasts.push(`你有 ${earlyBird} 個早八,鬧鐘要設好幾個 ⏰`); }
    else if (earlyBird >= 1) { score -= 8; roasts.push(`${earlyBird} 個早八,還行 😪`); }
    else { roasts.push('零早八,人生勝利組 🌞'); }

    if (maxPerDay >= 6) { score -= 20; roasts.push(`單日最多塞了 ${maxPerDay} 節,當天會升天 💀`); }
    else if (maxPerDay >= 4) { score -= 8; roasts.push(`某天 ${maxPerDay} 節連發,記得帶午餐`); }

    if (freeDays >= 2) { roasts.push(`平日有 ${freeDays} 天空堂,排得很爽 🎉`); }
    else if (freeDays === 0) { score -= 12; roasts.push('平日天天有課,沒有喘息日 😮‍💨'); }

    if (daysWithClass >= 6) { score -= 10; roasts.push('連假日都有課?太拚了'); }

    score = Math.max(0, Math.min(100, score));
    const grade = score >= 85 ? 'S' : score >= 70 ? 'A' : score >= 55 ? 'B' : score >= 40 ? 'C' : 'D';
    return { score, grade, totalSlots, earlyBird, maxPerDay, freeDays, roasts };
}

export function initSchedule() {
    document.getElementById('schedule-clear').addEventListener('click', () => {
        if (!confirm('確定清空課表?')) return;
        localStorage.removeItem(SCHEDULE_KEY);
        renderScheduleView();
        refreshScheduleButtons();
    });

    document.getElementById('schedule-export').addEventListener('click', () => exportToPDF('view-schedule'));

    document.getElementById('schedule-vibe-btn').addEventListener('click', () => {
        const slot = document.getElementById('schedule-vibe-result');
        const v = analyzeScheduleVibe();
        if (v.score === null) {
            slot.innerHTML = `<div class="vibe-box"><div class="vibe-msg">${v.msg}</div></div>`;
            return;
        }
        const roastHtml = v.roasts.map(r => `<li>${escapeHtml(r)}</li>`).join('');
        slot.innerHTML = `
            <div class="vibe-box vibe-grade-${v.grade}">
                <div class="vibe-score-wrap">
                    <div class="vibe-grade">${v.grade}</div>
                    <div class="vibe-score">${v.score}<span>/100</span></div>
                </div>
                <div class="vibe-detail">
                    <div class="vibe-stats">共 ${v.totalSlots} 節 · 早八 ${v.earlyBird} · 單日最多 ${v.maxPerDay} 節 · 平日空 ${v.freeDays} 天</div>
                    <ul class="vibe-roasts">${roastHtml}</ul>
                </div>
            </div>`;
    });

    document.getElementById('schedule-ai-balance').addEventListener('click', async () => {
        if (!getToken()) {
            toast('請先登入才能使用 AI 平衡顧問', 'warn');
            return;
        }
        const sched = getSchedule();
        const items = Object.values(sched).map(c => ({ semester: c.semester, serial_no: c.serial_no }));
        const slot = document.getElementById('schedule-ai-balance-result');
        const btn = document.getElementById('schedule-ai-balance');
        if (items.length === 0) {
            slot.innerHTML = '<div class="ai-summary-box" style="margin:10px 0">課表是空的,先加幾門課再來</div>';
            return;
        }
        btn.disabled = true;
        slot.innerHTML = '<div class="ai-summary-box" style="margin:10px 0"><span style="color:#888">AI 評估中…</span></div>';
        try {
            const resp = await fetchScheduleBalance(items);
            if (resp && resp.advice) {
                slot.innerHTML = `<div class="ai-summary-box" style="margin:10px 0">
                    <div class="ai-summary-label"><i class="fas fa-robot"></i> AI 平衡顧問</div>
                    <div class="ai-summary-text">${escapeHtml(resp.advice)}</div>
                </div>`;
            } else {
                slot.innerHTML = '<div class="ai-summary-box" style="margin:10px 0;color:#999">AI 服務暫時不可用</div>';
            }
        } catch (err) {
            slot.innerHTML = '<div class="ai-summary-box" style="margin:10px 0;color:#c33">查詢失敗</div>';
        } finally {
            btn.disabled = false;
        }
    });

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
