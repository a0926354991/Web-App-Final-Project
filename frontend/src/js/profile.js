// 使用者資訊輸入頁(能力 / 偏好 / 興趣)。
import { ABILITY_FIELDS, PREF_FIELDS, WEIGHT_FIELDS, INTEREST_OPTIONS } from './config.js';
import { profileState } from './state.js';
import { getToken, fetchProfile, saveProfile, fetchSuggestedInterests, fetchDepartments } from './api.js';
import { toast, escapeHtml } from './utils.js';
import { updateRadarFromProfile } from './dashboard.js';
import { loadDashboardRecommendations } from './fit.js';

const els = {
    form: document.getElementById('profile-form'),
    needLogin: document.getElementById('profile-need-login'),
    abilityGroup: document.getElementById('ability-group'),
    prefGroup: document.getElementById('pref-group'),
    weightGroup: document.getElementById('weight-group'),
    interestTags: document.getElementById('interest-tags'),
    dept: document.getElementById('profile-dept'),
    save: document.getElementById('profile-save'),
    saved: document.getElementById('profile-saved'),
};

// 系所下拉只需填一次。沿用 /departments(與探索頁同來源)。
let _deptsLoaded = false;
async function ensureDeptOptions() {
    if (_deptsLoaded) return;
    try {
        const depts = await fetchDepartments();
        depts.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.name;
            opt.textContent = d.code ? `${d.code}  ${d.name}` : d.name;
            els.dept.appendChild(opt);
        });
        _deptsLoaded = true;
    } catch (err) {
        console.error('載入系所清單失敗:', err);
    }
}

// 收集整份 profile（能力 + 偏好 + 權重 + 興趣）成 request body
function collectProfileBody() {
    const body = {
        interests: [...profileState.selectedInterests],
        department: els.dept ? els.dept.value : '',
    };
    [...ABILITY_FIELDS, ...PREF_FIELDS, ...WEIGHT_FIELDS].forEach(f => {
        const el = document.getElementById(`slider-${f.key}`);
        if (el) body[f.key] = Number(el.value);
    });
    return body;
}

// 權重滑桿拖動 → debounce 自動存檔 + 即時重算儀表板推薦（demo 重點：拉滑桿即時重排）
let _weightSaveTimer = null;
function scheduleWeightSave() {
    if (!getToken()) return;
    clearTimeout(_weightSaveTimer);
    _weightSaveTimer = setTimeout(async () => {
        try {
            const saved = await saveProfile(collectProfileBody());
            updateRadarFromProfile(saved);
            loadDashboardRecommendations();
        } catch (err) {
            console.warn('weight auto-save failed', err);
        }
    }, 500);
}

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
    els.weightGroup.innerHTML = '';
    WEIGHT_FIELDS.forEach(f => {
        const dflt = { weight_recommendation: 25, weight_sweetness: 20, weight_loading: 20, weight_interest: 20, weight_ability: 15 }[f.key];
        els.weightGroup.appendChild(buildSliderRow(f, profile[f.key] ?? dflt));
    });
    // 權重滑桿拖動即時存檔重算
    els.weightGroup.querySelectorAll('input[type=range]').forEach(inp => {
        inp.addEventListener('input', scheduleWeightSave);
    });
    buildInterestTags(profile.interests || []);
    profileState.department = profile.department || '';
    if (els.dept) els.dept.value = profileState.department;
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
    // 系所下拉選項與 profile 載入狀態無關(自身有 _deptsLoaded 防重複),
    // 每次進頁都確保已填,否則 profileState.loaded 早被設過 → 下拉永遠空。
    await ensureDeptOptions();
    if (!profileState.loaded) {
        const p = await fetchProfile().catch(() => null);
        if (p) renderProfileForm(p);
    } else if (els.dept) {
        // profile 已載入過、下拉這次才填好 → 用暫存的科系把選項 select 起來
        els.dept.value = profileState.department || '';
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

        const body = collectProfileBody();

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
