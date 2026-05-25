// Token 管理 + fetch 包裝 + 各 endpoint 高層函式。
// 每個函式回傳 parsed JSON (或 null);錯誤都 throw,由 caller 接。
import { API_BASE, TOKEN_KEY } from './config.js';
import { courseUrlPath } from './utils.js';

// ------- Token -------
export function getToken() { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
export function clearToken() { localStorage.removeItem(TOKEN_KEY); }

export function authHeaders() {
    const t = getToken();
    return t ? { 'Authorization': `Bearer ${t}` } : {};
}

// ------- 低層 helper -------
async function apiGet(path, opts = {}) {
    const headers = { ...(opts.auth ? authHeaders() : {}) };
    const res = await fetch(`${API_BASE}${path}`, { headers });
    if (!res.ok) {
        if (opts.allow404 && res.status === 404) return null;
        if (opts.allowAny) return null;
        const err = await res.json().catch(() => ({}));
        throw Object.assign(new Error(err.detail || `${res.status}`), { status: res.status, detail: err.detail });
    }
    return res.json();
}

async function apiSend(method, path, body, opts = {}) {
    const headers = {
        ...(opts.auth ? authHeaders() : {}),
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    };
    const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    if (!res.ok) {
        if (opts.allowConflict && res.status === 409) return { _conflict: true };
        const err = await res.json().catch(() => ({}));
        throw Object.assign(new Error(err.detail || `${res.status}`), { status: res.status, detail: err.detail });
    }
    if (res.status === 204) return null;
    return res.json();
}

// ------- Endpoints -------
// 公開
export const fetchDepartments = () => apiGet('/departments');
export const fetchCourses = (params) => apiGet(`/courses?${params.toString()}`);
export const fetchCourse = (id) => apiGet(`/courses/${courseUrlPath(id)}`);
export const fetchCourseReviews = (id) => apiGet(`/courses/${courseUrlPath(id)}/reviews`);
export const fetchRelated = (id, limit = 5) => apiGet(`/courses/${courseUrlPath(id)}/related?limit=${limit}`, { allowAny: true });
export const fetchTeacher = (name) => apiGet(`/teachers/${encodeURIComponent(name)}`);

// Auth
export const apiLogin = (username, password) => apiSend('POST', '/auth/login', { username, password });
export const apiRegister = (username, password) => apiSend('POST', '/auth/register', { username, password });
export const apiLogout = () => apiSend('POST', '/auth/logout', undefined, { auth: true });
export const apiMe = () => apiGet('/auth/me', { auth: true });

// Profile
export const fetchProfile = () => apiGet('/me/profile', { auth: true });
export const saveProfile = (body) => apiSend('PUT', '/me/profile', body, { auth: true });

// History
export const fetchHistory = () => apiGet('/me/history', { auth: true });
export const addHistory = (body) => apiSend('POST', '/me/history', body, { auth: true });
export const deleteHistory = (id) => apiSend('DELETE', `/me/history/${id}`, undefined, { auth: true });

// Wishlist
export const fetchWishlist = () => apiGet('/me/wishlist', { auth: true });
export const addWishlist = (body) => apiSend('POST', '/me/wishlist', body, { auth: true, allowConflict: true });
export const deleteWishlist = (id) => apiSend('DELETE', `/me/wishlist/${id}`, undefined, { auth: true });

// Recommendations / fit
export const fetchRecommendations = (limit = 5) => apiGet(`/me/recommendations?limit=${limit}`, { auth: true, allowAny: true });
export const fetchFit = (id) => apiGet(`/me/fit/${courseUrlPath(id)}`, { auth: true, allowAny: true });
export const fetchBatchFits = (items) => apiSend('POST', '/me/fits', { items }, { auth: true });

// AI features
export const fetchCourseSummary = (id) => apiGet(`/me/courses/${courseUrlPath(id)}/summary`, { auth: true, allowAny: true });
export const fetchSubstitutes = (id, limit = 5) => apiGet(`/me/courses/${courseUrlPath(id)}/substitutes?limit=${limit}`, { auth: true, allowAny: true });
export const summarizeHistory = (historyId) => apiSend('POST', `/me/history/${historyId}/summarize`, undefined, { auth: true });
export const fetchScheduleBalance = (items) => apiSend('POST', '/me/schedule/balance', { items }, { auth: true });
export const fetchSuggestedInterests = () => apiGet('/me/suggested-interests', { auth: true, allowAny: true });
export const fetchTeacherStyle = (name) => apiGet(`/teachers/${encodeURIComponent(name)}/style`, { allowAny: true });
export const fetchPrerequisites = (id) => apiGet(`/courses/${courseUrlPath(id)}/prerequisites`, { allowAny: true });
