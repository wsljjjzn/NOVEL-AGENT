// web_prototype/js/characters.js — 角色库联动、时间切片演进、性格雷达图与特质调参

    function jitterTraitsRandomly() {
      if (!curActiveChar || !curActiveChar.personality) return;
      Object.keys(curActiveChar.personality).forEach(trait => {
        const cur = Number(curActiveChar.personality[trait]);
        const delta = (Math.random() - 0.5) * 2;
        const next = Math.max(1, Math.min(10, Math.round(cur + delta)));
        curActiveChar.personality[trait] = next;
        const slider = document.querySelector(`input[oninput*="${trait}"]`);
        if (slider) slider.value = next;
        const label = document.getElementById(`label-trait-${trait}`);
        if (label) label.innerText = `${next} / 10`;
      });
      updateRadarChartFromPersonality(curActiveChar.personality);
      if (typeof showToast === 'function') {
        showToast(`已激发【${curActiveChar.name}】的情境性格波动！`);
      }
    }

    async function loadRealCharacters(name) {
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(name)}/characters`);
        if (!res.ok) return;
        const data = await res.json();
        currentCharacters = data.characters || [];
        
        // 渲染登场角色标签
        renderCharacterTags();
        if (currentCharacters.length > 0) {
          selectRealCharacter(currentCharacters[0].name);
        }
        if (typeof updateStageStepperAndTabs === 'function') {
          updateStageStepperAndTabs();
        }
      } catch (err) {
        console.error("读取角色失败:", err);
      }
    }

    function renderCharacterTags() {
      const container = document.getElementById('cast-characters-container') || document.querySelector('aside .flex-wrap');
      const charsBadge = document.getElementById('sidebar-chars-badge');
      if (charsBadge && currentCharacters) {
        charsBadge.innerText = `${currentCharacters.length} 人`;
      }
      if (!container || !currentCharacters) return;
      container.innerHTML = '';
      currentCharacters.forEach(c => {
        const btn = document.createElement('button');
        btn.className = "px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-700/50 text-emerald-300 text-xs flex items-center space-x-1 hover:bg-emerald-900 transition";
        btn.onclick = () => selectRealCharacter(c.name);
        btn.innerHTML = `<span>${c.name}</span><span class="text-[10px] text-emerald-400/80 font-mono">(${c.role || '角色'})</span>`;
        container.appendChild(btn);
      });
    }

    let curActiveSliceChapter = 'latest';

    function selectRealCharacter(name) {
      const char = currentCharacters.find(c => c.name === name);
      if (!char) return;
      curActiveChar = char;
      const nameEl = document.getElementById('current-char-name');
      if (nameEl) nameEl.innerText = char.name;
      const roleEl = document.getElementById('current-char-role');
      if (roleEl) roleEl.innerText = char.role || '配角';

      // 装载切片穿梭选择器
      renderCharacterSliceSelector(char);
      switchRightTab('character');
    }

    function renderCharacterSliceSelector(char) {
      const select = document.getElementById('char-slice-chapter-select');
      if (!select) return;
      select.innerHTML = '<option value="latest">📌 当前最新状态</option>';

      if (currentProject && currentProject.chapters) {
        const eventsMap = new Set((char.chapter_events || []).map(e => Number(e.chapter)));
        currentProject.chapters.forEach(c => {
          const chNum = Number(c.chapter);
          const hasEvent = eventsMap.has(chNum);
          const opt = document.createElement('option');
          opt.value = chNum;
          opt.innerText = hasEvent ? `第 ${chNum} 章 · [有性格演变记录]` : `第 ${chNum} 章切片`;
          select.appendChild(opt);
        });
      }

      curActiveSliceChapter = 'latest';
      select.value = 'latest';
      updateCharacterSliceDisplay(char, 'latest');
    }

    async function onSelectCharacterSlice(sliceVal) {
      if (!curActiveChar) return;
      curActiveSliceChapter = sliceVal;
      await updateCharacterSliceDisplay(curActiveChar, sliceVal);
    }

    function stepCharacterSlice(delta) {
      const select = document.getElementById('char-slice-chapter-select');
      if (!select || select.options.length <= 1) return;
      let curIdx = select.selectedIndex;
      let nextIdx = curIdx + delta;
      if (nextIdx < 0) nextIdx = 0;
      if (nextIdx >= select.options.length) nextIdx = select.options.length - 1;
      select.selectedIndex = nextIdx;
      onSelectCharacterSlice(select.value);
    }

    async function updateCharacterSliceDisplay(char, sliceVal) {
      const sliceTag = document.getElementById('char-slice-status-tag');
      const headerSliceBadge = document.getElementById('current-char-chapter-slice');
      const moodEl = document.getElementById('char-slice-mood');
      const badgeEl = document.getElementById('char-slice-event-badge');
      const summaryEl = document.getElementById('char-slice-summary');
      const shiftsList = document.getElementById('char-slice-shifts-list');
      const rollbackBar = document.getElementById('char-slice-rollback-bar');

      if (sliceVal === 'latest') {
        if (sliceTag) {
          sliceTag.className = "text-[10px] text-emerald-400 font-mono bg-emerald-950/40 px-1.5 py-0.5 rounded border border-emerald-800/40";
          sliceTag.innerText = "● 实时最新";
        }
        if (headerSliceBadge) {
          headerSliceBadge.className = "px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px] font-mono";
          headerSliceBadge.innerText = "当前状态";
        }
        if (moodEl) moodEl.innerText = (char.chapter_events && char.chapter_events.length > 0 ? char.chapter_events[char.chapter_events.length - 1].mood || '平静自若' : '平静自若');
        if (badgeEl) badgeEl.innerText = "当前常态";
        if (summaryEl) summaryEl.innerText = "正在查看角色全局最新基准状态。可调节下方滑块，或切换切片回溯历史。";
        if (shiftsList) {
          shiftsList.classList.add('hidden');
          shiftsList.innerHTML = '';
        }
        if (rollbackBar) rollbackBar.classList.add('hidden');

        renderTraitsSliders(char, false);
        updateRadarChartFromPersonality(char.personality);
      } else {
        const chNum = Number(sliceVal);
        if (sliceTag) {
          sliceTag.className = "text-[10px] text-amber-400 font-mono bg-amber-950/40 px-1.5 py-0.5 rounded border border-amber-800/40";
          sliceTag.innerText = `⏱️ 第 ${chNum} 章切片`;
        }
        if (headerSliceBadge) {
          headerSliceBadge.className = "px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-mono";
          headerSliceBadge.innerText = `第 ${chNum} 章切片 (回溯锁定)`;
        }
        if (rollbackBar) rollbackBar.classList.remove('hidden');

        // 发送后端获取切片数据
        try {
          const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/characters/${encodeURIComponent(char.name)}/slice/${chNum}`);
          if (res.ok) {
            const slice = await res.json();
            if (moodEl) moodEl.innerText = slice.mood || "平静";
            if (badgeEl) badgeEl.innerText = slice.is_exact_event ? "⚡ 本章有演变" : "延续前文状态";
            if (summaryEl) summaryEl.innerText = slice.summary || (slice.is_exact_event ? "本章记录了该角色的关键剧情行为与心理波动。" : "本章该角色未发生重大性格转折，特质状态与行为逻辑承接前文。");

            // 渲染 shifts 与 actions
            if (shiftsList) {
              let itemsHtml = '';
              (slice.key_actions || []).forEach(act => {
                itemsHtml += `<div class="text-emerald-400/90 flex items-start space-x-1"><span class="text-emerald-400">• 行动:</span><span>${act}</span></div>`;
              });
              (slice.personality_shifts || []).forEach(sh => {
                itemsHtml += `<div class="text-amber-300 flex items-start space-x-1"><span class="text-amber-400">• 特质偏移:</span><span>${sh.trait} ${sh.old_value}→${sh.new_value} (${sh.reason || '剧情推动'})</span></div>`;
              });
              (slice.relationship_changes || []).forEach(rc => {
                itemsHtml += `<div class="text-sky-300 flex items-start space-x-1"><span class="text-sky-400">• 关系网:</span><span>对 ${rc.target || rc.name} ${rc.old || ''}→${rc.new || ''}</span></div>`;
              });

              if (itemsHtml) {
                shiftsList.innerHTML = itemsHtml;
                shiftsList.classList.remove('hidden');
              } else {
                shiftsList.classList.add('hidden');
                shiftsList.innerHTML = '';
              }
            }

            // 更新人格滑块（切片只读预览状态，带历史数值）
            renderTraitsSliders({ ...char, personality: slice.personality || char.personality }, true);
            updateRadarChartFromPersonality(slice.personality || char.personality);
          }
        } catch (err) {
          console.error("获取切片失败:", err);
        }
      }
    }

    // 覆盖为当前最新状态
    async function restoreActiveSliceToCurrent() {
      if (!curActiveChar || curActiveSliceChapter === 'latest') return;
      const chNum = Number(curActiveSliceChapter);
      const ok = confirm(`确认将第 ${chNum} 章的历史特质切片覆盖为【${curActiveChar.name}】的当前最新状态吗？`);
      if (!ok) return;

      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/characters/${encodeURIComponent(curActiveChar.name)}/slice/${chNum}`);
        if (res.ok) {
          const slice = await res.json();
          if (slice.personality) {
            for (const [trait, val] of Object.entries(slice.personality)) {
              await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/characters/update_trait`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  character_name: curActiveChar.name,
                  trait_name: trait,
                  value: Number(val),
                }),
              });
            }
            showToast(`已成功将第 ${chNum} 章人格切片覆盖为最新状态！`);
            await loadRealCharacters(currentProject.name);
            selectRealCharacter(curActiveChar.name);
          }
        }
      } catch (e) {
        showToast("覆盖状态失败", false);
      }
    }

    function renderTraitsSliders(char, isReadOnly = false) {
      const container = document.getElementById('traits-container');
      if (!container || !char || !char.personality) return;
      container.innerHTML = '';

      Object.entries(char.personality).forEach(([trait, val]) => {
        const row = document.createElement('div');
        row.className = "space-y-1";
        row.innerHTML = `
          <div class="flex justify-between text-[11px]">
            <span class="${isReadOnly ? 'text-emerald-500/80' : 'text-emerald-400/90'} font-medium flex items-center space-x-1">
              <span>${trait}</span>
              ${isReadOnly ? '<span class="text-[9px] text-amber-400/90 font-mono">(切片只读)</span>' : ''}
            </span>
            <span class="font-mono ${isReadOnly ? 'text-amber-400' : 'text-emerald-400'} font-semibold" id="label-trait-${trait}">${val} / 10</span>
          </div>
          <input type="range" min="0" max="10" value="${val}" 
            ${isReadOnly ? 'disabled' : ''}
            oninput="onRealTraitSliderChange('${trait}', this.value)" 
            class="w-full ${isReadOnly ? 'accent-amber-500 opacity-60 cursor-not-allowed' : 'accent-emerald-400 cursor-pointer'} h-1.5 bg-emerald-950/80 rounded-lg">
        `;
        container.appendChild(row);
      });
    }

    // 动态雷达图 5 维度联动引擎 (数学精确的正五边形放射角与半径映射)
    function updateRadarChartFromPersonality(personality) {
      if (!personality) return;
      const radar = document.getElementById('radar-polygon');
      if (!radar) return;

      const entries = Object.entries(personality);
      if (entries.length === 0) return;

      // 5 个轴向的匹配规则与 fallback (顺时针方向)
      const rules = [
        { keywords: ["警惕", "防备", "谨慎", "冷静", "理智", "智谋", "心境"], fallbackName: "警惕心", fallbackVal: 8 },
        { keywords: ["洞察", "敏锐", "观察", "心机", "智慧", "感知", "谋略"], fallbackName: "洞察力", fallbackVal: 7 },
        { keywords: ["信任", "忠诚", "温和", "善良", "友善", "包容", "亲和"], fallbackName: "信任度", fallbackVal: 4 },
        { keywords: ["决绝", "果断", "冷酷", "威慑", "魄力", "凶狠", "行动"], fallbackName: "果断决绝", fallbackVal: 6 },
        { keywords: ["同理", "同情", "感性", "情绪", "共情", "慈悲", "执念"], fallbackName: "同理心", fallbackVal: 5 },
      ];

      const cx = 100.0;
      const cy = 85.0;
      const R = 60.0; // 满分 10 分时的最大半径
      // 5 轴向放射角: -90° (顶), -18° (右上), 54° (右下), 126° (左下), 198° (左上)
      const angles = [
        -Math.PI / 2,
        -Math.PI / 2 + 2 * Math.PI / 5,
        -Math.PI / 2 + 4 * Math.PI / 5,
        -Math.PI / 2 + 6 * Math.PI / 5,
        -Math.PI / 2 + 8 * Math.PI / 5
      ];

      const points = [];
      const usedKeys = new Set();

      rules.forEach((rule, i) => {
        let matchedName = null;
        let matchedVal = null;

        // 1. 优先在未占用的特质中做关键字匹配
        for (const [k, v] of entries) {
          if (!usedKeys.has(k) && rule.keywords.some(kw => k.includes(kw))) {
            matchedName = k;
            matchedVal = Number(v);
            usedKeys.add(k);
            break;
          }
        }

        // 2. 若当前特质词库不含预设关键词，按索引分配未使用的个性特质
        if (matchedName === null) {
          for (const [k, v] of entries) {
            if (!usedKeys.has(k)) {
              matchedName = k;
              matchedVal = Number(v);
              usedKeys.add(k);
              break;
            }
          }
        }

        // 3. 确定该轴向特质名称与数值
        const finalName = matchedName || rule.fallbackName;
        const finalVal = matchedVal !== null ? matchedVal : rule.fallbackVal;
        const clampedVal = Math.max(0.5, Math.min(10, finalVal));
        const r = (clampedVal / 10.0) * R;

        const x = cx + r * Math.cos(angles[i]);
        const y = cy + r * Math.sin(angles[i]);
        points.push(`${x.toFixed(1)},${y.toFixed(1)}`);

        // 联动更新 5 个顶点高亮指示小圆点
        const dot = document.getElementById(`radar-dot-${i}`);
        if (dot) {
          dot.setAttribute('cx', x.toFixed(1));
          dot.setAttribute('cy', y.toFixed(1));
        }

        // 联动更新 5 个特质维度文本标签
        const lbl = document.getElementById(`radar-lbl-${i}`);
        if (lbl) {
          lbl.textContent = finalName.length > 5 ? finalName.slice(0, 4) + '..' : finalName;
        }
      });

      // 实时设置雷达多边形顶点，触发丝滑形变
      radar.setAttribute('points', points.join(' '));
      setupRadarInteractions();
    }

    // 核心滑块拖拽响应：实时联动更新雷达图 + 防抖持久化落盘
    function onRealTraitSliderChange(trait, val) {
      const numVal = Number(val);
      const label = document.getElementById(`label-trait-${trait}`);
      if (label) label.innerText = `${numVal} / 10`;

      if (curActiveChar && curActiveChar.personality) {
        curActiveChar.personality[trait] = numVal;
        // 关键联动：拖动参数滑块时实时联动更新雷达图！
        updateRadarChartFromPersonality(curActiveChar.personality);
      }

      // 防抖 300ms 写回后端
      clearTimeout(traitUpdateTimer);
      traitUpdateTimer = setTimeout(async () => {
        if (!currentProject || !curActiveChar) return;
        try {
          await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/characters/update_trait`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              character_name: curActiveChar.name,
              trait_name: trait,
              value: numVal,
            }),
          });
          showToast(`已持久化【${curActiveChar.name}】的「${trait}」= ${numVal}`);
        } catch (e) {
          console.error("更新特质失败:", e);
        }
      }, 300);
    }

    // 自主添加特质
    async function confirmAddTrait() {
      const nameInput = document.getElementById('new-trait-name');
      const valInput = document.getElementById('new-trait-value');
      const traitName = nameInput.value.trim();
      const initialVal = Number(valInput.value) || 5;
      if (!traitName) return alert('请输入特质名称');

      if (currentProject && curActiveChar) {
        try {
          const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/characters/add_trait`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              character_name: curActiveChar.name,
              trait_name: traitName,
              initial_value: initialVal,
            }),
          });
          if (res.ok) {
            curActiveChar.personality[traitName] = initialVal;
            renderTraitsSliders(curActiveChar);
            updateRadarChartFromPersonality(curActiveChar.personality);
            showToast(`成功为【${curActiveChar.name}】添加「${traitName}」特质！`);
          }
        } catch (e) {
          console.error("添加特质失败:", e);
        }
      } else {
        // 演示模式降级
        if (curActiveChar) {
          if (!curActiveChar.personality) curActiveChar.personality = {};
          curActiveChar.personality[traitName] = initialVal;
          renderTraitsSliders(curActiveChar);
          updateRadarChartFromPersonality(curActiveChar.personality);
        }
      }
      closeAddTraitModal();
      nameInput.value = '';
    }

    // 新增章节弹窗
    async function addNewChapterPrompt() {
      const title = prompt("请输入新章节标题：", "新的征途");
      if (!title || !title.trim()) return;
      if (!currentProject) {
        alert("请先选中或创建一个小说项目！");
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(currentProject.name)}/chapters/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: title.trim(), content: "（新章节，点击开始创作……）" }),
        });
        if (res.ok) {
          const ret = await res.json();
          showToast(`已创建第 ${ret.chapter} 章《${ret.title}》！`);
          onSelectProject(currentProject.name);
        }
      } catch (err) {
        console.error("创建章节失败:", err);
      }
    }

    // ========================================================
