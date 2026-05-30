// 所有常數集中地。沒有副作用,只能 import const。
// API_BASE 解析順序:
//   1. window.NTU_API_BASE — 部署時在 index.html 用 <script>window.NTU_API_BASE='...'</script> 覆寫
//   2. 非 localhost 開啟時 → 同主機的 :8000 (Docker / 雲端部署常見:前端後端同機不同 port)
//   3. fallback 到本機開發預設
function resolveApiBase() {
    if (typeof window !== 'undefined' && window.NTU_API_BASE) {
        return String(window.NTU_API_BASE).replace(/\/$/, '');
    }
    if (typeof window !== 'undefined' && window.location) {
        const { protocol, hostname } = window.location;
        if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
            return `${protocol}//${hostname}:8000`;
        }
    }
    return 'http://localhost:8000';
}

export const API_BASE = resolveApiBase();
export const PAGE_SIZE = 20;
export const MAX_COMPARE = 3;

export const TOKEN_KEY = 'ntu_app_token';
export const THEME_KEY = 'ntu_app_theme';
export const SCHEDULE_KEY = 'ntu_app_schedule';

export const DEFAULT_ABILITIES = [50, 50, 50, 50, 50];
export const ABILITY_LABELS = ['數理邏輯', '文字表達', '程式實作', '人文素養', '團隊協作'];

export const ABILITY_FIELDS = [
    { key: 'ability_logic', label: '數理邏輯' },
    { key: 'ability_writing', label: '文字表達' },
    { key: 'ability_coding', label: '程式實作' },
    { key: 'ability_humanities', label: '人文素養' },
    { key: 'ability_teamwork', label: '團隊協作' },
];

export const PREF_FIELDS = [
    { key: 'pref_sweetness', label: '甜度偏好', hint: '高 = 重視給分甜' },
    { key: 'pref_loading', label: 'loading 偏好', hint: '高 = 喜歡扎實' },
];

// 適合度成份權重滑桿(拉高你更看重的成份,後端自動歸一化)
export const WEIGHT_FIELDS = [
    { key: 'weight_recommendation', label: 'PTT 推薦' },
    { key: 'weight_sweetness', label: '甜度' },
    { key: 'weight_loading', label: 'loading' },
    { key: 'weight_interest', label: '興趣' },
    { key: 'weight_ability', label: '能力' },
];

export const INTEREST_OPTIONS = [
    'AI', '程式', '金融', '商管', '設計', '人文', '語言',
    '自然科學', '社會科學', '醫學', '法律', '體育', '藝術',
];

export const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];
export const PERIOD_ORDER = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'A', 'B', 'C', 'D'];

export const TOAST_ICONS = {
    success: 'fa-check-circle',
    error: 'fa-times-circle',
    info: 'fa-info-circle',
    warn: 'fa-exclamation-triangle',
};
