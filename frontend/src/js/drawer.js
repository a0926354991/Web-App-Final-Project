// 課程 / 教師 / related 抽屜。
import { drawerState, historyState } from './state.js';
import { getToken, fetchCourse, fetchCourseReviews, fetchRelated, fetchTeacher, fetchFit } from './api.js';
import { courseId, escapeHtml, escapeAttr, drawerSkeletonHTML, lowSampleBadge } from './utils.js';
import { openHistoryModal } from './history.js';
import { scheduleToggleBtn } from './schedule.js';
import { wishlistToggleBtn } from './wishlist.js';

const drawer = document.getElementById('detail-drawer');
const drawerOverlay = document.getElementById('drawer-overlay');
const drawerBody = document.getElementById('drawer-body');
const drawerTitle = document.getElementById('drawer-title');

export function closeDrawer() {
    drawer.classList.remove('open');
    drawerOverlay.classList.remove('open');
}

export async function openDrawer(id) {
    drawer.classList.add('open');
    drawerOverlay.classList.add('open');
    drawerTitle.textContent = '載入中…';
    drawerBody.innerHTML = drawerSkeletonHTML();

    try {
        const [detail, reviewsResp, fit, related] = await Promise.all([
            fetchCourse(id),
            fetchCourseReviews(id),
            getToken() ? fetchFit(id) : Promise.resolve(null),
            fetchRelated(id, 5),
        ]);
        drawerTitle.textContent = detail.course_name;
        drawerBody.innerHTML = renderFitBox(fit)
            + renderDrawerContent(detail, reviewsResp.items)
            + renderRelatedSection(related || []);
        const addBtn = document.getElementById('drawer-add-history-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => openHistoryModal(courseId(detail), detail.course_name));
        }
        drawerBody.querySelectorAll('.related-item').forEach(el => {
            el.addEventListener('click', () => openDrawer(el.dataset.id));
        });
    } catch (err) {
        console.error(err);
        drawerBody.innerHTML = '<p class="drawer-empty">載入失敗</p>';
    }
}

export async function openTeacherInDrawer(name) {
    drawer.classList.add('open');
    drawerOverlay.classList.add('open');
    drawerTitle.textContent = '載入中…';
    drawerBody.innerHTML = drawerSkeletonHTML();

    try {
        const d = await fetchTeacher(name);
        drawerTitle.textContent = `教師:${d.teacher}`;
        drawerBody.innerHTML = renderTeacherContent(d);
        drawerBody.querySelectorAll('.teacher-course-row').forEach(row => {
            row.addEventListener('click', () => openDrawer(row.dataset.id));
        });
    } catch (err) {
        console.error(err);
        drawerBody.innerHTML = '<p class="drawer-empty">載入失敗</p>';
    }
}

function renderTeacherContent(d) {
    const s = d.stats;
    const fmt = v => v == null ? '—' : v.toFixed(2);
    const courses = d.courses.map(c => `
        <div class="teacher-course-row" data-id="${escapeAttr(courseId(c))}">
            <div class="teacher-course-main">
                <div class="teacher-course-name">${escapeHtml(c.course_name)} <span class="teacher-course-code">${escapeHtml(c.course_code)}</span></div>
                <div class="teacher-course-meta">${escapeHtml(c.department) || '—'} · ${escapeHtml(c.credits) || '?'} 學分 · ${escapeHtml(c.semester)} · 開過 ${c.n_offerings} 次</div>
            </div>
            <div class="teacher-course-rev">PTT ${c.n_reviews}</div>
        </div>
    `).join('');

    return `
        <div class="drawer-section">
            <div class="course-name-big">${escapeHtml(d.teacher)}</div>
            <div class="teacher-stats-grid">
                <div class="teacher-stat"><div class="ts-label">開過課數</div><div class="ts-val">${s.n_courses}</div></div>
                <div class="teacher-stat"><div class="ts-label">不同課號</div><div class="ts-val">${s.n_unique_codes}</div></div>
                <div class="teacher-stat"><div class="ts-label">PTT 評價</div><div class="ts-val">${s.n_reviews}</div></div>
                <div class="teacher-stat"><div class="ts-label">平均推薦</div><div class="ts-val">${fmt(s.avg_recommendation)} <span class="ts-unit">/5</span></div></div>
                <div class="teacher-stat"><div class="ts-label">平均甜度</div><div class="ts-val">${fmt(s.avg_sweetness)} <span class="ts-unit">/5</span></div></div>
                <div class="teacher-stat"><div class="ts-label">平均 loading</div><div class="ts-val">${fmt(s.avg_workload)} <span class="ts-unit">/5</span></div></div>
            </div>
        </div>

        <div class="drawer-section">
            <h3>所有開過的課 (${d.courses.length})</h3>
            ${courses || '<p class="drawer-empty">沒有資料</p>'}
        </div>
    `;
}

function renderRelatedSection(related) {
    if (!related || related.length === 0) return '';
    const cfCount = related.filter(r => r.source === 'cf').length;
    const label = cfCount > 0 ? `修過 X 也修了 (${cfCount} 來自其他使用者紀錄)` : '相關課程';
    const items = related.map(r => {
        const tag = r.source === 'cf'
            ? `<span class="related-tag related-cf">CF · ${r.score.toFixed(0)}%</span>`
            : `<span class="related-tag related-content">內容類似 · ${r.score.toFixed(0)}</span>`;
        return `
            <div class="related-item teacher-course-row" data-id="${escapeAttr(courseId(r))}">
                <div class="teacher-course-main">
                    <div class="teacher-course-name">${escapeHtml(r.course_name)} <span class="teacher-course-code">${escapeHtml(r.course_code)}</span></div>
                    <div class="teacher-course-meta">${escapeHtml(r.teacher) || '—'} · ${escapeHtml(r.credits)} 學分 · ${escapeHtml(r.semester)}</div>
                </div>
                ${tag}
            </div>
        `;
    }).join('');
    return `<div class="drawer-section"><h3>${label}</h3>${items}</div>`;
}

function renderFitBox(fit) {
    if (!fit) return '';
    return `
        <div class="drawer-fit-box">
            <div class="drawer-fit-total">適合度 ${fit.total.toFixed(0)}% ${lowSampleBadge(fit.n_reviews)}</div>
            ${fit.explanation ? `<div class="drawer-fit-why">${escapeHtml(fit.explanation)}</div>` : ''}
            <div class="drawer-fit-breakdown">
                <span><strong>PTT 推薦</strong>${fit.recommendation.toFixed(0)}</span>
                <span><strong>甜度匹配</strong>${fit.sweetness.toFixed(0)}</span>
                <span><strong>Loading 匹配</strong>${fit.loading.toFixed(0)}</span>
                <span><strong>興趣命中</strong>${fit.interest.toFixed(0)}</span>
                <span><strong>能力匹配</strong>${fit.ability.toFixed(0)}</span>
                <span><strong>PTT 樣本</strong>${fit.n_reviews} 篇</span>
            </div>
        </div>
    `;
}

function renderDrawerContent(d, reviews) {
    drawerState.currentId = courseId(d);
    const sortedReviews = [...reviews].sort((a, b) => {
        const aHas = a.summary ? 1 : 0;
        const bHas = b.summary ? 1 : 0;
        return bHas - aHas;
    });

    const reviewsHtml = reviews.length === 0
        ? '<p class="drawer-empty" style="margin-top: 10px;">尚無 PTT 評價</p>'
        : sortedReviews.map(r => {
            const hasSummary = !!r.summary;
            const body = hasSummary
                ? `<div class="review-summary">${escapeHtml(r.summary)}</div>`
                : `<div class="review-summary" style="color:#888">
                       <div style="font-weight:500;color:#555;margin-bottom:4px">${escapeHtml(r.post_title) || '(無標題)'}</div>
                       <span style="font-size:0.78rem">這是討論串(非 [評價] 模板文),點原文閱讀完整內容</span>
                   </div>`;
            return `
            <div class="review-item">
                <div class="review-meta">
                    ${r.recommendation ? `<span class="badge rec">推薦 ${escapeHtml(r.recommendation)}/5</span>` : ''}
                    ${r.sweetness ? `<span class="badge">甜 ${escapeHtml(r.sweetness)}</span>` : ''}
                    ${r.workload ? `<span class="badge">涼 ${escapeHtml(r.workload)}</span>` : ''}
                    ${r.year_term ? `<span class="badge">${escapeHtml(r.year_term)}</span>` : ''}
                    ${r.post_tag ? `<span class="badge">${escapeHtml(r.post_tag)}</span>` : ''}
                </div>
                ${body}
                <a class="review-link" href="${escapeAttr(r.post_url)}" target="_blank" rel="noopener">
                    <i class="fas fa-external-link-alt"></i> 看原文
                </a>
            </div>
            `;
        }).join('');

    const inHist = historyState.idSet.has(courseId(d));
    const histBtn = getToken() ? `
        <button class="drawer-add-history-btn ${inHist ? 'in-history' : ''}" id="drawer-add-history-btn" ${inHist ? 'disabled' : ''}>
            ${inHist ? '<i class="fas fa-check"></i> 已在修課歷史中' : '<i class="fas fa-plus"></i> 加入修課歷史'}
        </button>` : '';
    const addBtn = scheduleToggleBtn(d) + wishlistToggleBtn(d) + histBtn;

    return `
        <div class="drawer-section">
            <div class="course-name-big">${escapeHtml(d.course_name)}</div>
            <div class="course-meta-row"><strong>學期</strong> ${escapeHtml(d.semester)}　|　<strong>課號</strong> ${escapeHtml(d.course_code)}　|　<strong>流水號</strong> ${escapeHtml(d.serial_no)}</div>
            <div class="course-meta-row"><strong>教師</strong> ${d.teacher ? `<a href="#" class="teacher-link" data-teacher="${escapeAttr(d.teacher)}">${escapeHtml(d.teacher)}</a>` : '—'}</div>
            <div class="course-meta-row"><strong>系所</strong> ${escapeHtml(d.department) || '—'}</div>
            <div class="course-meta-row"><strong>學分</strong> ${escapeHtml(d.credits) || '—'}　|　<strong>必選修</strong> ${escapeHtml(d.req_type) || '—'}</div>
            <div class="course-meta-row"><strong>時間</strong> ${escapeHtml(d.schedule_time) || '—'}　|　<strong>地點</strong> ${escapeHtml(d.location) || '—'}</div>
            <div class="course-meta-row"><strong>語言</strong> ${escapeHtml(d.language) || '—'}</div>
            ${addBtn}
        </div>

        ${d.overview ? `<div class="drawer-section"><h3>課程概述</h3><div class="course-text">${escapeHtml(d.overview)}</div></div>` : ''}
        ${d.objectives ? `<div class="drawer-section"><h3>課程目標</h3><div class="course-text">${escapeHtml(d.objectives)}</div></div>` : ''}
        ${d.grading ? `<div class="drawer-section"><h3>評量方式</h3><div class="course-text">${escapeHtml(d.grading)}</div></div>` : ''}

        <div class="drawer-section">
            <h3>PTT 評價 (${reviews.length})</h3>
            ${reviewsHtml}
        </div>

        ${d.detail_url ? `<div class="drawer-section">
            <a class="review-link" href="${escapeAttr(d.detail_url)}" target="_blank" rel="noopener">
                <i class="fas fa-external-link-alt"></i> 課程網原始頁面
            </a>
        </div>` : ''}
    `;
}

export function initDrawer() {
    document.getElementById('drawer-close').addEventListener('click', closeDrawer);
    drawerOverlay.addEventListener('click', closeDrawer);

    // 全域 .teacher-link 委派
    document.addEventListener('click', (e) => {
        const link = e.target.closest('.teacher-link');
        if (!link) return;
        e.preventDefault();
        e.stopPropagation();
        openTeacherInDrawer(link.dataset.teacher);
    });
}
