/* ══════════════════════════════════════════════════════
   TRIPP — HUD Engine
   Canvas fullscreen always. UI hugs edges. Center free.
   White map → dark globe theme interpolation.
   ══════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const FRAMES = 200;
  const imgs = new Array(FRAMES);
  let loaded = 0;
  let curFrame = 0;
  let progress = 0; // 0 → 1

  /* ─── CANVAS ─────────────────────────────────── */
  const canvas = document.getElementById('worldCanvas');
  const ctx = canvas.getContext('2d');

  function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    drawFrame(curFrame);
  }

  function drawFrame(i) {
    i = Math.max(0, Math.min(FRAMES - 1, i));
    const img = imgs[i];
    if (!img || !img.complete || !img.naturalWidth) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cr = canvas.width / canvas.height;
    const ir = img.naturalWidth / img.naturalHeight;
    let dw, dh, dx, dy;
    if (ir > cr) {
      dh = canvas.height; dw = dh * ir;
      dx = (canvas.width - dw) / 2; dy = 0;
    } else {
      dw = canvas.width; dh = dw / ir;
      dx = 0; dy = (canvas.height - dh) / 2;
    }
    ctx.drawImage(img, dx, dy, dw, dh);
  }

  function preload() {
    for (let i = 1; i <= FRAMES; i++) {
      const img = new Image();
      img.src = `/static/landing/images/ezgif-frame-${String(i).padStart(3,'0')}.jpg`;
      img.onload = () => { loaded++; if (loaded === 1) { resizeCanvas(); drawFrame(0); } };
      imgs[i - 1] = img;
    }
  }
  preload();
  window.addEventListener('resize', resizeCanvas);

  /* ─── DYNAMIC THEME ENGINE ────────────────────── */
  const root = document.documentElement;

  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpRGB(r1,g1,b1,r2,g2,b2,t) {
    return [Math.round(lerp(r1,r2,t)),Math.round(lerp(g1,g2,t)),Math.round(lerp(b1,b2,t))];
  }

  function applyTheme(p) {
    // p=0: white map phase  |  p=1: dark globe phase

    // Card bg: white glass → dark glass
    const [cr,cg,cb] = lerpRGB(255,255,255, 6,13,26, p);
    const ca = lerp(0.12, 0.62, p);
    root.style.setProperty('--dcard', `rgba(${cr},${cg},${cb},${ca})`);

    // Primary text: dark → warm white
    const [tr,tg,tb] = lerpRGB(12,10,10, 240,237,232, p);
    root.style.setProperty('--dt', `rgb(${tr},${tg},${tb})`);

    // Secondary text
    const [t2r,t2g,t2b] = lerpRGB(80,74,70, 138,155,176, p);
    root.style.setProperty('--dt2', `rgb(${t2r},${t2g},${t2b})`);

    // Border
    if (p < 0.5) {
      const ba = lerp(0.10, 0.03, p * 2);
      root.style.setProperty('--dborder', `rgba(0,0,0,${ba.toFixed(2)})`);
    } else {
      const ba = lerp(0.03, 0.22, (p - 0.5) * 2);
      root.style.setProperty('--dborder', `rgba(232,184,75,${ba.toFixed(2)})`);
    }

    // Blur amount
    const blurPx = Math.round(lerp(18, 26, p));
    root.style.setProperty('--dblur', `${blurPx}px`);

    // Stars fade in
    const sv = Math.max(0, (p - 0.35) / 0.65);
    document.querySelectorAll('.star').forEach(s => {
      s.style.opacity = (sv * parseFloat(s.dataset.pk)).toFixed(2);
    });

    // Body bg tint
    const bodyR = Math.round(lerp(245, 6, p));
    const bodyG = Math.round(lerp(240, 13, p));
    const bodyB = Math.round(lerp(235, 26, p));
    document.body.style.background = `rgb(${bodyR},${bodyG},${bodyB})`;
  }

  /* ─── STARFIELD ───────────────────────────────── */
  function buildStars() {
    const sf = document.getElementById('stars');
    for (let i = 0; i < 90; i++) {
      const s = document.createElement('div');
      s.className = 'star';
      const sz = (Math.random() * 1.8 + 0.6).toFixed(1);
      const pk = (Math.random() * 0.45 + 0.12).toFixed(2);
      s.dataset.pk = pk;
      s.style.cssText = `
        left:${(Math.random()*100).toFixed(1)}%;
        top:${(Math.random()*100).toFixed(1)}%;
        width:${sz}px; height:${sz}px;
        --dur:${(Math.random()*5+2.5).toFixed(1)}s;
        --delay:${(Math.random()*7).toFixed(1)}s;
        --pk:${pk};
      `;
      sf.appendChild(s);
    }
  }
  buildStars();

  /* ─── HERO TITLE SPLIT ────────────────────────── */
  const titleEl = document.getElementById('hudTitle');
  const titleWords = 'Plan a trip that feels effortless.'.split(' ');
  const goldItalic = ['effortless.'];

  titleWords.forEach((w, i) => {
    const sp = document.createElement('span');
    sp.className = 'word' + (goldItalic.includes(w) ? ' gold-ital' : '');
    sp.textContent = w;
    titleEl.appendChild(sp);
    if (i < titleWords.length - 1) titleEl.appendChild(document.createTextNode(' '));
  });

  /* ─── HERO ENTRANCE ───────────────────────────── */
  function heroIn() {
    // TL / TR
    setTimeout(() => document.getElementById('hudTL').classList.add('vis'), 100);
    setTimeout(() => document.getElementById('hudTR').classList.add('vis'), 180);

    // Left panel slides in
    setTimeout(() => document.getElementById('hudLeft').classList.add('vis'), 300);

    // Right stats
    setTimeout(() => document.getElementById('hudRight').classList.add('vis'), 420);

    // Badge
    setTimeout(() => document.getElementById('hudBadge').classList.add('vis'), 650);

    // Words
    const wEls = titleEl.querySelectorAll('.word');
    wEls.forEach((w, i) => {
      setTimeout(() => w.classList.add('vis'), 800 + i * 80);
    });
    const afterWords = 800 + wEls.length * 80;

    // Subtitle & buttons
    setTimeout(() => document.getElementById('hudSub').classList.add('vis'), afterWords + 60);
    setTimeout(() => document.getElementById('hudBtns').classList.add('vis'), afterWords + 200);

    // Bottom bar
    setTimeout(() => {
      const hb = document.getElementById('hudBottom');
      hb.classList.add('vis');
      hb.querySelectorAll('.feat-pill').forEach((fp, i) => {
        setTimeout(() => fp.classList.add('vis'), i * 90);
      });
    }, afterWords + 400);

    // Stats counter
    setTimeout(animateCounters, afterWords + 300);
  }

  window.addEventListener('load', heroIn);

  /* ─── COUNTERS ────────────────────────────────── */
  function animateCounters() {
    document.querySelectorAll('.sp-num').forEach(el => {
      const target = parseInt(el.dataset.target);
      const dur = 2200;
      const t0 = performance.now();
      function tick(now) {
        const t = Math.min((now - t0) / dur, 1);
        const ease = 1 - Math.pow(1 - t, 4);
        el.textContent = Math.floor(ease * target).toLocaleString();
        if (t < 1) requestAnimationFrame(tick);
        else el.textContent = target.toLocaleString();
      }
      requestAnimationFrame(tick);
    });
  }

  /* ─── SCROLL ENGINE ───────────────────────────── */
  let ticking = false;

  function onScroll() {
    if (!ticking) { requestAnimationFrame(tick); ticking = true; }
  }

  function tick() {
    const sy = window.scrollY;
    const totalH = document.documentElement.scrollHeight - window.innerHeight;

    // Progress 0→1 over first 2.5 viewport heights
    progress = Math.min(Math.max(sy / (window.innerHeight * 2.5), 0), 1);

    // Canvas frame
    const fi = Math.floor(progress * (FRAMES - 1));
    if (fi !== curFrame) { curFrame = fi; drawFrame(fi); }

    // Theme
    applyTheme(progress);

    // Scroll bar
    document.getElementById('scrollBar').style.width = ((sy / totalH) * 100) + '%';

    // Hide scroll hint
    const sh = document.getElementById('sHint');
    if (sh) sh.style.opacity = Math.max(1 - sy / 180, 0);

    ticking = false;
  }

  window.addEventListener('scroll', onScroll, { passive: true });

  /* ─── INTERSECTION OBSERVERS ──────────────────── */
  function obs(el, fn, thresh = 0.12) {
    if (!el) return;
    new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) fn(e.target); });
    }, { threshold: thresh }).observe(el);
  }

  // Panel 2
  obs(document.querySelector('.p2-left'), el => el.classList.add('vis'));
  obs(document.getElementById('p2Grid'), el => {
    el.classList.add('vis');
    el.querySelectorAll('.fcard').forEach((c, i) => {
      setTimeout(() => c.classList.add('vis'), i * 120);
    });
  });

  // Panel 3
  obs(document.getElementById('p3Wrap'), el => {
    el.classList.add('vis');
    el.querySelectorAll('.p3card').forEach((c, i) => {
      setTimeout(() => {
        c.classList.add('vis');
        setTimeout(() => c.classList.add('glow'), 100);
      }, 380 + i * 150);
    });
    // Trigger priv-title / btn via parent
  });

  // Panel 4
  obs(document.getElementById('p4Grid'), el => {
    document.getElementById('p4Trip').classList.add('vis');
    setTimeout(() => document.getElementById('p4Exp').classList.add('vis'), 110);
  });

  // Reveal all sec-h2, sec-p
  document.querySelectorAll('.sec-h2, .sec-p, .sec-eyebrow').forEach(el => {
    obs(el, e => { e.style.opacity='1'; e.style.transform='none'; }, 0.1);
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity .7s var(--eout), transform .7s var(--eout)';
  });

  /* ─── CUSTOM CURSOR ───────────────────────────── */
  const cur = document.getElementById('cur');
  const ring = document.getElementById('curRing');
  let mx=0, my=0, rx=0, ry=0;

  document.addEventListener('mousemove', e => {
    mx = e.clientX; my = e.clientY;
    cur.style.left = mx + 'px';
    cur.style.top  = my + 'px';
  });

  (function ringLoop() {
    rx += (mx - rx) * 0.11;
    ry += (my - ry) * 0.11;
    ring.style.left = rx + 'px';
    ring.style.top  = ry + 'px';
    requestAnimationFrame(ringLoop);
  })();

  document.querySelectorAll('a,button,.fcard,.p3card,.p4card,.feat-pill').forEach(el => {
    el.addEventListener('mouseenter', () => {
      cur.style.width = cur.style.height = '20px';
      ring.style.width = ring.style.height = '52px';
      ring.style.borderColor = 'rgba(232,184,75,0.7)';
    });
    el.addEventListener('mouseleave', () => {
      cur.style.width = cur.style.height = '10px';
      ring.style.width = ring.style.height = '34px';
      ring.style.borderColor = 'rgba(232,184,75,0.5)';
    });
  });

  /* ─── BUTTON RIPPLE ───────────────────────────── */
  const ripCSS = document.createElement('style');
  ripCSS.textContent = `@keyframes rip{to{transform:scale(1);opacity:0}}`;
  document.head.appendChild(ripCSS);

  document.querySelectorAll('.btn-go,.p4-btn,.tr-cta,.p3-btn,.p4-btn').forEach(btn => {
    btn.style.cssText += 'position:relative;overflow:hidden;';
    btn.addEventListener('click', e => {
      const r = document.createElement('span');
      const rect = btn.getBoundingClientRect();
      const sz = Math.max(rect.width, rect.height) * 2;
      r.style.cssText = `
        position:absolute;width:${sz}px;height:${sz}px;
        top:${e.clientY-rect.top-sz/2}px;left:${e.clientX-rect.left-sz/2}px;
        background:rgba(255,255,255,0.22);border-radius:50%;
        transform:scale(0);animation:rip .55s ease-out forwards;
        pointer-events:none;
      `;
      btn.appendChild(r);
      r.addEventListener('animationend', () => r.remove());
    });
  });

  /* ─── INITIAL THEME ───────────────────────────── */
  applyTheme(0);

})();
