// web_prototype/js/project-chapters.js — 小说工程与章节目录树管理、正文加载与落盘保存

    // 小说工程列表动态拉取与智能同步管理器 (loadProjectList)
    // 解决小说删除后残留选项问题、创建/删除全自动联动
    // ========================================================
    async function loadProjectList(selectTargetName = null) {
      try {
        const projRes = await fetch(`${API_BASE}/projects`);
        if (!projRes.ok) return [];
        const projects = await projRes.json();
        const selector = document.getElementById('project-selector');
        if (selector) {
          selector.innerHTML = '';
          if (projects && projects.length > 0) {
            projects.forEach(p => {
              const opt = document.createElement('option');
              opt.value = p.name;
              opt.innerText = `《${p.title || p.name}》(${p.chapters || 0}章 · ${Number(p.words || 0).toLocaleString()}字)`;
              if (selectTargetName && p.name === selectTargetName) opt.selected = true;
              selector.appendChild(opt);
            });
            const target = (selectTargetName && projects.some(p => p.name === selectTargetName))
              ? selectTargetName
              : projects[0].name;
            selector.value = target;
            await onSelectProject(target);
          } else {
            const opt = document.createElement('option');
            opt.value = '';
            opt.innerText = '暂无小说工程 (点击 + 新建)';
            selector.appendChild(opt);
            currentProject = null;
            clearStudioWorkspace();
          }
        }
        return projects;
      } catch (e) {
        console.error('拉取小说工程列表失败:', e);
        return [];
      }
    }

    function clearStudioWorkspace() {
      currentProject = null;
      currentChapterData = null;
      currentChapterNum = 1;
      const titleEl = document.getElementById('plan-novel-title');
      if (titleEl) titleEl.innerText = '暂无小说工程';
      const descInput = document.getElementById('plan-description-input');
      if (descInput) descInput.value = '';
      const chapSelector = document.getElementById('chapter-selector');
      if (chapSelector) chapSelector.innerHTML = '<option value="">无章节</option>';
      const editor = document.getElementById('editor-body');
      if (editor) editor.innerHTML = '<p class="text-stone-400">请先在上方新建或选择一本小说工程……</p>';
      const charTags = document.getElementById('character-tags-container');
      if (charTags) charTags.innerHTML = '<span class="text-xs text-stone-500">暂无登场角色</span>';
      const headerGenre = document.getElementById('header-genre');
      if (headerGenre) headerGenre.innerText = '未分类';
    }

    // ========================================================

    function showCreateProjectModal() {
      document.getElementById('create-project-modal').classList.remove('hidden');
      document.getElementById('new-proj-name').focus();
    }
    function closeCreateProjectModal() {
      document.getElementById('create-project-modal').classList.add('hidden');
    }
    async function confirmCreateProject() {
      const name = document.getElementById('new-proj-name').value.trim();
      const genre = document.getElementById('new-proj-genre').value.trim();
      const desc = document.getElementById('new-proj-desc').value.trim();
      if (!name) return alert("请输入小说书名！");

      try {
        const res = await fetch(`${API_BASE}/projects`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name, genre: genre, description: desc }),
        });
        if (res.ok) {
          showToast(`已成功创建新小说工程《${name}》！`);
          closeCreateProjectModal();
          document.getElementById('new-proj-name').value = '';
          // 重新初始化列表并切入新书
          await loadProjectList(name);
        } else {
          const err = await res.json();
          alert(err.detail || "创建失败");
        }
      } catch (e) {
        console.error("创建失败:", e);
      }
    }

    // 切换小说工程：彻底刷新全屏三大透视视角！
    async function onSelectProject(name) {
      if (!name) return;
      const version = ++projectLoadVersion;
      ++chapterLoadVersion;
      chapterLoading = true;
      editorTarget = null;
      evolutionProposal = null;
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(name)}`);
        if (!res.ok) return;
        const project = await res.json();
        if (version !== projectLoadVersion) return;
        currentProject = project;

        // 顶栏更新
        document.getElementById('header-genre').innerText = currentProject.genre || "未分类";

        // 1. 刷新【视角 1：企划构思 (Planning)】
        refreshPlanningView(currentProject);

        // 2. 刷新【视角 2：剧情棋盘 (StoryBoard)】
        refreshStoryboardView(currentProject);

        // 3. 刷新【视角 3：沉浸写作 (Studio)】
        renderChaptersTree(currentProject.chapters);
        renderChapterDropdown(currentProject.chapters);
        refreshSidebarForeshadowing(currentProject.foreshadowing);
        loadRealCharacters(name);

        // 加载第一章或当前章
        if (currentProject.chapters && currentProject.chapters.length > 0) {
          loadRealChapter(currentProject.chapters[0].chapter);
        } else {
          // 空项目提示
          const selector = document.getElementById('chapter-selector');
          if (selector) selector.innerHTML = '<option value="">暂无章节</option>';
          const curTitle = document.getElementById('editor-cur-title');
          if (curTitle) curTitle.innerText = "暂无章节";
          const h1 = document.getElementById('editor-h1');
          if (h1) h1.innerText = "点击左侧目录「+ 加章」开始创作";
          const container = document.getElementById('editor-container');
          if (container) container.innerHTML = `<p class="text-emerald-500/80 italic">本书尚未创建章节，请点击左侧「+ 加章」开启第一章创作！</p>`;
        }
      } catch (err) {
        console.error("加载项目失败:", err);
      }
    }

    // 刷新【视角 1：企划构思】
    function refreshPlanningView(p) {
      document.getElementById('plan-novel-title').innerText = p.title || p.name;
      document.getElementById('plan-novel-genre').innerText = p.genre || "未分类";
      document.getElementById('plan-description-input').value = p.description || "";
      document.getElementById('plan-name-input').value = p.title || p.name;
      document.getElementById('plan-genre-input').value = p.genre || "";

      document.getElementById('plan-total-words').innerText = `${Number(p.total_words || 0).toLocaleString()} 字`;
      document.getElementById('plan-total-chapters').innerText = `${p.chapters ? p.chapters.length : 0} 章`;
      document.getElementById('plan-total-foreshadowing').innerText = `${p.foreshadowing ? p.foreshadowing.length : 0} 个`;

      // 渲染细纲总览
      const outlineList = document.getElementById('plan-outline-list');
      if (outlineList && p.outline) {
        document.getElementById('plan-outline-count').innerText = `共 ${p.outline.length} 章细纲`;
        outlineList.innerHTML = '';
        p.outline.forEach(o => {
          const item = document.createElement('div');
          item.className = "p-2 bg-[#020503] rounded border border-emerald-900/80 space-y-1 hover:border-emerald-500/50 cursor-pointer transition group";
          item.onclick = () => {
            loadRealChapter(o.chapter);
            switchPerspective('writing');
          };
          item.innerHTML = `
            <div class="flex items-center justify-between text-emerald-300 font-semibold group-hover:text-emerald-200">
              <span>第${o.chapter}章 · ${o.title}</span>
              <span class="text-[10px] text-emerald-400/80 group-hover:underline">前往写作 →</span>
            </div>
            <p class="text-emerald-500/80 text-[11px] leading-relaxed line-clamp-2">${o.expected_content || '暂无详细预期剧情'}</p>
          `;
          outlineList.appendChild(item);
        });
      }
    }

    // 保存企划设定
    async function saveCurrentProjectPlan() {
      if (!currentProject) return;
      const title = document.getElementById('plan-name-input').value.trim();
      const genre = document.getElementById('plan-genre-input').value.trim();
      const desc = document.getElementById('plan-description-input').value.trim();

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: title, genre: genre, description: desc }),
        });
        if (res.ok) {
          showToast("已成功保存小说企划与世界观设定！");
          onSelectProject(currentProject.name);
        }
      } catch (e) {
        console.error("保存企划失败:", e);
      }
    }

    // 刷新左侧栏关联伏笔
    function refreshSidebarForeshadowing(foreshadows) {
      const container = document.getElementById('sidebar-foreshadowing-container');
      const badge = document.getElementById('sidebar-foreshadow-badge');
      if (!container) return;
      const list = foreshadows || [];
      if (badge) badge.innerText = `${list.length} 个待回收`;
      container.innerHTML = '';
      if (list.length === 0) {
        container.innerHTML = '<div class="text-[11px] text-emerald-600 py-1 italic">暂无开放伏笔</div>';
        return;
      }
      list.forEach(f => {
        const div = document.createElement('div');
        div.className = "text-xs bg-[#050c07]/80 border border-emerald-900/80 p-1.5 rounded text-emerald-400/90 flex items-start space-x-1.5 hover:border-amber-500/40 transition cursor-pointer";
        div.onclick = () => switchPerspective('storyboard');
        div.innerHTML = `<span class="text-amber-400 font-bold">•</span><span class="line-clamp-2">${f}</span>`;
        container.appendChild(div);
      });
    }

    // 刷新【视角 2：剧情棋盘】
    function refreshStoryboardView(p) {
      // 1. 渲染伏笔台账
      const fCount = document.getElementById('storyboard-foreshadow-count');
      const fGrid = document.getElementById('storyboard-foreshadow-grid');
      const foreshadows = p.foreshadowing || [];
      if (fCount) fCount.innerText = `${foreshadows.length} 个开放伏笔`;

      if (fGrid) {
        fGrid.innerHTML = '';
        if (foreshadows.length === 0) {
          fGrid.innerHTML = '<div class="col-span-2 text-emerald-600 py-4 text-center">暂无开放伏笔，点击右上角「+ 埋设新伏笔」即可加入台账！</div>';
        } else {
          foreshadows.forEach((f, idx) => {
            const card = document.createElement('div');
            card.className = "bg-[#050c07] border border-emerald-900/80 rounded-xl p-3.5 space-y-2 flex flex-col justify-between hover:border-amber-500/40 transition";
            card.innerHTML = `
              <div class="space-y-1">
                <div class="flex items-center justify-between">
                  <span class="text-amber-400 font-semibold flex items-center space-x-1">
                    <span>🪢</span>
                    <span>线索 #${idx + 1}</span>
                  </span>
                  <span class="text-[10px] bg-amber-950/80 text-amber-300 px-1.5 py-0.5 rounded border border-amber-800/40">开放中</span>
                </div>
                <p class="text-emerald-400/90 text-xs leading-relaxed">${f}</p>
              </div>
              <div class="flex justify-end pt-1">
                <button onclick="resolveForeshadowingPrompt('${f.replace(/'/g, "\\'")}')" class="px-2 py-1 bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-800/50 rounded text-[11px] font-medium transition">
                  ✓ 标记已回收闭环
                </button>
              </div>
            `;
            fGrid.appendChild(card);
          });
        }
      }

      // 2. 渲染章节细纲节拍矩阵
      const bGrid = document.getElementById('storyboard-beats-grid');
      const outlines = p.outline || [];
      if (bGrid) {
        bGrid.innerHTML = '';
        if (outlines.length === 0) {
          bGrid.innerHTML = '<div class="col-span-3 text-emerald-600 py-4 text-center">暂无章节大纲，点击上方「+ 追加新章节细纲」创建！</div>';
        } else {
          outlines.forEach(o => {
            const card = document.createElement('div');
            const hasChapterWritten = p.chapters && p.chapters.some(ch => ch.chapter === o.chapter && ch.has_content);
            card.className = "bg-[#050c07] border border-emerald-900/80 rounded-xl p-4 space-y-2.5 hover:border-emerald-500/50 transition flex flex-col justify-between";
            card.innerHTML = `
              <div class="space-y-1.5">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold text-emerald-400">第 ${o.chapter} 节拍 · ${o.title}</span>
                  <span class="text-[10px] px-1.5 py-0.5 rounded font-mono ${hasChapterWritten ? 'bg-emerald-950 text-emerald-300' : 'bg-emerald-950/80 text-emerald-500/80'}">
                    ${hasChapterWritten ? '已完稿' : '待起草'}
                  </span>
                </div>
                <p class="text-emerald-400/90 text-xs leading-relaxed line-clamp-3">${o.expected_content || '暂无详细描述'}</p>
                ${o.key_foreshadowing && o.key_foreshadowing.length > 0 ? `
                  <div class="text-[11px] text-amber-400/90 bg-amber-950/30 p-1.5 rounded border border-amber-900/40">
                    <span class="font-bold">• 埋线:</span> ${o.key_foreshadowing.join('；')}
                  </div>
                ` : ''}
              </div>
              <button onclick="loadRealChapter(${o.chapter}); switchPerspective('writing');" class="w-full mt-2 py-1 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-400/90 rounded text-xs transition">
                前往该章写作 →
              </button>
            `;
            bGrid.appendChild(card);
          });
        }
      }
    }

    // 埋设新伏笔
    async function promptAddForeshadowing() {
      if (!currentProject) return;
      const text = prompt("请输入要埋设的新伏笔线索：", "例如：主角随身佩戴的钥匙在月圆之夜隐隐发光");
      if (!text || !text.trim()) return;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/foreshadowing/add`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text.trim() }),
        });
        if (res.ok) {
          showToast("已成功将新线索埋设进伏笔台账！");
          onSelectProject(currentProject.name);
        }
      } catch (e) {
        console.error("添加伏笔失败:", e);
      }
    }

    // 标记伏笔已解决
    async function resolveForeshadowingPrompt(text) {
      if (!currentProject) return;
      if (!confirm(`确认标记回收伏笔：\n“${text}”？`)) return;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/foreshadowing/resolve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text }),
        });
        if (res.ok) {
          showToast("伏笔已成功闭环回收！");
          onSelectProject(currentProject.name);
        }
      } catch (e) {
        console.error("解决伏笔失败:", e);
      }
    }

    // 切换左侧手风琴板块折叠/展开
    function toggleSidebarSection(containerId, arrowId) {
      const container = document.getElementById(containerId);
      const arrow = document.getElementById(arrowId);
      if (!container) return;
      const isHidden = container.classList.contains('hidden');
      if (isHidden) {
        container.classList.remove('hidden');
        if (arrow) arrow.style.transform = 'rotate(0deg)';
      } else {
        container.classList.add('hidden');
        if (arrow) arrow.style.transform = 'rotate(-90deg)';
      }
    }

    // ==========================================
    // 章节选择器与目录树引擎 (位于左侧栏)
    // ==========================================

    // 渲染左侧章节下拉选择器
    function renderChapterDropdown(chapters) {
      const selector = document.getElementById('chapter-selector');
      if (!selector) return;
      if (!chapters || chapters.length === 0) {
        selector.innerHTML = '<option value="">暂无章节</option>';
        return;
      }
      selector.innerHTML = '';
      chapters.forEach(ch => {
        const opt = document.createElement('option');
        opt.value = ch.chapter;
        const stateMark = ch.has_content ? '✓' : '⏱';
        const words = ch.has_content ? `${(ch.word_count / 1000).toFixed(1)}k字` : '大纲';
        opt.innerText = `第 ${ch.chapter} 章 · ${ch.title} [${stateMark} ${words}]`;
        if (Number(ch.chapter) === Number(currentChapterNum)) {
          opt.selected = true;
        }
        selector.appendChild(opt);
      });
    }

    // 用户在左侧下拉菜单中直接选择章节
    function onSelectChapterDropdown(val) {
      if (!val) return;
      loadRealChapter(Number(val));
    }

    // 渲染左侧章节选择目录树
    function renderChaptersTree(chapters) {
      const container = document.getElementById('sidebar-chapters-list');
      if (!container || !chapters) return;

      // 更新左侧手风琴板块一的章节徽章
      const chaptersBadge = document.getElementById('sidebar-chapters-badge');
      if (chaptersBadge) {
        chaptersBadge.innerText = `${chapters.length} 章`;
      }

      container.innerHTML = `<div class="text-[11px] font-medium text-emerald-600 px-2 py-1 uppercase tracking-wider flex justify-between items-center">
        <span>章节列表 (${chapters.length} 章)</span>
      </div>`;
      
      if (chapters.length === 0) {
        container.innerHTML += '<div class="text-xs text-emerald-600 p-3 italic">暂无章节，请点击上方「+ 加章」</div>';
        return;
      }

      chapters.forEach(ch => {
        const isCurrent = Number(ch.chapter) === Number(currentChapterNum);
        const row = document.createElement('div');
        row.id = `sidebar-ch-item-${ch.chapter}`;
        row.className = isCurrent 
          ? "flex items-center justify-between px-2.5 py-1.5 rounded-md bg-emerald-950/60 border border-emerald-500/50 text-emerald-100 cursor-pointer font-semibold shadow-sm transition"
          : "flex items-center justify-between px-2.5 py-1.5 rounded-md hover:bg-emerald-950/60/60 cursor-pointer text-emerald-500/80 group transition";
        row.onclick = () => {
          loadRealChapter(ch.chapter);
        };
        row.innerHTML = `
          <div class="flex items-center space-x-2 truncate flex-1 min-w-0">
            <span class="${ch.has_content ? 'text-emerald-500' : 'text-amber-500/80'} text-xs shrink-0">${ch.has_content ? '✓' : '⏱'}</span>
            <span class="truncate">第${ch.chapter}章 · ${ch.title}</span>
          </div>
          <div class="flex items-center space-x-1 shrink-0 ml-1">
            <span class="text-[11px] text-emerald-700 font-mono group-hover:text-emerald-500/80">${ch.has_content ? (ch.word_count/1000).toFixed(1) + 'k' : '大纲'}</span>
            <button onclick="event.stopPropagation(); deleteChapterPrompt(${ch.chapter}, '${ch.title.replace(/'/g, "\\'")}')" class="opacity-0 group-hover:opacity-100 hover:bg-rose-950 hover:text-rose-400 text-emerald-600 p-0.5 rounded transition text-[11px]" title="删除第 ${ch.chapter} 章">🗑️</button>
          </div>
        `;
        container.appendChild(row);
      });
    }

    // 删除单章处理逻辑
    async function deleteChapterPrompt(chNum, title) {
      if (!currentProject) return;
      const ok = confirm(`确认删除「第 ${chNum} 章 · ${title || '无标题'}」吗？\n\n警告：该操作将永久删除该章正文与大纲！`);
      if (!ok) return;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${chNum}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          showToast(`已成功删除第 ${chNum} 章！`);
          // 重新拉取项目最新目录
          await onSelectProject(currentProject.name);
          // 如果当前正好在被删章节，自动切换到剩余相邻章节
          if (Number(currentChapterNum) === Number(chNum)) {
            const remaining = (currentProject.chapters || []).filter(c => Number(c.chapter) !== Number(chNum));
            if (remaining.length > 0) {
              loadRealChapter(remaining[0].chapter);
            }
          }
        } else {
          let errMsg = '未知错误';
          try {
            const err = await res.json();
            errMsg = err.detail || errMsg;
          } catch (_) {}
          if (res.status === 404) {
            alert(`删除章节失败: 后端路由尚未载入 (404 Not Found)。\n\n请在终端按 Ctrl+C 停止 na-studio 并重新运行 uv run na-studio 生效最新后端功能。`);
          } else {
            alert(`删除章节失败: ${errMsg}`);
          }
        }
      } catch (e) {
        console.error("删除章节异常:", e);
        showToast("删除章节发生网络异常", false);
      }
    }

    // 删除整本小说文章工程处理逻辑
    async function deleteCurrentProjectPrompt() {
      if (!currentProject) {
        showToast("请先选择要删除的小说工程", false);
        return;
      }
      const projName = currentProject.name;
      const ok = confirm(`确认彻底删除长篇小说工程《${projName}》吗？\n\n警告：该操作将永久删除该作品的所有章节、大纲、角色系统与伏笔台账！`);
      if (!ok) return;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projName)}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          showToast(`小说工程《${projName}》已彻底删除！`);
          currentProject = null;
          // 重新拉取项目列表并切换到剩余的第一部小说
          await loadProjectList();
        } else {
          let errMsg = '未知错误';
          try {
            const err = await res.json();
            errMsg = err.detail || errMsg;
          } catch (_) {}
          if (res.status === 404) {
            alert(`删除小说失败: 后端路由尚未载入 (404 Not Found)。\n\n请在终端按 Ctrl+C 停止 na-studio 并重新运行 uv run na-studio 生效最新后端功能。`);
          } else {
            alert(`删除小说失败: ${errMsg}`);
          }
        }
      } catch (e) {
        console.error("删除小说异常:", e);
        showToast("删除小说发生网络异常", false);
      }
    }

    // 加载单章完整正文与上下文
    async function loadRealChapter(chNum) {
      if (!currentProject) return;
      const projectName = currentProject.name;
      const version = ++chapterLoadVersion;
      chapterLoading = true;
      evolutionProposal = null;

      // 同步更新左侧章节下拉菜单的选中状态
      const selector = document.getElementById('chapter-selector');
      if (selector) selector.value = currentChapterNum;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/${chNum}`);
        if (!res.ok) {
          showToast(`无法加载第 ${chNum} 章，请检查后端服务`, true);
          return;
        }
        const data = await res.json();
        if (version !== chapterLoadVersion || currentProject?.name !== projectName) return;
        editorTarget = null;
        currentChapterNum = Number(chNum);
        if (selector) selector.value = currentChapterNum;
        
        // 安全更新各显示节点
        const curTitle = document.getElementById('editor-cur-title');
        if (curTitle) curTitle.innerText = `第 ${chNum} 章 · ${data.title}`;
        
        const h1 = document.getElementById('editor-h1');
        if (h1) h1.innerText = `第${chNum}章 ${data.title}`;
        
        const wordStatus = document.getElementById('editor-words-status');
        if (wordStatus) wordStatus.innerText = `本章 ${Number(data.word_count).toLocaleString()} 字`;

        // 更新审稿、角色与剧情面板的章节状态指示
        const targetReviewLabel = document.getElementById('review-target-chapter-label');
        if (targetReviewLabel) targetReviewLabel.innerText = `待审章节: 第 ${chNum} 章 (${data.title})`;
        
        const sliceLabel = document.getElementById('current-char-chapter-slice');
        if (sliceLabel) sliceLabel.innerText = `状态切片: 第 ${chNum} 章`;

        // 同步更新右侧剧情灵感面板的大纲和伏笔
        const rPlotTitle = document.getElementById('right-plot-chapter-title');
        if (rPlotTitle) rPlotTitle.innerText = `第 ${chNum} 章 · 本章大纲细纲`;
        const rPlotExpected = document.getElementById('right-plot-expected-content');
        if (rPlotExpected) {
          rPlotExpected.value = (data.outline && data.outline.expected_content) ? data.outline.expected_content : '';
        }
        const rPlotForeshadow = document.getElementById('right-plot-foreshadowing-info');
        if (rPlotForeshadow) {
          if (data.outline && data.outline.key_foreshadowing && data.outline.key_foreshadowing.length > 0) {
            rPlotForeshadow.innerText = `本章伏笔: ${data.outline.key_foreshadowing.join('；')}`;
          } else {
            rPlotForeshadow.innerText = `本章暂未关联特定埋线 (可在右侧或大纲添加)`;
          }
        }

        // 重置审稿面板显示
        const rInit = document.getElementById('review-initial-box');
        if (rInit) rInit.classList.remove('hidden');
        const rLoad = document.getElementById('review-loading-box');
        if (rLoad) rLoad.classList.add('hidden');
        const rErr = document.getElementById('review-error-box');
        if (rErr) rErr.classList.add('hidden');
        const rRes = document.getElementById('review-result-box');
        if (rRes) rRes.classList.add('hidden');

        // 渲染正文 (使用唯一定级 contenteditable 容器，支持多段拖动划选、Cmd+A 全选、跨行删除合并)
        const container = document.getElementById('editor-container');
        if (container) {
          if (data.content && data.content.trim()) {
            const paras = data.content.split('\n\n').filter(p => p.trim());
            let html = `<h1 class="text-2xl font-bold font-sans text-emerald-200 dark:text-emerald-200 mb-8 border-b border-emerald-900/80 pb-3 select-none" id="editor-h1">第${chNum}章 ${data.title}</h1>`;
            html += `<div id="editor-body" contenteditable="true" spellcheck="false" class="focus:outline-none min-h-[500px] outline-none text-emerald-300 leading-[1.85] selection:bg-emerald-500 selection:text-black">`;
            paras.forEach((p, idx) => {
              html += `<p class="mb-5 indent-8 content-paragraph">${p}</p>`;
            });
            html += `</div>`;
            container.innerHTML = html;
          } else {
            container.innerHTML = `
              <h1 class="text-2xl font-bold font-sans text-emerald-200 dark:text-emerald-200 mb-8 border-b border-emerald-900/80 pb-3 select-none" id="editor-h1">第${chNum}章 ${data.title}</h1>
              <div id="editor-empty-prompt-card" contenteditable="false" class="my-6 p-6 rounded-2xl bg-gradient-to-br from-emerald-950/40 via-slate-900/60 to-slate-950 border border-emerald-500/30 text-center space-y-3.5 shadow-xl select-none">
                <div class="w-12 h-12 mx-auto rounded-full bg-emerald-900/50 flex items-center justify-center text-2xl shadow-inner">🪄</div>
                <div class="space-y-1">
                  <h3 class="text-base font-bold text-emerald-200">第 ${chNum} 章正文尚未起草</h3>
                  <p class="text-xs text-emerald-500/80 max-w-lg mx-auto leading-relaxed">
                    ${data.outline && data.outline.expected_content ? `已就绪大纲细纲: “${data.outline.expected_content.slice(0, 60)}...”` : '当前尚未设置大纲细纲，您可在右侧「💡 剧情」随时添加或脑暴走向。'}
                  </p>
                </div>
                <div class="flex items-center justify-center space-x-3 pt-1">
                  <button onclick="triggerGenerateChapterContent()" class="px-5 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-bold rounded-xl text-xs font-semibold shadow-lg shadow-emerald-500/30 transition flex items-center space-x-2 cursor-pointer">
                    <span>🪄</span>
                    <span>根据大纲与角色一键生成正文</span>
                  </button>
                  <button onclick="switchRightTab('plot')" class="px-4 py-2.5 bg-emerald-950/80 hover:bg-emerald-900/60 text-emerald-400/90 rounded-xl text-xs font-medium border border-emerald-800/80 transition flex items-center space-x-1.5 cursor-pointer">
                    <span>💡</span>
                    <span>去右侧脑暴走向</span>
                  </button>
                </div>
              </div>
              <div id="editor-body" contenteditable="true" spellcheck="false" class="focus:outline-none min-h-[500px] outline-none text-emerald-300 leading-[1.85] selection:bg-emerald-500 selection:text-black">
                <p class="mb-5 indent-8 content-paragraph" data-placeholder="点击此处自由输入，开启人工起草……"></p>
              </div>
            `;
          }

          // 重新绑定编辑区选区与打字机居中监听
          container.removeEventListener('mouseup', recordEditorSelection);
          container.removeEventListener('keyup', recordEditorSelection);
          container.addEventListener('mouseup', recordEditorSelection);
          container.addEventListener('keyup', recordEditorSelection);

          // 应用作者个性化排版偏好 (字号/行距/字体族)
          applyEditorTypography();
          const edBody = document.getElementById('editor-body');
          if (edBody) {
            edBody.addEventListener('keyup', handleTypewriterScroll);
            edBody.addEventListener('input', () => {
              handleTypewriterScroll();
              const text = (typeof getCleanEditorText === 'function') ? getCleanEditorText() : edBody.innerText.trim();
              const wordStatus = document.getElementById('editor-words-status');
              if (wordStatus) {
                wordStatus.innerText = `本章 ${text.length.toLocaleString()} 字`;
              }
              const emptyPrompt = document.getElementById('editor-empty-prompt-card');
              if (emptyPrompt) {
                if (text.length > 0) emptyPrompt.classList.add('hidden');
                else emptyPrompt.classList.remove('hidden');
              }
              if (typeof updateStageStepperAndTabs === 'function') {
                updateStageStepperAndTabs();
              }
            });
          }
        }

        editorTarget = {project: projectName, chapter: Number(chNum)};
        // 刷新左侧章节列表激活高亮
        if (currentProject.chapters) {
          renderChaptersTree(currentProject.chapters);
        }

        // 状态感知：更新顶栏创作航标与面板前置就绪指示
        if (typeof updateStageStepperAndTabs === 'function') {
          updateStageStepperAndTabs(data);
        }

      } catch (err) {
        console.error("读取章节失败:", err);
        showToast("读取章节发生网络错误", true);
      } finally {
        if (version === chapterLoadVersion) {
          chapterLoading = false;
          if (selector) selector.value = currentChapterNum;
        }
      }
    }


    async function saveCurrentChapterToBackend() {
      if (chapterLoading || !editorTarget || editorTarget.project !== currentProject?.name) return;
      const target = {...editorTarget};
      if (!currentProject) {
        showToast("已在本地内存模拟保存 (未连接工程)");
        return;
      }
      const body = document.getElementById('editor-body');
      let fullText = '';
      if (typeof getCleanEditorText === 'function') {
        fullText = getCleanEditorText();
      } else if (body) {
        const paras = Array.from(body.querySelectorAll('p'))
          .filter(p => (typeof p.closest === 'function') ? !p.closest('[contenteditable="false"]') : true)
          .map(p => (p.innerText || '').replace(/（点击此处自由输入[，,][^）]*）/g, '').trim())
          .filter(p => p.length > 0);
        fullText = paras.join('\n\n') || (body.innerText ? body.innerText.trim() : '');
      }
      
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(target.project)}/chapters/${target.chapter}/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: fullText }),
        });
        if (res.ok) {
          const ret = await res.json();
          if (chapterLoading || editorTarget?.project !== target.project || editorTarget?.chapter !== target.chapter) return;
          document.getElementById('editor-words-status').innerText = `本章 ${Number(ret.word_count).toLocaleString()} 字 (已落盘)`;
          showToast(`第 ${currentChapterNum} 章正文已成功持久化落盘！`);
        } else {
          showToast('保存失败：' + ((await res.json()).detail || res.status), false);
        }
      } catch (err) {
        console.error("保存失败:", err);
        showToast("保存失败，请检查后端服务", false);
      }
    }

    // 角色特质与实时调参
    let currentCharacters = [];
    let curActiveChar = null;
    let traitUpdateTimer = null;

    // ========================================================
