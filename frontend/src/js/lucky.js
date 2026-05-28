// 「今天修什麼」隨機抽課轉盤 — 從個性化推薦中抽一門,帶輪播動畫。
import { getToken, fetchRecommendations } from './api.js';
import { courseId, escapeHtml, escapeAttr, toast } from './utils.js';
import { openDrawer } from './drawer.js';
import { openAuthModal } from './auth.js';

const modal = document.getElementById('lucky-modal');
const reel = document.getElementById('lucky-reel');
let pool = [];      // 候選課程 (推薦清單)
let spinning = false;

function close() { modal.hidden = true; }

async function ensurePool() {
    if (pool.length) return pool;
    pool = (await fetchRecommendations(20)) || [];
    return pool;
}

function renderCard(it, { final = false } = {}) {
    const id = courseId(it);
    return `
        <div class="lucky-card ${final ? 'lucky-final' : ''}" ${final ? `data-id="${escapeAttr(id)}"` : ''}>
            <div class="lucky-fit">適合度 ${it.fit.total.toFixed(0)}%</div>
            <div class="lucky-name">${escapeHtml(it.course_name)}</div>
            <div class="lucky-meta">${escapeHtml(it.teacher || '—')} · ${escapeHtml(it.credits)} 學分 · ${escapeHtml(it.semester)}</div>
            ${final && it.fit.explanation ? `<div class="lucky-why">${escapeHtml(it.fit.explanation)}</div>` : ''}
        </div>`;
}

async function spin() {
    if (spinning) return;
    const items = await ensurePool();
    if (!items.length) {
        reel.innerHTML = '<p style="color:#999;text-align:center;padding:30px">沒有可推薦的課程,先填個人偏好吧</p>';
        return;
    }
    spinning = true;
    // 輪播動畫:快速切換隨機課名,逐漸變慢,最後定格
    const spins = 18;
    let i = 0;
    const tick = () => {
        const rnd = items[Math.floor(Math.random() * items.length)];
        reel.innerHTML = renderCard(rnd);
        i++;
        if (i < spins) {
            // ease-out:越後面間隔越長
            const delay = 40 + Math.pow(i / spins, 3) * 260;
            setTimeout(tick, delay);
        } else {
            // 定格:從推薦清單權重抽 (前面排名高的機率略高,但仍隨機)
            const pick = items[Math.floor(Math.random() * Math.min(items.length, 8))];
            reel.innerHTML = renderCard(pick, { final: true });
            const card = reel.querySelector('.lucky-final');
            if (card) card.addEventListener('click', () => { close(); openDrawer(card.dataset.id); });
            spinning = false;
        }
    };
    tick();
}

export function initLucky() {
    const btn = document.getElementById('lucky-draw-btn');
    if (btn) {
        btn.addEventListener('click', () => {
            if (!getToken()) { toast('請先登入才能抽課', 'warn'); openAuthModal('login'); return; }
            modal.hidden = false;
            spin();
        });
    }
    document.getElementById('lucky-close').addEventListener('click', close);
    document.getElementById('lucky-spin').addEventListener('click', spin);
    modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
}

// 登入狀態改變時清掉舊 pool (換使用者重抓)
export function resetLuckyPool() { pool = []; }
