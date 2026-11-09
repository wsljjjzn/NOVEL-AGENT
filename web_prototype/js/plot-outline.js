// web_prototype/js/plot-outline.js — 剧情脑暴发散、大纲细纲协同与伏笔管理

    // 10. AI 剧情发散提议 (用户决定是否使用)
    // ========================================================
    let currentPlotIdeas = [];

    async function triggerPlotBrainstorm() {
      if (!currentProject) {
        showToast("请先选择小说工程", false);
        return;
      }
      const customPrompt = document.getElementById('ai-plot-custom-prompt').value.trim();
      const loading = document.getElementById('ai-plot-loading');
      const grid = document.getElementById('ai-plot-ideas-grid');
      const btn = document.getElementById('btn-trigger-plot-ai');

      btn.disabled = true;
      loading.classList.remove('hidden');
      grid.innerHTML = '';
      showToast(`剧情架构师正在通过 ${currentModelTier.toUpperCase()} 档脑暴剧情走向...`);

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/ai/brainstorm_plots`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chapter: currentChapterNum,
            instruction: customPrompt,
            model_tier: currentModelTier,
          }),
        });

        loading.classList.add('hidden');
        btn.disabled = false;

        if (res.ok) {
          const data = await res.json();
          currentPlotIdeas = data.ideas || [];
          renderPlotIdeas();
          // 同步给右侧剧情灵感面板
          currentRightPlotIdeas = data.ideas || [];
          renderRightPlotIdeas();
        } else {
          grid.innerHTML = '<div class="col-span-full text-rose-400 text-center py-4">脑暴生成失败，请检查模型服务。</div>';
        }
      } catch (e) {
        console.error("剧情发散异常:", e);
        loading.classList.add('hidden');
        btn.disabled = false;
        grid.innerHTML = '<div class="col-span-full text-rose-400 text-center py-4">网络请求失败，请检查服务。</div>';
      }
    }

    function renderPlotIdeas() {
      const grid = document.getElementById('ai-plot-ideas-grid');
      grid.innerHTML = '';

      if (currentPlotIdeas.length === 0) {
        grid.innerHTML = '<div class="col-span-full text-emerald-600 text-center py-4">未生成有效提议。</div>';
        return;
      }

      currentPlotIdeas.forEach((idea, idx) => {
        const card = document.createElement('div');
        const cardId = `plot-idea-${idx}`;
        card.id = cardId;
        card.className = "bg-[#050c07] border border-emerald-500/30 rounded-xl p-4 flex flex-col justify-between space-y-3 hover:border-emerald-400/60 transition shadow-lg";
        card.innerHTML = `
          <div class="space-y-2">
            <div class="flex items-center justify-between border-b border-emerald-900/80 pb-2">
              <span class="font-bold text-emerald-300 text-xs">${idea.title}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 font-mono">分支 #${idx + 1}</span>
            </div>
            <div class="space-y-1.5 text-[11px] leading-relaxed">
              <p class="text-emerald-300"><span class="text-emerald-500/80 font-semibold">• 核心展开: </span>${idea.premise}</p>
              <p class="text-amber-300/90"><span class="text-emerald-500/80 font-semibold">• 主要冲突: </span>${idea.conflict}</p>
              ${idea.hook ? `<p class="text-emerald-300/90"><span class="text-emerald-500/80 font-semibold">• 伏笔呼应: </span>${idea.hook}</p>` : ''}
            </div>
          </div>
          <div class="flex items-center space-x-2 pt-2 border-t border-emerald-900/80">
            <button onclick="adoptPlotIdeaAsCurrentChapter(${idx})" class="flex-1 py-1.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded font-medium text-xs shadow transition flex items-center justify-center space-x-1" title="采纳并更新为当前章细纲 (绝不污染正文)">
              <span>✓ 采纳为本章大纲</span>
            </button>
            <button onclick="adoptPlotIdea(${idx})" class="px-2.5 py-1.5 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-300 rounded text-xs border border-emerald-800/80 transition" title="追加为新章节大纲 (正文留空)">
              + 新章大纲
            </button>
            <button onclick="dismissPlotIdea('${cardId}')" class="px-2 py-1.5 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-500/80 hover:text-emerald-300 rounded text-xs border border-emerald-800/80 transition" title="忽略">
              忽略
            </button>
          </div>
        `;
        grid.appendChild(card);
      });
    }

    // 采纳想法：作为新章大纲追加（正文留空！绝不污染小说正文）
    async function adoptPlotIdea(index) {
      const idea = currentPlotIdeas[index];
      if (!idea || !currentProject) return;

      const title = idea.title.replace(/^方向\s*[A-Z]\s*·\s*/, '');
      const outlineContent = `【核心剧情】\n${idea.premise}\n\n【冲突与危机】\n${idea.conflict}\n\n【伏笔钩子】\n${idea.hook || ''}`;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            content: "", // 正文留空！
            expected_content: outlineContent,
          }),
        });

        if (res.ok) {
          const ret = await res.json();
          showToast(`已成功采纳该想法，追加为第 ${ret.chapter} 章大纲《${ret.title}》（正文留空）！`);
          // 刷新项目棋盘与大纲
          onSelectProject(currentProject.name);
          // 移除该卡片
          dismissPlotIdea(`plot-idea-${index}`);
        }
      } catch (err) {
        console.error("采纳想法追加大纲失败:", err);
      }
    }

    // 采纳想法为当前章大纲（只改大纲，绝不改正文）
    async function adoptPlotIdeaAsCurrentChapter(index) {
      const idea = currentPlotIdeas[index];
      if (!idea || !currentProject) return;
      const outlineContent = `【核心剧情】\n${idea.premise}\n\n【冲突与危机】\n${idea.conflict}\n\n【伏笔钩子】\n${idea.hook || ''}`;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_content: outlineContent,
            key_foreshadowing: idea.hook ? [idea.hook] : undefined,
          }),
        });

        if (res.ok) {
          showToast(`已成功将该想法采纳为第 ${currentChapterNum} 章大纲！`);
          // 同步右侧大纲文本框
          const textarea = document.getElementById('right-plot-expected-content');
          if (textarea) textarea.value = outlineContent;
          dismissPlotIdea(`plot-idea-${index}`);
        }
      } catch (e) {
        console.error("采纳为当前大纲失败:", e);
      }
    }

    function dismissPlotIdea(cardId) {
      const card = document.getElementById(cardId);
      if (card) {
        card.classList.add('opacity-0', 'transition-opacity');
        setTimeout(() => card.remove(), 200);
      }
    }

    // ========================================================
    // 11. 右侧栏：剧情灵感推演、大纲协同与正文生成引擎
    // ========================================================
    let currentRightPlotIdeas = [];

    // 右侧栏触发剧情发散脑暴
    async function triggerRightPlotBrainstorm() {
      if (!currentProject) {
        showToast("请先选择小说工程", false);
        return;
      }
      const customPrompt = document.getElementById('right-ai-plot-prompt').value.trim();
      const loading = document.getElementById('right-ai-plot-loading');
      const container = document.getElementById('right-plot-ideas-container');
      const btn = document.getElementById('btn-right-plot-brainstorm');

      btn.disabled = true;
      loading.classList.remove('hidden');
      container.innerHTML = '';
      showToast(`剧情架构师正在通过 ${currentModelTier.toUpperCase()} 档在右侧推演剧情走向...`);

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/ai/brainstorm_plots`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chapter: currentChapterNum,
            instruction: customPrompt,
            model_tier: currentModelTier,
          }),
        });

        loading.classList.add('hidden');
        btn.disabled = false;

        if (res.ok) {
          const data = await res.json();
          currentRightPlotIdeas = data.ideas || [];
          renderRightPlotIdeas();
        } else {
          container.innerHTML = '<div class="text-rose-400 text-center py-3 text-xs">剧情推演失败，请检查模型配置。</div>';
        }
      } catch (e) {
        console.error("剧情推演异常:", e);
        loading.classList.add('hidden');
        btn.disabled = false;
        container.innerHTML = '<div class="text-rose-400 text-center py-3 text-xs">网络请求异常，请重试。</div>';
      }
    }

    function renderRightPlotIdeas() {
      const container = document.getElementById('right-plot-ideas-container');
      const countEl = document.getElementById('right-plot-ideas-count');
      if (countEl) countEl.innerText = currentRightPlotIdeas.length;
      if (!container) return;
      container.innerHTML = '';

      if (currentRightPlotIdeas.length === 0) {
        container.innerHTML = '<div class="text-emerald-600 py-3 text-center italic text-xs bg-[#020503]/40 rounded-lg border border-dashed border-emerald-900/80">暂无候选提议，点击上方「⚡ 开始灵感脑暴」为本章构思走向</div>';
        return;
      }

      currentRightPlotIdeas.forEach((idea, idx) => {
        const card = document.createElement('div');
        const cardId = `right-idea-${idx}`;
        card.id = cardId;
        card.className = "bg-[#020503]/80 border border-emerald-500/30 rounded-xl p-3 flex flex-col space-y-2 hover:border-emerald-400/60 transition shadow-sm text-xs";
        card.innerHTML = `
          <div class="flex items-center justify-between border-b border-emerald-900/80 pb-1.5">
            <span class="font-bold text-emerald-300 truncate">${idea.title}</span>
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 font-mono">分支 #${idx + 1}</span>
          </div>
          <div class="space-y-1 text-[11px] leading-relaxed">
            <p class="text-emerald-300"><span class="text-emerald-500/80 font-semibold">• 核心展开: </span>${idea.premise}</p>
            <p class="text-amber-300/90"><span class="text-emerald-500/80 font-semibold">• 主要冲突: </span>${idea.conflict}</p>
            ${idea.hook ? `<p class="text-emerald-300/90"><span class="text-emerald-500/80 font-semibold">• 伏笔呼应: </span>${idea.hook}</p>` : ''}
          </div>
          <div class="flex items-center space-x-1.5 pt-1.5 border-t border-emerald-900/80">
            <button onclick="adoptIdeaAsCurrentChapterOutline(${idx})" class="flex-1 py-1 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded font-medium text-[11px] transition shadow flex items-center justify-center space-x-1" title="采纳并更新为本章细纲 (绝不改动正文)">
              <span>✓ 采纳为本章大纲</span>
            </button>
            <button onclick="adoptIdeaAsNewChapterOutline(${idx})" class="px-2 py-1 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-400/90 rounded text-[11px] transition border border-emerald-800/80" title="追加为新章节大纲 (正文留空)">
              + 新章大纲
            </button>
            <button onclick="dismissRightPlotIdea('${cardId}')" class="px-1.5 py-1 text-emerald-600 hover:text-emerald-400/90 text-[11px] transition" title="忽略">
              ✕
            </button>
          </div>
        `;
        container.appendChild(card);
      });
    }

    function dismissRightPlotIdea(cardId) {
      const card = document.getElementById(cardId);
      if (card) {
        card.classList.add('opacity-0', 'transition-opacity');
        setTimeout(() => card.remove(), 200);
      }
    }

    // 采纳想法为本章大纲（只更新大纲，绝不写入正文！）
    async function adoptIdeaAsCurrentChapterOutline(index) {
      const idea = currentRightPlotIdeas[index];
      if (!idea || !currentProject) return;
      const expectedText = `【核心剧情】\n${idea.premise}\n\n【冲突与危机】\n${idea.conflict}\n\n【伏笔钩子】\n${idea.hook || ''}`;
      
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_content: expectedText,
            key_foreshadowing: idea.hook ? [idea.hook] : undefined,
          }),
        });
        if (res.ok) {
          showToast(`已成功将分支想法采纳为第 ${currentChapterNum} 章大纲！`);
          // 更新右侧文本框
          const textarea = document.getElementById('right-plot-expected-content');
          if (textarea) textarea.value = expectedText;
          // 移除该卡片
          dismissRightPlotIdea(`right-idea-${index}`);
        }
      } catch (e) {
        console.error("更新大纲失败:", e);
        showToast("更新大纲发生错误", false);
      }
    }

    // 采纳想法为新章大纲（追加大纲，正文留空！）
    async function adoptIdeaAsNewChapterOutline(index) {
      const idea = currentRightPlotIdeas[index];
      if (!idea || !currentProject) return;
      const title = idea.title.replace(/^方向\s*[A-Z]\s*·\s*/, '');
      const expectedText = `【核心剧情】\n${idea.premise}\n\n【冲突与危机】\n${idea.conflict}\n\n【伏笔钩子】\n${idea.hook || ''}`;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            content: "", // 正文留空！绝不污染正文！
            expected_content: expectedText,
          }),
        });
        if (res.ok) {
          const ret = await res.json();
          showToast(`已成功追加第 ${ret.chapter} 章大纲《${ret.title}》（正文留空待起草）！`);
          onSelectProject(currentProject.name);
          dismissRightPlotIdea(`right-idea-${index}`);
        }
      } catch (e) {
        console.error("追加大纲失败:", e);
      }
    }

    // 保存当前章节大纲输入框中的内容
    async function saveCurrentChapterOutline() {
      if (!currentProject) return;
      const val = document.getElementById('right-plot-expected-content').value.trim();
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_content: val }),
        });
        if (res.ok) {
          showToast(`第 ${currentChapterNum} 章大纲细纲已保存！`);
          updateStageStepperAndTabs();
        }
      } catch (e) {
        console.error("保存大纲失败:", e);
      }
    }

    // ========================================================
