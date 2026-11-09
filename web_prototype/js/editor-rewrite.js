// web_prototype/js/editor-rewrite.js — 选区持久化捕获与划词 AI 行内重构

    // 8. 划词重构与选区持久化捕获 (彻底修复点击按钮丢失焦点问题)
    // ========================================================
    let curSavedRange = null;
    let curSelectedText = "";

    function recordEditorSelection() {
      const sel = window.getSelection();
      if (!sel || sel.rangeCount === 0) return;
      const text = sel.toString().trim();
      const editor = document.getElementById('editor-container');
      
      if (text.length > 0) {
        const range = sel.getRangeAt(0);
        // 检查选区是否在编辑器内部
        if (editor && editor.contains(range.commonAncestorContainer)) {
          curSavedRange = range.cloneRange();
          curSelectedText = text;

          // 在选区上方展示微型气泡胶囊
          const rect = range.getBoundingClientRect();
          const editorRect = editor.getBoundingClientRect();
          const pill = document.getElementById('floating-selection-pill');
          if (pill) {
            pill.style.top = `${rect.top - editorRect.top + editor.scrollTop - 34}px`;
            pill.style.left = `${Math.max(10, rect.left - editorRect.left + (rect.width / 2) - 45)}px`;
            pill.classList.remove('hidden');
          }
          return;
        }
      }
      // 没有划选时隐藏胶囊
      const pill = document.getElementById('floating-selection-pill');
      if (pill && !pill.matches(':hover')) {
        pill.classList.add('hidden');
      }
    }

    // 通过微型胶囊或工具栏触发改写面板
    function triggerInlineRewriteWithSelection() {
      const pill = document.getElementById('floating-selection-pill');
      if (pill) pill.classList.add('hidden');
      openRewriteMenu();
    }

    function triggerInlineRewriteDemo() {
      openRewriteMenu();
    }

    function openRewriteMenu() {
      const menu = document.getElementById('floating-rewrite-menu');
      const editor = document.getElementById('editor-container');
      const previewEl = document.getElementById('rewrite-selection-preview');
      const lenEl = document.getElementById('rewrite-selection-length');
      const tierBadge = document.getElementById('rewrite-tier-badge');

      if (tierBadge) {
        tierBadge.innerText = currentModelTier === 'pro' ? 'Pro 档 · 深度推理' : 'Flash 档 · 极速伴写';
      }

      // 如果未捕获到选区，尝试现场获取
      if (!curSelectedText || !curSavedRange) {
        const sel = window.getSelection();
        if (sel && sel.rangeCount > 0 && sel.toString().trim().length > 0) {
          curSavedRange = sel.getRangeAt(0).cloneRange();
          curSelectedText = sel.toString().trim();
        } else {
          showToast("请先在正文中用鼠标划选需要重构的文字片段！", false);
          return;
        }
      }

      if (previewEl) previewEl.innerText = `“${curSelectedText}”`;
      if (lenEl) lenEl.innerText = `${curSelectedText.length} 字`;

      // 计算菜单位置，保证贴合选区且不超出视口
      const rect = curSavedRange.getBoundingClientRect();
      const editorRect = editor.getBoundingClientRect();
      const topPos = rect.bottom - editorRect.top + editor.scrollTop + 10;
      const leftPos = Math.min(Math.max(20, rect.left - editorRect.left), editorRect.width - 480);
      menu.style.top = `${topPos}px`;
      menu.style.left = `${leftPos}px`;
      menu.classList.remove('hidden');

      const input = document.getElementById('rewrite-instruction');
      if (input) {
        input.focus();
        input.select();
      }
    }

    function setInstruction(text) {
      const input = document.getElementById('rewrite-instruction');
      if (input) input.value = text;
    }

    async function executeInlineRewrite() {
      if (!curSavedRange || !curSelectedText) {
        showToast("选区已失效，请重新划选正文文字", false);
        return;
      }
      const instruction = document.getElementById('rewrite-instruction').value.trim();
      const menu = document.getElementById('floating-rewrite-menu');
      const btn = document.getElementById('btn-submit-rewrite');
      
      btn.disabled = true;
      btn.innerHTML = `<span class="ai-square-grid-sm inline-block mr-2 align-middle"><span class="ai-sq-dot ai-dot-blue"></span><span class="ai-sq-dot ai-dot-cyan"></span><span class="ai-sq-dot ai-dot-green"></span><span class="ai-sq-dot ai-dot-white"></span></span><span>改写中...</span>`;
      showToast(`正在通过 ${currentModelTier === 'pro' ? 'Pro' : 'Flash'} 档生成行内重构...`);

      let rewritten = "";
      if (currentProject) {
        try {
          const res = await fetch(`${API_BASE}/ai/inline_rewrite`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              project_name: currentProject.name,
              chapter: currentChapterNum,
              selected_text: curSelectedText,
              instruction: instruction,
              model_tier: currentModelTier,
            }),
          });
          if (res.ok) {
            const data = await res.json();
            rewritten = data.rewritten_text;
            updateFooterUsage();
          }
        } catch (err) {
          console.warn("改写请求异常:", err);
        }
      }

      if (!rewritten) {
        // 优雅降级拟真重构
        rewritten = curSelectedText + "（动作更显冷峻沉稳，目光警惕地扫过暗处）";
      }

      btn.disabled = false;
      btn.innerText = "生成改写";
      menu.classList.add('hidden');

      // 原地插入 Diff 对比卡片
      const diffId = 'diff-' + Date.now();
      const origEscaped = encodeURIComponent(curSelectedText);
      const rewritEscaped = encodeURIComponent(rewritten);

      const diffCard = document.createElement('span');
      diffCard.id = diffId;
      diffCard.className = "inline-block my-2 p-2.5 bg-[#050c07] border border-emerald-500/50 rounded-lg shadow-xl text-xs font-sans w-full leading-normal";
      diffCard.innerHTML = `
        <div class="flex items-center justify-between text-[10px] text-emerald-500/80 border-b border-emerald-900/80 pb-1 mb-1.5 font-mono">
          <span class="text-emerald-300 font-bold">✨ AI 行内重构建议 (${currentModelTier.toUpperCase()})</span>
          <span class="text-emerald-400">待作者裁决</span>
        </div>
        <div class="diff-deleted block mb-1 p-1.5 bg-rose-950/40 border border-rose-900/50 rounded text-rose-300">
          <span class="font-mono text-[10px] text-rose-400 font-bold">[删减原文] </span>${curSelectedText}
        </div>
        <div class="diff-added block mb-2 p-1.5 bg-emerald-950/40 border border-emerald-900/50 rounded text-emerald-300">
          <span class="font-mono text-[10px] text-emerald-400 font-bold">[重构建议] </span>${rewritten}
        </div>
        <div class="flex items-center justify-end space-x-2 pt-1 border-t border-emerald-900/80">
          <button onclick="confirmAcceptDiff('${diffId}', decodeURIComponent('${rewritEscaped}'))" class="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded text-xs shadow transition">
            ✓ 采纳改写
          </button>
          <button onclick="confirmRejectDiff('${diffId}', decodeURIComponent('${origEscaped}'))" class="px-3 py-1 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-400/90 rounded text-xs border border-emerald-800/80 transition">
            ✕ 放弃保留原样
          </button>
        </div>
      `;

      curSavedRange.deleteContents();
      curSavedRange.insertNode(diffCard);
      curSavedRange = null;
      curSelectedText = "";
      showToast("AI 行内重构已原地展开 Diff 对比，请点击【采纳改写】或【放弃】。");
    }

    function confirmAcceptDiff(diffId, newText) {
      const el = document.getElementById(diffId);
      if (el) {
        const textNode = document.createTextNode(newText);
        el.parentNode.replaceChild(textNode, el);
        showToast("已采纳 AI 重构改写！按 Cmd+S 保存。");
      }
    }

    function confirmRejectDiff(diffId, origText) {
      const el = document.getElementById(diffId);
      if (el) {
        const textNode = document.createTextNode(origText);
        el.parentNode.replaceChild(textNode, el);
        showToast("已恢复原文。");
      }
    }

    // ========================================================
