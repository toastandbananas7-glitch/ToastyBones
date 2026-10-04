/* ToastyBones "pro" carousels (2026-10-04). Add-on: remove the <script> tag and the old carousels are unchanged.
   Adds on top of the existing carousel script: 3D coverflow, per-cover glow color, sparks + glitch jolt when a card
   lands in the middle, mouse tilt on the focused card, and a quiet retro blip (mutable). */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var narrow = function () { return window.innerWidth < 640; };
  var clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };

  // ---- scrollbar width, so the full-bleed stage never causes sideways page scroll
  function setSbw() {
    var w = window.innerWidth - document.documentElement.clientWidth;
    document.documentElement.style.setProperty('--sbw', Math.max(0, w) + 'px');
  }
  setSbw();
  window.addEventListener('resize', setSbw);

  // ---- sound (Web Audio; only after a user gesture, which browsers require anyway)
  var audio = null;
  var soundOn = true;
  try { soundOn = localStorage.getItem('tb_sound') !== 'off'; } catch (e) {}
  var lastGesture = 0;
  ['pointerdown', 'keydown', 'touchstart'].forEach(function (ev) {
    window.addEventListener(ev, function () {
      lastGesture = Date.now();
      if (!audio && soundOn) {
        try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audio = null; }
      }
      if (audio && audio.state === 'suspended') audio.resume();
    }, { passive: true, capture: true });
  });
  function blip() {
    if (!soundOn || !audio || reduce || Date.now() - lastGesture > 900) return;
    var t = audio.currentTime;
    var o = audio.createOscillator(), g = audio.createGain();
    o.type = 'square';
    o.frequency.setValueAtTime(420, t);
    o.frequency.exponentialRampToValueAtTime(980, t + 0.07);
    g.gain.setValueAtTime(0.045, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    o.connect(g); g.connect(audio.destination);
    o.start(t); o.stop(t + 0.13);
    // short static burst
    var len = Math.floor(audio.sampleRate * 0.05);
    var buf = audio.createBuffer(1, len, audio.sampleRate), d = buf.getChannelData(0);
    for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    var n = audio.createBufferSource(), ng = audio.createGain();
    n.buffer = buf; ng.gain.value = 0.03;
    n.connect(ng); ng.connect(audio.destination); n.start(t);
  }

  // ---- the cover's dominant hue, turned into a bright neon for the glow
  function glowFor(img, wrap) {
    function go() {
      try {
        var c = document.createElement('canvas'); c.width = c.height = 32;
        var x = c.getContext('2d'); x.drawImage(img, 0, 0, 32, 32);
        var px = x.getImageData(0, 0, 32, 32).data, sx = 0, sy = 0, sw = 0;
        for (var i = 0; i < px.length; i += 4) {
          var r = px[i] / 255, g = px[i + 1] / 255, b = px[i + 2] / 255;
          var mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
          if (d < 0.14 || mx < 0.22) continue;                 // skip grays and near-black
          var h;
          if (mx === r) h = ((g - b) / d) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4;
          h *= 60 * Math.PI / 180;
          var w = d * mx;
          sx += Math.cos(h) * w; sy += Math.sin(h) * w; sw += w;
        }
        if (sw < 0.4) return;                                   // gray cover: keep the default yellow
        var hue = Math.round(((Math.atan2(sy, sx) * 180 / Math.PI) + 360) % 360);
        wrap.style.setProperty('--glow', 'hsl(' + hue + ',100%,60%)');
      } catch (e) { /* tainted or missing image: keep the default yellow */ }
    }
    if (img.complete && img.naturalWidth) go(); else img.addEventListener('load', go, { once: true });
  }

  function spark(wrap) {
    if (reduce) return;
    var n = narrow() ? 8 : 16;
    for (var i = 0; i < n; i++) {
      var s = document.createElement('i');
      s.className = 'pro-spark';
      var a = Math.random() * Math.PI * 2, dist = 60 + Math.random() * 110;
      s.style.setProperty('--dx', Math.round(Math.cos(a) * dist) + 'px');
      s.style.setProperty('--dy', Math.round(Math.sin(a) * dist - 20) + 'px');
      wrap.appendChild(s);
      setTimeout(function (el) { return function () { el.remove(); }; }(s), 800);
    }
  }

  function setup(car) {
    var wraps = Array.prototype.slice.call(car.querySelectorAll('.album-card-wrap'));
    if (!wraps.length) return;
    wraps.forEach(function (w) { var im = w.querySelector('img'); if (im) glowFor(im, w); });

    var raf = null;
    function update() {
      raf = null;
      var cr = car.getBoundingClientRect(), cx = cr.left + cr.width / 2, mob = narrow();
      wraps.forEach(function (w) {
        var r = w.getBoundingClientRect();
        if (!r.width) return;
        var d = clamp((r.left + r.width / 2 - cx) / r.width, -4, 4), ad = Math.abs(d);
        var face = w.querySelector('.coverflow-face');
        if (!face) return;
        face.style.setProperty('--r', (-d * (mob ? 14 : 30)).toFixed(1) + 'deg');
        face.style.setProperty('--s', (mob ? 1.1 - Math.min(ad, 2) * 0.12 : 1.22 - Math.min(ad, 2) * 0.2).toFixed(3));
        w.style.setProperty('--z', String(100 - Math.round(ad * 10)));
      });
    }
    function request() { if (raf === null) raf = requestAnimationFrame(update); }
    car.addEventListener('scroll', request, { passive: true });
    window.addEventListener('resize', request);
    setTimeout(update, 50); setTimeout(update, 500);

    // a card becomes the focused one: sparks, glitch jolt, blip
    var observer = new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        var face = m.target;
        if (!face.classList.contains('is-focused') || (m.oldValue || '').indexOf('is-focused') !== -1) return;
        if (reduce) return;
        blip();
        spark(face.closest('.album-card-wrap'));
        face.classList.remove('pro-glitch'); void face.offsetWidth; face.classList.add('pro-glitch');
        setTimeout(function () { face.classList.remove('pro-glitch'); }, 380);
      });
    });
    wraps.forEach(function (w) {
      var f = w.querySelector('.coverflow-face');
      if (f) observer.observe(f, { attributes: true, attributeFilter: ['class'], attributeOldValue: true });
    });

    // mouse tilt on the focused card (desktop only)
    if (!reduce) {
      car.addEventListener('mousemove', function (e) {
        if (narrow()) return;
        var face = e.target.closest && e.target.closest('.coverflow-face');
        if (!face || !face.classList.contains('is-focused')) return;
        var r = face.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
        face.style.setProperty('--ty', (px * 14).toFixed(1) + 'deg');
        face.style.setProperty('--tx', (-py * 12).toFixed(1) + 'deg');
      });
      car.addEventListener('mouseout', function (e) {
        var face = e.target.closest && e.target.closest('.coverflow-face');
        if (face) { face.style.setProperty('--ty', '0deg'); face.style.setProperty('--tx', '0deg'); }
      });
    }

    // blip when an arrow is clicked (the sound is also tied to the card landing, this covers a tiny step)
    var box = car.parentElement;
    if (box) {
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'pro-sound';
      btn.setAttribute('aria-label', 'Toggle carousel sound');
      var paint = function () { btn.textContent = soundOn ? '🔊' : '🔇'; };
      paint();
      btn.addEventListener('click', function () {
        soundOn = !soundOn;
        try { localStorage.setItem('tb_sound', soundOn ? 'on' : 'off'); } catch (e) {}
        document.querySelectorAll('.pro-sound').forEach(function (b) { b.textContent = soundOn ? '🔊' : '🔇'; });
        if (soundOn && !audio) { try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {} }
      });
      box.appendChild(btn);
    }
  }

  // ---- hover player: the carousel scroller clips it (and card animations offset "fixed" children), so on hover the
  // player element is moved up to <body> and floated above the card. The site's own show/hide code keeps working
  // because it holds a reference to the element, not its position.
  function placePreview(w) {
    var pv = w.__pv || w.querySelector('.spotify-preview'), f = w.querySelector('.coverflow-face');
    if (!pv || !f) return;
    w.__pv = pv; pv.__wrap = w;
    if (pv.parentElement !== document.body) document.body.appendChild(pv);
    var r = f.getBoundingClientRect();
    pv.style.position = 'fixed';
    pv.style.bottom = 'auto';
    pv.style.left = Math.round(r.left + r.width / 2) + 'px';
    var top = r.top - (pv.offsetHeight || 160) - 12;
    pv.style.top = Math.round(Math.max(8, top)) + 'px';
  }
  document.addEventListener('mouseover', function (e) {
    var w = e.target.closest && e.target.closest('.album-carousel .album-card-wrap');
    if (w) placePreview(w);
  }, true);
  window.addEventListener('scroll', function () {
    document.querySelectorAll('body > .spotify-preview.visible').forEach(function (pv) { if (pv.__wrap) placePreview(pv.__wrap); });
  }, { passive: true });

  function start() { document.querySelectorAll('.album-carousel').forEach(setup); }
  if (document.readyState === 'complete') setTimeout(start, 400);
  else window.addEventListener('load', function () { setTimeout(start, 400); });
})();
