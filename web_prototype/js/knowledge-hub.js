// web_prototype/js/knowledge-hub.js — 知识库与文献学习中心控制器

    // 知识库与文献学习中心专属控制器 (Knowledge Hub Controller)
    // 支持看板总览、书籍导入与分块学习、删除管理、交互检索与注入联动
    // ========================================================
    let currentKbFilesList = [];
    let selectedKbFileBlob = null;
    let selectedKbFileName = '';

    function openKnowledgeHubModal() {
      const modal = document.getElementById('knowledge-hub-modal');
      if (!modal) return;
      modal.classList.remove('hidden');
      switchKbTab('library');
      refreshKbHubData();
      
      // 同步勾选状态
      const localToggle = document.getElementById('knowledge-enabled');
      const hubToggle = document.getElementById('kb-global-injection-toggle');
      if (localToggle && hubToggle) {
        hubToggle.checked = localToggle.checked;
      }
      setTimeout(initKbDropZone, 100);
      setTimeout(initTiltCards, 100);
    }

    function closeKnowledgeHubModal() {
      const modal = document.getElementById('knowledge-hub-modal');
      if (modal) modal.classList.add('hidden');
    }

    function syncKbInjectionToggle(checked) {
      const localToggle = document.getElementById('knowledge-enabled');
      if (localToggle) localToggle.checked = checked;
    }

    function switchKbTab(tabName) {
      const tabs = ['library', 'learn', 'search', 'settings'];
      tabs.forEach(t => {
        const btn = document.getElementById(`kb-tab-btn-${t}`);
        const content = document.getElementById(`kb-tab-content-${t}`);
        if (t === tabName) {
          if (btn) {
            btn.className = 'px-3.5 py-2 border-b-2 border-[#5e6ad2] font-semibold text-[#5e6ad2] transition flex items-center space-x-1.5 cursor-pointer';
          }
          if (content) content.classList.remove('hidden');
        } else {
          if (btn) {
            btn.className = 'px-3.5 py-2 border-b-2 border-transparent text-[var(--ink-muted)] hover:text-[var(--ink)] font-medium transition flex items-center space-x-1.5 cursor-pointer';
          }
          if (content) content.classList.add('hidden');
        }
      });
      if (tabName === 'library') {
        refreshKbHubData();
      }
      setTimeout(initTiltCards, 100);
    }

    async function refreshKbHubData() {
      try {
        const [statsRes, filesRes] = await Promise.all([
          fetch(`${API_BASE}/knowledge/stats`),
          fetch(`${API_BASE}/knowledge/files`),
        ]);
        if (statsRes.ok) {
          const stats = await statsRes.json();
          const fEl = document.getElementById('kb-stat-files');
          const cEl = document.getElementById('kb-stat-chunks');
          const uEl = document.getElementById('kb-stat-units');
          const chEl = document.getElementById('kb-stat-chars');
          if (fEl) fEl.innerText = Number(stats.file_count || 0).toLocaleString();
          if (cEl) cEl.innerText = Number(stats.chunk_count || 0).toLocaleString();
          if (uEl) uEl.innerText = Number(stats.knowledge_unit_count || 0).toLocaleString();
          if (chEl) chEl.innerText = Number(stats.total_chars || 0).toLocaleString();
        }
        if (filesRes.ok) {
          const data = await filesRes.json();
          currentKbFilesList = data.files || [];
          renderKbFilesTable(currentKbFilesList);
        }
      } catch (e) {
        console.error('加载知识库数据失败:', e);
      }
    }

    function renderKbFilesTable(files) {
      const tbody = document.getElementById('kb-files-tbody');
      const badge = document.getElementById('kb-files-count-badge');
      if (badge) badge.innerText = `(共 ${files.length} 份)`;
      if (!tbody) return;

      if (!files || files.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-[var(--ink-muted)]">暂无入库文献，请点击上方「导入新书籍」添加素材</td></tr>`;
        return;
      }

      tbody.innerHTML = '';
      files.slice(0, 50).forEach(f => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-[var(--canvas-soft)] transition-colors';
        const isUser = f.type === 'user';
        tr.innerHTML = `
          <td class="p-3 font-medium text-[var(--ink)] truncate max-w-xs flex items-center space-x-2" title="${f.full_path}">
            <span>${isUser ? '📘' : '🏛️'}</span>
            <span class="truncate">${f.name}</span>
          </td>
          <td class="p-3">
            <span class="px-2 py-0.5 rounded-full text-[10px] font-mono ${isUser ? 'bg-[#5e6ad2]/10 text-[#5e6ad2] border border-[#5e6ad2]/30' : 'bg-[var(--badge-bg)] text-[var(--badge-text)]'}">${isUser ? '用户导入' : '系统典籍'}</span>
          </td>
          <td class="p-3 font-mono text-[var(--ink-secondary)]">${Number(f.chunks).toLocaleString()} 块</td>
          <td class="p-3 font-mono text-[var(--ink-muted)]">${Number(f.chars).toLocaleString()} 字</td>
          <td class="p-3 text-right">
            ${isUser ? `<button onclick="deleteKbBookConfirm('${encodeURIComponent(f.name)}')" class="text-rose-500 hover:text-rose-600 font-medium px-2 py-0.5 rounded hover:bg-rose-500/10 transition cursor-pointer">删除</button>` : `<span class="text-[var(--ink-faint)] text-[10px]">内置只读</span>`}
          </td>
        `;
        tbody.appendChild(tr);
      });
      if (files.length > 50) {
        const moreRow = document.createElement('tr');
        moreRow.innerHTML = `<td colspan="5" class="p-2 text-center text-[10px] text-[var(--ink-muted)] font-mono">... 以及其他 ${files.length - 50} 份文献索引</td>`;
        tbody.appendChild(moreRow);
      }
    }

    function initKbDropZone() {
      const dropZone = document.getElementById('kb-drop-zone');
      const fileInput = document.getElementById('kb-file-input');
      if (!dropZone || !fileInput || dropZone.dataset.bound) return;
      dropZone.dataset.bound = 'true';

      dropZone.addEventListener('click', () => fileInput.click());
      dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('border-[#5e6ad2]', 'bg-[#5e6ad2]/5');
      });
      dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('border-[#5e6ad2]', 'bg-[#5e6ad2]/5');
      });
      dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-[#5e6ad2]', 'bg-[#5e6ad2]/5');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          handleKbFileSelected(e.dataTransfer.files[0]);
        }
      });
    }

    function handleKbFileSelected(file) {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.txt') && !file.name.toLowerCase().endsWith('.md')) {
        alert('仅支持上传 .txt 或 .md 格式的书籍与文本资料');
        return;
      }
      selectedKbFileBlob = file;
      selectedKbFileName = file.name;

      const infoCard = document.getElementById('kb-selected-file-info');
      const nameLabel = document.getElementById('kb-file-name-label');
      const metaLabel = document.getElementById('kb-file-meta-label');

      if (nameLabel) nameLabel.innerText = file.name;
      if (metaLabel) {
        const sizeKb = (file.size / 1024).toFixed(1);
        metaLabel.innerText = `${sizeKb} KB · 预计切分约 ${Math.ceil(file.size / 800)} 个段落块`;
      }
      if (infoCard) infoCard.classList.remove('hidden');
    }

    function clearKbSelectedFile() {
      selectedKbFileBlob = null;
      selectedKbFileName = '';
      const input = document.getElementById('kb-file-input');
      if (input) input.value = '';
      const infoCard = document.getElementById('kb-selected-file-info');
      if (infoCard) infoCard.classList.add('hidden');
      const statusBox = document.getElementById('kb-learn-status-box');
      if (statusBox) statusBox.classList.add('hidden');
    }

    async function executeBookLearning() {
      if (!selectedKbFileBlob) return alert('请先选择要学习的书籍或文档');
      const mode = document.querySelector('input[name="kbLearnMode"]:checked')?.value || 'preprocess';

      const btn = document.getElementById('btn-start-kb-learn');
      const statusBox = document.getElementById('kb-learn-status-box');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳ 正在解析并学习入库中...</span>';
      }
      if (statusBox) {
        statusBox.classList.remove('hidden');
        statusBox.innerHTML = `<div>[1/2] 正在读取本地书籍《${selectedKbFileName}》...</div>`;
      }

      try {
        const textContent = await selectedKbFileBlob.text();
        if (statusBox) {
          statusBox.innerHTML += `<div>[2/2] 发送入库管道，执行纯确定性分块处理 (${(textContent.length).toLocaleString()} 字符)...</div>`;
        }

        const res = await fetch(`${API_BASE}/knowledge/upload_and_learn`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: selectedKbFileName,
            content: textContent,
            mode: mode,
            tier: currentModelTier,
          }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '学习入库失败');

        if (statusBox) {
          statusBox.innerHTML += `
            <div class="text-[#5e6ad2] font-bold mt-2">✓ 入库完成: ${data.summary}</div>
            <div class="text-[var(--ink-secondary)]">• 生成 Chunks: ${data.chunks} 个</div>
            <div class="text-[var(--ink-secondary)]">• 录入字符: ${Number(data.chars).toLocaleString()} 字</div>
          `;
        }
        showToast(`已成功学习入库《${selectedKbFileName}》！`);
        refreshKbHubData();
      } catch (e) {
        console.error('学习书籍失败:', e);
        if (statusBox) {
          statusBox.innerHTML += `<div class="text-rose-500 font-bold mt-1">✕ 学习失败: ${e.message}</div>`;
        }
        showToast(e.message, false);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>🚀 开始处理并学习入库</span>';
        }
      }
    }

    async function deleteKbBookConfirm(encodedName) {
      const filename = decodeURIComponent(encodedName);
      if (!confirm(`确定要从知识库中彻底移除《${filename}》吗？移除后相关段落将不再作为写作参考素材。`)) return;
      try {
        const res = await fetch(`${API_BASE}/knowledge/files/${encodeURIComponent(filename)}`, {
          method: 'DELETE',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '删除失败');
        showToast(data.summary || `已删除《${filename}》`);
        refreshKbHubData();
      } catch (e) {
        console.error('删除文献失败:', e);
        showToast(e.message, false);
      }
    }

    async function executeStandaloneSearch() {
      const input = document.getElementById('kb-standalone-query');
      const query = input ? input.value.trim() : '';
      if (!query) return alert('请输入检索关键词');

      const btn = document.getElementById('btn-kb-search-action');
      const statusTag = document.getElementById('kb-search-status-tag');
      const container = document.getElementById('kb-search-cards-container');

      if (btn) btn.innerHTML = '<span>⏳ 检索中...</span>';
      if (statusTag) statusTag.innerText = 'SEARCHING...';

      try {
        const res = await fetch(`${API_BASE}/knowledge/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || '检索失败');

        if (statusTag) statusTag.innerText = `FOUND: ${data.sources?.length || 0} ITEMS`;

        if (!data.sources || data.sources.length === 0) {
          container.innerHTML = `
            <div class="p-6 text-center text-[var(--ink-muted)] bg-[var(--canvas-soft)] rounded-xl border border-dashed border-[var(--hairline)]">
              ${data.warning || '未找到匹配知识'}。建议更换关键词，或在「导入书籍与学习」中添加相关素材。
            </div>
          `;
          return;
        }

        container.innerHTML = '';
        data.sources.forEach(s => {
          const card = document.createElement('div');
          card.className = 'tilt-card p-4 bg-[var(--canvas-soft)] border border-[var(--hairline)] rounded-xl space-y-2 shadow-sm';
          card.innerHTML = `
            <div class="flex items-center justify-between border-b border-[var(--hairline)] pb-2 text-[11px]">
              <span class="font-bold text-[#5e6ad2] flex items-center space-x-1.5">
                <span>📑</span>
                <span>[${s.id}] ${s.source.split('/').pop()}</span>
              </span>
              <span class="text-[10px] px-2 py-0.5 rounded-full bg-[#5e6ad2]/10 text-[#5e6ad2] font-mono">${s.kind || 'excerpt'}</span>
            </div>
            <p class="text-xs text-[var(--ink)] leading-relaxed whitespace-pre-wrap">${s.text}</p>
          `;
          container.appendChild(card);
        });
        setTimeout(initTiltCards, 100);
      } catch (e) {
        console.error('检索失败:', e);
        showToast(e.message, false);
      } finally {
        if (btn) btn.innerHTML = '<span>🔍 检索匹配</span>';
      }
    }


    function openSettingsModal(defaultTab = 'editor') {
      const modal = document.getElementById('settings-modal');
      modal.classList.remove('hidden');
      switchSettingsTab(defaultTab);
      loadCurrentSettings();
      syncSettingsFormInputs();
    }

    function closeSettingsModal() {
      const modal = document.getElementById('settings-modal');
      modal.classList.add('hidden');
    }

    function switchSettingsTab(tabName) {
      ['editor', 'theme', 'backup', 'api', 'token', 'doctor'].forEach(t => {
        const panel = document.getElementById(`settings-tab-${t}`);
        const btn = document.getElementById(`tab-settings-${t}`);
        if (panel) panel.classList.add('hidden');
        if (btn) {
          btn.classList.remove('bg-emerald-950/80', 'text-emerald-300');
          btn.classList.add('text-emerald-500/80');
        }
      });
      const activePanel = document.getElementById(`settings-tab-${tabName}`);
      const activeBtn = document.getElementById(`tab-settings-${tabName}`);
      if (activePanel) activePanel.classList.remove('hidden');
      if (activeBtn) {
        activeBtn.classList.remove('text-emerald-500/80');
        activeBtn.classList.add('bg-emerald-950/80', 'text-emerald-300');
      }

      if (tabName === 'doctor') {
        refreshSettingsDoctor();
      }
    }

    function toggleApiKeyVisibility() {
      const input = document.getElementById('input-api-key');
      const eye = document.getElementById('eye-icon');
      if (!input || !eye) return;
      isApiKeyVisible = !isApiKeyVisible;
      input.type = isApiKeyVisible ? 'text' : 'password';
      eye.innerText = isApiKeyVisible ? '🙈' : '👁️';
    }

    async function loadCurrentSettings() {
      const statusTitle = document.getElementById('settings-status-title');
      const statusDesc = document.getElementById('settings-status-desc');
      const statusBadge = document.getElementById('settings-status-badge');
      const statusDot = document.getElementById('settings-status-dot');
      const apiKeyInput = document.getElementById('input-api-key');
      const baseUrlInput = document.getElementById('input-base-url');

      try {
        const res = await fetch(`${API_BASE}/system/settings`);
        if (!res.ok) return;
        const data = await res.json();

        if (baseUrlInput && data.base_url) {
          baseUrlInput.value = data.base_url;
        }

        if (data.api_key_configured) {
          statusTitle.innerText = `API Key 已就绪 (${data.masked_api_key})`;
          statusDesc.innerText = "大模型行内重构 (Cmd+K)、六维智能审稿与剧情脑暴已全部激活";
          statusBadge.className = "px-2.5 py-0.5 rounded text-[10px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800";
          statusBadge.innerText = "✓ 已配置";
          statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-400";
          apiKeyInput.placeholder = `当前已配置: ${data.masked_api_key} (如需更换请输入新 Key)`;
        } else {
          statusTitle.innerText = "API Key 尚未配置";
          statusDesc.innerText = "大模型功能（审稿、脑暴、重构）需配置 DeepSeek API Key 后方可使用";
          statusBadge.className = "px-2.5 py-0.5 rounded text-[10px] font-mono bg-amber-950 text-amber-300 border border-amber-800";
          statusBadge.innerText = "⚠ 待配置";
          statusDot.className = "w-2.5 h-2.5 rounded-full bg-amber-400";
          apiKeyInput.placeholder = "请输入您的 DeepSeek API Key (sk-...)";
        }
      } catch (e) {
        console.warn("读取设置失败:", e);
      }
    }

    async function saveApiSettings() {
      const keyInput = document.getElementById('input-api-key');
      const baseUrlInput = document.getElementById('input-base-url');
      const apiKey = keyInput.value.trim();
      const baseUrl = baseUrlInput.value.trim();

      if (!apiKey) {
        showToast("请输入有效的 API Key", false);
        keyInput.focus();
        return;
      }

      const btn = document.getElementById('btn-save-settings');
      btn.disabled = true;
      btn.innerText = "正在保存至 .env...";

      try {
        const res = await fetch(`${API_BASE}/system/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: apiKey,
            base_url: baseUrl || 'https://api.deepseek.com/v1',
          }),
        });

        btn.disabled = false;
        btn.innerText = "💾 保存 API 配置并生效";

        if (res.ok) {
          const data = await res.json();
          showToast(data.message || "API 配置已成功保存！");
          keyInput.value = '';
          loadCurrentSettings();
        } else {
          const err = await res.json();
          showToast(err.detail || "保存失败", false);
        }
      } catch (e) {
        btn.disabled = false;
        btn.innerText = "💾 保存 API 配置并生效";
        showToast("网络请求异常，保存失败", false);
      }
    }

    async function testApiKeyConnectivity() {
      const keyInput = document.getElementById('input-api-key');
      const baseUrlInput = document.getElementById('input-base-url');
      const resultBox = document.getElementById('settings-test-result');
      const btn = document.getElementById('btn-test-key');

      const apiKey = keyInput.value.trim();
      const baseUrl = baseUrlInput.value.trim();

      btn.disabled = true;
      btn.innerText = "探测中...";
      resultBox.classList.remove('hidden');
      resultBox.className = "p-3 rounded-lg border bg-[#050c07] border-emerald-500/40 text-emerald-300 text-xs flex items-center space-x-2";
      resultBox.innerHTML = '<span class="w-3 h-3 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></span><span>正在向模型端点发起握手探测...</span>';

      try {
        const res = await fetch(`${API_BASE}/system/test_api_key`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: apiKey || null,
            base_url: baseUrl || null,
          }),
        });

        btn.disabled = false;
        btn.innerText = "🔌 测试连通性";

        if (res.ok) {
          const data = await res.json();
          if (data.ok) {
            resultBox.className = "p-3 rounded-lg border bg-emerald-950/40 border-emerald-500/40 text-emerald-300 text-xs space-y-1";
            resultBox.innerHTML = `
              <div class="font-bold flex items-center space-x-1.5">
                <span>✓</span>
                <span>${data.detail}</span>
              </div>
              ${data.models && data.models.length > 0 ? `<div class="text-[10px] text-emerald-500/80">可用模型: ${data.models.join(', ')}</div>` : ''}
            `;
          } else {
            resultBox.className = "p-3 rounded-lg border bg-rose-950/40 border-rose-500/40 text-rose-300 text-xs";
            resultBox.innerHTML = `✕ ${data.detail}`;
          }
        } else {
          resultBox.className = "p-3 rounded-lg border bg-rose-950/40 border-rose-500/40 text-rose-300 text-xs";
          resultBox.innerHTML = "✕ 探测接口响应错误，请检查后端服务。";
        }
      } catch (e) {
        btn.disabled = false;
        btn.innerText = "🔌 测试连通性";
        resultBox.className = "p-3 rounded-lg border bg-rose-950/40 border-rose-500/40 text-rose-300 text-xs";
        resultBox.innerHTML = `✕ 探测失败: ${e}`;
      }
    }

    async function refreshSettingsDoctor() {
      const container = document.getElementById('settings-doctor-steps');
      if (!container) return;
      container.innerHTML = '<div class="text-emerald-400 py-3 italic flex items-center space-x-2"><span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span><span>正在实时执行 6 阶段核心引擎自检...</span></div>';

      try {
        const res = await fetch(`${API_BASE}/system/doctor`);
        if (res.ok) {
          const data = await res.json();
          container.innerHTML = '';
          (data.steps || []).forEach(s => {
            const row = document.createElement('div');
            row.className = "p-2.5 bg-[#050c07] rounded-lg border border-emerald-900/80 space-y-1";
            row.innerHTML = `
              <div class="flex items-center justify-between font-semibold text-emerald-300">
                <span class="flex items-center space-x-1.5">
                  <span class="${s.ok ? 'text-emerald-400' : 'text-rose-400'} font-bold">${s.ok ? '✓' : '✕'}</span>
                  <span>[${s.index}/6] ${s.title}</span>
                </span>
                <span class="${s.ok ? 'text-emerald-400' : 'text-rose-400'} text-[11px] font-mono">${s.detail}</span>
              </div>
              <div class="text-[10px] text-emerald-500/80 pl-4 space-y-0.5">
                ${s.sub_items.map(item => `<div>• ${item}</div>`).join('')}
              </div>
            `;
            container.appendChild(row);
          });
        }
      } catch (e) {
        container.innerHTML = '<div class="text-rose-400 py-2">自检请求失败</div>';
      }
    }



