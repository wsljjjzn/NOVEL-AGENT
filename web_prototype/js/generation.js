// web_prototype/js/generation.js — 正文生成前置自检 (Preflight) 与真实正文起草驱动

    // 12. 正文生成引擎 (大纲细纲 + 角色状态切片 + 伏笔确定性驱动)
    // 【硬规则】：审核单独在后续由用户手动触发，生成完绝不自动跑审稿
    // ========================================================
    function showGenerateModalLoading(isLoading) {
      const modal = document.getElementById('chapter-generate-loading-modal');
      const tierBadge = document.getElementById('gen-modal-tier-badge');
      if (tierBadge) {
        tierBadge.innerText = `${currentModelTier.toUpperCase()} 档`;
      }
      if (modal) {
        if (isLoading) {
          modal.classList.remove('hidden');
        } else {
          modal.classList.add('hidden');
        }
      }
    }

    // 开启正文起草前置自检模态框 (Pre-flight Inspector)
    function openChapterPreflightModal() {
      if (!currentProject) {
        showToast("请先选择小说工程", false);
        return;
      }
      const modal = document.getElementById('chapter-preflight-modal');
      if (!modal) return;

      const r = getChapterReadiness();

      // 设置标题
      const label = document.getElementById('preflight-chapter-label');
      const curTitle = document.getElementById('editor-cur-title');
      const titleText = curTitle ? curTitle.innerText : `第 ${r.chNum} 章`;
      if (label) label.innerText = `${titleText} · 前置自检`;

      // 1. 剧情走向自检卡
      const outlineDot = document.getElementById('preflight-outline-dot');
      const outlineTitle = document.getElementById('preflight-outline-title');
      const outlineSnippet = document.getElementById('preflight-outline-snippet');
      const btnBrainstorm = document.getElementById('btn-preflight-brainstorm');

      if (r.hasOutline) {
        if (outlineDot) outlineDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
        if (outlineTitle) outlineTitle.innerText = '剧情细纲 (✓ 已就绪)';
        if (outlineSnippet) outlineSnippet.innerText = `“${r.outlineText.slice(0, 100)}${r.outlineText.length > 100 ? '...' : ''}”`;
        if (btnBrainstorm) btnBrainstorm.classList.add('hidden');
      } else {
        if (outlineDot) outlineDot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-pulse';
        if (outlineTitle) outlineTitle.innerText = '本章剧情走向 (⚠️ 尚未设定细纲)';
        if (outlineSnippet) outlineSnippet.innerText = '当前章节尚未填写细纲。建议编写或使用 AI 快速脑暴核心情节，确保正文叙事紧凑。';
        if (btnBrainstorm) {
          btnBrainstorm.classList.remove('hidden');
          btnBrainstorm.disabled = false;
          btnBrainstorm.innerHTML = '<span>✨ AI 快速脑暴细纲</span>';
        }
      }

      // 2. 出场角色自检卡
      const charsDot = document.getElementById('preflight-chars-dot');
      const charsTitle = document.getElementById('preflight-chars-title');
      const charsSnippet = document.getElementById('preflight-chars-snippet');

      if (r.hasChars) {
        if (charsDot) charsDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
        if (charsTitle) charsTitle.innerText = `出场角色档案 (✓ ${r.charCount} 人已就绪)`;
        const names = currentCharacters.map(c => c.name).slice(0, 5).join('、');
        if (charsSnippet) charsSnippet.innerText = `已就绪出场人物：${names}${r.charCount > 5 ? ' 等' : ''}。正文创作将遵循其基础人格与心境。`;
      } else {
        if (charsDot) charsDot.className = 'w-2 h-2 rounded-full bg-amber-400';
        if (charsTitle) charsTitle.innerText = '出场角色档案 (⚠️ 尚未录入)';
        if (charsSnippet) charsSnippet.innerText = '当前工程未录入角色。AI 起草正文时将自动泛化生成角色姓名。';
      }

      // 3. 叙事连贯度
      const contDot = document.getElementById('preflight-continuity-dot');
      const contTitle = document.getElementById('preflight-continuity-title');
      const contSnippet = document.getElementById('preflight-continuity-snippet');

      if (r.hasPreceding) {
        if (contDot) contDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
        if (contTitle) contTitle.innerText = '前文梗概衔接 (✓ 连贯)';
        if (contSnippet) contSnippet.innerText = r.chNum === 1 ? '第一章开篇，故事主线起航。' : `前序第 ${r.chNum - 1} 章正文已完成，AI 将提取前章情节点确保转场连贯。`;
      } else {
        if (contDot) contDot.className = 'w-2 h-2 rounded-full bg-amber-400';
        if (contTitle) contTitle.innerText = '前文梗概衔接 (⚡ 检测到前序章节空白)';
        if (contSnippet) contSnippet.innerText = `前序第 ${r.chNum - 1} 章正文为空。AI 正文创作将基于整体大纲推演上下文。`;
      }

      // 4. 覆盖提示
      const overwriteCard = document.getElementById('preflight-card-overwrite');
      const overwriteWords = document.getElementById('preflight-overwrite-words');
      if (overwriteCard) {
        if (r.words > 0) {
          overwriteCard.classList.remove('hidden');
          if (overwriteWords) overwriteWords.innerText = r.words.toLocaleString();
        } else {
          overwriteCard.classList.add('hidden');
        }
      }

      // 设置模型档位徽章
      const tierLabel = document.getElementById('preflight-tier-label');
      if (tierLabel) tierLabel.innerText = currentModelTier === 'pro' ? 'PRO 档 · 深度推理' : 'FLASH 档 · 极速伴写';

      modal.classList.remove('hidden');
    }

    function closeChapterPreflightModal() {
      const modal = document.getElementById('chapter-preflight-modal');
      if (modal) modal.classList.add('hidden');
    }

    async function quickBrainstormForPreflight() {
      const btn = document.getElementById('btn-preflight-brainstorm');
      if (!currentProject || !btn) return;

      btn.disabled = true;
      btn.innerHTML = '<span>⏳ 构思中...</span>';

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/ai/brainstorm_plots`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_tier: 'flash' }),
        });
        if (!res.ok) throw new Error('灵感脑暴未能完成');
        const data = await res.json();
        const topIdea = (data.ideas && data.ideas.length > 0) ? data.ideas[0] : null;
        if (!topIdea) throw new Error('未获取到剧情走向');

        const expectedText = `【核心剧情】\n${topIdea.premise}\n\n【冲突与危机】\n${topIdea.conflict}\n\n【伏笔钩子】\n${topIdea.hook || ''}`;

        // 保存大纲到后台
        await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_content: expectedText,
            key_foreshadowing: topIdea.hook ? [topIdea.hook] : undefined,
          }),
        });

        // 同步更新右侧大纲输入框
        const rPlotExpected = document.getElementById('right-plot-expected-content');
        if (rPlotExpected) rPlotExpected.value = expectedText;

        // 更新模态框卡片为绿色就绪态
        const outlineDot = document.getElementById('preflight-outline-dot');
        const outlineTitle = document.getElementById('preflight-outline-title');
        const outlineSnippet = document.getElementById('preflight-outline-snippet');

        if (outlineDot) outlineDot.className = 'w-2 h-2 rounded-full bg-emerald-400';
        if (outlineTitle) outlineTitle.innerText = `剧情细纲 (✓ 已补齐: ${topIdea.title})`;
        if (outlineSnippet) outlineSnippet.innerText = `“${expectedText.slice(0, 100)}...”`;

        btn.innerHTML = '<span>✓ 已补齐</span>';
        showToast(`已为第 ${currentChapterNum} 章快速生成并补齐大纲细纲！`);
        updateStageStepperAndTabs();
      } catch (err) {
        console.error('快速脑暴大纲失败:', err);
        btn.disabled = false;
        btn.innerHTML = '<span>⚠️ 重试</span>';
        showToast('脑暴大纲失败，请在右侧「💡 剧情」手动输入', false);
      }
    }

    async function confirmExecuteGeneration() {
      closeChapterPreflightModal();
      showGenerateModalLoading(true);

      const targetWordsEl = document.getElementById('preflight-target-words');
      const targetWords = targetWordsEl ? (parseInt(targetWordsEl.value) || 2500) : 2500;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            instructions: "",
            target_words: targetWords,
            model_tier: currentModelTier,
            use_knowledge_base: document.getElementById('knowledge-enabled').checked,
            knowledge_query: document.getElementById('knowledge-query').value,
          }),
        });

        showGenerateModalLoading(false);

        if (res.ok) {
          const ret = await res.json();
          if (ret.knowledge) renderKnowledge(ret.knowledge);
          await loadRealChapter(currentChapterNum);
          updateFooterUsage();
          showToast(`✓ 第 ${currentChapterNum} 章正文已成功起草 (${ret.word_count} 字)！您可直接润色修改，或在右上角手动点击「🔍 审稿」`);
        } else {
          let errMsg = '请检查模型 API 配置';
          try {
            const err = await res.json();
            errMsg = err.detail || errMsg;
          } catch (_) {}
          showToast(`正文生成失败: ${errMsg}`, false);
        }
      } catch (e) {
        console.error("生成正文发生异常:", e);
        showGenerateModalLoading(false);
        showToast("正文生成发生网络异常，请重试", false);
      }
    }

    async function triggerGenerateChapterContent() {
      openChapterPreflightModal();
    }

    function runQuickReviewDemo() {
      startRealChapterReview();
    }

    function selectCharacter(name) {
      selectRealCharacter(name);
    }

    // 全局点击关闭浮动气泡
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#floating-rewrite-menu') && !e.target.closest('#floating-selection-pill') && !e.target.closest('button[onclick*="triggerInlineRewrite"]')) {
        const menu = document.getElementById('floating-rewrite-menu');
        if (menu) menu.classList.add('hidden');
      }
    });

    // 快捷键支持：Cmd+K / Ctrl+K 重构，Cmd+S 保存，Cmd+, 打开设置，Esc 关闭模态
    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        openRewriteMenu();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        saveCurrentChapterToBackend();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault();
        const modal = document.getElementById('settings-modal');
        if (modal.classList.contains('hidden')) {
          openSettingsModal();
        } else {
          closeSettingsModal();
        }
      }
      if (e.key === 'Escape') {
        closeKnowledgeHubModal();
        closeSettingsModal();
        closeCreateProjectModal();
        closeTokenSavingModal();
        closeChapterPreflightModal();
        const rewriteMenu = document.getElementById('floating-rewrite-menu');
        if (rewriteMenu) rewriteMenu.classList.add('hidden');
      }
    });

    // ==========================================
    // 真实后端 API 联动引擎 (生产级全真实数据驱动)
    // ==========================================
    function renderKnowledge(data) {
      const box = document.getElementById('knowledge-preview');
      if (!box) return;
      if (data.sources?.length) {
        box.textContent = data.sources.map(s => `[来源 ${s.id} | ${s.source.split('/').pop()}]\n${s.text}`).join('\n\n');
        box.classList.remove('text-[var(--ink-muted)]');
        box.classList.add('text-[var(--ink)]');
      } else {
        const warn = data.warning || '未找到匹配知识';
        box.textContent = `${warn}。\n\n💡 提示：当前已入库《星际旅行与深空生存硬核科幻知识手册》（涵盖：太空、氧气、辐射、曲率、休眠等设定）；\n您可输入上述关键词进行检索预览，或在终端运行「uv run na kb learn <文件>」导入您自己的设定集文档。`;
        box.classList.add('text-[var(--ink-muted)]');
      }
    }

    async function previewKnowledge(e) {
      if (!currentProject || chapterLoading) {
        showToast("请等待章节加载完成", false);
        return;
      }
      const project = currentProject.name, chapter = currentChapterNum;
      const btn = (e && e.currentTarget) || document.querySelector('button[onclick*="previewKnowledge"]');
      const origText = btn ? btn.innerHTML : '';
      if (btn) btn.innerHTML = '<span>⏳ 检索中...</span>';
      try {
        const response = await fetch(`${API_BASE}/projects/${encodeURIComponent(project)}/chapters/${chapter}/knowledge/preview`, {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({query: document.getElementById('knowledge-query').value}),
        });
        const data = await response.json();
        if (currentProject?.name !== project || currentChapterNum !== chapter) return;
        if (!response.ok) throw new Error(data.detail || '检索失败');
        renderKnowledge(data);
        showToast(data.sources?.length ? `已检索到 ${data.sources.length} 条知识参考` : '未找到匹配知识');
      } catch (error) { 
        showToast(error.message, false); 
      } finally {
        if (btn) btn.innerHTML = origText;
      }
    }

    let currentProject = null;
    let evolutionProposal = null;
    let editorTarget = null;
    let chapterLoadVersion = 0;
    let projectLoadVersion = 0;
    let chapterLoading = false;
    let currentChapterNum = 1;
    let currentModelTier = "flash";

    // 档位切换 (满足需求: 自由切换模型档位)
    function onModelTierChange(tier) {
      currentModelTier = tier;
      showToast(`已切换模型档位: ${tier === 'pro' ? 'DeepSeek-V4 Pro (深度推理)' : 'DeepSeek-V4 Flash (极速伴写)'}`);
    }

    // ========================================================
