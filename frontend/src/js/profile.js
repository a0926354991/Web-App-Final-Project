// 使用者資訊輸入頁(能力 / 偏好 / 興趣)。
import { ABILITY_FIELDS, PREF_FIELDS, INTEREST_OPTIONS } from './config.js';
import { profileState } from './state.js';
import { getToken, fetchProfile, saveProfile, fetchSuggestedInterests } from './api.js';
import { toast, escapeHtml } from './utils.js';
import { updateRadarFromProfile } from './dashboard.js';
import { loadDashboardRecommendations } from './fit.js';

const els = {
    form: document.getElementById('profile-form'),
    needLogin: document.getElementById('profile-need-login'),
    abilityGroup: document.getElementById('ability-group'),
    prefGroup: document.getElementById('pref-group'),
    interestTags: document.getElementById('interest-tags'),
    save: document.getElementById('profile-save'),
    saved: document.getElementById('profile-saved'),
};

function buildSliderRow(field, value, hint) {
    const row = document.createElement('div');
    row.className = 'slider-row';
    row.innerHTML = `
        <label for="slider-${field.key}">${field.label}${hint ? `<br><span style="font-size:0.75rem;color:#888">${hint}</span>` : ''}</label>
        <input type="range" id="slider-${field.key}" name="${field.key}" min="0" max="100" value="${value}">
        <span class="slider-value" id="value-${field.key}">${value}</span>
    `;
    const input = row.querySelector('input');
    const valSpan = row.querySelector('.slider-value');
    input.addEventListener('input', () => { valSpan.textContent = input.value; });
    return row;
}

function buildInterestTags(selected) {
    els.interestTags.innerHTML = '';
    profileState.selectedInterests = new Set(selected);
    INTEREST_OPTIONS.forEach(name => {
        const tag = document.createElement('span');
        tag.className = 'interest-tag' + (profileState.selectedInterests.has(name) ? ' selected' : '');
        tag.textContent = name;
        tag.addEventListener('click', () => {
            if (profileState.selectedInterests.has(name)) {
                profileState.selectedInterests.delete(name);
                tag.classList.remove('selected');
            } else {
                profileState.selectedInterests.add(name);
                tag.classList.add('selected');
            }
        });
        els.interestTags.appendChild(tag);
    });
}

function renderProfileForm(profile) {
    els.abilityGroup.innerHTML = '';
    ABILITY_FIELDS.forEach(f => els.abilityGroup.appendChild(buildSliderRow(f, profile[f.key])));
    els.prefGroup.innerHTML = '';
    PREF_FIELDS.forEach(f => els.prefGroup.appendChild(buildSliderRow(f, profile[f.key], f.hint)));
    buildInterestTags(profile.interests || []);
    profileState.loaded = true;
}

export async function renderProfileView() {
    if (!getToken()) {
        els.form.hidden = true;
        els.needLogin.hidden = false;
        return;
    }
    els.needLogin.hidden = true;
    els.form.hidden = false;
    if (!profileState.loaded) {
        const p = await fetchProfile().catch(() => null);
        if (p) renderProfileForm(p);
    }
}

export function initProfile() {
    document.getElementById('profile-ai-suggest').addEventListener('click', async () => {
        if (!getToken()) {
            toast('請先登入', 'warn');
            return;
        }
        const slot = document.getElementById('profile-ai-suggest-result');
        const btn = document.getElementById('profile-ai-suggest');
        btn.disabled = true;
        slot.innerHTML = '<div class="ai-summary-box" style="margin-top:10px"><span style="color:#888">AI 分析中…</span></div>';
        try {
            const resp = await fetchSuggestedInterests();
            if (resp && resp.suggestions) {
                slot.innerHTML = `<div class="ai-summary-box" style="margin-top:10px">
                    <div class="ai-summary-label"><i class="fas fa-robot"></i> AI 建議的額外興趣</div>
                    <div class="ai-summary-text" style="white-space:pre-wrap">${escapeHtml(resp.suggestions)}</div>
                </div>`;
            } else if (resp && resp.has_history === false) {
                slot.innerHTML = '<div class="ai-summary-box" style="margin-top:10px;color:#999">尚無修課歷史,無法建議</div>';
            } else {
                slot.innerHTML = '<div class="ai-summary-box" style="margin-top:10px;color:#999">AI 服務暫時不可用(quota 限制或網路問題)</div>';
            }
        } catch (err) {
            slot.innerHTML = '<div class="ai-summary-box" style="margin-top:10px;color:#c33">查詢失敗</div>';
        } finally {
            btn.disabled = false;
        }
    });

    els.form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!getToken()) return;

        const body = { interests: [...profileState.selectedInterests] };
        [...ABILITY_FIELDS, ...PREF_FIELDS].forEach(f => {
            body[f.key] = Number(document.getElementById(`slider-${f.key}`).value);
        });

        els.save.disabled = true;
        els.saved.hidden = true;
        try {
            const saved = await saveProfile(body);
            updateRadarFromProfile(saved);
            // 偏好改了 → 推薦/適合度的輸入全變了,重抓儀表板推薦,避免顯示舊分數
            loadDashboardRecommendations();
            els.saved.hidden = false;
            setTimeout(() => { els.saved.hidden = true; }, 2500);
        } catch (err) {
            console.error(err);
            toast('儲存失敗,請稍後再試', 'error');
        } finally {
            els.save.disabled = false;
        }
    });
}
