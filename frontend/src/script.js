/* ============================================================
   NTU 個性化選課推薦 — Frontend SPA
   All mock data and logic contained here.
   ============================================================ */

// ============================================================
// MOCK DATA
// ============================================================

const MOCK_COURSES = [
  {
    id: '1001', code: 'CSIE5001', name: '機器學習', professor: '林軒田',
    department: '資訊工程學系', credits: 3, semester: '114-2',
    time: '二 3,4,5', location: '德田館 102', language: '中文授課',
    required: '選修', capacity: 120,
    overview: '本課程介紹機器學習的基礎理論與實作，涵蓋監督式學習、非監督式學習及深度學習。',
    goals: '使學生能夠理解並實作主流機器學習演算法，並具備解決實際問題的能力。',
    requirements_text: '需具備線性代數、機率統計及 Python 程式設計基礎。',
    grading: '作業 40% + 期中考 30% + 期末專案 30%',
    notes: '選課競爭激烈，請提早加選。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1001',
    rating_quality: 4.8, rating_sweet: 3.5, rating_easy: 2.5, rating_rich: 4.9,
    tags: ['#扎實', '#作業偏難', '#期末報告', '#程式實作'],
    reviews: [
      { User_ID: 'User10231', Semester: '113-2', Comment: '林老師教得非常清楚，雖然課程難度高，但每個概念都解釋得很到位。作業量偏多，要有心理準備。強力推薦給對 ML 有熱忱的人！', Rating_Quality: 5, Rating_Sweet: 3, Rating_Easy: 2, Rating_Rich: 5 },
      { User_ID: 'User28847', Semester: '113-1', Comment: '這門課讓我對機器學習有了系統性的認識。作業用 Python 實作，很有收穫。期末專案自由度高，可以做自己感興趣的題目。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 3, Rating_Rich: 5 },
      { User_ID: 'User55102', Semester: '112-2', Comment: '課程內容紮實，老師會用直觀的方式解釋複雜的數學推導。不點名，但如果不去上課很容易跟不上。', Rating_Quality: 4, Rating_Sweet: 3, Rating_Easy: 2, Rating_Rich: 4 },
    ]
  },
  {
    id: '1002', code: 'CSIE3001', name: '資料結構與演算法', professor: '呂育道',
    department: '資訊工程學系', credits: 3, semester: '114-2',
    time: '一 2,3 三 2', location: '博理館 101', language: '中文授課',
    required: '必修', capacity: 80,
    overview: '介紹常用資料結構（陣列、鏈結串列、樹、圖）及演算法設計技巧（分治、動態規劃、貪婪）。',
    goals: '培養學生的演算法分析能力與問題解決思維。',
    requirements_text: '需已修過計算機程式設計。',
    grading: '作業 50% + 期中考 25% + 期末考 25%',
    notes: '考試難度中等，作業需要大量練習。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1002',
    rating_quality: 4.5, rating_sweet: 3.0, rating_easy: 2.0, rating_rich: 4.7,
    tags: ['#點名', '#期中考', '#期末考', '#扎實', '#作業偏難'],
    reviews: [
      { User_ID: 'User73421', Semester: '113-2', Comment: '呂老師講課節奏清晰，會在 PPT 上標記重要觀念。作業都是 LeetCode 等級的題目，寫完真的會進步很多！', Rating_Quality: 5, Rating_Sweet: 3, Rating_Easy: 2, Rating_Rich: 5 },
      { User_ID: 'User99012', Semester: '113-1', Comment: '這門課是 CS 必修中數一數二重要的。雖然不容易，但學到的東西對面試非常有幫助。老師給分公正。', Rating_Quality: 4, Rating_Sweet: 3, Rating_Easy: 2, Rating_Rich: 5 },
    ]
  },
  {
    id: '1003', code: 'NLP4001', name: '自然語言處理', professor: '陳信希',
    department: '資訊工程學系', credits: 3, semester: '114-2',
    time: '四 6,7,8', location: '資電館 103', language: '中文授課',
    required: '選修', capacity: 60,
    overview: '涵蓋 NLP 的核心技術，包括詞向量、序列模型、Transformer 及大型語言模型 (LLM)。',
    goals: '使學生能夠理解並應用現代 NLP 技術解決實際語言理解問題。',
    requirements_text: '需有機器學習基礎，建議先修完機器學習。',
    grading: '專案 60% + 作業 30% + 課堂參與 10%',
    notes: '課程結合最新研究，內容每學期更新。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1003',
    rating_quality: 5.0, rating_sweet: 4.5, rating_easy: 3.5, rating_rich: 4.8,
    tags: ['#給分甜', '#期末報告', '#不點名', '#NLP', '#英文授課'],
    reviews: [
      { User_ID: 'User44123', Semester: '113-2', Comment: '超棒的課！老師對 NLP 充滿熱情，會介紹最新的 ChatGPT/LLM 相關研究。期末專案可以自己選題，我做了一個中文情感分析，老師給的回饋非常詳細。', Rating_Quality: 5, Rating_Sweet: 5, Rating_Easy: 4, Rating_Rich: 5 },
      { User_ID: 'User20987', Semester: '113-1', Comment: '這門課給分很甜，認真做專案的話 A+ 機率很高。老師不點名，但上課內容很有趣所以大家都會自動去聽。強烈推薦！', Rating_Quality: 5, Rating_Sweet: 5, Rating_Easy: 4, Rating_Rich: 5 },
      { User_ID: 'User67344', Semester: '112-2', Comment: '陳信希老師業界資歷豐富，課程內容非常實用。作業份量適中，期末專案佔比重，需要組隊完成。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 3, Rating_Rich: 4 },
    ]
  },
  {
    id: '1004', code: 'HIST1001', name: '世界史概論', professor: '陳永發',
    department: '歷史學系', credits: 2, semester: '114-2',
    time: '三 5,6', location: '普通教學館 302', language: '中文授課',
    required: '通識', capacity: 150,
    overview: '從史前文明到當代國際關係，帶領學生縱覽人類文明的演進脈絡。',
    goals: '培養學生歷史思維與人文素養，理解當代社會問題的歷史根源。',
    requirements_text: '無先修要求，適合所有學系學生選修。',
    grading: '期中報告 40% + 期末考 40% + 課堂討論 20%',
    notes: '授課以講述為主，期末考為申論題。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1004',
    rating_quality: 4.0, rating_sweet: 4.5, rating_easy: 4.0, rating_rich: 3.5,
    tags: ['#輕鬆', '#給分甜', '#人文素養', '#不點名'],
    reviews: [
      { User_ID: 'User31256', Semester: '113-2', Comment: '老師上課充滿故事性，讓歷史變得生動有趣。給分很友善，認真念書期末考不難。通識課首選！', Rating_Quality: 4, Rating_Sweet: 5, Rating_Easy: 4, Rating_Rich: 3 },
      { User_ID: 'User80023', Semester: '113-1', Comment: '很好的通識課，讓我對歷史的理解從死記硬背轉變為理解脈絡。老師偶爾點名但很隨機。', Rating_Quality: 4, Rating_Sweet: 4, Rating_Easy: 4, Rating_Rich: 4 },
    ]
  },
  {
    id: '1005', code: 'MATH2001', name: '微積分甲下', professor: '張鎮華',
    department: '數學系', credits: 4, semester: '114-2',
    time: '一 3,4 三 3,4', location: '普通教學館 101', language: '中文授課',
    required: '必修', capacity: 90,
    overview: '多變數微積分、向量分析、無窮級數、微分方程基礎。',
    goals: '使學生具備工程與科學計算所需的數學基礎。',
    requirements_text: '需已修過微積分甲上。',
    grading: '期中考一 25% + 期中考二 25% + 期末考 35% + 作業 15%',
    notes: '考試為紙筆測驗，需要大量練習題目。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1005',
    rating_quality: 4.2, rating_sweet: 2.5, rating_easy: 1.5, rating_rich: 4.8,
    tags: ['#期中考', '#期末考', '#扎實', '#作業偏難'],
    reviews: [
      { User_ID: 'User12987', Semester: '113-2', Comment: '張老師教學嚴謹，板書清楚。微積分對理工科學生非常重要，雖然難但必修課要認真對待。考試很有挑戰性。', Rating_Quality: 4, Rating_Sweet: 2, Rating_Easy: 1, Rating_Rich: 5 },
    ]
  },
  {
    id: '1006', code: 'ECON2001', name: '個體經濟學', professor: '駱明慶',
    department: '經濟學系', credits: 3, semester: '114-2',
    time: '二 6,7,8', location: '社科院 B105', language: '中文授課',
    required: '必修', capacity: 100,
    overview: '消費者行為、廠商理論、市場均衡、賽局理論。',
    goals: '理解市場機制與個體經濟決策的理論基礎。',
    requirements_text: '需已修過經濟學原理。',
    grading: '期中考 40% + 期末考 40% + 作業 20%',
    notes: '老師給分公正，期末考可帶手寫小抄一張。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1006',
    rating_quality: 4.3, rating_sweet: 3.8, rating_easy: 3.0, rating_rich: 4.2,
    tags: ['#給分甜', '#期中考', '#期末考'],
    reviews: [
      { User_ID: 'User50234', Semester: '113-2', Comment: '駱老師是台大最好的經濟學老師之一！上課幽默風趣，用很多現實例子解釋理論。考試難度適中，給分也不錯。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 3, Rating_Rich: 4 },
      { User_ID: 'User67891', Semester: '113-1', Comment: '課程內容實用，老師會讓學生思考現實問題。期末考可以帶小抄是很大的優點，讓人比較不緊張。', Rating_Quality: 4, Rating_Sweet: 4, Rating_Easy: 3, Rating_Rich: 4 },
    ]
  },
  {
    id: '1007', code: 'PHIL1001', name: '哲學概論', professor: '苑舉正',
    department: '哲學系', credits: 2, semester: '114-2',
    time: '五 3,4', location: '哲學系館 115', language: '中文授課',
    required: '通識', capacity: 80,
    overview: '介紹哲學的主要領域：形上學、認識論、倫理學、邏輯學及政治哲學。',
    goals: '培養批判性思考與哲學分析能力，開拓學生的思維視野。',
    requirements_text: '無先修要求。',
    grading: '期中考 30% + 期末論文 40% + 課堂參與 30%',
    notes: '需要積極課堂討論，老師重視學生的思辨能力。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1007',
    rating_quality: 4.6, rating_sweet: 4.0, rating_easy: 3.5, rating_rich: 4.3,
    tags: ['#點名', '#期末報告', '#人文素養', '#輕鬆'],
    reviews: [
      { User_ID: 'User23456', Semester: '113-2', Comment: '苑老師上課非常生動，很會引導學生思考。期末論文可以自由發揮，老師給分寬鬆。推薦給想訓練批判性思維的同學。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 4, Rating_Rich: 4 },
    ]
  },
  {
    id: '1008', code: 'PROJ3001', name: '軟體工程與專案管理', professor: '劉邦鋒',
    department: '資訊工程學系', credits: 3, semester: '114-2',
    time: '三 6,7,8', location: '資電館 201', language: '中文授課',
    required: '選修', capacity: 40,
    overview: '敏捷開發、版本控制、CI/CD、系統設計、專案管理工具與實際開發流程。',
    goals: '培養學生實際軟體工程能力，模擬業界開發環境。',
    requirements_text: '需有基本程式設計能力，建議有 Web 開發或物件導向程式設計經驗。',
    grading: '分組專案 70% + 個人報告 20% + 課堂參與 10%',
    notes: '全程分組，需組成 4-5 人的開發團隊，模擬真實公司開發流程。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1008',
    rating_quality: 4.7, rating_sweet: 4.2, rating_easy: 3.8, rating_rich: 4.5,
    tags: ['#期末報告', '#給分甜', '#不點名', '#團隊協作'],
    reviews: [
      { User_ID: 'User45678', Semester: '113-2', Comment: '這門課讓我真正理解了業界的開發流程！老師有豐富的業界經驗，分享了很多實務案例。分組專案很有挑戰性但也很有收穫。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 4, Rating_Rich: 5 },
      { User_ID: 'User34521', Semester: '113-1', Comment: '全程用 Git 管理專案，學到了很多工具的使用。給分算甜，只要認真做專案應該都會過得不錯。強烈推薦！', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 4, Rating_Rich: 4 },
    ]
  },
  {
    id: '1009', code: 'STAT2001', name: '統計學', professor: '鄭明燕',
    department: '統計學系', credits: 3, semester: '114-2',
    time: '一 5,6 四 5', location: '社科院 101', language: '中文授課',
    required: '選修', capacity: 100,
    overview: '描述統計、機率論、抽樣分佈、假設檢定、迴歸分析。',
    goals: '使學生具備資料分析與統計推論的基本能力。',
    requirements_text: '需有高中數學基礎，修過微積分者更佳。',
    grading: '期中考 35% + 期末考 35% + 作業 20% + 期末報告 10%',
    notes: '期末報告需應用統計方法分析真實資料集。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1009',
    rating_quality: 4.1, rating_sweet: 3.3, rating_easy: 2.8, rating_rich: 4.4,
    tags: ['#期中考', '#期末考', '#期末報告', '#扎實'],
    reviews: [
      { User_ID: 'User98234', Semester: '113-2', Comment: '老師教得清楚，考試題目來自課本，認真念書不難考好。期末報告可以分組，選自己感興趣的資料集分析。', Rating_Quality: 4, Rating_Sweet: 3, Rating_Easy: 3, Rating_Rich: 4 },
    ]
  },
  {
    id: '1010', code: 'ART2001', name: '藝術史導論', professor: '白適銘',
    department: '藝術史研究所', credits: 2, semester: '114-2',
    time: '五 5,6', location: '文學院 201', language: '中文授課',
    required: '通識', capacity: 60,
    overview: '從古埃及、希臘羅馬到文藝復興，再到現代當代藝術，建立學生的藝術史觀。',
    goals: '培養美學鑑賞能力，理解藝術作品的歷史脈絡與文化意涵。',
    requirements_text: '無先修要求，歡迎所有學系學生。',
    grading: '期末報告 50% + 心得文章 30% + 出席 20%',
    notes: '課程含博物館參訪活動，需自費前往。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1010',
    rating_quality: 4.4, rating_sweet: 4.8, rating_easy: 4.5, rating_rich: 3.8,
    tags: ['#輕鬆', '#給分甜', '#期末報告', '#人文素養'],
    reviews: [
      { User_ID: 'User12345', Semester: '113-2', Comment: '超輕鬆的通識課！老師展示大量藝術作品圖片，上課很享受。期末報告可以寫任何你喜歡的藝術作品，給分非常甜。', Rating_Quality: 4, Rating_Sweet: 5, Rating_Easy: 5, Rating_Rich: 3 },
      { User_ID: 'User55678', Semester: '113-1', Comment: '博物館參訪很有趣，老師帶你實地解說。這門課讓我開始對藝術有了真正的興趣。通識選這門絕對值得！', Rating_Quality: 5, Rating_Sweet: 5, Rating_Easy: 4, Rating_Rich: 4 },
    ]
  },
  {
    id: '1011', code: 'DB4001', name: '資料庫系統', professor: '徐俊傑',
    department: '資訊工程學系', credits: 3, semester: '114-2',
    time: '二 1,2,3', location: '資電館 105', language: '中文授課',
    required: '選修', capacity: 70,
    overview: 'SQL、關聯式資料庫設計、交易管理、NoSQL 系統、查詢最佳化。',
    goals: '使學生能設計、實作並管理現代資料庫系統。',
    requirements_text: '需有程式設計基礎，瞭解資料結構者佳。',
    grading: '作業 40% + 期中考 25% + 期末專案 35%',
    notes: '期末專案需設計完整資料庫並實作應用程式。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1011',
    rating_quality: 4.5, rating_sweet: 4.0, rating_easy: 3.2, rating_rich: 4.6,
    tags: ['#期末報告', '#給分甜', '#程式實作'],
    reviews: [
      { User_ID: 'User87654', Semester: '113-2', Comment: '課程內容非常實用！SQL 和資料庫設計是每個後端工程師必備的技能。老師期末專案評分寬鬆，只要完成功能就能拿到不錯的分數。', Rating_Quality: 5, Rating_Sweet: 4, Rating_Easy: 3, Rating_Rich: 5 },
    ]
  },
  {
    id: '1012', code: 'ENV3001', name: '環境科學與永續發展', professor: '盛中德',
    department: '環境工程學研究所', credits: 2, semester: '114-2',
    time: '四 3,4', location: '工綜館 215', language: '中文授課',
    required: '通識', capacity: 90,
    overview: '氣候變遷、碳中和、循環經濟、永續城市設計及環境政策分析。',
    goals: '建立學生的環境意識與永續發展觀念，培養解決全球環境問題的能力。',
    requirements_text: '無先修要求，適合所有系所學生。',
    grading: '期末報告 50% + 課堂參與 30% + 心得 20%',
    notes: '鼓勵跨系學生選修，期末報告可跨領域討論。',
    url: 'https://course.ntu.edu.tw/courses/114-2/1012',
    rating_quality: 4.3, rating_sweet: 4.6, rating_easy: 4.3, rating_rich: 3.9,
    tags: ['#輕鬆', '#給分甜', '#期末報告', '#不點名'],
    reviews: [
      { User_ID: 'User24680', Semester: '113-2', Comment: '很重要的議題，老師介紹了台灣和國際的永續發展案例。給分非常好，期末報告只要認真寫都能拿高分。推薦選修！', Rating_Quality: 4, Rating_Sweet: 5, Rating_Easy: 4, Rating_Rich: 4 },
    ]
  },
];

// Mock prereq data
const PREREQ_DATA = {
  '1001': { prereqs: ['線性代數', 'Python 程式設計'], blockers: [] },
  '1002': { prereqs: ['計算機程式設計'], blockers: [] },
  '1003': { prereqs: ['機器學習'], blockers: [] },
  '1005': { prereqs: ['微積分甲上'], blockers: [] },
  '1006': { prereqs: ['經濟學原理'], blockers: [] },
  '1011': { prereqs: ['計算機程式設計', '資料結構'], blockers: [] },
};

// Mock schedule courses (already enrolled this semester)
const INITIAL_SCHEDULE = [
  { courseId: '1001', name: '機器學習', professor: '林軒田', time: '二 3,4,5', color: '#3B82F6' },
  { courseId: '1009', name: '統計學', professor: '鄭明燕', time: '一 5,6 四 5', color: '#8B5CF6' },
  { courseId: '1008', name: '軟體工程', professor: '劉邦鋒', time: '三 6,7,8', color: '#10B981' },
];

// Color palette for schedule courses
const COURSE_COLORS = ['#3B82F6','#8B5CF6','#10B981','#F59E0B','#EF4444','#EC4899','#06B6D4','#84CC16'];

// Category display map
const CATEGORY_MAP = {
  math: { label: '數理邏輯', icon: '📐' },
  cs: { label: '程式實作', icon: '💻' },
  lang: { label: '文字表達', icon: '✍️' },
  humanities: { label: '人文素養', icon: '🎨' },
  team: { label: '團隊協作', icon: '🤝' },
  other: { label: '其他', icon: '📚' },
};

// GPA map
const GPA_MAP = { 'A+': 4.3, 'A': 4.0, 'A-': 3.7, 'B+': 3.3, 'B': 3.0, 'B-': 2.7, 'C+': 2.3, 'C': 2.0, 'F': 0.0 };

// NTU period info
const PERIODS = [
  { code: '1', time: '08:10', label: '第1節' },
  { code: '2', time: '09:10', label: '第2節' },
  { code: '3', time: '10:20', label: '第3節' },
  { code: '4', time: '11:20', label: '第4節' },
  { code: 'N', time: '12:20', label: '午休N' },
  { code: '5', time: '13:20', label: '第5節' },
  { code: '6', time: '14:20', label: '第6節' },
  { code: '7', time: '15:30', label: '第7節' },
  { code: '8', time: '16:30', label: '第8節' },
  { code: '9', time: '17:30', label: '第9節' },
];
const DAYS = ['週一', '週二', '週三', '週四', '週五'];
const DAY_CHARS = ['一', '二', '三', '四', '五'];

// ============================================================
// STATE
// ============================================================
const state = {
  currentView: 'dashboard',
  user: null, // { id, name, dept, avatar }
  history: [], // course history records
  schedule: [...INITIAL_SCHEDULE], // current schedule
  filteredCourses: [...MOCK_COURSES],
  currentPage: 1,
  perPage: 9,
  filters: { search: '', hasRating: false, noEarlyMorning: false, english: false, minCredits: 0, maxCredits: 6, minSweet: 0, days: [], sort: 'name' },
  currentAnalysisCourse: null,
  radarChart: null,
  fitDonutChart: null,
  analysisReviewPage: 1,
};

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  loadFromStorage();
  initAvatars();
  initSidebar();
  initFilters();
  initHistory();
  initSchedule();
  initAnalysis();
  navigate('dashboard');
  updateUserUI();
});

function loadFromStorage() {
  const saved = localStorage.getItem('ntu_user');
  if (saved) state.user = JSON.parse(saved);

  const savedHistory = localStorage.getItem('ntu_history');
  if (savedHistory) state.history = JSON.parse(savedHistory);
}

function saveHistory() {
  localStorage.setItem('ntu_history', JSON.stringify(state.history));
}

function saveUser() {
  localStorage.setItem('ntu_user', JSON.stringify(state.user));
}

// ============================================================
// AVATAR HELPER
// ============================================================
function getAvatar(name, bg = '002D62', color = 'ffffff') {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name || '?')}&background=${bg}&color=${color}&size=80`;
}

function initAvatars() {
  const name = state.user ? state.user.name : '未登入';
  const bg = state.user ? '9E1B32' : 'cccccc';
  const col = state.user ? 'ffffff' : '000000';
  document.getElementById('headerAvatar').src = getAvatar(name, bg, col);
  document.getElementById('sidebarAvatar').src = getAvatar(name, bg, col);
}

// ============================================================
// NAVIGATION
// ============================================================
function navigate(view) {
  state.currentView = view;

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const viewEl = document.getElementById(`view-${view}`);
  if (viewEl) viewEl.classList.add('active');

  const navEl = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (navEl) navEl.classList.add('active');

  // View-specific initialization
  if (view === 'dashboard') renderDashboard();
  if (view === 'discovery') renderCourseGrid();
  if (view === 'history') renderHistoryTable();
  if (view === 'schedule') renderSchedule();
  if (view === 'analysis') renderQuickPicks();

  // Close mobile sidebar
  if (window.innerWidth <= 600) {
    document.getElementById('sidebar').classList.remove('mobile-open');
  }
}

function initSidebar() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => navigate(item.dataset.view));
  });

  document.getElementById('hamburgerBtn').addEventListener('click', () => {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 600) {
      sidebar.classList.toggle('mobile-open');
    } else {
      sidebar.classList.toggle('collapsed');
    }
  });

  document.getElementById('loginBtn').addEventListener('click', () => showLoginModal());
  document.getElementById('logoutBtn').addEventListener('click', logout);

  document.getElementById('mainContent').addEventListener('click', () => {
    if (window.innerWidth <= 600) {
      document.getElementById('sidebar').classList.remove('mobile-open');
    }
  });
}

// ============================================================
// USER AUTH
// ============================================================
function updateUserUI() {
  const u = state.user;
  if (u) {
    document.getElementById('headerName').textContent = u.name;
    document.getElementById('sidebarName').textContent = u.name;
    document.getElementById('sidebarId').textContent = u.id + (u.dept ? ` · ${u.dept}` : '');
    document.getElementById('statusText').textContent = '已登入 Online';
    document.querySelector('.status-dot').className = 'status-dot online';
    document.getElementById('loginBtn').classList.add('hidden');
    document.getElementById('logoutBtn').classList.remove('hidden');
    initAvatars();
  } else {
    document.getElementById('headerName').textContent = '未登入';
    document.getElementById('sidebarName').textContent = '未登入';
    document.getElementById('sidebarId').textContent = '請先登入';
    document.getElementById('statusText').textContent = '等待登入';
    document.querySelector('.status-dot').className = 'status-dot waiting';
    document.getElementById('loginBtn').classList.remove('hidden');
    document.getElementById('logoutBtn').classList.add('hidden');
    initAvatars();
  }
  updateStats();
}

function showLoginModal() {
  document.getElementById('loginModal').classList.remove('hidden');
}
function hideLoginModal() {
  document.getElementById('loginModal').classList.add('hidden');
}

document.getElementById('loginModalClose').addEventListener('click', hideLoginModal);
document.getElementById('loginModal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) hideLoginModal();
});

document.getElementById('loginForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const id = document.getElementById('loginId').value.trim();
  const name = document.getElementById('loginName').value.trim();
  const dept = document.getElementById('loginDept').value.trim();
  state.user = { id, name, dept, avatar: '' };
  saveUser();
  updateUserUI();
  hideLoginModal();
  showToast('success', `歡迎回來，${name}！`);
  navigate('dashboard');
});

function logout() {
  state.user = null;
  localStorage.removeItem('ntu_user');
  updateUserUI();
  showToast('info', '已登出');
  navigate('dashboard');
}

// ============================================================
// DASHBOARD
// ============================================================
function renderDashboard() {
  updateStats();
  renderRadarChart();
  renderRecommendations();
}

function updateStats() {
  const totalCredits = state.history.reduce((s, c) => s + (parseFloat(c.credits) || 0), 0);
  const totalCourses = state.history.length;
  const scheduled = state.schedule.length;
  document.getElementById('statCredits').textContent = totalCredits;
  document.getElementById('statCourses').textContent = totalCourses;
  document.getElementById('statScheduled').textContent = scheduled;

  if (state.history.length > 0) {
    const graded = state.history.filter(c => c.grade && GPA_MAP[c.grade] !== undefined);
    if (graded.length > 0) {
      const totalW = graded.reduce((s, c) => s + (GPA_MAP[c.grade] * (parseFloat(c.credits) || 1)), 0);
      const totalC = graded.reduce((s, c) => s + (parseFloat(c.credits) || 1), 0);
      document.getElementById('statGpa').textContent = (totalW / totalC).toFixed(2);
    } else {
      document.getElementById('statGpa').textContent = '-';
    }
  } else {
    document.getElementById('statGpa').textContent = '-';
  }
}

function computeRadarData() {
  const cats = { math: 0, cs: 0, lang: 0, humanities: 0, team: 0 };
  const counts = { math: 0, cs: 0, lang: 0, humanities: 0, team: 0 };

  state.history.forEach(c => {
    if (cats[c.category] !== undefined) {
      const gpa = GPA_MAP[c.grade] || 3.0;
      cats[c.category] += gpa;
      counts[c.category]++;
    }
  });

  const normalize = (key) => {
    if (counts[key] === 0) return 40 + Math.random() * 20 | 0; // base value if no data
    return Math.min(100, Math.round((cats[key] / counts[key]) / 4.3 * 85 + 15));
  };

  return [
    normalize('math'),
    normalize('lang'),
    normalize('cs'),
    normalize('humanities'),
    normalize('team'),
  ];
}

function renderRadarChart() {
  const ctx = document.getElementById('radarChart').getContext('2d');
  if (state.radarChart) state.radarChart.destroy();

  const data = computeRadarData();

  state.radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['數理邏輯', '文字表達', '程式實作', '人文素養', '團隊協作'],
      datasets: [{
        label: '能力值',
        data: data,
        backgroundColor: 'rgba(158, 27, 50, 0.15)',
        borderColor: 'rgba(158, 27, 50, 0.85)',
        borderWidth: 2,
        pointBackgroundColor: '#9E1B32',
        pointBorderColor: '#fff',
        pointHoverBackgroundColor: '#fff',
        pointHoverBorderColor: '#9E1B32',
        pointRadius: 5,
        pointHoverRadius: 7,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 20, color: '#999', backdropColor: 'transparent', font: { size: 10 } },
          grid: { color: 'rgba(0,0,0,0.07)' },
          angleLines: { color: 'rgba(0,0,0,0.1)' },
          pointLabels: { font: { size: 13, family: '"Microsoft JhengHei", Arial, sans-serif' }, color: '#444' }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: '#1F2937', padding: 10, bodyFont: { size: 13 } }
      }
    }
  });
}

function renderRecommendations() {
  const topCourses = [...MOCK_COURSES]
    .sort((a, b) => (b.rating_quality || 0) - (a.rating_quality || 0))
    .slice(0, 4);

  const badges = [
    { cls: 'top', icon: '⭐', text: '極度推薦' },
    { cls: 'fit', icon: '✅', text: '適合度高' },
    { cls: 'gap', icon: '⏰', text: '填補空堂' },
    { cls: 'fit', icon: '💡', text: '補強弱點' },
  ];

  const list = document.getElementById('recommendList');
  list.innerHTML = topCourses.map((c, i) => `
    <div class="rec-card" onclick="openCourseModal('${c.id}')">
      <div class="rec-card-badge ${badges[i].cls}">${badges[i].icon} ${badges[i].text}</div>
      <div class="rec-card-name">${c.name}</div>
      <div class="rec-card-tags">
        ${c.tags.slice(0, 3).map(t => `<span class="tag tag-blue">${t}</span>`).join('')}
      </div>
      <div class="rec-card-meta">
        <span><i class="fas fa-user"></i> ${c.professor}</span>
        <span><i class="fas fa-book"></i> ${c.credits} 學分</span>
        ${c.rating_sweet ? `<span><i class="fas fa-candy-cane"></i> 甜度 ${c.rating_sweet}</span>` : ''}
      </div>
    </div>
  `).join('');
}

// ============================================================
// COURSE DISCOVERY
// ============================================================
function initFilters() {
  const searchInput = document.getElementById('searchInput');
  searchInput.addEventListener('input', debounce(() => {
    state.filters.search = searchInput.value;
    state.currentPage = 1;
    applyFilters();
  }, 300));

  document.getElementById('applyFilterBtn').addEventListener('click', applyFilters);
  document.getElementById('resetFilterBtn').addEventListener('click', resetFilters);

  document.getElementById('toggleFilterBtn').addEventListener('click', () => {
    document.getElementById('filterPanel').classList.toggle('mobile-show');
  });

  // Range sliders
  const minCredits = document.getElementById('filterMinCredits');
  const maxCredits = document.getElementById('filterMaxCredits');
  const minSweet = document.getElementById('filterMinSweet');

  minCredits.addEventListener('input', () => {
    document.getElementById('filterMinCreditsVal').textContent = minCredits.value;
  });
  maxCredits.addEventListener('input', () => {
    document.getElementById('filterMaxCreditsVal').textContent = maxCredits.value;
  });
  minSweet.addEventListener('input', () => {
    const v = parseFloat(minSweet.value);
    document.getElementById('filterMinSweetVal').textContent = v === 0 ? '不限' : v.toFixed(1);
  });

  document.getElementById('sortBy').addEventListener('change', () => {
    state.filters.sort = document.getElementById('sortBy').value;
    applyFilters();
  });
}

function applyFilters() {
  state.filters.search = document.getElementById('searchInput').value.toLowerCase();
  state.filters.hasRating = document.getElementById('filterHasRating').checked;
  state.filters.noEarlyMorning = document.getElementById('filterNoEarlyMorning').checked;
  state.filters.english = document.getElementById('filterEnglish').checked;
  state.filters.minCredits = parseFloat(document.getElementById('filterMinCredits').value) || 0;
  state.filters.maxCredits = parseFloat(document.getElementById('filterMaxCredits').value) || 6;
  state.filters.minSweet = parseFloat(document.getElementById('filterMinSweet').value) || 0;
  state.filters.days = [...document.querySelectorAll('.filter-day:checked')].map(c => c.value);
  state.filters.sort = document.getElementById('sortBy').value;
  state.currentPage = 1;

  let filtered = [...MOCK_COURSES];

  if (state.filters.search) {
    filtered = filtered.filter(c =>
      c.name.toLowerCase().includes(state.filters.search) ||
      c.professor.toLowerCase().includes(state.filters.search) ||
      c.code.toLowerCase().includes(state.filters.search) ||
      c.department.toLowerCase().includes(state.filters.search)
    );
  }
  if (state.filters.hasRating) filtered = filtered.filter(c => c.rating_quality);
  if (state.filters.english) filtered = filtered.filter(c => c.language.includes('英文'));
  if (state.filters.noEarlyMorning) filtered = filtered.filter(c => !c.time.includes('1') || !c.time.match(/[一二三四五]\s*1/));
  if (state.filters.minCredits > 0) filtered = filtered.filter(c => c.credits >= state.filters.minCredits);
  if (state.filters.maxCredits < 6) filtered = filtered.filter(c => c.credits <= state.filters.maxCredits);
  if (state.filters.minSweet > 0) filtered = filtered.filter(c => (c.rating_sweet || 0) >= state.filters.minSweet);
  if (state.filters.days.length > 0) {
    filtered = filtered.filter(c => state.filters.days.some(d => c.time.includes(d)));
  }

  // Sort
  const sortKey = { name: 'name', sweet: 'rating_sweet', quality: 'rating_quality', easy: 'rating_easy' }[state.filters.sort] || 'name';
  if (sortKey === 'name') {
    filtered.sort((a, b) => a.name.localeCompare(b.name, 'zh-Hant'));
  } else {
    filtered.sort((a, b) => (b[sortKey] || 0) - (a[sortKey] || 0));
  }

  state.filteredCourses = filtered;
  renderCourseGrid();
}

function resetFilters() {
  document.getElementById('searchInput').value = '';
  document.getElementById('filterHasRating').checked = false;
  document.getElementById('filterNoEarlyMorning').checked = false;
  document.getElementById('filterEnglish').checked = false;
  document.getElementById('filterMinCredits').value = 0;
  document.getElementById('filterMaxCredits').value = 6;
  document.getElementById('filterMinCreditsVal').textContent = '0';
  document.getElementById('filterMaxCreditsVal').textContent = '6';
  document.getElementById('filterMinSweet').value = 0;
  document.getElementById('filterMinSweetVal').textContent = '不限';
  document.querySelectorAll('.filter-day').forEach(c => c.checked = false);
  document.getElementById('sortBy').value = 'name';
  state.filteredCourses = [...MOCK_COURSES];
  state.currentPage = 1;
  renderCourseGrid();
}

function renderCourseGrid() {
  const total = state.filteredCourses.length;
  const totalPages = Math.ceil(total / state.perPage);
  const start = (state.currentPage - 1) * state.perPage;
  const pageCourses = state.filteredCourses.slice(start, start + state.perPage);

  document.getElementById('resultMeta').textContent =
    `找到 ${total} 門課程，第 ${state.currentPage} / ${totalPages} 頁`;

  const grid = document.getElementById('courseGrid');
  if (pageCourses.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-hint);font-style:italic">查無符合條件的課程</div>`;
  } else {
    grid.innerHTML = pageCourses.map(c => renderCourseCard(c)).join('');
  }

  renderPagination(totalPages);
}

function renderCourseCard(c) {
  const ratingHTML = c.rating_quality
    ? `<span class="rating-stars"><i class="fas fa-star" style="color:#D97706;font-size:10px"></i> <span class="star-val">${c.rating_quality}</span></span>`
    : `<span style="color:var(--text-hint);font-style:italic">無評價</span>`;

  return `
    <div class="course-card-grid" onclick="openCourseModal('${c.id}')">
      <div class="course-name">${c.name}</div>
      <div class="course-prof"><i class="fas fa-user" style="font-size:11px;color:var(--text-hint)"></i> ${c.professor} &nbsp;·&nbsp; ${c.department.split('、')[0]}</div>
      <div class="course-tags">
        ${c.tags.slice(0, 4).map(t => `<span class="tag ${tagColor(t)}">${t}</span>`).join('')}
      </div>
      <div class="course-meta">
        <span><i class="fas fa-book"></i> ${c.credits} 學分</span>
        <span><i class="fas fa-clock"></i> ${c.time || '時間未定'}</span>
        ${ratingHTML}
      </div>
    </div>
  `;
}

function tagColor(tag) {
  if (['#給分甜','#輕鬆','#不點名','#無考試'].includes(tag)) return 'tag-green';
  if (['#扎實','#作業偏難','#早八'].includes(tag)) return 'tag-red';
  if (['#期末報告','#期末考','#期中考'].includes(tag)) return 'tag-yellow';
  if (['#NLP','#英文授課','#程式實作','#人文素養'].includes(tag)) return 'tag-purple';
  return 'tag-blue';
}

function renderPagination(totalPages) {
  const pg = document.getElementById('pagination');
  if (totalPages <= 1) { pg.innerHTML = ''; return; }

  let html = '';
  html += `<button class="page-btn" onclick="changePage(${state.currentPage - 1})" ${state.currentPage === 1 ? 'disabled' : ''}><i class="fas fa-chevron-left"></i></button>`;

  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || Math.abs(i - state.currentPage) <= 1) {
      html += `<button class="page-btn ${i === state.currentPage ? 'active' : ''}" onclick="changePage(${i})">${i}</button>`;
    } else if (Math.abs(i - state.currentPage) === 2) {
      html += `<span style="padding:0 4px;line-height:32px;color:var(--text-hint)">…</span>`;
    }
  }

  html += `<button class="page-btn" onclick="changePage(${state.currentPage + 1})" ${state.currentPage === totalPages ? 'disabled' : ''}><i class="fas fa-chevron-right"></i></button>`;
  pg.innerHTML = html;
}

function changePage(p) {
  const totalPages = Math.ceil(state.filteredCourses.length / state.perPage);
  if (p < 1 || p > totalPages) return;
  state.currentPage = p;
  renderCourseGrid();
  document.getElementById('courseGrid').scrollIntoView({ behavior: 'smooth' });
}

// ============================================================
// COURSE DETAIL MODAL
// ============================================================
function openCourseModal(id) {
  const course = MOCK_COURSES.find(c => c.id === id);
  if (!course) return;

  const prereq = PREREQ_DATA[id];
  const missingPrereqs = prereq ? checkPrereqs(prereq.prereqs) : [];

  const ratingHTML = (label, val, cls) => val
    ? `<div class="detail-rating-box"><div class="detail-rating-value ${cls}">${val}</div><div class="detail-rating-label">${label}</div></div>`
    : `<div class="detail-rating-box"><div class="detail-rating-value" style="color:var(--text-hint);font-size:16px">-</div><div class="detail-rating-label">${label}</div></div>`;

  const content = `
    <div class="detail-upper">
      <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px">
        <div style="flex:1">
          <div class="detail-course-name">${course.name}</div>
          <div class="detail-meta">
            <span><i class="fas fa-user"></i> ${course.professor}</span>
            <span><i class="fas fa-sitemap"></i> ${course.department.split('、')[0]}</span>
            <span><i class="fas fa-book"></i> ${course.credits} 學分</span>
            <span><i class="fas fa-clock"></i> ${course.time || '時間未定'}</span>
            <span><i class="fas fa-map-marker-alt"></i> ${course.location || '地點未定'}</span>
            <span><i class="fas fa-language"></i> ${course.language}</span>
          </div>
          <div class="detail-tags">
            ${course.tags.map(t => `<span class="tag ${tagColor(t)}">${t}</span>`).join('')}
          </div>
        </div>
        <a href="${course.url}" target="_blank" class="btn-secondary" style="white-space:nowrap;font-size:12px">
          <i class="fas fa-external-link-alt"></i> 課程頁面
        </a>
      </div>

      <div class="detail-ratings">
        ${ratingHTML('品質', course.rating_quality, 'r-quality')}
        ${ratingHTML('甜度', course.rating_sweet, 'r-sweet')}
        ${ratingHTML('涼度', course.rating_easy, 'r-easy')}
        ${ratingHTML('紮實', course.rating_rich, 'r-rich')}
      </div>
    </div>

    ${prereq && missingPrereqs.length > 0 ? `
    <div style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:8px;padding:12px 16px;margin-bottom:20px;display:flex;align-items:flex-start;gap:10px">
      <i class="fas fa-exclamation-triangle" style="color:#D97706;margin-top:2px"></i>
      <div>
        <div style="font-weight:700;font-size:13px;margin-bottom:4px">⚠️ 先修條件警告</div>
        <div style="font-size:13px;color:#92400E">您尚未修習：<strong>${missingPrereqs.join('、')}</strong>。建議先完成先修課程再選修本課程。</div>
      </div>
    </div>` : ''}

    <div class="detail-info-grid">
      <div class="detail-info-item">
        <div class="detail-info-label">必選修</div>
        <div class="detail-info-value">${course.required}</div>
      </div>
      <div class="detail-info-item">
        <div class="detail-info-label">修課人數上限</div>
        <div class="detail-info-value">${course.capacity || '未限制'} 人</div>
      </div>
      <div class="detail-info-item">
        <div class="detail-info-label">加簽方式</div>
        <div class="detail-info-value">1 類</div>
      </div>
      <div class="detail-info-item">
        <div class="detail-info-label">開課學期</div>
        <div class="detail-info-value">${course.semester}</div>
      </div>
    </div>

    ${course.overview ? `
    <div class="detail-section">
      <div class="detail-section-title"><i class="fas fa-align-left"></i> 課程概述</div>
      <div class="detail-section-body">${course.overview}</div>
    </div>` : ''}

    ${course.goals ? `
    <div class="detail-section">
      <div class="detail-section-title"><i class="fas fa-bullseye"></i> 課程目標</div>
      <div class="detail-section-body">${course.goals}</div>
    </div>` : ''}

    ${course.grading ? `
    <div class="detail-section">
      <div class="detail-section-title"><i class="fas fa-percentage"></i> 評量方式</div>
      <div class="detail-section-body">${course.grading}</div>
    </div>` : ''}

    ${course.requirements_text ? `
    <div class="detail-section">
      <div class="detail-section-title"><i class="fas fa-clipboard-check"></i> 課程要求</div>
      <div class="detail-section-body">${course.requirements_text}</div>
    </div>` : ''}

    <hr class="detail-divider">

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <h3 style="font-size:15px;font-weight:700">
        <i class="fas fa-comments" style="color:var(--ntu-red)"></i>
        歷年評價 (${course.reviews.length} 則)
      </h3>
      <button class="btn-add-course" onclick="addToScheduleFromModal('${course.id}');document.getElementById('courseModal').classList.add('hidden')">
        <i class="fas fa-calendar-plus"></i> 加入課表
      </button>
    </div>

    <div style="display:flex;flex-direction:column;gap:14px">
      ${course.reviews.length > 0 ? course.reviews.map(r => renderReviewItem(r)).join('') : '<div class="no-rating">尚無評價資料</div>'}
    </div>
  `;

  document.getElementById('modalContent').innerHTML = content;
  document.getElementById('courseModal').classList.remove('hidden');
}

function renderReviewItem(r) {
  return `
    <div class="review-item">
      <div class="review-header">
        <span class="review-user"><i class="fas fa-user-circle"></i> ${r.User_ID}</span>
        <span class="review-sem">${r.Semester}</span>
        ${r.Rating_Quality ? `<div class="review-ratings">
          <span class="review-rating-item">品質 <span>${r.Rating_Quality}</span></span>
          <span class="review-rating-item">甜度 <span>${r.Rating_Sweet}</span></span>
          <span class="review-rating-item">涼度 <span>${r.Rating_Easy}</span></span>
        </div>` : ''}
      </div>
      <div class="review-body">${r.Comment.replace(/\n/g, '<br>')}</div>
    </div>
  `;
}

document.getElementById('modalCloseBtn').addEventListener('click', () => {
  document.getElementById('courseModal').classList.add('hidden');
});
document.getElementById('courseModal').addEventListener('click', (e) => {
  if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
});

// ============================================================
// COURSE HISTORY
// ============================================================
function initHistory() {
  document.getElementById('historyForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const name = document.getElementById('hCourseName').value.trim();
    const prof = document.getElementById('hProfessor').value.trim();
    const sem = document.getElementById('hSemester').value.trim();
    const credits = document.getElementById('hCredits').value;
    const grade = document.getElementById('hGrade').value;
    const category = document.getElementById('hCategory').value;
    const note = document.getElementById('hNote').value.trim();

    state.history.push({
      id: Date.now().toString(),
      name, professor: prof, semester: sem,
      credits: parseFloat(credits) || 0,
      grade, category, note
    });

    saveHistory();
    renderHistoryTable();
    updateStats();
    renderRadarChart();
    e.target.reset();
    showToast('success', `已新增「${name}」到修課歷程`);
  });

  document.getElementById('importBtn').addEventListener('click', importSampleData);
}

function importSampleData() {
  const sample = [
    { id: 's1', name: '線性代數', professor: '陳宜良', semester: '113-1', credits: 3, grade: 'A', category: 'math', note: '很重要的基礎課' },
    { id: 's2', name: 'Python 程式設計', professor: '蔡欣穆', semester: '112-2', credits: 3, grade: 'A+', category: 'cs', note: '入門很友善' },
    { id: 's3', name: '計算機程式設計', professor: '林智仁', semester: '112-1', credits: 4, grade: 'A-', category: 'cs', note: 'C語言入門' },
    { id: 's4', name: '大學寫作', professor: '陳平原', semester: '112-1', credits: 2, grade: 'B+', category: 'lang', note: '訓練論文寫作' },
    { id: 's5', name: '經濟學原理', professor: '何泰寬', semester: '112-2', credits: 3, grade: 'A', category: 'other', note: '通識必備' },
  ];

  const existing = new Set(state.history.map(h => h.name));
  const toAdd = sample.filter(s => !existing.has(s.name));
  state.history.push(...toAdd);
  saveHistory();
  renderHistoryTable();
  updateStats();
  renderRadarChart();
  showToast('success', `匯入 ${toAdd.length} 筆範例修課資料`);
}

function renderHistoryTable() {
  const tbody = document.getElementById('historyTableBody');
  document.getElementById('historyCount').textContent = `共 ${state.history.length} 門`;

  if (state.history.length === 0) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="7">尚無修課紀錄，請新增或匯入資料</td></tr>`;
    return;
  }

  tbody.innerHTML = state.history.map(c => {
    const gradeClass = c.grade
      ? (c.grade.startsWith('A') ? 'grade-A' : c.grade.startsWith('B') ? 'grade-B' : c.grade === 'F' ? 'grade-F' : 'grade-C')
      : '';
    const catLabel = CATEGORY_MAP[c.category]?.label || '其他';
    const catIcon = CATEGORY_MAP[c.category]?.icon || '📚';

    return `
      <tr>
        <td style="font-weight:600">${c.name}</td>
        <td>${c.professor || '-'}</td>
        <td>${c.semester || '-'}</td>
        <td>${c.credits}</td>
        <td>${c.grade ? `<span class="grade-badge ${gradeClass}">${c.grade}</span>` : '-'}</td>
        <td>${catIcon} ${catLabel}</td>
        <td>
          <button class="btn-icon del" onclick="deleteCourse('${c.id}')" title="刪除">
            <i class="fas fa-trash"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function deleteCourse(id) {
  const c = state.history.find(h => h.id === id);
  state.history = state.history.filter(h => h.id !== id);
  saveHistory();
  renderHistoryTable();
  updateStats();
  renderRadarChart();
  showToast('info', `已刪除「${c?.name || ''}」`);
}

// ============================================================
// SCHEDULE
// ============================================================
function parseTimeSlot(timeStr) {
  if (!timeStr) return [];
  const dayIdx = { '一': 0, '二': 1, '三': 2, '四': 3, '五': 4, '六': 5 };
  const results = [];
  const regex = /([一二三四五六])\s*([\d,N A-Da-d\s,]+?)(?=[一二三四五六]|$)/g;
  let m;
  while ((m = regex.exec(timeStr)) !== null) {
    const day = dayIdx[m[1]];
    if (day !== undefined) {
      const periods = m[2].split(/[\s,]+/).map(p => p.trim().toUpperCase()).filter(p => p && PERIODS.find(pp => pp.code === p));
      if (periods.length) results.push({ day, periods });
    }
  }
  return results;
}

function initSchedule() {
  document.getElementById('addToScheduleBtn').addEventListener('click', () => {
    navigate('discovery');
    showToast('info', '請從課程列表選擇課程後點擊「加入課表」');
  });
}

function renderSchedule() {
  renderScheduleLegend();
  renderScheduleTable();
  renderGapSuggestions();
}

function renderScheduleLegend() {
  const legend = document.getElementById('scheduleLegend');
  legend.innerHTML = state.schedule.map(c => `
    <div class="legend-item">
      <div class="legend-dot" style="background:${c.color}"></div>
      <span>${c.name}</span>
    </div>
  `).join('');
}

function renderScheduleTable() {
  const table = document.getElementById('scheduleTable');

  // Build cell map: cellMap[day][period] = course
  const cellMap = {};
  for (let d = 0; d < 5; d++) cellMap[d] = {};

  state.schedule.forEach(course => {
    const slots = parseTimeSlot(course.time);
    slots.forEach(({ day, periods }) => {
      periods.forEach(p => {
        cellMap[day][p] = course;
      });
    });
  });

  let html = '<thead><tr>';
  html += `<th class="period-col">時段</th>`;
  DAYS.forEach(d => { html += `<th>${d}</th>`; });
  html += '</tr></thead><tbody>';

  PERIODS.forEach(period => {
    html += '<tr>';
    html += `<td class="period-cell">${period.code}<br><span style="font-size:10px;font-weight:400">${period.time}</span></td>`;
    for (let d = 0; d < 5; d++) {
      const c = cellMap[d][period.code];
      if (c) {
        html += `<td style="padding:3px;background:#F0F4FF">
          <div class="schedule-cell-content" style="background:${c.color}" title="${c.name} · ${c.professor}" onclick="showScheduleCourseInfo('${c.courseId}')">
            <div class="cell-name">${c.name}</div>
            <div class="cell-prof">${c.professor}</div>
          </div>
        </td>`;
      } else {
        html += `<td class="free-cell" onclick="highlightFreeSlot(${d}, '${period.code}')"></td>`;
      }
    }
    html += '</tr>';
  });

  html += '</tbody>';
  table.innerHTML = html;
}

function renderGapSuggestions() {
  // Find free slots and suggest courses
  const usedSlots = new Set();
  state.schedule.forEach(c => {
    parseTimeSlot(c.time).forEach(({ day, periods }) => {
      periods.forEach(p => usedSlots.add(`${day}-${p}`));
    });
  });

  // Suggest courses that fit in free slots
  const scheduledIds = new Set(state.schedule.map(c => c.courseId));
  const suggestions = MOCK_COURSES
    .filter(c => !scheduledIds.has(c.id) && c.rating_sweet >= 4)
    .slice(0, 3);

  const panel = document.getElementById('gapSuggestions');
  panel.innerHTML = suggestions.map(c => `
    <div class="gap-course">
      <div class="gap-course-info">
        <div class="gap-course-name">${c.name}</div>
        <div class="gap-course-meta">
          <i class="fas fa-user"></i> ${c.professor} &nbsp;·&nbsp;
          <i class="fas fa-clock"></i> ${c.time} &nbsp;·&nbsp;
          甜度 <strong>${c.rating_sweet || '-'}</strong>
        </div>
      </div>
      <button class="btn-add-gap" onclick="addToScheduleFromModal('${c.id}')">
        <i class="fas fa-plus"></i> 加入
      </button>
    </div>
  `).join('');
}

function addToScheduleFromModal(courseId) {
  const course = MOCK_COURSES.find(c => c.id === courseId);
  if (!course) return;
  if (state.schedule.find(s => s.courseId === courseId)) {
    showToast('warn', `「${course.name}」已在課表中`);
    return;
  }

  // Check prereqs
  const prereq = PREREQ_DATA[courseId];
  const missing = prereq ? checkPrereqs(prereq.prereqs) : [];

  if (missing.length > 0) {
    showPrereqWarning(course, missing, () => {
      doAddToSchedule(course);
    });
  } else {
    doAddToSchedule(course);
  }
}

function doAddToSchedule(course) {
  const color = COURSE_COLORS[state.schedule.length % COURSE_COLORS.length];
  state.schedule.push({ courseId: course.id, name: course.name, professor: course.professor, time: course.time, color });
  showToast('success', `已將「${course.name}」加入課表`);
  if (state.currentView === 'schedule') renderSchedule();
  updateStats();
}

function showScheduleCourseInfo(courseId) {
  openCourseModal(courseId);
}

function highlightFreeSlot(day, period) {
  showToast('info', `${DAYS[day]} 第${period}節 為空堂，可選擇推薦課程填補`);
}

// ============================================================
// PREREQUISITE CHECKING
// ============================================================
function checkPrereqs(prereqs) {
  if (!prereqs || prereqs.length === 0) return [];
  const taken = new Set(state.history.map(h => h.name.trim()));
  return prereqs.filter(p => !taken.has(p));
}

function showPrereqWarning(course, missing, onConfirm) {
  document.getElementById('prereqModalBody').innerHTML = `
    <p>您選擇的課程「<strong>${course.name}</strong>」要求以下先修課程：</p>
    <div class="prereq-items" style="margin-top:12px">
      ${missing.map(m => `<div class="prereq-item missing"><i class="fas fa-times-circle"></i> ${m} — 尚未修習</div>`).join('')}
    </div>
    <p style="margin-top:12px;color:var(--text-secondary)">缺少先備知識可能導致學習困難，建議先完成先修課程。</p>
  `;
  document.getElementById('prereqModal').classList.remove('hidden');

  const confirmFn = () => {
    document.getElementById('prereqModal').classList.add('hidden');
    onConfirm();
    document.getElementById('prereqIgnore').removeEventListener('click', confirmFn);
  };
  document.getElementById('prereqIgnore').addEventListener('click', confirmFn);
}

document.getElementById('prereqCancel').addEventListener('click', () => {
  document.getElementById('prereqModal').classList.add('hidden');
});

// ============================================================
// FIT ANALYSIS
// ============================================================
function initAnalysis() {
  document.getElementById('analyzeBtn').addEventListener('click', () => {
    const q = document.getElementById('analysisSearchInput').value.trim().toLowerCase();
    if (!q) { showToast('warn', '請輸入要分析的課程名稱'); return; }
    const course = MOCK_COURSES.find(c => c.name.toLowerCase().includes(q) || c.professor.toLowerCase().includes(q));
    if (!course) { showToast('error', '找不到符合的課程'); return; }
    analyzeCourse(course);
  });

  document.getElementById('analysisSearchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('analyzeBtn').click();
  });
}

function renderQuickPicks() {
  const picks = MOCK_COURSES.filter(c => c.rating_quality >= 4.5).slice(0, 8);
  document.getElementById('quickPicks').innerHTML = picks.map(c => `
    <button class="quick-pick-btn" onclick="analyzeCourse(MOCK_COURSES.find(x=>x.id==='${c.id}'))">
      <i class="fas fa-search"></i> ${c.name}
    </button>
  `).join('');
}

function analyzeCourse(course) {
  state.currentAnalysisCourse = course;
  state.analysisReviewPage = 1;
  document.getElementById('analysisResult').classList.remove('hidden');
  document.getElementById('analysisSearchInput').value = course.name;

  // Compute fit score
  const fitData = computeFitScore(course);

  // Course header
  document.getElementById('analysisCourseHeader').innerHTML = `
    <div class="analysis-course-name">${course.name}</div>
    <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px">
      <i class="fas fa-user"></i> ${course.professor} &nbsp;·&nbsp;
      <i class="fas fa-sitemap"></i> ${course.department.split('、')[0]} &nbsp;·&nbsp;
      <i class="fas fa-book"></i> ${course.credits} 學分
    </div>
    <div class="analysis-course-tags">
      ${course.tags.map(t => `<span class="tag ${tagColor(t)}">${t}</span>`).join('')}
    </div>
  `;

  // Analysis text
  document.getElementById('analysisText').innerHTML = generateAnalysisText(course, fitData);

  // Rating bars
  document.getElementById('analysisRatings').innerHTML = course.rating_quality ? `
    <div class="rating-row"><span class="rating-name">品質</span><div class="rating-bar"><div class="rating-fill quality" style="width:${(course.rating_quality/5*100).toFixed(0)}%"></div></div><span class="rating-val">${course.rating_quality}</span></div>
    <div class="rating-row"><span class="rating-name">甜度</span><div class="rating-bar"><div class="rating-fill sweet" style="width:${(course.rating_sweet/5*100).toFixed(0)}%"></div></div><span class="rating-val">${course.rating_sweet}</span></div>
    <div class="rating-row"><span class="rating-name">涼度</span><div class="rating-bar"><div class="rating-fill easy" style="width:${(course.rating_easy/5*100).toFixed(0)}%"></div></div><span class="rating-val">${course.rating_easy}</span></div>
    <div class="rating-row"><span class="rating-name">紮實</span><div class="rating-bar"><div class="rating-fill rich" style="width:${(course.rating_rich/5*100).toFixed(0)}%"></div></div><span class="rating-val">${course.rating_rich}</span></div>
  ` : '<div class="no-rating">此課程暫無評分資料</div>';

  // Fit score donut
  renderFitDonut(fitData.total);

  // Fit dimensions
  document.getElementById('fitDimensions').innerHTML = fitData.dimensions.map(d => `
    <div class="fit-dim">
      <div class="fit-dim-header">
        <span class="fit-dim-name">${d.name}</span>
        <span class="fit-dim-val">${d.score}%</span>
      </div>
      <div class="fit-dim-bar">
        <div class="fit-dim-fill" style="width:${d.score}%;background:${d.color}"></div>
      </div>
    </div>
  `).join('');

  // Prereq check
  const prereq = PREREQ_DATA[course.id];
  if (prereq && prereq.prereqs.length > 0) {
    const missing = checkPrereqs(prereq.prereqs);
    const prereqHTML = prereq.prereqs.map(p => {
      const ok = !missing.includes(p);
      return `<div class="prereq-item ${ok ? 'ok' : 'missing'}">
        <i class="fas fa-${ok ? 'check-circle' : 'times-circle'}"></i>
        ${p} — ${ok ? '已修習 ✓' : '尚未修習'}
      </div>`;
    }).join('');

    document.getElementById('prereqContent').innerHTML = `
      ${missing.length === 0
        ? `<div class="prereq-pass"><i class="fas fa-check-circle"></i> 您已具備所有先修條件，可以順利選修此課程！</div>`
        : `<div class="prereq-warn"><i class="fas fa-exclamation-triangle"></i><div>尚缺 ${missing.length} 項先修課程，建議先完成再選修。</div></div>`
      }
      <div class="prereq-items">${prereqHTML}</div>
    `;
  } else {
    document.getElementById('prereqContent').innerHTML = `
      <div class="prereq-pass"><i class="fas fa-check-circle"></i> 此課程無先修限制，任何人都可選修！</div>
    `;
  }

  // Reviews
  renderAnalysisReviews(course);

  // Scroll to result
  document.getElementById('analysisResult').scrollIntoView({ behavior: 'smooth' });
}

function computeFitScore(course) {
  // Base on user history and preferences
  const hasHistory = state.history.length > 0;

  // Credit fit: prefer balanced workload
  const creditFit = Math.min(100, 60 + (course.credits === 3 ? 20 : course.credits === 2 ? 10 : 0));

  // Rating fit
  const ratingFit = course.rating_quality ? Math.round(course.rating_quality / 5 * 100) : 60;

  // Sweet fit: based on user's grade avg
  const hasGoodGrades = state.history.some(h => h.grade === 'A' || h.grade === 'A+');
  const sweetFit = course.rating_sweet
    ? Math.min(100, Math.round(course.rating_sweet / 5 * 80 + (hasGoodGrades ? 20 : 0)))
    : 55;

  // Schedule fit: no conflict
  const scheduleFit = checkScheduleConflict(course) ? 40 : 90;

  const total = Math.round((creditFit * 0.2 + ratingFit * 0.35 + sweetFit * 0.25 + scheduleFit * 0.2));

  return {
    total,
    dimensions: [
      { name: '課程品質', score: ratingFit, color: '#3B82F6' },
      { name: '給分適合度', score: sweetFit, color: '#10B981' },
      { name: '時間相容', score: scheduleFit, color: '#F59E0B' },
      { name: '學分規劃', score: creditFit, color: '#8B5CF6' },
    ]
  };
}

function checkScheduleConflict(course) {
  const newSlots = parseTimeSlot(course.time);
  for (const s of state.schedule) {
    const existSlots = parseTimeSlot(s.time);
    for (const ns of newSlots) {
      for (const es of existSlots) {
        if (ns.day === es.day && ns.periods.some(p => es.periods.includes(p))) return true;
      }
    }
  }
  return false;
}

function generateAnalysisText(course, fitData) {
  const score = fitData.total;
  let opening = '';
  if (score >= 85) opening = `🌟 <strong>強烈推薦！</strong>「${course.name}」與您的修課規劃高度契合。`;
  else if (score >= 70) opening = `✅ <strong>適合選修。</strong>「${course.name}」整體上符合您的需求。`;
  else if (score >= 55) opening = `⚠️ <strong>需要考量。</strong>「${course.name}」有些方面可能需要注意。`;
  else opening = `❌ <strong>謹慎評估。</strong>「${course.name}」可能不是最適合您目前學習狀況的選擇。`;

  const pieces = [];
  if (course.rating_quality >= 4.5) pieces.push('課程品質口碑極佳，學生普遍給予高度評價');
  if (course.rating_sweet >= 4) pieces.push('給分策略友善，認真學習基本上可以拿到不錯的成績');
  if (course.rating_easy <= 2.5) pieces.push('課程難度較高，需要投入較多時間與精力準備');
  if (course.tags.includes('#不點名')) pieces.push('不強制出席，時間安排較有彈性');
  if (course.tags.includes('#期末報告')) pieces.push('以期末報告作為主要評量，適合喜歡自主探索的學生');
  if (course.tags.includes('#扎實')) pieces.push('課程內容紮實充實，修完能力提升顯著');
  if (checkScheduleConflict(course)) pieces.push('⚠️ 此課程時間與您現有課表存在衝突，請注意');

  return `<p>${opening}</p>${pieces.length ? `<ul style="margin-top:8px;padding-left:20px">${pieces.map(p => `<li style="margin-bottom:4px">${p}</li>`).join('')}</ul>` : ''}`;
}

function renderFitDonut(score) {
  const ctx = document.getElementById('fitDonut').getContext('2d');
  if (state.fitDonutChart) state.fitDonutChart.destroy();

  const color = score >= 80 ? '#10B981' : score >= 60 ? '#3B82F6' : score >= 40 ? '#F59E0B' : '#EF4444';

  state.fitDonutChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [score, 100 - score],
        backgroundColor: [color, '#F3F4F6'],
        borderWidth: 0,
        hoverOffset: 4,
      }]
    },
    options: {
      responsive: false,
      cutout: '72%',
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      animation: { duration: 800, easing: 'easeInOutQuart' }
    }
  });

  document.getElementById('donutPct').textContent = `${score}%`;
  document.getElementById('donutPct').style.color = color;
}

function renderAnalysisReviews(course) {
  const perPage = 3;
  const total = course.reviews.length;
  const totalPages = Math.ceil(total / perPage);
  const start = (state.analysisReviewPage - 1) * perPage;
  const pageReviews = course.reviews.slice(start, start + perPage);

  document.getElementById('reviewCount').textContent = `${total} 則評價`;

  const list = document.getElementById('reviewsList');
  if (pageReviews.length === 0) {
    list.innerHTML = '<div class="no-rating">尚無評價資料</div>';
  } else {
    list.innerHTML = pageReviews.map(r => renderReviewItem(r)).join('');
  }

  const pg = document.getElementById('reviewsPagination');
  if (totalPages <= 1) { pg.innerHTML = ''; return; }
  pg.innerHTML = Array.from({ length: totalPages }, (_, i) => `
    <button class="page-btn ${i + 1 === state.analysisReviewPage ? 'active' : ''}" onclick="changeReviewPage(${i + 1})">${i + 1}</button>
  `).join('');
}

function changeReviewPage(p) {
  state.analysisReviewPage = p;
  renderAnalysisReviews(state.currentAnalysisCourse);
}

// ============================================================
// TOAST
// ============================================================
function showToast(type, msg) {
  const icons = { success: 'fa-check-circle', error: 'fa-times-circle', info: 'fa-info-circle', warn: 'fa-exclamation-circle' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i> ${msg}`;
  document.getElementById('toastContainer').appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

// ============================================================
// UTILITY
// ============================================================
function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// Expose globals for inline onclick handlers
window.MOCK_COURSES = MOCK_COURSES;
window.openCourseModal = openCourseModal;
window.addToScheduleFromModal = addToScheduleFromModal;
window.deleteCourse = deleteCourse;
window.changePage = changePage;
window.changeReviewPage = changeReviewPage;
window.analyzeCourse = analyzeCourse;
window.showScheduleCourseInfo = showScheduleCourseInfo;
window.highlightFreeSlot = highlightFreeSlot;
