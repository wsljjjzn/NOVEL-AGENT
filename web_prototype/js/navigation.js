// web_prototype/js/navigation.js — 双层级架构导航（工作台/巡航舱）、侧栏 Tab 与阶段步进器

    // 2. 双层级架构导航系统
    // Level 1: 顶层舱体切换 (工匠工作台 vs 自动巡航舱)
    // Level 2: 工匠工作台专属子视角 (企划构思 / 剧情棋盘 / 沉浸写作)
    let currentTopMode = 'craft'; // 'craft' | 'autopilot'
    let currentCraftPerspective = 'writing'; // 'planning' | 'storyboard' | 'writing'

    function switchTopMode(mode) {
      currentTopMode = mode;
      closeMobileSidebars();

      const btnCraft = document.getElementById('btn-mode-craft');
      const btnAuto = document.getElementById('btn-mode-autopilot');
      const craftSubnav = document.getElementById('craft-subnav-container');
      const autoBadge = document.getElementById('autopilot-subnav-badge');
      const autoView = document.getElementById('perspective-autopilot');

      if (mode === 'craft') {
        // 激活工匠工作台
        if (btnCraft) btnCraft.className = "tactile-interactive px-3 py-1 text-xs rounded-md font-semibold bg-[var(--surface-card)] text-[var(--ink)] shadow-sm transition-all cursor-pointer flex items-center space-x-1.5";
        if (btnAuto) btnAuto.className = "tactile-interactive px-3 py-1 text-xs rounded-md font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-all cursor-pointer flex items-center space-x-1.5";
        if (craftSubnav) craftSubnav.classList.remove('hidden');
        if (autoBadge) {
          autoBadge.classList.add('hidden');
          autoBadge.classList.remove('flex');
        }
        if (autoView) autoView.classList.add('hidden');

        // 恢复工匠台当前激活的子视角
        switchCraftPerspective(currentCraftPerspective);
      } else {
        // 激活自动巡航舱
        if (btnCraft) btnCraft.className = "tactile-interactive px-3 py-1 text-xs rounded-md font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-all cursor-pointer flex items-center space-x-1.5";
        if (btnAuto) btnAuto.className = "tactile-interactive px-3 py-1 text-xs rounded-md font-semibold bg-[var(--surface-card)] text-[var(--ink)] shadow-sm transition-all cursor-pointer flex items-center space-x-1.5";
        if (craftSubnav) craftSubnav.classList.add('hidden');
        if (autoBadge) {
          autoBadge.classList.remove('hidden');
          autoBadge.classList.add('flex');
        }

        // 隐藏工匠台下所有子视角
        ['planning', 'storyboard', 'writing'].forEach(p => {
          const el = document.getElementById(`perspective-${p}`);
          if (el) el.classList.add('hidden');
        });

        // 激活巡航舱主容器
        if (autoView) autoView.classList.remove('hidden');
        if (currentProject && typeof refreshAutopilotView === 'function') {
          refreshAutopilotView(currentProject);
        }
      }
    }

    function switchCraftPerspective(p) {
      currentCraftPerspective = p;
      ['planning', 'storyboard', 'writing'].forEach(m => {
        const el = document.getElementById(`perspective-${m}`);
        if (el) el.classList.add('hidden');
        const btn = document.getElementById(`btn-craft-${m}`);
        if (btn) {
          btn.className = "tactile-interactive px-2.5 py-0.5 text-xs rounded-md font-medium text-[var(--ink-muted)] hover:text-[var(--ink)] transition-all cursor-pointer";
        }
      });
      const activeEl = document.getElementById(`perspective-${p}`);
      if (activeEl) activeEl.classList.remove('hidden');
      const activeBtn = document.getElementById(`btn-craft-${p}`);
      if (activeBtn) {
        activeBtn.className = "tactile-interactive px-2.5 py-0.5 text-xs rounded-md font-semibold bg-[var(--surface-card)] text-[var(--ink)] shadow-sm transition-all cursor-pointer";
      }

      // 切换视角时若已有工程数据，实时刷新对应视图
      if (currentProject) {
        if (p === 'planning' && typeof refreshPlanningView === 'function') {
          refreshPlanningView(currentProject);
        } else if (p === 'storyboard' && typeof refreshStoryboardView === 'function') {
          refreshStoryboardView(currentProject);
        }
      }
    }

    // 视角切换兼容入口（向后兼容所有既有代码调用）
    function switchPerspective(mode) {
      if (mode === 'autopilot') {
        switchTopMode('autopilot');
      } else {
        switchTopMode('craft');
        switchCraftPerspective(mode);
      }
    }

    // 3. 创作主线航标与前置依赖状态感知引擎
    function focusEditorBody() {
      const body = document.getElementById('editor-body');
      if (body) {
        body.focus();
        body.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        const container = document.getElementById('editor-container');
        if (container) container.scrollIntoView({ behavior: 'smooth' });
      }
    }

    // 纯净正文提取器：自动过滤 UI 占位卡片、剥离引导占位文字，支持真实打字内容捕获
    function getCleanEditorText() {
      const body = document.getElementById('editor-body');
      if (!body) return '';

      const paras = Array.from(body.querySelectorAll('p'))
        .filter(p => (typeof p.closest === 'function') ? !p.closest('[contenteditable="false"]') : true)
        .map(p => {
          let t = (p.innerText || '').trim();
          t = t.replace(/^（点击此处自由输入[，,][^）]*）/g, '')
               .replace(/（点击此处自由输入[，,][^）]*）/g, '')
               .replace(/^（本章暂无正文内容[，,][^）]*）/g, '')
               .trim();
          return t;
        })
        .filter(t => t.length > 0);

      if (paras.length > 0) {
        return paras.join('\n\n');
      }

      // 兜底：如果用户直接在 body 中输入没有嵌套 p 标签
      const clone = body.cloneNode(true);
      if (typeof clone.querySelectorAll === 'function') {
        clone.querySelectorAll('[contenteditable="false"]').forEach(el => el.remove());
      }
      let raw = (clone.innerText || '').trim();
      raw = raw.replace(/^（点击此处自由输入[，,][^）]*）/g, '')
               .replace(/（点击此处自由输入[，,][^）]*）/g, '')
               .replace(/^（本章暂无正文内容[，,][^）]*）/g, '')
               .trim();
      return raw;
    }

    function getChapterReadiness(data = null) {
      const chNum = currentChapterNum || 1;
      const text = getCleanEditorText();
      const words = text ? text.length : (data ? (Number(data.word_count) || 0) : 0);
      const hasContent = words > 0; // 只要有真实字符输入，即认定正文起步就绪

      const rPlotExpected = document.getElementById('right-plot-expected-content');
      const outlineText = (data && data.outline && data.outline.expected_content)
        ? data.outline.expected_content.trim()
        : (rPlotExpected ? rPlotExpected.value.trim() : '');
      const hasOutline = outlineText.length > 0;

      const hasChars = Boolean(currentCharacters && currentCharacters.length > 0);
      const charCount = currentCharacters ? currentCharacters.length : 0;

      // 前序连贯性：第 1 章天然连贯；第 N 章检查 N-1 章是否存在且字数 > 0
      let hasPreceding = true;
      if (chNum > 1 && currentProject && currentProject.chapters) {
        const prev = currentProject.chapters.find(c => Number(c.chapter) === chNum - 1);
        hasPreceding = Boolean(prev && (Number(prev.word_count) || 0) > 0);
      }

      return {
        chNum,
        words,
        hasContent,
        hasOutline,
        outlineText,
        hasChars,
        charCount,
        hasPreceding,
      };
    }

    function updateStageStepperAndTabs(data = null) {
      const r = getChapterReadiness(data);

      // 1. 更新顶栏航标 4 个阶段圆点与文字
      const dotOutline = document.getElementById('step-dot-outline');
      const dotChar = document.getElementById('step-dot-char');
      const dotBody = document.getElementById('step-dot-body');
      const dotReview = document.getElementById('step-dot-review');

      if (dotOutline) dotOutline.className = r.hasOutline ? 'w-2 h-2 rounded-full bg-emerald-400 transition-colors' : 'w-2 h-2 rounded-full bg-amber-400 transition-colors';
      if (dotChar) dotChar.className = r.hasChars ? 'w-2 h-2 rounded-full bg-emerald-400 transition-colors' : 'w-2 h-2 rounded-full bg-slate-500 transition-colors';
      if (dotBody) dotBody.className = r.hasContent ? 'w-2 h-2 rounded-full bg-emerald-400 transition-colors' : 'w-2 h-2 rounded-full bg-slate-500 transition-colors';
      if (dotReview) dotReview.className = r.hasContent ? 'w-2 h-2 rounded-full bg-emerald-400 transition-colors' : 'w-2 h-2 rounded-full bg-slate-500 transition-colors';

      // 2. 更新右侧侧边栏 Tab 状态小圆点
      const tabDotChar = document.getElementById('tab-dot-character');
      const tabDotPlot = document.getElementById('tab-dot-plot');
      const tabDotRev = document.getElementById('tab-dot-review');

      if (tabDotChar) tabDotChar.className = r.hasChars ? 'w-1.5 h-1.5 rounded-full bg-emerald-400 transition-colors' : 'w-1.5 h-1.5 rounded-full bg-slate-500 transition-colors';
      if (tabDotPlot) tabDotPlot.className = r.hasOutline ? 'w-1.5 h-1.5 rounded-full bg-emerald-400 transition-colors' : 'w-1.5 h-1.5 rounded-full bg-amber-400 transition-colors';
      if (tabDotRev) tabDotRev.className = r.hasContent ? 'w-1.5 h-1.5 rounded-full bg-emerald-400 transition-colors' : 'w-1.5 h-1.5 rounded-full bg-slate-500 transition-colors';

      // 3. 更新前序断层警示条
      const banner = document.getElementById('continuity-warning-banner');
      const bannerText = document.getElementById('continuity-warning-text');
      if (banner && bannerText) {
        if (!r.hasPreceding && r.chNum > 1) {
          bannerText.innerText = `检测到前序第 ${r.chNum - 1} 章正文尚未完成，AI 正文创作将基于故事大纲推演上下文。建议先完善前章以获得最佳叙事连贯度。`;
          banner.classList.remove('hidden');
        } else {
          banner.classList.add('hidden');
        }
      }

      // 4. 更新审稿面板中的空态引导
      updateReviewPanelReadiness(r.hasContent, r.words);
    }

    function updateReviewPanelReadiness(hasContent, words = 0) {
      const guidance = document.getElementById('review-empty-guidance');
      const scopeDesc = document.getElementById('review-scope-desc');
      const btn = document.getElementById('btn-start-review');
      const btnText = document.getElementById('btn-start-review-text');
      const title = document.getElementById('review-initial-status-title');

      if (!guidance || !btn) return;

      if (hasContent) {
        guidance.classList.add('hidden');
        if (scopeDesc) scopeDesc.classList.remove('hidden');
        if (title) title.innerText = `当前章节正文已就绪 (${words.toLocaleString()} 字)`;
        btn.classList.remove('opacity-60');
        if (btnText) btnText.innerText = '开始本章六维智能审稿';
      } else {
        guidance.classList.remove('hidden');
        if (scopeDesc) scopeDesc.classList.add('hidden');
        if (title) title.innerText = '当前章节正文尚在酝酿中';
        btn.classList.add('opacity-60');
        if (btnText) btnText.innerText = '开始六维审稿 (正文就绪后开启)';
      }
    }

    // 右侧 Tab 切换 (角色、剧情灵感、审稿)
    function switchRightTab(tab) {
      ['character', 'plot', 'review'].forEach(t => {
        const panel = document.getElementById(`right-panel-${t}`);
        const btn = document.getElementById(`tab-btn-${t}`);
        if (panel) panel.classList.add('hidden');
        if (btn) {
          btn.className = "flex-1 py-1 text-xs font-medium rounded text-[var(--ink-muted)] hover:text-[var(--ink)] flex items-center justify-center space-x-1.5 transition cursor-pointer";
        }
      });
      const activePanel = document.getElementById(`right-panel-${tab}`);
      const activeBtn = document.getElementById(`tab-btn-${tab}`);
      if (activePanel) activePanel.classList.remove('hidden');
      if (activeBtn) {
        activeBtn.className = "flex-1 py-1 text-xs font-semibold rounded bg-[var(--surface-card)] text-[var(--ink)] border border-[var(--hairline)] shadow-sm flex items-center justify-center space-x-1.5 transition cursor-pointer";
      }
    }

    // 4. 手动拖动特质 Slider (满足需求 1: 作者自由调参)
    function onManualTraitChange(trait, val) {
      const label = document.getElementById(`label-trait-${trait}`);
      if (label) {
        label.innerText = `${val} / 10`;
      }
      // 联动重绘雷达图多边形
      syncRadarBySliders();
    }

    function syncRadarBySliders() {
      // 获取当前4项滑块的值
      const alertInput = document.querySelector('input[oninput*="alert"]');
      const trustInput = document.querySelector('input[oninput*="trust"]');
      const insightInput = document.querySelector('input[oninput*="insight"]');
      const decisiveInput = document.querySelector('input[oninput*="decisive"]');

      const a = alertInput ? alertInput.value : 8;
      const t = trustInput ? trustInput.value : 3;
      const ins = insightInput ? insightInput.value : 7;
      const dec = decisiveInput ? decisiveInput.value : 6;

      // 动态映射到 SVG 坐标 (center 100, 85)
      const topY = 85 - (a * 7.5);
      const rightX = 100 + (ins * 8.5);
      const bottomX = 100 + (t * 5.5);
      const leftBottomX = 100 - (dec * 6);
      
      const radar = document.getElementById('radar-polygon');
      if (radar) {
        radar.setAttribute('points', `100,${topY} ${rightX},70 ${bottomX},140 ${leftBottomX},135 35,75`);
      }
    }

    // 5. 自主添加特质弹窗 (满足需求 1: 自定义添加状态)
    function showAddTraitModal() {
      document.getElementById('add-trait-modal').classList.remove('hidden');
      document.getElementById('new-trait-name').focus();
    }
    function closeAddTraitModal() {
      document.getElementById('add-trait-modal').classList.add('hidden');
    }
    function confirmAddTrait() {
      const name = document.getElementById('new-trait-name').value.trim();
      const val = document.getElementById('new-trait-value').value;
      if (!name) return alert('请输入特质名称');

      const container = document.getElementById('traits-container');
      const id = 'custom-' + Date.now();
      const newRow = document.createElement('div');
      newRow.className = "space-y-1 p-2 bg-[#020503]/60 rounded border border-emerald-900/80";
      newRow.innerHTML = `
        <div class="flex justify-between text-[11px]">
          <span class="text-emerald-300 font-medium">${name} (自定义)</span>
          <span class="font-mono text-emerald-400 font-semibold" id="label-${id}">${val} / 10</span>
        </div>
        <input type="range" min="0" max="10" value="${val}" oninput="document.getElementById('label-${id}').innerText = this.value + ' / 10'; syncRadarBySliders();" class="w-full accent-emerald-400 cursor-pointer h-1.5 bg-emerald-950/80 rounded-lg">
      `;
      container.appendChild(newRow);
      closeAddTraitModal();
      document.getElementById('new-trait-name').value = '';
    }

    // 6. AI 角色动态演化推演 (完全真实联动)
    let curEvolutionSuggestions = [];

    async function runCharacterEvolutionAnalysis() {
      if (!currentProject) {
        showToast("请先选择小说工程", false);
        return;
      }

      // 前置条件 1：检查是否有正文内容 (>= 50 字)
      const fullText = (typeof getCleanEditorText === 'function') ? getCleanEditorText() : '';
      if (fullText.length < 50) {
        showToast(`第 ${currentChapterNum} 章正文尚未起草，请先完成本章内容再推演角色变化！`, false);
        const box = document.getElementById('ai-suggestion-box');
        if (box) {
          box.classList.remove('hidden');
          box.innerHTML = `
            <div class="p-3 bg-amber-950/30 border border-amber-500/30 rounded-lg text-amber-300 text-[11px] leading-relaxed space-y-1">
              <div class="font-bold flex items-center space-x-1"><span>⚠️</span><span>本章正文过短 (${fullText.length} 字)</span></div>
              <p class="text-amber-200/80">角色人格演变推演依赖本章正文的实际剧情冲突与人物互动。请先起草或生成正文后再行推演。</p>
            </div>
          `;
        }
        return;
      }

      // 前置条件 2：检查当前项目是否已录入角色档案
      if (!currentCharacters || currentCharacters.length === 0) {
        showToast("当前工程尚未录入任何角色档案，请先在上方建立核心角色！", false);
        const box = document.getElementById('ai-suggestion-box');
        if (box) {
          box.classList.remove('hidden');
          box.innerHTML = `
            <div class="p-3 bg-amber-950/30 border border-amber-500/30 rounded-lg text-amber-300 text-[11px] leading-relaxed space-y-1">
              <div class="font-bold flex items-center space-x-1"><span>👥</span><span>未检测到出场角色档案</span></div>
              <p class="text-amber-200/80">请先在上方添加出场角色的基础特质与初始性格参数，系统方可比对本章剧情对角色人格的演变偏离。</p>
            </div>
          `;
        }
        return;
      }

      showToast(`正在通过 ${currentModelTier === 'pro' ? 'Pro 档' : 'Flash 档'} 推演第 ${currentChapterNum} 章角色经历与性格偏移...`);
      const box = document.getElementById('ai-suggestion-box');
      const actions = document.getElementById('ai-suggestion-actions');
      const target = {project: currentProject.name, chapter: currentChapterNum};
      evolutionProposal = null;
      actions.classList.add('hidden');
      box.classList.remove('hidden');
      box.innerHTML = `
        <div class="py-2.5 flex flex-col items-center justify-center space-y-2 text-center">
          ${renderAiDotsLoader('sm')}
          <span class="text-[11px] text-[var(--ink-secondary)]">正在比对本章正文与角色人格演变契约...</span>
        </div>
      `;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/analyze_characters?tier=${currentModelTier}`, {
          method: 'POST',
        });
        if (res.ok) {
          const data = await res.json();
          if (currentProject?.name !== target.project || currentChapterNum !== target.chapter) return;
          evolutionProposal = {...target, id: data.proposal_id};
          curEvolutionSuggestions = data.suggestions || [];
          if (curEvolutionSuggestions.length === 0) {
            box.innerHTML = '<div class="text-emerald-500/80 py-1">本章剧情对角色人格与关系未产生显著剧烈偏离，当前参数保持稳定。</div>';
            actions.classList.add('hidden');
            return;
          }

          let html = '';
          curEvolutionSuggestions.forEach(sug => {
            html += `<div class="font-bold text-emerald-300 border-b border-emerald-900/80 pb-1 mb-1">【${sug.character_name}】(${sug.role || '角色'})</div>`;
            if (sug.shifts && sug.shifts.length > 0) {
              sug.shifts.forEach(sh => {
                const diff = sh.new_value - sh.old_value;
                const sign = diff >= 0 ? `+${diff}` : `${diff}`;
                html += `
                  <div class="flex items-center justify-between py-0.5">
                    <span>【${sh.trait}】: ${sh.old_value} $\\to$ ${sh.new_value}</span>
                    <span class="${diff >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}">${sign}</span>
                  </div>
                  <div class="text-[10px] text-emerald-500/80 pb-1">原因: ${sh.reason}</div>
                `;
              });
            }
            if (sug.summary) {
              html += `<div class="text-[10px] text-emerald-300/80 bg-[#050c07] p-1.5 rounded mt-1">经历: ${sug.summary}</div>`;
            }
          });
          box.innerHTML = html;
          actions.classList.remove('hidden');
        } else {
          box.textContent = (await res.json()).detail || '分析失败，请重试';
        }
      } catch (err) {
        console.error("推演失败:", err);
        box.innerHTML = '<div class="text-rose-400 py-1">推演请求失败，请检查服务。</div>';
      }
    }

    async function applyAiSuggestionReal() {
      if (!currentProject || !evolutionProposal || evolutionProposal.project !== currentProject.name || evolutionProposal.chapter !== currentChapterNum) {
        showToast('请先分析当前章节，再确认提议', false);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/confirm_character_evolution?tier=${currentModelTier}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({proposal_id: evolutionProposal.id}),
        });
        if (!res.ok) {
          showToast((await res.json()).detail || '确认失败，请重新分析', false);
          return;
        }
        evolutionProposal = null;
        if (res.ok) {
          showToast(`已成功将第 ${currentChapterNum} 章角色演变持久化写入 characters.json！`);
          document.getElementById('ai-suggestion-box').innerHTML = `
            <div class="text-emerald-400 font-medium py-1">✓ 演变提议已成功采纳并落盘至角色状态机！</div>
          `;
          document.getElementById('ai-suggestion-actions').classList.add('hidden');
          // 重新读取当前角色的最新特质并刷新滑块
          loadRealCharacters(currentProject.name);
        }
      } catch (e) {
        console.error("确认采纳失败:", e);
      }
    }

    function rejectAiSuggestionReal() {
      document.getElementById('ai-suggestion-box').innerHTML = `
        <div class="text-emerald-600 py-1">已忽略本次 AI 演化提议，保持作者当前参数。</div>
      `;
      document.getElementById('ai-suggestion-actions').classList.add('hidden');
    }

    // 7. Token 防御与透明查看弹窗 (满足需求 2)
    function showTokenSavingModal() {
      document.getElementById('token-saving-modal').classList.remove('hidden');
    }
    function closeTokenSavingModal() {
      document.getElementById('token-saving-modal').classList.add('hidden');
    }

    // ========================================================
