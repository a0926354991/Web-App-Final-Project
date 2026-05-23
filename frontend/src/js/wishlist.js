// 想修清單 view + 「加入想修」按鈕委派。
import { wishlistState } from './state.js';
import { getToken, fetchWishlist, addWishlist as apiAddWishlist, deleteWishlist } from './api.js';
import { courseId, parseCourseId, escapeHtml, escapeAttr, toast, exportToPDF } from './utils.js';
import { openAuthModal } from './auth.js';
import { openDrawer } from './drawer.js';

export async function loadWishlist() {
    if (!getToken()) {
        wishlistState.items = [];
        wishlistState.idSet = new Set();
        return;
    }
    try {
        wishlistState.items = await fetchWishlist();
        wishlistState.idSet = new Set(wishlistState.items.map(i => courseId(i)));
        wishlistState.loaded = true;
    } catch (err) {
        console.warn('loadWishlist failed', err);
    }
}

async function addToWishlist(id) {
    if (!getToken()) { openAuthModal('login'); return; }
    const { semester, serial_no } = parseCourseId(id);
    try {
        const res = await apiAddWishlist({ semester, serial_no });
        await loadWishlist();
        refreshWishlistButtons();
        if (res && res._conflict) toast('已在想修清單中', 'info');
        else toast('已加入想修清單', 'success');
    } catch (err) {
        toast(`加入失敗:${err.detail || err.message}`, 'error');
    }
}

async function removeFromWishlist(wishlist_id) {
    try {
        await deleteWishlist(wishlist_id);
        await loadWishlist();
        refreshWishlistButtons();
    } catch (err) {
        toast('刪除失敗', 'error');
    }
}

export async function renderWishlistView() {
    const needLogin = document.getElementById('wishlist-need-login');
    const content = document.getElementById('wishlist-content');
    if (!getToken()) {
        content.hidden = true;
        needLogin.hidden = false;
        return;
    }
    needLogin.hidden = true;
    content.hidden = false;
    if (!wishlistState.loaded) await loadWishlist();

    const body = document.getElementById('wishlist-body');
    const meta = document.getElementById('wishlist-meta');
    const items = wishlistState.items;
    meta.textContent = `共 ${items.length} 門想修課`;
    if (items.length === 0) {
        body.innerHTML = '<tr><td colspan="8" class="empty-row">還是空的 — 到課程探索點愛心按鈕加入想修</td></tr>';
        return;
    }
    body.innerHTML = items.map(w => `
        <tr data-id="${escapeAttr(courseId(w))}">
            <td>${escapeHtml(w.semester)}</td>
            <td>${escapeHtml(w.course_code)}</td>
            <td>${escapeHtml(w.course_name)}</td>
            <td>${escapeHtml(w.teacher)}</td>
            <td>${escapeHtml(w.credits)}</td>
            <td>${escapeHtml(w.department)}</td>
            <td>${escapeHtml(w.notes) || ''}</td>
            <td class="action-cell">
                <button class="btn-delete-row" data-wid="${w.id}" title="移除"><i class="fas fa-trash"></i></button>
            </td>
        </tr>
    `).join('');

    body.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.btn-delete-row')) return;
            openDrawer(row.dataset.id);
        });
    });
    body.querySelectorAll('.btn-delete-row').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await removeFromWishlist(btn.dataset.wid);
            renderWishlistView();
        });
    });
}

export function wishlistToggleBtn(course) {
    if (!getToken()) return '';
    const id = courseId(course);
    const has = wishlistState.idSet.has(id);
    return `<button class="btn-toggle-wishlist ${has ? 'in-wishlist' : ''}" data-wishlist-toggle="${escapeAttr(id)}">
        ${has ? '<i class="fas fa-heart"></i> 已加入想修' : '<i class="far fa-heart"></i> 加入想修'}
    </button>`;
}

function refreshWishlistButtons() {
    document.querySelectorAll('[data-wishlist-toggle]').forEach(btn => {
        const has = wishlistState.idSet.has(btn.dataset.wishlistToggle);
        btn.classList.toggle('in-wishlist', has);
        btn.innerHTML = has ? '<i class="fas fa-heart"></i> 已加入想修' : '<i class="far fa-heart"></i> 加入想修';
    });
}

export function initWishlist() {
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-wishlist-toggle]');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const id = btn.dataset.wishlistToggle;
        if (wishlistState.idSet.has(id)) {
            const item = wishlistState.items.find(w => courseId(w) === id);
            if (item) removeFromWishlist(item.id);
        } else {
            addToWishlist(id);
        }
    });

    document.getElementById('wishlist-export').addEventListener('click', () => exportToPDF('view-wishlist'));
}
