// web_prototype/js/ui.js — UI 交互管理器（分栏调节、卡片微动效、Zen专注模式、全局Toast与快捷键）

    // 工作区左右分栏自由拖拽调节管理器 (WorkspaceResizer)
    // 支持左右侧边栏自由拖动伸缩、持久化记忆、双击复位、安全边界保护
    // ========================================================
    function initWorkspaceResizers() {
      const leftSidebar = document.getElementById('sidebar-left');
      const rightSidebar = document.getElementById('sidebar-right');
      const leftResizer = document.getElementById('resizer-left');
      const rightResizer = document.getElementById('resizer-right');

      if (!leftSidebar || !rightSidebar || !leftResizer || !rightResizer) return;

      // 1. 从 localStorage 读取历史记忆宽度
      const savedLeftW = localStorage.getItem('novel_workspace_left_width');
      if (savedLeftW) {
        const w = parseInt(savedLeftW, 10);
        if (w >= 180 && w <= 550) leftSidebar.style.width = w + 'px';
      }

      const savedRightW = localStorage.getItem('novel_workspace_right_width');
      if (savedRightW) {
        const w = parseInt(savedRightW, 10);
        if (w >= 220 && w <= 650) rightSidebar.style.width = w + 'px';
      }

      // 2. 左侧手柄拖拽逻辑
      leftResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = leftSidebar.offsetWidth;
        document.body.classList.add('cursor-col-resize', 'select-none');

        function onMouseMove(moveEvent) {
          const deltaX = moveEvent.clientX - startX;
          const winWidth = window.innerWidth;
          const rightW = rightSidebar.offsetWidth || 320;
          const maxAllowed = Math.min(550, winWidth - rightW - 360);
          const newWidth = Math.max(180, Math.min(maxAllowed, startWidth + deltaX));
          leftSidebar.style.width = newWidth + 'px';
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          document.body.classList.remove('cursor-col-resize', 'select-none');
          localStorage.setItem('novel_workspace_left_width', leftSidebar.offsetWidth);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });

      // 双击左手柄恢复默认 280px
      leftResizer.addEventListener('dblclick', () => {
        leftSidebar.style.width = '280px';
        localStorage.setItem('novel_workspace_left_width', 280);
        if (typeof showToast === 'function') showToast('已恢复章节侧栏默认宽度 (280px)');
      });

      // 3. 右侧手柄拖拽逻辑
      rightResizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startWidth = rightSidebar.offsetWidth;
        document.body.classList.add('cursor-col-resize', 'select-none');

        function onMouseMove(moveEvent) {
          const deltaX = moveEvent.clientX - startX;
          const winWidth = window.innerWidth;
          const leftW = leftSidebar.offsetWidth || 280;
          const maxAllowed = Math.min(650, winWidth - leftW - 360);
          const newWidth = Math.max(220, Math.min(maxAllowed, startWidth - deltaX));
          rightSidebar.style.width = newWidth + 'px';
        }

        function onMouseUp() {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          document.body.classList.remove('cursor-col-resize', 'select-none');
          localStorage.setItem('novel_workspace_right_width', rightSidebar.offsetWidth);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });

      // 双击右手柄恢复默认 320px
      rightResizer.addEventListener('dblclick', () => {
        rightSidebar.style.width = '320px';
        localStorage.setItem('novel_workspace_right_width', 320);
        if (typeof showToast === 'function') showToast('已恢复副驾侧栏默认宽度 (320px)');
      });
    }

    // 核心初始化：终端同款 Doctor 自检 + 项目探测 + 每5字0.1s打字机日志输出
    // ========================================================

    // 3D 卡片悬停朝向鼠标微动效 (3D Perspective Tilt Cards)
    // 鼠标在卡片上移动时，卡片产生轻盈的面向鼠标 3D 偏转与动态光泽
    // ========================================================
    function initTiltCards() {
      const cards = document.querySelectorAll('.tilt-card');
      cards.forEach(card => {
        if (card.dataset.tiltBound) return;
        card.dataset.tiltBound = 'true';

        card.addEventListener('mousemove', (e) => {
          const rect = card.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const y = e.clientY - rect.top;
          const centerX = rect.width / 2;
          const centerY = rect.height / 2;

          // 适度角度：±3.5度，兼顾高级感与稳定性
          const rotateX = ((centerY - y) / centerY) * 3.5;
          const rotateY = ((x - centerX) / centerX) * 3.5;

          card.style.transform = `perspective(800px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-2px)`;
        });

        card.addEventListener('mouseleave', () => {
          card.style.transform = 'perspective(800px) rotateX(0deg) rotateY(0deg) translateY(0px)';
        });
      });
    }



    // 轻量全局 Toast 提示 (1秒后平滑淡出消失)
    let globalToastTimer = null;
    function showToast(msg, isSuccess = true) {
      let toast = document.getElementById('global-toast');
      if (!toast) {
        toast = document.createElement('div');
        toast.id = 'global-toast';
        toast.className = 'fixed bottom-10 right-8 z-50 px-4 py-2 rounded-lg text-xs font-medium shadow-2xl transition-all duration-500 ease-out transform translate-y-2 opacity-0 pointer-events-none flex items-center space-x-2';
        document.body.appendChild(toast);
      }

      if (globalToastTimer) {
        clearTimeout(globalToastTimer);
      }

      toast.className = isSuccess 
        ? 'fixed bottom-10 right-8 z-50 px-4 py-2.5 rounded-lg text-xs font-medium shadow-2xl transition-all duration-500 ease-out transform translate-y-0 opacity-100 flex items-center space-x-2 bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 backdrop-blur-md select-none'
        : 'fixed bottom-10 right-8 z-50 px-4 py-2.5 rounded-lg text-xs font-medium shadow-2xl transition-all duration-500 ease-out transform translate-y-0 opacity-100 flex items-center space-x-2 bg-rose-950/90 text-rose-300 border border-rose-500/50 backdrop-blur-md select-none';
      toast.innerHTML = isSuccess ? `<span>✓</span><span>${msg}</span>` : `<span>✕</span><span>${msg}</span>`;

      // 1 秒之后平滑淡出消失
      globalToastTimer = setTimeout(() => {
        toast.classList.remove('translate-y-0', 'opacity-100');
        toast.classList.add('translate-y-2', 'opacity-0', 'pointer-events-none');
      }, 1000);
    }


    // 动态交互：沉浸专注模式 (Zen Mode)
    // ========================================================
    function toggleZenMode() {
      const persp = document.getElementById('perspective-writing');
      if (!persp) return;
      const isZen = persp.classList.toggle('zen-mode-active');
      const btn = document.getElementById('btn-toggle-zen');
      if (btn) {
        btn.innerHTML = isZen 
          ? `<span>✕</span><span class="hidden sm:inline">退出专注</span>` 
          : `<span>🎯</span><span class="hidden sm:inline">专注模式</span>`;
        if (isZen) {
          btn.classList.add('bg-[#5e6ad2]', 'text-white');
        } else {
          btn.classList.remove('bg-[#5e6ad2]', 'text-white');
        }
      }
      if (typeof showToast === 'function') {
        showToast(isZen ? '已进入沉浸专注写作 (按 ESC 退出)' : '已恢复标准三栏工作台');
      }
    }

    // 全局按键：ESC 退出专注模式
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const persp = document.getElementById('perspective-writing');
        if (persp && persp.classList.contains('zen-mode-active')) {
          toggleZenMode();
        }
      }
    });

    // ========================================================
    // 动态交互：雷达图悬停提示与随机波动
    // ========================================================
    function setupRadarInteractions() {
      const svg = document.getElementById('radar-svg-canvas');
      const tooltip = document.getElementById('radar-live-tooltip');
      const tipText = document.getElementById('radar-tooltip-text');
      if (!svg || !tooltip) return;

      for (let i = 0; i < 5; i++) {
        const dot = document.getElementById(`radar-dot-${i}`);
        const lbl = document.getElementById(`radar-lbl-${i}`);
        [dot, lbl].forEach(el => {
          if (!el) return;
          el.style.cursor = 'pointer';
          el.addEventListener('mouseenter', () => {
            const name = lbl ? lbl.textContent : '特质';
            let val = '7.5';
            if (curActiveChar && curActiveChar.personality) {
              const matched = Object.entries(curActiveChar.personality).find(([k]) => k.includes(name) || name.includes(k));
              if (matched) val = matched[1];
            }
            if (tipText) tipText.innerHTML = `✦ <b>${name}</b>: ${val} / 10 · 实时联动`;
            tooltip.classList.remove('opacity-0');
          });
          el.addEventListener('mouseleave', () => {
            tooltip.classList.add('opacity-0');
          });
        });
      }
    }

