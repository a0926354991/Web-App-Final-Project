// 所有跨模組共享的 mutable state。物件本身是 const,但內部欄位可改;
// 各模組 import 同一個 reference,確保看到的是同一份。
export const discoverState = {
    initialized: false,
    offset: 0,
    total: 0,
    currentParams: {},
    resultsSortDirection: 'desc',
};

export const compareState = { ids: new Set() };

export const profileState = {
    loaded: false,
    selectedInterests: new Set(),
    department: '',
};

export const historyState = {
    items: [],
    idSet: new Set(),
    loaded: false,
};

export const wishlistState = {
    items: [],
    idSet: new Set(),
    loaded: false,
};

// 抽屜目前顯示的課程 id (供 drawer 內按鈕用)
export const drawerState = { currentId: null };

// Auth 視窗模式 'login' | 'register'
export const authState = { mode: 'login', pendingHistoryId: null };
