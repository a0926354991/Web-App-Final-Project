// Dashboard view — 能力雷達圖。Chart.js 從 CDN 載入是 window.Chart 全域物件。
import { DEFAULT_ABILITIES, ABILITY_LABELS } from './config.js';

// 模組級單例 — 在 init() 創建,其他模組透過 getter 取 (避免 module top-level
// 對 DOM 早綁;index.html 必須先 load Chart.js 與 canvas 存在才能初始化)
let radarChart = null;

export function initRadarChart() {
    const canvas = document.getElementById('radarChart');
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    radarChart = new window.Chart(ctx, {
        type: 'radar',
        data: {
            labels: ABILITY_LABELS,
            datasets: [{
                label: '目前能力值',
                data: DEFAULT_ABILITIES,
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
    return radarChart;
}

export function getRadarChart() { return radarChart; }

export function updateRadarFromProfile(p) {
    if (!radarChart) return;
    radarChart.data.datasets[0].data = [
        p.ability_logic,
        p.ability_writing,
        p.ability_coding,
        p.ability_humanities,
        p.ability_teamwork,
    ];
    radarChart.update();
}

export function resetRadarToDefault() {
    if (!radarChart) return;
    radarChart.data.datasets[0].data = DEFAULT_ABILITIES;
    radarChart.update();
}

export function updateChartThemeFromBody() {
    if (!radarChart) return;
    const dark = document.body.classList.contains('theme-dark');
    const grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
    const angle = dark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.1)';
    const labelColor = dark ? '#c0c0c0' : '#444';
    const tickColor = dark ? '#999' : '#888';
    radarChart.options.scales.r.grid.color = grid;
    radarChart.options.scales.r.angleLines.color = angle;
    radarChart.options.scales.r.pointLabels.color = labelColor;
    radarChart.options.scales.r.ticks.color = tickColor;
    radarChart.update();
}
