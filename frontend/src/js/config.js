// 所有常數集中地。沒有副作用,只能 import const。
export const API_BASE = 'http://localhost:8000';
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
