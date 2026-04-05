// 漢堡選單的開關邏輯 (判斷螢幕寬度來決定套用哪個 CSS Class)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isMobile = window.innerWidth <= 992;

    if (isMobile) {
        // 手機版：滑出/收起
        sidebar.classList.toggle('mobile-open');
    } else {
        // 電腦版：壓縮/展開
        sidebar.classList.toggle('desktop-collapsed');
    }
}

// 點擊主畫面時，如果手機版側欄是開著的，就自動收起來
document.querySelector('.main-content').addEventListener('click', function () {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 992 && sidebar.classList.contains('mobile-open')) {
        sidebar.classList.remove('mobile-open');
    }
});

// 初始化雷達圖 (Chart.js)
const ctx = document.getElementById('radarChart').getContext('2d');
const radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
        labels: ['數理邏輯', '文字表達', '程式實作', '人文素養', '團隊協作'],
        datasets: [{
            label: '目前能力值',
            data: [85, 65, 90, 50, 75],
            backgroundColor: 'rgba(33, 150, 243, 0.2)', /* 半透明藍色 */
            borderColor: 'rgba(33, 150, 243, 1)',
            borderWidth: 2,
            pointBackgroundColor: 'rgba(33, 150, 243, 1)',
            pointBorderColor: '#fff',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: 'rgba(33, 150, 243, 1)',
            pointRadius: 4,
            pointHoverRadius: 6
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false, // 允許圖表隨著容器變形
        scales: {
            r: {
                angleLines: { color: 'rgba(0,0,0,0.1)' },
                grid: { color: 'rgba(0,0,0,0.05)' },
                suggestedMin: 0,
                suggestedMax: 100,
                ticks: {
                    stepSize: 20,
                    color: '#888',
                    backdropColor: 'transparent' // 移除數字背後的白色框
                },
                pointLabels: {
                    font: {
                        size: 14,
                        family: '"Microsoft JhengHei", Arial, sans-serif'
                    },
                    color: '#444'
                }
            }
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                padding: 10,
                bodyFont: { size: 14 }
            }
        }
    }
});

// 讓側邊欄按鈕有切換 Active 的效果
const sidebarItems = document.querySelectorAll('.sidebar-item');
sidebarItems.forEach(item => {
    item.addEventListener('click', function (e) {
        e.preventDefault();
        sidebarItems.forEach(i => i.classList.remove('active'));
        this.classList.add('active');

        // 點擊選單後，如果是手機版就自動收起側欄
        if (window.innerWidth <= 992) {
            document.getElementById('sidebar').classList.remove('mobile-open');
        }
    });
});