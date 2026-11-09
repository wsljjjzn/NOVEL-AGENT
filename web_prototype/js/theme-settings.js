// web_prototype/js/theme-settings.js — 外观主题、个性化偏好、自检与 API Key 设置

    // Cursor Studio 主题外观与暗色/亮色切换逻辑 (全方位适配)
    // ========================================================
    function initThemeMode() {
      const saved = localStorage.getItem('novel_cursor_theme_mode') || 'dark';
      setThemeMode(saved, false);
    }

    function setThemeMode(mode, showNotice = true) {
      localStorage.setItem('novel_cursor_theme_mode', mode);
      const htmlEl = document.documentElement;
      const bodyEl = document.body;

      let effectiveDark = true;
      if (mode === 'light') {
        effectiveDark = false;
      } else if (mode === 'dark') {
        effectiveDark = true;
      } else if (mode === 'system') {
        effectiveDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      }

      if (effectiveDark) {
        htmlEl.classList.add('dark');
        bodyEl.classList.add('dark');
      } else {
        htmlEl.classList.remove('dark');
        bodyEl.classList.remove('dark');
      }

      updateThemeUiIndicators(mode, effectiveDark);

      if (showNotice && typeof showToast === 'function') {
        const modeDesc = mode === 'light' ? '☀️ 亮色模式' : (mode === 'dark' ? '🌙 暗色模式' : '💻 跟随系统');
        showToast(`已切换外观: ${modeDesc}`);
      }
    }

    function toggleThemeMode() {
      const isDark = document.documentElement.classList.contains('dark');
      const icon = document.getElementById('theme-icon-slot');
      if (icon) {
        icon.style.transition = 'transform 0.4s ease';
        icon.style.transform = 'rotate(360deg)';
        setTimeout(() => { icon.style.transform = ''; }, 400);
      }
      setThemeMode(isDark ? 'light' : 'dark', true);
    }

    function updateThemeUiIndicators(mode, effectiveDark) {
      const iconSlot = document.getElementById('theme-icon-slot');
      const textSlot = document.getElementById('theme-text-slot');
      if (iconSlot && textSlot) {
        if (effectiveDark) {
          iconSlot.innerText = '🌙';
          textSlot.innerText = '暗色';
        } else {
          iconSlot.innerText = '☀️';
          textSlot.innerText = '亮色';
        }
      }

      const tag = document.getElementById('current-palette-tag');
      if (tag) {
        tag.innerText = `CURRENT: ${mode.toUpperCase()}`;
      }

      // Update modal buttons
      ['light', 'dark', 'system'].forEach(m => {
        const btn = document.getElementById(`btn-theme-${m}`);
        if (!btn) return;
        if (m === mode) {
          btn.className = "p-3.5 rounded-lg border-2 border-[#5e6ad2] bg-[var(--surface-card)] text-[var(--ink)] flex flex-col items-center space-y-1.5 transition text-xs font-bold cursor-pointer shadow-md";
        } else {
          btn.className = "p-3.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-card)] text-[var(--ink-secondary)] flex flex-col items-center space-y-1.5 transition text-xs font-medium cursor-pointer hover:border-[#5e6ad2]";
        }
      });
    }

    // 移动端响应式侧栏抽屉切换
    function toggleMobileSidebar(side) {
      if (side === 'left') {
        const left = document.getElementById('sidebar-left');
        const right = document.getElementById('sidebar-right');
        if (right) right.classList.remove('open');
        if (left) left.classList.toggle('open');
      } else if (side === 'right') {
        const left = document.getElementById('sidebar-left');
        const right = document.getElementById('sidebar-right');
        if (left) left.classList.remove('open');
        if (right) right.classList.toggle('open');
      }
    }

    function closeMobileSidebars() {
      const left = document.getElementById('sidebar-left');
      const right = document.getElementById('sidebar-right');
      if (left) left.classList.remove('open');
      if (right) right.classList.remove('open');
    }

    // ========================================================
    // 0. 系统偏好设置体系 (写作排版 / 终端视效 / 备份导出 / 模型API)
    // ========================================================
    let isApiKeyVisible = false;

    let novelSettings = {
      fontSize: '17px',
      lineHeight: '1.85',
      fontFamily: 'font-serif',
      typewriterScroll: false,
      autoSaveInterval: '30',
      wordCountMetric: 'pure_chinese',
      crtEffect: true,
      themePalette: 'emerald',
      splashMode: 'full',
      snapshotRetention: '30',
    };

    function loadNovelSettings() {
      initThemeMode();
      try {
        const raw = localStorage.getItem('novel_ide_user_settings');
        if (raw) {
          novelSettings = Object.assign({}, novelSettings, JSON.parse(raw));
        }
      } catch (e) {
        console.error("加载设置失败:", e);
      }
      applyAllSettings();
      syncSettingsFormInputs();
    }

    function saveNovelSettings() {
      try {
        localStorage.setItem('novel_ide_user_settings', JSON.stringify(novelSettings));
      } catch (e) {
        console.error("持久化设置失败:", e);
      }
    }

    async function updateFooterUsage() {
      try {
        const res = await fetch(`${API_BASE}/system/usage`);
        if (!res.ok) return;
        const data = await res.json();
        const labelEl = document.getElementById('footer-cost-label');
        const containerEl = document.getElementById('footer-token-stats');
        if (!labelEl) return;

        if (!data.calls || data.calls === 0) {
          labelEl.textContent = '⚡ 今日消耗: ￥0.00';
          if (containerEl) {
            containerEl.title = '今日暂无模型调用，Token 消耗为 0（点击查看详情）';
            containerEl.className = 'text-[var(--ink-muted)] hover:text-[var(--ink)] flex items-center space-x-1 cursor-pointer transition-colors';
          }
        } else {
          const costText = data.cost_cny < 0.0001 ? '<￥0.0001' : `￥${data.cost_cny.toFixed(4)}`;
          const tokensText = data.total_tokens ? `${data.total_tokens.toLocaleString()} tokens` : '';
          labelEl.textContent = `⚡ 今日消耗: ${costText} (${tokensText || `${data.calls}次`})`;
          if (containerEl) {
            containerEl.title = `会话累计调用: ${data.calls} 次 · 输入: ${data.prompt_tokens.toLocaleString()} · 输出: ${data.completion_tokens.toLocaleString()} · 预估费用: ￥${data.cost_cny.toFixed(4)}`;
            containerEl.className = 'text-[#5e6ad2] hover:text-[#717ff5] font-semibold flex items-center space-x-1 cursor-pointer transition-colors';
          }
        }
      } catch (e) {
        // 静默失败
      }
    }

    function showUsageDetailToast() {
      const containerEl = document.getElementById('footer-token-stats');
      if (containerEl && containerEl.title) {
        showToast(containerEl.title);
      } else {
        showToast('⚡ 今日暂无模型调用，Token 消耗为 0');
      }
    }

    function updateNovelSetting(key, val) {
      novelSettings[key] = val;
      saveNovelSettings();
      applyAllSettings();
      if (typeof showToast === 'function') {
        showToast(`已应用偏好设置: ${key}`);
      }
    }

    function syncSettingsFormInputs() {
      const fs = document.getElementById('setting-font-size');
      if (fs) fs.value = novelSettings.fontSize || '17px';
      const lh = document.getElementById('setting-line-height');
      if (lh) lh.value = novelSettings.lineHeight || '1.85';
      const ff = document.getElementById('setting-font-family');
      if (ff) ff.value = novelSettings.fontFamily || 'font-serif';
      const tw = document.getElementById('setting-typewriter-scroll');
      if (tw) tw.checked = !!novelSettings.typewriterScroll;
      const as = document.getElementById('setting-autosave-interval');
      if (as) as.value = novelSettings.autoSaveInterval || '30';
      const wc = document.getElementById('setting-wordcount-metric');
      if (wc) wc.value = novelSettings.wordCountMetric || 'pure_chinese';
      const crt = document.getElementById('setting-crt-effect');
      if (crt) crt.checked = novelSettings.crtEffect !== false;

      const radios = document.getElementsByName('splashMode');
      radios.forEach(r => {
        if (r.value === (novelSettings.splashMode || 'full')) r.checked = true;
      });

      updateThemePaletteButtons();
    }

    function applyAllSettings() {
      applyEditorTypography();
      applyCrtAndPaletteTheme();
    }

    function applyEditorTypography() {
      const container = document.getElementById('editor-container');
      if (!container) return;
      container.style.fontSize = novelSettings.fontSize || '17px';
      container.style.lineHeight = novelSettings.lineHeight || '1.85';

      container.classList.remove('font-serif', 'font-sans', 'font-mono');
      if (novelSettings.fontFamily === 'font-sans') {
        container.classList.add('font-sans');
        container.style.fontFamily = 'system-ui, -apple-system, PingFang SC, Microsoft YaHei, sans-serif';
      } else if (novelSettings.fontFamily === 'font-mono') {
        container.classList.add('font-mono');
        container.style.fontFamily = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';
      } else if (novelSettings.fontFamily === 'font-kaiti') {
        container.style.fontFamily = 'STKaiti, KaiTi, 楷体, serif';
      } else {
        container.classList.add('font-serif');
        container.style.fontFamily = 'Songti SC, STSong, SimSun, serif';
      }
    }

    function setThemePalette(paletteName) {
      novelSettings.themePalette = paletteName;
      saveNovelSettings();
      applyCrtAndPaletteTheme();
      updateThemePaletteButtons();
      if (typeof showToast === 'function') {
        showToast(`已切换调色板: ${paletteName.toUpperCase()}`);
      }
    }

    function updateThemePaletteButtons() {
      const palettes = ['emerald', 'amber', 'cyan', 'monochrome'];
      const cur = novelSettings.themePalette || 'emerald';
      palettes.forEach(p => {
        const btn = document.getElementById(`btn-theme-${p}`);
        if (!btn) return;
        if (p === cur) {
          btn.className = "p-3 rounded-lg border-2 border-emerald-500 bg-[#050c07] text-emerald-300 flex flex-col items-center space-y-1 transition text-xs font-bold shadow";
        } else {
          btn.className = "p-3 rounded-lg border border-emerald-900/60 hover:border-emerald-700 bg-[#020503] text-emerald-500/80 flex flex-col items-center space-y-1 transition text-xs font-medium cursor-pointer";
        }
      });
      const tag = document.getElementById('current-palette-tag');
      if (tag) tag.innerText = `CURRENT: ${cur.toUpperCase()}`;
    }

    function applyCrtAndPaletteTheme() {
      document.body.classList.remove('theme-amber', 'theme-cyan', 'theme-monochrome');
      const cur = novelSettings.themePalette || 'emerald';
      if (cur === 'amber') document.body.classList.add('theme-amber');
      else if (cur === 'cyan') document.body.classList.add('theme-cyan');
      else if (cur === 'monochrome') document.body.classList.add('theme-monochrome');

      if (novelSettings.crtEffect === false) {
        document.body.classList.add('no-crt');
      } else {
        document.body.classList.remove('no-crt');
      }
    }

    function handleTypewriterScroll() {
      if (!novelSettings.typewriterScroll) return;
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      const container = document.getElementById('editor-container');
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const targetY = containerRect.top + containerRect.height / 2;
      const delta = rect.top - targetY;
      if (Math.abs(delta) > 25) {
        container.scrollTop += delta;
      }
    }

    // 导出文件辅助下载器
    function downloadFile(filename, content, mime) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    // 导出当前章节 TXT
    function exportCurrentChapterTxt() {
      if (!currentChapterData) return (typeof showToast === 'function' ? showToast("当前未打开章节") : alert("当前未打开章节"));
      const title = currentChapterData.title || `第${currentChapterNum}章`;
      const content = currentChapterData.content || '';
      const text = `${title}\n\n${content}\n`;
      downloadFile(`${title}.txt`, text, 'text/plain;charset=utf-8');
      if (typeof showToast === 'function') showToast(`已成功导出《${title}.txt》`);
    }

    // 导出当前章节 Markdown
    function exportCurrentChapterMarkdown() {
      if (!currentChapterData) return (typeof showToast === 'function' ? showToast("当前未打开章节") : alert("当前未打开章节"));
      const title = currentChapterData.title || `第${currentChapterNum}章`;
      const content = currentChapterData.content || '';
      const md = `# ${title}\n\n${content}\n`;
      downloadFile(`${title}.md`, md, 'text/markdown;charset=utf-8');
      if (typeof showToast === 'function') showToast(`已成功导出《${title}.md》`);
    }

    // 导出全书 TXT
    function exportFullNovelTxt() {
      if (!currentProject) return (typeof showToast === 'function' ? showToast("未载入小说工程") : alert("未载入小说工程"));
      const title = currentProject.title || currentProject.name || '未命名作品';
      let full = `《${title}》\n作品类型: ${currentProject.genre || '未分类'}\n创作简介: ${currentProject.description || ''}\n\n` +
                 `========================================\n\n`;
      if (currentProject.chapters && currentProject.chapters.length > 0) {
        currentProject.chapters.forEach(c => {
          full += `第${c.chapter}章 ${c.title}\n\n${c.content || '（暂无正文）'}\n\n----------------------------------------\n\n`;
        });
      }
      downloadFile(`${title}_全本正文.txt`, full, 'text/plain;charset=utf-8');
      if (typeof showToast === 'function') showToast(`已成功导出全书《${title}_全本正文.txt》`);
    }

    // 导出全案 Markdown
    function exportFullNovelMarkdown() {
      if (!currentProject) return (typeof showToast === 'function' ? showToast("未载入小说工程") : alert("未载入小说工程"));
      const title = currentProject.title || currentProject.name || '未命名作品';
      let md = `# 《${title}》\n\n` +
               `> 作品类型: ${currentProject.genre || '未分类'} | 总字数: ${Number(currentProject.total_words || 0).toLocaleString()} 字\n\n` +
               `### 故事核心动力与世界观\n${currentProject.description || ''}\n\n---\n\n` +
               `## 目录大纲\n\n`;
      if (currentProject.outline) {
        currentProject.outline.forEach(o => {
          md += `- **第${o.chapter}章 ${o.title}**: ${o.expected_content || ''}\n`;
        });
      }
      md += `\n---\n\n## 正文合集\n\n`;
      if (currentProject.chapters) {
        currentProject.chapters.forEach(c => {
          md += `### 第${c.chapter}章 ${c.title}\n\n${c.content || ''}\n\n`;
        });
      }
      downloadFile(`${title}_创作全案.md`, md, 'text/markdown;charset=utf-8');
      if (typeof showToast === 'function') showToast(`已成功导出全案《${title}_创作全案.md》`);
    }

    // 导出工程 JSON 备份
    function exportProjectJsonBackup() {
      if (!currentProject) return (typeof showToast === 'function' ? showToast("未载入小说工程") : alert("未载入小说工程"));
      const title = currentProject.title || currentProject.name || 'novel_backup';
      const backupData = {
        exported_at: new Date().toISOString(),
        project: currentProject,
        characters: currentCharactersList || [],
        settings: novelSettings
      };
      downloadFile(`${title}_backup.json`, JSON.stringify(backupData, null, 2), 'application/json');
      if (typeof showToast === 'function') showToast(`已成功导出工程备份《${title}_backup.json》`);
    }

        // ========================================================
