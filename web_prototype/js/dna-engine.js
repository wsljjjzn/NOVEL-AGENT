// web_prototype/js/dna-engine.js — 小说创作基因双螺旋原生 Canvas 2D 终端自检引擎

    // 0. 小说创作基因双螺旋 ASCII 终端引擎 (NovelDnaEngine)
    // 采用二次方角速度加速模型 + 持续巡航自旋 + 大画幅高振幅纯终端波形
    // ========================================================
            // 0. 小说创作基因双螺旋原生 Canvas 2D 引擎 (NovelDnaEngine)
    // 缓速轻灵自旋 + 鼠标物理磁吸/扰动波形 + 径向脉冲光圈 + 3D 深度粒子
    // ========================================================
    class NovelDnaEngine {
      constructor(canvasId) {
        this.canvas = document.getElementById('dna-interactive-canvas') || document.getElementById(canvasId);
        this.ctx = this.canvas && this.canvas.getContext ? this.canvas.getContext('2d') : null;
        this.angle = 0;
        this.progress = 0.05;
        this.baseSpeed = 0.012;   // 缓速旋转，优雅从容
        this.maxSpeed = 0.038;
        this.isLocked = false;
        this.animFrameId = null;

        // 鼠标物理扰动参数
        this.pointerX = -9999;
        this.pointerY = -9999;
        this.smoothPointerX = -9999;
        this.smoothPointerY = -9999;
        this.isHovering = false;
        this.hoverIntensity = 0;
        this.ripple = 0;
        this.rippleCenterX = 0;

        this.novelPairs = ['0xPLOT', '0xCHAR', '0xCLUE', '0xFLOW', '0xARC', '0xWORD', 'A-T', 'C-G'];

        if (this.canvas) {
          this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            this.pointerX = e.clientX - rect.left;
            this.pointerY = e.clientY - rect.top;
            this.isHovering = true;
          });
          this.canvas.addEventListener('mouseleave', () => {
            this.isHovering = false;
          });
          this.canvas.addEventListener('click', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            this.rippleCenterX = e.clientX - rect.left;
            this.ripple = 1.0;
          });
        }

        window.addEventListener('resize', () => {
          this.updateDimensions();
        });
        this.updateDimensions();
      }

      updateDimensions() {
        if (!this.canvas) return;
        const rect = this.canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        this.width = rect.width || 600;
        this.height = rect.height || 220;
        this.canvas.width = Math.floor(this.width * dpr);
        this.canvas.height = Math.floor(this.height * dpr);
        if (this.ctx) {
          if (this.ctx.setTransform) {
            this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          }
        }
      }

      getAngularVelocity() {
        if (this.progress >= 1.0) return 0.014; // 巡航稳态：轻柔慢速旋转 (~4-5秒一圈)
        const p = Math.max(0, Math.min(1, this.progress));
        return this.baseSpeed + (this.maxSpeed - this.baseSpeed) * Math.pow(p, 2);
      }

      setProgress(val) {
        this.progress = Math.max(0, Math.min(1, val));
        if (this.progress >= 1.0 && !this.isLocked) {
          this.lock();
        }
        this.updateHud();
      }

      lock() {
        this.isLocked = true;
        this.progress = 1.0;
        const badge = document.getElementById('dna-stage-badge');
        if (badge) {
          badge.className = "px-2.5 py-0.5 bg-[#5e6ad2] text-white font-bold tracking-wider text-[10px] rounded-full shadow-sm";
          badge.innerText = "STAGE: CRUISE_ACTIVE // SYNCHED";
        }
        const monSync = document.getElementById('mon-sync-state');
        if (monSync) {
          monSync.className = "text-[9px] px-2 py-0.5 bg-[#5e6ad2] text-white font-bold rounded-full shadow-sm";
          monSync.innerText = "CRUISING";
        }
      }

      updateHud() {
        const pctEl = document.getElementById('dna-hud-percent');
        if (pctEl) pctEl.innerText = `${Math.round(this.progress * 100)}%`;

        const clueEl = document.getElementById('hud-gene-clue');
        const arcEl = document.getElementById('hud-gene-arc');
        const polarEl = document.getElementById('hud-gene-polar');
        const climaxEl = document.getElementById('hud-gene-climax');

        const monClue = document.getElementById('mon-gene-clue');
        const monArc = document.getElementById('mon-gene-arc');
        const monPolar = document.getElementById('mon-gene-polar');
        const monClimax = document.getElementById('mon-gene-climax');
        const monBarClue = document.getElementById('mon-bar-clue');
        const monBarArc = document.getElementById('mon-bar-arc');
        const monBarPolar = document.getElementById('mon-bar-polar');
        const monBarClimax = document.getElementById('mon-bar-climax');
        const monStackPtr = document.getElementById('mon-stack-ptr');
        const monAngVel = document.getElementById('mon-ang-vel');

        if (monStackPtr) {
          const memOffset = `0x7FFE${Math.floor(0x1000 + this.progress * 0xE000).toString(16).toUpperCase()}`;
          monStackPtr.innerText = memOffset;
        }

        if (monAngVel) {
          const curVel = this.getAngularVelocity();
          monAngVel.innerText = `${(curVel * 10).toFixed(1)} RAD/S`;
        }

        if (this.progress >= 0.20) {
          if (clueEl) clueEl.innerHTML = '<span class="text-[#5e6ad2] font-bold">READY</span>';
          if (monClue) {
            monClue.innerHTML = '<span class="text-[#5e6ad2] font-bold">[SYNCED]</span>';
            if (monBarClue) monBarClue.style.width = '100%';
          }
        }
        if (this.progress >= 0.50) {
          if (arcEl) arcEl.innerHTML = '<span class="text-[#5e6ad2] font-bold">ACTIVE</span>';
          if (monArc) {
            monArc.innerHTML = '<span class="text-[#5e6ad2] font-bold">[ACTIVE]</span>';
            if (monBarArc) monBarArc.style.width = '100%';
          }
        }
        if (this.progress >= 0.75) {
          if (polarEl) polarEl.innerHTML = '<span class="text-[#5e6ad2] font-bold">VERIFIED</span>';
          if (monPolar) {
            monPolar.innerHTML = '<span class="text-[#5e6ad2] font-bold">[VERIFIED]</span>';
            if (monBarPolar) monBarPolar.style.width = '100%';
          }
        }
        if (this.progress >= 1.0) {
          if (climaxEl) climaxEl.innerHTML = '<span class="text-[#5e6ad2] font-bold">LOCKED</span>';
          if (monClimax) {
            monClimax.innerHTML = '<span class="text-[#5e6ad2] font-bold">[LOCKED]</span>';
            if (monBarClimax) monBarClimax.style.width = '100%';
          }
        }

        const badge = document.getElementById('dna-stage-badge');
        if (badge && !this.isLocked) {
          if (this.progress < 0.25) {
            badge.innerText = "STAGE: COLD_START [0.2 Hz]";
          } else if (this.progress < 0.80) {
            badge.innerText = `STAGE: LOAD_ACCEL [${(this.getAngularVelocity() * 25).toFixed(1)} Hz]`;
          } else {
            badge.innerText = "STAGE: TURBO_BURST [CRITICAL]";
          }
        }
      }

      start() {
        this.updateDimensions();
        const loop = () => {
          this.tick();
          this.render();
          this.animFrameId = requestAnimationFrame(loop);
        };
        this.animFrameId = requestAnimationFrame(loop);
      }

      stop() {
        if (this.animFrameId) {
          cancelAnimationFrame(this.animFrameId);
          this.animFrameId = null;
        }
      }

      tick() {
        const speed = this.getAngularVelocity();
        this.angle = (this.angle + speed) % (Math.PI * 2);

        // 鼠标物理平滑追随
        if (this.isHovering) {
          this.hoverIntensity = Math.min(1.0, this.hoverIntensity + 0.08);
          if (this.smoothPointerX === -9999) {
            this.smoothPointerX = this.pointerX;
            this.smoothPointerY = this.pointerY;
          } else {
            this.smoothPointerX += (this.pointerX - this.smoothPointerX) * 0.18;
            this.smoothPointerY += (this.pointerY - this.smoothPointerY) * 0.18;
          }
        } else {
          this.hoverIntensity = Math.max(0.0, this.hoverIntensity - 0.04);
        }

        if (this.ripple > 0) {
          this.ripple = Math.max(0, this.ripple - 0.025);
        }
      }

      render() {
        if (!this.ctx || !this.canvas) return;
        const ctx = this.ctx;
        const w = this.width;
        const h = this.height;

        ctx.clearRect(0, 0, w, h);

        const isDark = document.documentElement.classList.contains('dark');
        const lavender = '#5e6ad2';
        const lavenderLight = isDark ? '#828fff' : '#4e5ac0';
        const hairlineColor = isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.06)';
        const textColor = isDark ? 'rgba(247, 248, 248, 0.9)' : 'rgba(14, 16, 23, 0.9)';

        // 1. 中轴基准微网格
        ctx.strokeStyle = hairlineColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const centerY = h / 2;
        ctx.moveTo(15, centerY);
        ctx.lineTo(w - 15, centerY);
        ctx.stroke();

        // 2. 双螺旋基础波长与振幅
        const baseAmp = Math.min(h * 0.35, 64);
        const waveLen = Math.max(160, w * 0.32);
        const step = 5;
        const numPoints = Math.floor((w - 30) / step);
        const startX = 15;
        const rungInterval = 26;

        // 计算任意 X 坐标下的鼠标物理扰动参数
        const getPerturbation = (x) => {
          if (this.hoverIntensity <= 0.01) return { ampScale: 1, waveOffset: 0, magnetY: 0, influence: 0 };
          const dx = x - this.smoothPointerX;
          const dist = Math.abs(dx);
          // 高斯扰动包络（半径约 95px）
          const influence = this.hoverIntensity * Math.exp(-Math.pow(dist / 95, 2));
          // 振幅膨胀（鼠标处振幅隆起高达 70%）
          const ampScale = 1.0 + influence * 0.70;
          // 波动相位变形涟漪
          const waveOffset = influence * Math.sin(dx * 0.06 - this.angle * 2.8) * 16;
          // 垂直磁吸力（向光标 Y 方向靠拢）
          const magnetY = (this.smoothPointerY - centerY) * influence * 0.45;
          return { ampScale, waveOffset, magnetY, influence };
        };

        // 3. 点击冲击波环 (Shockwave)
        if (this.ripple > 0) {
          const rippleRadius = (1.0 - this.ripple) * (w * 0.45);
          ctx.strokeStyle = `rgba(94, 106, 210, ${this.ripple * 0.4})`;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(this.rippleCenterX || (w / 2), centerY, rippleRadius, 0, Math.PI * 2);
          ctx.stroke();
        }

        // 4. 梯级 (Rungs / 碱基对键)
        for (let i = 0; i < numPoints; i++) {
          const x = startX + i * step;
          if (Math.floor(x) % rungInterval < step) {
            const { ampScale, waveOffset, magnetY, influence } = getPerturbation(x);
            const currentAmp = baseAmp * ampScale;
            const phase = (x / waveLen) * Math.PI * 2 + this.angle + (influence * 0.6);

            const yA = centerY + currentAmp * Math.sin(phase) + waveOffset + magnetY;
            const yB = centerY - currentAmp * Math.sin(phase) - waveOffset + magnetY;
            const zMid = Math.cos(phase);

            // 梯级颜色受鼠标悬停局部高光提亮
            const alphaBase = 0.12 + (zMid + 1) * 0.22 + influence * 0.35;
            ctx.strokeStyle = influence > 0.3
              ? `rgba(130, 143, 255, ${Math.min(0.9, alphaBase)})`
              : `rgba(94, 106, 210, ${Math.min(0.7, alphaBase)})`;
            ctx.lineWidth = 1.2 + influence * 1.5;
            ctx.beginPath();
            ctx.moveTo(x, yA);
            ctx.lineTo(x, yB);
            ctx.stroke();

            // 中间节点显示基因标签
            if (Math.abs(yA - yB) > 38 && zMid > 0.15) {
              const pairIdx = Math.floor(x / 55) % this.novelPairs.length;
              const tag = this.novelPairs[pairIdx];
              ctx.font = '9px "SF Mono", "JetBrains Mono", monospace';
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = isDark ? 'rgba(18, 19, 21, 0.9)' : 'rgba(255, 255, 255, 0.9)';
              const midY = (yA + yB) / 2;
              const tw = ctx.measureText(tag).width + 6;
              ctx.fillRect(x - tw/2, midY - 6, tw, 12);
              ctx.strokeStyle = influence > 0.3 ? lavenderLight : lavender;
              ctx.strokeRect(x - tw/2, midY - 6, tw, 12);
              ctx.fillStyle = textColor;
              ctx.fillText(tag, x, midY);
            }
          }
        }

        // 5. 绘制两条螺旋链 (Strand 0 & Strand 1)
        for (const strand of [0, 1]) {
          ctx.beginPath();
          for (let i = 0; i <= numPoints; i++) {
            const x = startX + i * step;
            const { ampScale, waveOffset, magnetY, influence } = getPerturbation(x);
            const currentAmp = baseAmp * ampScale;
            const phase = (x / waveLen) * Math.PI * 2 + this.angle + (strand * Math.PI) + (influence * 0.6);
            const y = centerY + currentAmp * Math.sin(phase) + (strand === 0 ? waveOffset : -waveOffset) + magnetY;

            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.strokeStyle = strand === 0 ? lavender : lavenderLight;
          ctx.lineWidth = 2.2;
          ctx.stroke();

          // 沿线绘制 3D 深度粒子与鼠标近距发光光晕
          for (let i = 0; i <= numPoints; i += 2) {
            const x = startX + i * step;
            const { ampScale, waveOffset, magnetY, influence } = getPerturbation(x);
            const currentAmp = baseAmp * ampScale;
            const phase = (x / waveLen) * Math.PI * 2 + this.angle + (strand * Math.PI) + (influence * 0.6);
            const y = centerY + currentAmp * Math.sin(phase) + (strand === 0 ? waveOffset : -waveOffset) + magnetY;
            const z = Math.cos(phase);
            const r = 2.0 + (z + 1) * 1.4 + influence * 2.5;

            ctx.fillStyle = strand === 0 ? lavender : lavenderLight;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fill();

            // 悬停区域粒子增加柔和外发光
            if (influence > 0.4 && z > 0) {
              ctx.fillStyle = `rgba(130, 143, 255, ${influence * 0.35})`;
              ctx.beginPath();
              ctx.arc(x, y, r * 2.2, 0, Math.PI * 2);
              ctx.fill();
            }
          }
        }
      }
    }

let novelDnaEngine = null;
let isSplashReady = false;
let splashSkipRequested = false;

    // 快速跳过终端诊断，瞬间打满日志并解锁工作台
    function skipSplashDiagnostics() {
      splashSkipRequested = true;
      const skipBtn = document.getElementById('btn-skip-splash');
      if (skipBtn) {
        skipBtn.innerHTML = '<span>⚡</span><span>已加速 [100%]</span>';
        skipBtn.classList.add('opacity-40', 'pointer-events-none');
      }
    }

    // 格式化终端输出流中的高光状态与微秒时间戳
    function formatLogMarkup(text) {
      if (!text) return '';
      let safe = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // 1. 微秒/十六进制时间戳高亮 [ +0.xxx s ]
      safe = safe.replace(/(\[\+[0-9.]+s\])/g, '<span class="text-emerald-600/90 font-mono text-[10px]">$1</span>');

      // 2. 状态标签高亮
      const badges = [
        { label: '[PASS]', cls: 'bg-emerald-950 text-emerald-300 border border-emerald-600/80 font-bold' },
        { label: '[VERIFIED]', cls: 'bg-emerald-950 text-emerald-200 border border-emerald-500 font-bold' },
        { label: '[ONLINE]', cls: 'bg-emerald-950 text-emerald-400 border border-emerald-700 font-semibold' },
        { label: '[ARMED]', cls: 'bg-emerald-950 text-amber-300 border border-amber-600/80 font-bold' },
        { label: '[READY]', cls: 'bg-emerald-950 text-emerald-300 border border-emerald-600 font-semibold' },
        { label: '[100%]', cls: 'bg-emerald-950 text-emerald-200 border border-emerald-400 font-bold phosphor-glow-subtle' },
        { label: '[OK]', cls: 'text-emerald-400 font-bold' },
        { label: '[LOADED]', cls: 'bg-emerald-950 text-amber-300 border border-amber-600/80 font-semibold' },
      ];

      badges.forEach(b => {
        const escaped = b.label.replace('[', '\\[').replace(']', '\\]');
        safe = safe.replace(new RegExp(escaped, 'g'), `<span class="px-1 py-0.2 rounded text-[10px] font-mono ${b.cls}">${b.label}</span>`);
      });

      // 3. 模块名前缀高亮，如 [BOOT/SOCKET], [SYS/RUNTIME], [KERNEL/ISOLATION], [FORESHADOW/LEDGER] 等
      safe = safe.replace(/(\[[A-Z0-9_\/-]+\])(?!\s*<\/span>)/g, '<span class="text-emerald-400 font-semibold">$1</span>');

      // 4. 名家创作法则彩蛋整行增亮
      if (text.includes('[EPIGRAM/LAW]')) {
        safe = `<span class="text-amber-300/95 phosphor-glow-subtle font-medium">${safe}</span>`;
      }

      return safe;
    }

    // 加快一倍速度：每 10 个字 50ms（即 0.05秒10字，约 200 字/秒），支持语法高亮与即时跳过
    async function typeLogLine(container, text, chunkSize = 35, delayMs = 12) {
      if (!container) return;
      const line = document.createElement('div');
      line.className = "flex items-start space-x-1.5 font-mono text-[11px] leading-relaxed";
      
      const isLaw = text.includes('[EPIGRAM/LAW]');

      const prompt = document.createElement('span');
      if (isLaw) {
        prompt.className = "text-amber-400 shrink-0 font-bold select-none phosphor-glow-subtle";
        prompt.textContent = "★>";
      } else {
        prompt.className = "text-emerald-500 shrink-0 font-bold select-none";
        prompt.textContent = ">>";
      }
      line.appendChild(prompt);

      const content = document.createElement('span');
      content.className = isLaw ? "text-amber-300/95 font-medium break-all" : "text-emerald-300 break-all";
      line.appendChild(content);

      const cursor = document.createElement('span');
      cursor.className = isLaw ? "text-amber-400 animate-pulse font-black shrink-0 select-none" : "text-emerald-400 animate-pulse font-black shrink-0 select-none";
      cursor.textContent = "▋";
      line.appendChild(cursor);

      container.appendChild(line);
      container.scrollTop = container.scrollHeight;

      if (splashSkipRequested) {
        cursor.remove();
        content.innerHTML = formatLogMarkup(text);
        container.scrollTop = container.scrollHeight;
        return;
      }

      // 逐块打字机输出
      for (let i = 0; i < text.length; i += chunkSize) {
        if (splashSkipRequested) {
          break;
        }
        content.textContent += text.slice(i, i + chunkSize);
        container.scrollTop = container.scrollHeight;
        await new Promise(r => setTimeout(r, delayMs));
      }
      cursor.remove();
      content.innerHTML = formatLogMarkup(text);
      container.scrollTop = container.scrollHeight;
    }

    // 关闭载入自检遮罩并进入企划构思视角
    function dismissSplashScreen() {
      initThemeMode();
      if (novelDnaEngine) {
        novelDnaEngine.stop();
      }
      const splash = document.getElementById('splash-doctor-screen');
      if (splash) {
        splash.classList.add('opacity-0', 'pointer-events-none');
        setTimeout(() => splash.remove(), 700);
      }
      // 保证进入工作台直接聚焦在【企划构思】
      switchPerspective('planning');
    }

    // 全局快捷键：在启动界面进行中按 SPACE / ENTER 可跳过打字，就绪后按 ENTER 进入工作台
    document.addEventListener('keydown', (e) => {
      const splash = document.getElementById('splash-doctor-screen');
      if (!splash || splash.classList.contains('opacity-0')) return;

      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        if (!isSplashReady) {
          skipSplashDiagnostics();
        } else {
          dismissSplashScreen();
        }
      }
    });

    // ========================================================
