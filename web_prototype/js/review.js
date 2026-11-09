// web_prototype/js/review.js — 六维审稿报告、三级修复采纳与达标放行引擎

    // 9. 六维审稿智能助手真实引擎交互（达标放行 + 本地销项）
    // ========================================================
    let currentReviewIssues = [];
    let currentReviewFilter = 'all'; // 'all' | 'blocking' | 'advisory' | 'resolved'
    let currentOverallScore = 0;

    function setReviewFilter(filter) {
      currentReviewFilter = filter;
      ['all', 'blocking', 'advisory', 'resolved'].forEach(f => {
        const btn = document.getElementById(`rf-tab-${f}`);
        if (!btn) return;
        if (f === filter) {
          btn.className = "px-2 py-0.5 rounded font-medium bg-emerald-500 text-black font-bold transition";
        } else {
          btn.className = "px-2 py-0.5 rounded font-medium text-emerald-500/80 hover:text-emerald-300 transition";
        }
      });
      renderReviewIssuesList();
    }

    async function startRealChapterReview() {
      if (!currentProject) {
        showToast("请先选择或创建一个小说工程", false);
        return;
      }
      switchRightTab('review');

      // 前置条件判断：本章正文是否存在且达到有效审稿长度 (>= 50 字)
      const fullText = (typeof getCleanEditorText === 'function') ? getCleanEditorText() : '';
      if (fullText.length < 50) {
        showToast(`第 ${currentChapterNum} 章正文不足 50 字，请先起草正文后再发起审稿！`, false);
        updateReviewPanelReadiness(false, fullText.length);
        return;
      }

      const initialBox = document.getElementById('review-initial-box');
      const loadingBox = document.getElementById('review-loading-box');
      const errorBox = document.getElementById('review-error-box');
      const resultBox = document.getElementById('review-result-box');
      const targetLabel = document.getElementById('review-target-chapter-label');

      if (targetLabel) targetLabel.innerText = `待审章节: 第 ${currentChapterNum} 章`;

      initialBox.classList.add('hidden');
      errorBox.classList.add('hidden');
      resultBox.classList.add('hidden');
      loadingBox.classList.remove('hidden');

      showToast(`正在启动第 ${currentChapterNum} 章六维全维度智能审稿 (${currentModelTier.toUpperCase()} 档)...`);

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model_tier: currentModelTier,
            apply_level1: false,
            save: false,
          }),
        });

        loadingBox.classList.add('hidden');

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          errorBox.classList.remove('hidden');
          const errMsgEl = document.getElementById('review-error-message');
          errMsgEl.innerText = errData.detail || "审稿请求失败，请确保本地 DEEPSEEK_API_KEY 配置正确。";
          showToast("审稿未能完成，请检查配置", false);
          return;
        }

        const data = await res.json();
        currentOverallScore = Number(data.overall_score || 0);

        // 初始化 issue 状态（区分硬伤 vs 灵感，默认 open）
        currentReviewIssues = (data.issues || []).map((issue, idx) => {
          const isBlocking = (Number(issue.level) === 1 || issue.severity === 'critical');
          return {
            ...issue,
            _id: 'iss_' + idx + '_' + Date.now(),
            _idx: idx,
            isBlocking: isBlocking,
            status: 'open', // 'open' | 'resolved' | 'dismissed'
          };
        });

        // 渲染审稿面板
        resultBox.classList.remove('hidden');
        document.getElementById('review-score-val').innerText = currentOverallScore.toFixed(1);

        currentReviewFilter = 'all';
        setReviewFilter('all');
        renderReviewPassBanner();
      } catch (err) {
        console.error("审稿异常:", err);
        loadingBox.classList.add('hidden');
        errorBox.classList.remove('hidden');
        document.getElementById('review-error-message').innerText = "网络请求失败，请确保本地后端服务运行在 127.0.0.1:8000。";
      }
    }

    // 渲染达标放行状态横幅与计数标签
    function renderReviewPassBanner() {
      const banner = document.getElementById('review-pass-banner');
      if (!banner) return;

      const total = currentReviewIssues.length;
      const openBlocking = currentReviewIssues.filter(i => i.isBlocking && i.status === 'open').length;
      const openAdvisory = currentReviewIssues.filter(i => !i.isBlocking && i.status === 'open').length;
      const resolvedCount = currentReviewIssues.filter(i => i.status === 'resolved' || i.status === 'dismissed').length;

      // 更新数量徽标
      const cAll = document.getElementById('rf-count-all');
      const cBlk = document.getElementById('rf-count-blocking');
      const cAdv = document.getElementById('rf-count-advisory');
      const cRes = document.getElementById('rf-count-resolved');
      if (cAll) cAll.innerText = total;
      if (cBlk) cBlk.innerText = openBlocking;
      if (cAdv) cAdv.innerText = openAdvisory;
      if (cRes) cRes.innerText = resolvedCount;

      const issuesCountLabel = document.getElementById('review-issues-count');
      if (issuesCountLabel) {
        if (openBlocking > 0) {
          issuesCountLabel.className = "text-rose-400 font-semibold";
          issuesCountLabel.innerText = `🚨 待修硬伤 ${openBlocking} 项`;
        } else if (openAdvisory > 0) {
          issuesCountLabel.className = "text-emerald-400";
          issuesCountLabel.innerText = `💡 润色灵感 ${openAdvisory} 条`;
        } else {
          issuesCountLabel.className = "text-emerald-400 font-semibold";
          issuesCountLabel.innerText = `✓ 全部条目已达标`;
        }
      }

      // 判定是否达标放行：无 open 状态的阻断性硬伤，且（评分 >= 7.5 或总硬伤已归零）
      const isPassed = (openBlocking === 0) && (currentOverallScore >= 7.5 || total === 0 || (openBlocking === 0 && openAdvisory === 0));

      if (isPassed) {
        banner.innerHTML = `
          <div class="bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 rounded-lg p-3 text-xs flex items-center justify-between shadow-sm">
            <div class="flex items-start space-x-2">
              <span class="text-base leading-none">🎉</span>
              <div>
                <div class="font-bold text-emerald-300">本章审稿达标放行！</div>
                <div class="text-[10px] text-emerald-400/80 leading-relaxed mt-0.5">
                  无阻断性硬伤，设定自洽文理通顺。剩余主观建议供作者选读参考，不影响章节定稿。
                </div>
              </div>
            </div>
            <span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded font-mono text-[10px] font-bold shrink-0 ml-2">PASSED</span>
          </div>
        `;
      } else {
        banner.innerHTML = `
          <div class="bg-amber-950/40 border border-amber-500/40 text-amber-300 rounded-lg p-3 text-xs flex items-center justify-between shadow-sm">
            <div class="flex items-start space-x-2">
              <span class="text-base leading-none">🚨</span>
              <div>
                <div class="font-bold text-amber-300">待确认 ${openBlocking} 项阻断性硬伤</div>
                <div class="text-[10px] text-amber-400/80 leading-relaxed mt-0.5">
                  包含错别字、语病或设定前后冲突，建议点击「✓ 采纳修正」即可达标。
                </div>
              </div>
            </div>
            <span class="px-2 py-0.5 bg-rose-500/20 text-rose-300 border border-rose-500/40 rounded font-mono text-[10px] font-bold shrink-0 ml-2">ATTENTION</span>
          </div>
        `;
      }
    }

    // 渲染过滤后的 issue 列表
    function renderReviewIssuesList() {
      renderReviewPassBanner();
      const issuesContainer = document.getElementById('review-issues-list');
      if (!issuesContainer) return;
      issuesContainer.innerHTML = '';

      let filtered = [];
      if (currentReviewFilter === 'all') {
        filtered = currentReviewIssues;
      } else if (currentReviewFilter === 'blocking') {
        filtered = currentReviewIssues.filter(i => i.isBlocking && i.status === 'open');
      } else if (currentReviewFilter === 'advisory') {
        filtered = currentReviewIssues.filter(i => !i.isBlocking && i.status === 'open');
      } else if (currentReviewFilter === 'resolved') {
        filtered = currentReviewIssues.filter(i => i.status === 'resolved' || i.status === 'dismissed');
      }

      if (filtered.length === 0) {
        let emptyDesc = "当前分类下暂无条目";
        if (currentReviewFilter === 'blocking') emptyDesc = "🎉 太棒了！本章没有发现任何错别字或阻断性硬伤。";
        else if (currentReviewFilter === 'resolved') emptyDesc = "尚未处理或忽略任何条目";
        issuesContainer.innerHTML = `
          <div class="bg-[#050c07]/60 border border-emerald-900/80 rounded-lg p-4 text-center text-emerald-500/80 text-xs">
            ${emptyDesc}
          </div>
        `;
        return;
      }

      filtered.forEach((issue) => {
        const origIdx = issue._idx;
        const card = document.createElement('div');
        const isResolved = issue.status === 'resolved';
        const isDismissed = issue.status === 'dismissed';
        const isBlocking = issue.isBlocking;

        let badgeClass = "";
        let levelName = "";
        if (isResolved) {
          badgeClass = "bg-emerald-950 text-emerald-300 border border-emerald-800";
          levelName = "✓ 已修复";
        } else if (isDismissed) {
          badgeClass = "bg-emerald-950/80 text-emerald-500/80 border border-emerald-800/80";
          levelName = "已忽略";
        } else if (isBlocking) {
          badgeClass = "bg-rose-950 text-rose-300 border border-rose-800";
          levelName = "🚨 阻断硬伤";
        } else {
          badgeClass = "bg-emerald-950/60 text-emerald-300 border border-emerald-800";
          levelName = "💡 润色灵感";
        }

        const borderClass = isResolved ? "border-emerald-800/60 bg-emerald-950/10" : (isDismissed ? "border-emerald-900/60 opacity-60 bg-[#050c07]/40" : (isBlocking ? "border-rose-900/50 bg-[#050c07]" : "border-emerald-900/80 bg-[#050c07]"));

        card.className = `${borderClass} border rounded-lg p-3 space-y-2 hover:border-emerald-800/80 transition`;
        card.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="font-bold text-emerald-300 flex items-center space-x-1">
              <span class="${isResolved ? 'text-emerald-400' : (isBlocking ? 'text-rose-400' : 'text-emerald-400')}">•</span>
              <span>[${issue.dimension || '综合'}]</span>
              <span class="text-[11px] font-normal text-emerald-500/80 font-mono">#${origIdx + 1}</span>
            </span>
            <span class="text-[10px] px-1.5 py-0.5 rounded ${badgeClass} font-mono">${levelName}</span>
          </div>
          <p class="text-emerald-400/90 text-[11px] leading-relaxed ${isResolved ? 'line-through text-emerald-500/80' : ''}">${issue.description || ''}</p>
          ${issue.suggestion ? `<div class="text-[10px] text-emerald-300/90 bg-emerald-950/30 p-2 rounded border border-emerald-900/40">💡 建议: ${issue.suggestion}</div>` : ''}
          ${issue.before_text && issue.after_text ? `
            <div class="text-[10px] bg-[#020503] p-2 rounded border border-emerald-900/80 font-mono space-y-1">
              <div class="text-rose-400/90"><span class="text-emerald-600">- </span>${issue.before_text}</div>
              <div class="text-emerald-400/90"><span class="text-emerald-600">+ </span>${issue.after_text}</div>
            </div>
          ` : ''}
          <div class="flex items-center justify-between pt-1 border-t border-emerald-900/80 text-[11px]">
            ${issue.before_text ? `<button onclick="scrollToIssueInEditor('${encodeURIComponent(issue.before_text)}')" class="text-emerald-400 hover:underline">定位正文 →</button>` : '<span></span>'}
            <div class="flex items-center space-x-1.5">
              ${!isResolved && !isDismissed ? `
                <button onclick="dismissSingleReviewIssue(${origIdx})" class="px-2 py-0.5 rounded text-[10px] text-emerald-500/80 hover:text-emerald-300 hover:bg-emerald-950/60 transition">
                  忽略
                </button>
                ${issue.before_text && issue.after_text ? `
                  <button onclick="applySingleReviewFix(${origIdx}, this)" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded text-[11px] shadow transition flex items-center">
                    <span>✓ 采纳修正</span>
                  </button>
                ` : ''}
              ` : `
                <button onclick="undoDismissReviewIssue(${origIdx})" class="px-2 py-0.5 rounded text-[10px] text-emerald-400 hover:text-emerald-300 hover:bg-emerald-950/60 transition">
                  撤销状态
                </button>
              `}
            </div>
          </div>
        `;
        issuesContainer.appendChild(card);
      });
    }

    // 采纳单项审稿修正：本地销项 + 立即写回持久化，【绝不自动触发全局重审】！
    async function applySingleReviewFix(issueIndex, btnElement) {
      const issue = currentReviewIssues[issueIndex];
      if (!issue || !currentProject) return;

      let origText = "";
      if (btnElement) {
        origText = btnElement.innerHTML;
        btnElement.disabled = true;
        btnElement.innerHTML = `<span class="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin mr-1"></span>修正中...`;
      }

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${currentChapterNum}/apply_fixes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ issues: [issue] }),
        });
        if (res.ok) {
          showToast(`已成功采纳并修正：${issue.dimension || '审稿'} 问题！`);
          // 重新读取本章正文并装载到编辑器中
          await loadRealChapter(currentChapterNum);
          
          // 本地销项标记为 resolved，绝不调用 startRealChapterReview()！
          issue.status = 'resolved';
          renderReviewIssuesList();
        } else {
          const errData = await res.json().catch(() => ({}));
          showToast(errData.detail || "采纳修改失败：正文中未匹配到原锚点文本", true);
          if (btnElement) {
            btnElement.disabled = false;
            btnElement.innerHTML = origText;
          }
        }
      } catch (err) {
        console.error("采纳修正失败:", err);
        showToast("请求失败，请检查后端服务", true);
        if (btnElement) {
          btnElement.disabled = false;
          btnElement.innerHTML = origText;
        }
      }
    }

    // 忽略单项建议
    function dismissSingleReviewIssue(issueIndex) {
      if (currentReviewIssues[issueIndex]) {
        currentReviewIssues[issueIndex].status = 'dismissed';
        showToast("已忽略该建议");
        renderReviewIssuesList();
      }
    }

    // 撤销忽略或解决状态
    function undoDismissReviewIssue(issueIndex) {
      if (currentReviewIssues[issueIndex]) {
        currentReviewIssues[issueIndex].status = 'open';
        renderReviewIssuesList();
      }
    }

    function scrollToIssueInEditor(encodedBeforeText) {
      const text = decodeURIComponent(encodedBeforeText);
      const container = document.getElementById('editor-container');
      const paras = container.querySelectorAll('.content-paragraph');
      for (const p of paras) {
        if (p.innerText.includes(text)) {
          p.scrollIntoView({ behavior: 'smooth', block: 'center' });
          p.classList.add('bg-amber-500/20', 'transition-all');
          setTimeout(() => p.classList.remove('bg-amber-500/20'), 2000);
          break;
        }
      }
    }

    // ========================================================
