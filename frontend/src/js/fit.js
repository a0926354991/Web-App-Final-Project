// Dashboard 「為您推薦」 + 適合度分析 tab。
import { getToken, fetchRecommendations, fetchProfile } from './api.js';
import { courseId, escapeHtml, escapeAttr, lowSampleBadge } from './utils.js';
import { openDrawer } from './drawer.js';
import { inSchedule } from './schedule.js';

export async function loadDashboardRecommendations() {
    const listEl = document.getElementById('dashboard-recommend-list');
    if (!getToken()) {
        listEl.innerHTML = `
            <div class="course-card placeholder-mini">
                <p style="color:#999;text-align:center;margin:20px 0">登入後顯示個性化推薦</p>
            </div>`;
        return;
    }
    listEl.innerHTML = Array.from({ length: 3 }, () =>
        '<div class="course-card placeholder-mini" style="padding:14px"><span class="skeleton block" style="height:70px"></span></div>'
    ).join('');
    try {
        const items = await fetchRecommendations(5);
        if (!items || items.length === 0) {
            listEl.innerHTML = `<div class="course-card placeholder-mini">
                <p style="color:#999;text-align:center;margin:20px 0">沒有可推薦的課程</p>
            </div>`;
            return;
        }
        const p = await fetchProfile().catch(() => null);
        const noProfile = p && !p.updated_at;
        const banner = noProfile
            ? `<div class="empty-banner">
                  <i class="fas fa-info-circle"></i>
                  你還沒填個人偏好,推薦是預設的 —
                  <a href="#" data-goto="userinfo">填一下偏好</a>會更準
               </div>` : '';
        listEl.innerHTML = banner + items.map(it => {
            const id = courseId(it);
            const has = inSchedule(id);
            return `
            <div class="course-card" data-id="${escapeAttr(id)}">
                <div class="course-card-tag fit-tag">適合度 ${it.fit.total.toFixed(0)}%${lowSampleBadge(it.fit.n_reviews)}</div>
                <div class="course-card-subtags">
                    <span class="tag">推薦 ${it.fit.recommendation.toFixed(0)}</span>
                    <span class="tag">甜 ${it.fit.sweetness.toFixed(0)}</span>
                    <span class="tag">loading ${it.fit.loading.toFixed(0)}</span>
                    <span class="tag">興趣 ${it.fit.interest.toFixed(0)}</span>
                    <span class="tag">能力 ${it.fit.ability.toFixed(0)}</span>
                </div>
                <div class="course-card-details">
                    <span><i class="fas fa-book"></i> ${escapeHtml(it.course_name)}</span>
                    <span><i class="fas fa-user"></i> ${escapeHtml(it.teacher)}</span>
                    <span><i class="fas fa-clock"></i> ${escapeHtml(it.credits)} 學分 · ${escapeHtml(it.semester)}</span>
                </div>
                ${it.fit.explanation ? `<div class="fit-explanation">${escapeHtml(it.fit.explanation)}</div>` : ''}
                <button class="btn-toggle-schedule ${has ? 'in-schedule' : ''}" data-schedule-toggle="${escapeAttr(id)}" style="margin-top:10px">
                    ${has ? '<i class="fas fa-check"></i> 已在課表' : '<i class="fas fa-calendar-plus"></i> 加入課表'}
                </button>
            </div>`;
        }).join('');
        listEl.querySelectorAll('.course-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.closest('[data-schedule-toggle]')) return;
                openDrawer(card.dataset.id);
            });
        });
    } catch (err) {
        console.warn('loadDashboardRecommendations failed', err);
    }
}

export async function renderFitAnalysisView() {
    const needLogin = document.getElementById('fit-need-login');
    const content = document.getElementById('fit-content');
    if (!getToken()) {
        content.hidden = true;
        needLogin.hidden = false;
        return;
    }
    needLogin.hidden = true;
    content.hidden = false;

    const summary = document.getElementById('fit-profile-summary');
    const p = await fetchProfile().catch(() => null);
    if (p) {
        const noProfile = !p.updated_at;
        const banner = noProfile
            ? `<div class="empty-banner" style="margin-bottom:14px">
                  <i class="fas fa-info-circle"></i>
                  你還沒填個人偏好 —
                  <a href="#" data-goto="userinfo">先填寫</a>後分析結果才會準
               </div>` : '';
        summary.innerHTML = banner + `
            <div class="fit-summary-grid">
                <div class="fit-summary-tile"><div class="tile-label">甜度偏好</div><div class="tile-value">${p.pref_sweetness}/100</div></div>
                <div class="fit-summary-tile"><div class="tile-label">Loading 偏好</div><div class="tile-value">${p.pref_loading}/100</div></div>
                <div class="fit-summary-tile"><div class="tile-label">興趣領域</div><div class="tile-value">${p.interests.length > 0 ? p.interests.map(escapeHtml).join('、') : '未填'}</div></div>
            </div>`;
    }

    const listEl = document.getElementById('fit-list');
    listEl.innerHTML = Array.from({ length: 5 }, () =>
        '<div class="fit-list-item" style="padding:14px"><span class="skeleton block" style="height:56px"></span></div>'
    ).join('');
    try {
        const items = await fetchRecommendations(20);
        if (!items || items.length === 0) {
            listEl.innerHTML = '<p style="color:#999">沒有可推薦的課程</p>';
            return;
        }
        listEl.innerHTML = items.map((it, i) => `
            <div class="fit-list-item" data-id="${escapeAttr(courseId(it))}">
                <div class="fit-rank">#${i + 1}</div>
                <div class="fit-item-main">
                    <div class="fit-item-title">${escapeHtml(it.course_name)} <span style="color:#888;font-weight:normal;font-size:0.85rem">${escapeHtml(it.course_code)} · ${escapeHtml(it.semester)}</span></div>
                    <div class="fit-item-meta">${escapeHtml(it.teacher)} · ${escapeHtml(it.credits)} 學分 · PTT ${it.fit.n_reviews} 篇評價</div>
                    <div class="fit-bars">
                        <span class="fit-bar-pill">推薦 <strong>${it.fit.recommendation.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">甜 <strong>${it.fit.sweetness.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">loading <strong>${it.fit.loading.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">興趣 <strong>${it.fit.interest.toFixed(0)}</strong></span>
                        <span class="fit-bar-pill">能力 <strong>${it.fit.ability.toFixed(0)}</strong></span>
                    </div>
                    ${it.fit.explanation ? `<div class="fit-explanation">${escapeHtml(it.fit.explanation)}</div>` : ''}
                </div>
                <div class="fit-total-big">${it.fit.total.toFixed(0)}<span style="font-size:0.7em;color:#888">/100</span>${lowSampleBadge(it.fit.n_reviews)}</div>
            </div>
        `).join('');
        listEl.querySelectorAll('.fit-list-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('[data-schedule-toggle]')) return;
                openDrawer(el.dataset.id);
            });
        });
    } catch (err) {
        console.error(err);
        listEl.innerHTML = '<p style="color:#df3d31">載入失敗</p>';
    }
}
