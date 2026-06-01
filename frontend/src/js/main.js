// 入口 — 依序初始化各模組。
// 順序重要:
// 1. dashboard(radarChart) 必須在 chrome(theme) 與 auth 之前,因兩者都會碰它
// 2. drawer / auth / compare / history / wishlist / schedule / profile 各自綁定 DOM events
// 3. chrome 綁定 router/keyboard,要求其他模組 export 的 close*/render* 都已可用
// 4. bootstrapAuth 最後跑,觸發第一次資料載入
import { initRadarChart } from './dashboard.js';
import { initChrome } from './chrome.js';
import { initAuth, bootstrapAuth } from './auth.js';
import { initDrawer } from './drawer.js';
import { initCompare, loadCompareFromUrl } from './compare.js';
import { initHistory } from './history.js';
import { initWishlist } from './wishlist.js';
import { initSchedule } from './schedule.js';
import { initProfile } from './profile.js';
import { initLucky } from './lucky.js';

initRadarChart();
initDrawer();
initAuth();
initCompare();
initHistory();
initWishlist();
initSchedule();
initProfile();
initLucky();
initChrome();
bootstrapAuth().then(() => {
    // 登入狀態確認或資料首次載入後，讀取 URL 的比較參數並展開 Modal
    loadCompareFromUrl();
});
