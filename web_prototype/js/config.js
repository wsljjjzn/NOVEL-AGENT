// web_prototype/js/config.js — 全局环境配置与核心共享状态声明

// 全局统一 API 基地址：在 HTTP 托管下使用相对路径 /api，在本地静态 file:// 下回退到 8000 端口
const API_BASE = (window.location.protocol && window.location.protocol.startsWith('http'))
  ? '/api'
  : 'http://127.0.0.1:8000/api';

// 全局响应式状态
let currentProject = null;
let currentChapterNum = 1;
let currentChapterData = null;
let currentModelTier = 'pro';
let currentCharacters = [];
let curActiveChar = null;
let curActiveSlice = null;
let curActiveSliceChapter = 1;
let currentChapterSliceNum = 1;
let curSliceMode = 'active';
let chapterLoadVersion = 0;
let chapterLoading = false;
let evolutionProposal = null;
let editorTarget = { project: null, chapter: 1 };
let currentTopMode = 'craft';
let currentCraftPerspective = 'workbench';
let novelDnaEngine = null;
let splashSkipRequested = false;
let traitUpdateTimer = null;
let curEvolutionSuggestions = null;
let globalToastTimer = null;

    function renderAiDotsLoader(size = 'md', label = '') {
      const isLg = size === 'lg';
      const isSm = size === 'sm';
      const gridClass = isLg ? 'ai-square-grid-lg' : (isSm ? 'ai-square-grid-sm' : 'ai-square-grid');
      const padClass = isLg ? 'py-3 px-6' : (isSm ? 'py-1.5 px-3' : 'py-2 px-4');
      const textClass = isLg ? 'text-sm font-semibold text-[#60a5fa]' : (isSm ? 'text-[11px] text-[var(--ink-secondary)]' : 'text-xs text-[var(--ink)] font-medium');
      return `
        <div class="ai-square-loader ${padClass}">
          <div class="${gridClass}">
            <span class="ai-sq-dot ai-dot-blue"></span>
            <span class="ai-sq-dot ai-dot-cyan"></span>
            <span class="ai-sq-dot ai-dot-green"></span>
            <span class="ai-sq-dot ai-dot-white"></span>
          </div>
          ${label ? `<span class="ml-3 ${textClass}">${label}</span>` : ''}
        </div>
      `;
    }

    // ========================================================
