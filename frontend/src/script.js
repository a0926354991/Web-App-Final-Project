// ==========================================================================
// 設定
// ==========================================================================
const API_BASE = 'http://localhost:8000';
const PAGE_SIZE = 20;

// ==========================================================================
// Sidebar 開關 (漢堡選單)
// ==========================================================================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 992;
    if (isMobile) {
        sidebar.classList.toggle('mobile-open');
    } else {
        sidebar.classList.toggle('desktop-collapsed');
    }
}

document.querySelector('.main-content').addEventListener('click', () => {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 992 && sidebar.classList.contains('mobile-open')) {
        sidebar.classList.remove('mobile-open');
    }
});

// ==========================================================================
// View 切換 (router 雛形)
// ==========================================================================
const sidebarItems = document.querySelectorAll('.sidebar-item');
sidebarItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const target = item.dataset.target;
        if (!target) return;

        sidebarItems.forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        document.querySelectorAll('.view').forEach(v => v.hidden = true);
        const view = document.getElementById(`view-${target}`);
        if (view) view.hidden = false;

        if (target === 'discover' && !discoverState.initialized) {
            initDiscoverView();
        }

        if (window.innerWidth <= 992) {
            document.getElementById('sidebar').classList.remove('mobile-open');
        }
    });
});

// ==========================================================================
// 儀表板雷達圖 (dashboard) — 沿用原本寫死的能力值
// ==========================================================================
const ctx = document.getElementById('radarChart').getContext('2d');
new Chart(ctx, {
    type: 'radar',
    data: {
        labels: ['數理邏輯', '文字表達', '程式實作', '人文素養', '團隊協作'],
        datasets: [{
            label: '目前能力值',
            data: [85, 65, 90, 50, 75],
            backgroundColor: 'rgba(33, 150, 243, 0.2)',
            borderColor: 'rgba(33, 150, 243, 1)',
            borderWidth: 2,
            pointBackgroundColor: 'rgba(33, 150, 243, 1)',
            pointBorderColor: '#fff',
            pointRadius: 4,
            pointHoverRadius: 6,
        }],
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            r: {
                angleLines: { color: 'rgba(0,0,0,0.1)' },
                grid: { color: 'rgba(0,0,0,0.05)' },
                suggestedMin: 0,
                suggestedMax: 100,
                ticks: { stepSize: 20, color: '#888', backdropColor: 'transparent' },
                pointLabels: {
                    font: { size: 14, family: '"Microsoft JhengHei", Arial, sans-serif' },
                    color: '#444',
                },
            },
        },
        plugins: {
            legend: { display: false },
            tooltip: { backgroundColor: 'rgba(0, 0, 0, 0.8)', padding: 10, bodyFont: { size: 14 } },
        },
    },
});

// ==========================================================================
// 課程探索 (course discovery)
// ==========================================================================
const discoverState = {
    initialized: false,
    offset: 0,
    total: 0,
    currentParams: {},
};

const els = {
    searchInput: document.getElementById('search-input'),
    filterDept: document.getElementById('filter-dept'),
    filterCredits: document.getElementById('filter-credits'),
    searchBtn: document.getElementById('search-btn'),
    resultsBody: document.getElementById('results-body'),
    resultsMeta: document.getElementById('results-meta'),
    pagination: document.getElementById('pagination'),
    pagePrev: document.getElementById('page-prev'),
    pageNext: document.getElementById('page-next'),
    pageInfo: document.getElementById('page-info'),
};

async function initDiscoverView() {
    discoverState.initialized = true;

    try {
        const depts = await fetch(`${API_BASE}/departments`).then(r => r.json());
        depts.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.textContent = d;
            els.filterDept.appendChild(opt);
        });
    } catch (err) {
        console.error('載入系所清單失敗:', err);
        els.resultsMeta.textContent = '無法連線到 API server (預期：http://localhost:8000)。請確認後端有啟動。';
    }

    els.searchBtn.addEventListener('click', () => {
        discoverState.offset = 0;
        searchCourses();
    });

    els.searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            discoverState.offset = 0;
            searchCourses();
        }
    });

    els.pagePrev.addEventListener('click', () => {
        if (discoverState.offset >= PAGE_SIZE) {
            discoverState.offset -= PAGE_SIZE;
            searchCourses({ keepParams: true });
        }
    });

    els.pageNext.addEventListener('click', () => {
        if (discoverState.offset + PAGE_SIZE < discoverState.total) {
            discoverState.offset += PAGE_SIZE;
            searchCourses({ keepParams: true });
        }
    });

    await searchCourses();
}

async function searchCourses({ keepParams = false } = {}) {
    if (!keepParams) {
        discoverState.currentParams = {
            q: els.searchInput.value.trim(),
            dept: els.filterDept.value,
            credits: els.filterCredits.value,
        };
    }

    const params = new URLSearchParams();
    const { q, dept, credits } = discoverState.currentParams;
    if (q) params.set('q', q);
    if (dept) params.set('dept', dept);
    if (credits) params.set('credits', credits);
    params.set('limit', PAGE_SIZE);
    params.set('offset', discoverState.offset);

    els.resultsBody.innerHTML = '<tr><td colspan="6" class="empty-row">載入中…</td></tr>';
    els.pagination.hidden = true;

    try {
        const data = await fetch(`${API_BASE}/courses?${params}`).then(r => r.json());
        discoverState.total = data.total;
        renderResults(data.items);
        renderMeta();
        renderPagination();
    } catch (err) {
        console.error(err);
        els.resultsBody.innerHTML = '<tr><td colspan="6" class="empty-row">搜尋失敗，請確認 API server 是否啟動</td></tr>';
    }
}

function renderResults(items) {
    if (items.length === 0) {
        els.resultsBody.innerHTML = '<tr><td colspan="6" class="empty-row">沒有符合條件的課程</td></tr>';
        return;
    }
    els.resultsBody.innerHTML = items.map(c => `
        <tr data-serial="${escapeAttr(c.serial_no)}">
            <td>${escapeHtml(c.course_code)}</td>
            <td>${escapeHtml(c.course_name)}</td>
            <td>${escapeHtml(c.teacher)}</td>
            <td>${escapeHtml(c.department)}</td>
            <td>${escapeHtml(c.credits)}</td>
            <td>${escapeHtml(c.schedule_time) || '—'}</td>
        </tr>
    `).join('');

    els.resultsBody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', () => {
            els.resultsBody.querySelectorAll('tr').forEach(r => r.classList.remove('active'));
            row.classList.add('active');
            openDrawer(row.dataset.serial);
        });
    });
}

function renderMeta() {
    const t = discoverState.total;
    const from = t === 0 ? 0 : discoverState.offset + 1;
    const to = Math.min(discoverState.offset + PAGE_SIZE, t);
    els.resultsMeta.textContent = `共 ${t} 筆，顯示 ${from}–${to}`;
}

function renderPagination() {
    if (discoverState.total <= PAGE_SIZE) {
        els.pagination.hidden = true;
        return;
    }
    els.pagination.hidden = false;
    const page = Math.floor(discoverState.offset / PAGE_SIZE) + 1;
    const totalPages = Math.ceil(discoverState.total / PAGE_SIZE);
    els.pageInfo.textContent = `第 ${page} / ${totalPages} 頁`;
    els.pagePrev.disabled = discoverState.offset === 0;
    els.pageNext.disabled = discoverState.offset + PAGE_SIZE >= discoverState.total;
}

// ==========================================================================
// 課程詳情抽屜 (drawer)
// ==========================================================================
const drawer = document.getElementById('detail-drawer');
const drawerOverlay = document.getElementById('drawer-overlay');
const drawerBody = document.getElementById('drawer-body');
const drawerTitle = document.getElementById('drawer-title');

document.getElementById('drawer-close').addEventListener('click', closeDrawer);
drawerOverlay.addEventListener('click', closeDrawer);
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
});

function closeDrawer() {
    drawer.classList.remove('open');
    drawerOverlay.classList.remove('open');
}

async function openDrawer(serialNo) {
    drawer.classList.add('open');
    drawerOverlay.classList.add('open');
    drawerTitle.textContent = '載入中…';
    drawerBody.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> 載入課程資料…</div>';

    try {
        const [detail, reviewsResp] = await Promise.all([
            fetch(`${API_BASE}/courses/${encodeURIComponent(serialNo)}`).then(r => r.json()),
            fetch(`${API_BASE}/courses/${encodeURIComponent(serialNo)}/reviews`).then(r => r.json()),
        ]);
        drawerTitle.textContent = detail.course_name;
        drawerBody.innerHTML = renderDrawerContent(detail, reviewsResp.items);
    } catch (err) {
        console.error(err);
        drawerBody.innerHTML = '<p class="drawer-empty">載入失敗</p>';
    }
}

function renderDrawerContent(d, reviews) {
    const reviewsHtml = reviews.length === 0
        ? '<p class="drawer-empty" style="margin-top: 10px;">尚無 PTT 評價</p>'
        : reviews.map(r => `
            <div class="review-item">
                <div class="review-meta">
                    ${r.recommendation ? `<span class="badge rec">推薦 ${escapeHtml(r.recommendation)}/5</span>` : ''}
                    ${r.sweetness ? `<span class="badge">甜 ${escapeHtml(r.sweetness)}</span>` : ''}
                    ${r.workload ? `<span class="badge">涼 ${escapeHtml(r.workload)}</span>` : ''}
                    ${r.year_term ? `<span class="badge">${escapeHtml(r.year_term)}</span>` : ''}
                    ${r.post_tag ? `<span class="badge">${escapeHtml(r.post_tag)}</span>` : ''}
                </div>
                <div class="review-summary">${escapeHtml(r.summary) || '(無摘要)'}</div>
                <a class="review-link" href="${escapeAttr(r.post_url)}" target="_blank" rel="noopener">
                    <i class="fas fa-external-link-alt"></i> 看原文
                </a>
            </div>
        `).join('');

    return `
        <div class="drawer-section">
            <div class="course-name-big">${escapeHtml(d.course_name)}</div>
            <div class="course-meta-row"><strong>課號</strong> ${escapeHtml(d.course_code)}　|　<strong>流水號</strong> ${escapeHtml(d.serial_no)}</div>
            <div class="course-meta-row"><strong>教師</strong> ${escapeHtml(d.teacher) || '—'}</div>
            <div class="course-meta-row"><strong>系所</strong> ${escapeHtml(d.department) || '—'}</div>
            <div class="course-meta-row"><strong>學分</strong> ${escapeHtml(d.credits) || '—'}　|　<strong>必選修</strong> ${escapeHtml(d.req_type) || '—'}</div>
            <div class="course-meta-row"><strong>時間</strong> ${escapeHtml(d.schedule_time) || '—'}　|　<strong>地點</strong> ${escapeHtml(d.location) || '—'}</div>
            <div class="course-meta-row"><strong>語言</strong> ${escapeHtml(d.language) || '—'}</div>
        </div>

        ${d.overview ? `
        <div class="drawer-section">
            <h3>課程概述</h3>
            <div class="course-text">${escapeHtml(d.overview)}</div>
        </div>` : ''}

        ${d.objectives ? `
        <div class="drawer-section">
            <h3>課程目標</h3>
            <div class="course-text">${escapeHtml(d.objectives)}</div>
        </div>` : ''}

        ${d.grading ? `
        <div class="drawer-section">
            <h3>評量方式</h3>
            <div class="course-text">${escapeHtml(d.grading)}</div>
        </div>` : ''}

        <div class="drawer-section">
            <h3>PTT 評價 (${reviews.length})</h3>
            ${reviewsHtml}
        </div>

        ${d.detail_url ? `
        <div class="drawer-section">
            <a class="review-link" href="${escapeAttr(d.detail_url)}" target="_blank" rel="noopener">
                <i class="fas fa-external-link-alt"></i> 課程網原始頁面
            </a>
        </div>` : ''}
    `;
}

// ==========================================================================
// 小工具:防 XSS
// ==========================================================================
function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(s) {
    return escapeHtml(s);
}
