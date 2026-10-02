/* ============================================================
   AGORA — app.js
   Vanilla JS, zero dependencies. Powers all five pages:
     · index.html         (home)
     · shared-post.html   (shared-link landing)
     · download.html      (downloads)
     · about.html         (about the creator)
     · credits.html       (interactive credits)

   Contents:
     1. Link routing      — flat multi-page navigation
     2. Mobile menu       — toggle, a11y state, esc/outside close
     3. Smooth scrolling  — header-offset aware, reduced-motion safe
     4. Reveal on scroll  — IntersectionObserver entrance animations
     5. Chrome            — header scroll state, active nav, year
     6. Feedback form     — validation + same-origin API submit
     7. Shared-post       — URL param parsing + post preview stub
     8. Ambient layer      — custom cursor, soundscape, synced dot matrix
   ============================================================ */

(function agoraApp() {
  'use strict';

  var doc = document;
  var reduceMotion = function () {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  };

  /* ------------------------------------------------------------
     1. LINK ROUTING
     This is a static, flat multi-page site: every page lives in
     the same folder, so "routing" means resolving logical page
     names to real files. Authors write <a data-page="download">
     and this maps it — keeps the HTML self-documenting and the
     URLs trivial to change if pages ever move into subfolders.
     ------------------------------------------------------------ */
  // Root-absolute so links (and the CSS/JS they lead to) resolve
  // correctly no matter what path or query string the visitor
  // arrived on — e.g. a shared link like /shared-post.html?post=…
  var PAGE_MAP = {
    home: '/index.html',
    why: '/index.html#why-agora',
    download: '/download.html',
    about: '/about.html',
    credits: '/credits.html'
  };

  function getHashTarget(hash) {
    try {
      return doc.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (error) {
      return null;
    }
  }

  function initRouting() {
    var links = doc.querySelectorAll('a[data-page]');
    Array.prototype.forEach.call(links, function (link) {
      var target = PAGE_MAP[link.getAttribute('data-page')];
      if (target) link.setAttribute('href', target);
    });

    // If the page was opened with a hash (e.g. index.html#why-agora),
    // glide to the target once layout is ready.
    if (window.location.hash) {
      var target = getHashTarget(window.location.hash);
      if (target) {
        window.setTimeout(function () {
          target.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
        }, 80);
      }
    }
  }

  /* ------------------------------------------------------------
     2. MOBILE MENU
     ------------------------------------------------------------ */
  function initMenu() {
    var toggle = doc.querySelector('.nav__toggle');
    var menu = doc.querySelector('.mobile-menu');
    if (!toggle || !menu) return;

    function setMenu(open) {
      toggle.classList.toggle('is-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
      menu.classList.toggle('is-open', open);
      // Freeze the page behind the open menu (prevents scroll-through on phones).
      doc.documentElement.classList.toggle('menu-open', open);
    }

    toggle.addEventListener('click', function () {
      setMenu(!menu.classList.contains('is-open'));
    });

    // Close after choosing a destination.
    menu.addEventListener('click', function (event) {
      if (event.target.closest('a')) setMenu(false);
    });

    // Close on Escape and on any tap outside the header.
    doc.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setMenu(false);
    });

    doc.addEventListener('click', function (event) {
      if (!menu.classList.contains('is-open')) return;
      if (!event.target.closest('.site-header')) setMenu(false);
    });

    // Drop the menu state when resizing up to the desktop layout.
    // Keep in sync with the desktop nav breakpoint in style.css.
    var desktop = window.matchMedia('(min-width: 769px)');
    if (desktop.addEventListener) {
      desktop.addEventListener('change', function (e) {
        if (e.matches) setMenu(false);
      });
    }
  }

  /* ------------------------------------------------------------
     3. SMOOTH SCROLLING
     Intercepts in-page anchor links so the fixed header never
     hides the target. Honors prefers-reduced-motion.
     ------------------------------------------------------------ */
  function initSmoothScroll() {
    var HEADER_OFFSET = 84;
    var anchors = doc.querySelectorAll('a[href^="#"]');

    Array.prototype.forEach.call(anchors, function (link) {
      link.addEventListener('click', function (event) {
        var hash = link.getAttribute('href');
        if (!hash || hash === '#' || hash.length < 2) return;

        var target = getHashTarget(hash);
        if (!target) return;

        event.preventDefault();
        var offset = parseFloat(window.getComputedStyle(target).scrollMarginTop) || HEADER_OFFSET;
        var top = target.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: Math.max(top, 0), behavior: reduceMotion() ? 'auto' : 'smooth' });

        // Keep the URL shareable without piling up history entries.
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, '', hash);
        }
      });
    });
  }

  /* ------------------------------------------------------------
     4. REVEAL ON SCROLL
     Elements with [data-reveal] fade/rise in once.
     data-reveal-delay="120" staggers siblings in ms.
     ------------------------------------------------------------ */
  function initReveal() {
    var items = Array.prototype.slice.call(doc.querySelectorAll('[data-reveal]'));
    if (!items.length) return;

    if (reduceMotion() || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var delay = parseInt(el.getAttribute('data-reveal-delay') || '0', 10);
        if (delay) el.style.transitionDelay = delay + 'ms';
        el.classList.add('is-visible');
        observer.unobserve(el);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -7% 0px' });

    items.forEach(function (el) { observer.observe(el); });
  }

  /* ------------------------------------------------------------
     5. CHROME
     Header border on scroll · active nav link · footer year.
     ------------------------------------------------------------ */
  function initChrome() {
    var header = doc.querySelector('.site-header');
    if (header) {
      var onScroll = function () {
        header.classList.toggle('is-scrolled', window.scrollY > 8);
      };
      onScroll();
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    // "/" and "/index.html" are both home; other pages map by filename.
    var path = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();
    var pageKey = (path === 'index.html' || path === '') ? 'home' : path.replace(/\.html$/, '');
    Array.prototype.forEach.call(doc.querySelectorAll('[data-nav-key]'), function (link) {
      if (link.getAttribute('data-nav-key') === pageKey) link.classList.add('is-active');
    });

    var year = doc.getElementById('year');
    if (year) year.textContent = String(new Date().getFullYear());
  }

  /* ------------------------------------------------------------
     6. FEEDBACK FORM
     Validates locally, then posts JSON to the same-origin Cloudflare
     Pages Function at /api/contact. The API keeps the Resend key
     server-side and returns a JSON success or error response.
     ------------------------------------------------------------ */
  var CONTACT_EMAIL = 'mail@agora.in.net';
  var SUBMIT_TIMEOUT = 12000;                // ms before we give up on the API

  function initContactForm() {
    var form = doc.getElementById('feedback-form');
    if (!form) return;

    var success = doc.getElementById('feedback-success');
    var status = doc.getElementById('feedback-status');
    var button = form.querySelector('[data-submit]');
    var label = button ? button.querySelector('[data-button-label]') : null;
    var idleLabel = label ? label.textContent : '';
    var fields = form.querySelectorAll('[data-validate]');

    var RULES = {
      name: function (value) {
        return value.trim().length >= 2 ? '' : 'Please tell us your name.';
      },
      email: function (value) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value.trim())
          ? ''
          : 'That email address looks incomplete.';
      },
      topic: function (value) {
        return value ? '' : 'Choose a topic so it reaches the right inbox.';
      },
      message: function (value) {
        var text = value.trim();
        if (text.length < 10) return 'A little more detail helps — at least 10 characters.';
        if (text.length > 2000) return 'Please keep it under 2000 characters.';
        return '';
      }
    };

    function setStatus(message, kind) {
      if (!status) return;
      status.textContent = message || '';
      status.className = 'form-status' + (kind ? ' form-status--' + kind : '');
      status.hidden = !message;
    }

    function setError(input, message) {
      var note = form.querySelector('[data-error-for="' + input.name + '"]');
      var wrap = input.closest ? input.closest('.field') : null;
      if (message) {
        input.setAttribute('aria-invalid', 'true');
        if (wrap) wrap.classList.add('has-error');
        if (note) {
          note.textContent = message;
          note.hidden = false;
        }
      } else {
        input.removeAttribute('aria-invalid');
        if (wrap) wrap.classList.remove('has-error');
        if (note) {
          note.textContent = '';
          note.hidden = true;
        }
      }
    }

    function validate(input) {
      var rule = RULES[input.name];
      if (!rule) return true;
      var message = rule(input.value || '');
      setError(input, message);
      return !message;
    }

    // Only nag once a field has been touched — never on first focus.
    Array.prototype.forEach.call(fields, function (input) {
      input.addEventListener('blur', function () {
        if ((input.value || '').trim() || input.getAttribute('aria-invalid')) validate(input);
      });
      input.addEventListener('input', function () {
        if (input.getAttribute('aria-invalid')) validate(input);
      });
      input.addEventListener('change', function () {
        if (input.getAttribute('aria-invalid') || input.tagName === 'SELECT') validate(input);
      });
    });

    function setBusy(busy) {
      if (button) {
        button.disabled = busy;
        if (busy) button.setAttribute('aria-busy', 'true');
        else button.removeAttribute('aria-busy');
      }
      if (label) label.textContent = busy ? 'Sending...' : idleLabel;
    }

    function collect() {
      var topic = form.elements.topic;
      return {
        name: (form.elements.name.value || '').trim(),
        email: (form.elements.email.value || '').trim(),
        topic: topic.value,
        topicLabel: topic.options[topic.selectedIndex] ? topic.options[topic.selectedIndex].text : topic.value,
        message: (form.elements.message.value || '').trim(),
        page: window.location.href,
        submittedAt: new Date().toISOString()
      };
    }

    // Errors already written for humans survive the rejection handler below.
    function friendly(message) {
      var error = new Error(message);
      error.friendly = true;
      return error;
    }

    function postFeedback(payload) {
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = window.setTimeout(function () {
        if (controller) controller.abort();
      }, SUBMIT_TIMEOUT);

      return fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller ? controller.signal : undefined
      }).then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () { return {}; }).then(function (body) {
            var detail = body && body.error ? ' ' + body.error : '';
            throw friendly('The message could not be sent (HTTP ' + response.status + ').' + detail);
          });
        }
        return response.json().catch(function () { return { ok: true }; });
      }).then(function (body) {
        window.clearTimeout(timer);
        if (body && body.ok === false) throw friendly(body.error || 'The server could not accept the message.');
        return true;
      }, function (error) {
        window.clearTimeout(timer);
        if (error && error.friendly) throw error;
        if (error && error.name === 'AbortError') throw friendly('That took too long. Please try again.');
        throw friendly('We couldn\'t reach the contact service. Check your connection and try again.');
      });
    }

    function showSuccess() {
      var note = success ? success.querySelector('[data-success-note]') : null;
      if (note) {
        note.textContent = 'Your message is on its way — a human reads every one of these.';
      }
      form.hidden = true;
      if (success) {
        success.hidden = false;
        success.setAttribute('tabindex', '-1');
        success.focus();
      }
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      setStatus('');

      var firstInvalid = null;
      Array.prototype.forEach.call(fields, function (input) {
        if (!validate(input) && !firstInvalid) firstInvalid = input;
      });

      if (firstInvalid) {
        setStatus('Check the highlighted fields and try again.', 'error');
        firstInvalid.focus();
        return;
      }

      // Honeypot: people never see this field, so a value means a bot.
      var trap = form.querySelector('[data-honeypot]');
      if (trap && trap.value) {
        showSuccess();
        return;
      }

      var payload = collect();
      setBusy(true);

      postFeedback(payload).then(function () {
        setBusy(false);
        showSuccess();
      }, function (error) {
        setBusy(false);
        var message = error && error.message
          ? error.message
          : 'Something went wrong. Please try again, or email ' + CONTACT_EMAIL + '.';
        setStatus(message, 'error');
        // Keep the error visible in the form and give a short, direct cue
        // that the submission did not disappear silently.
        if (typeof window.alert === 'function') window.alert(message);
      });
    });
  }

  /* ------------------------------------------------------------
     7. SHARED-POST LANDING  (shared-post.html only)
     ------------------------------------------------------------
     Simulates the full flow that will run once the backend is
     connected, so the page is already structured for it:

       1. PARSE  — read the post id from the URL:
                    ?post=…   ?post_id=…   ?id=…   (shared by the
                    Android app's share sheet)
       2. FETCH  — GET /api/v1/posts/:id  (stubbed below)
       3. RENDER — author, body, and thread stats inside
                    #post-preview

     Until then, step 2 resolves with a simulated payload after
     a short delay and the preview renders in a placeholder
     state — exactly what a visitor would see pre-launch.
     ------------------------------------------------------------ */
  function initSharedPost() {
    var preview = doc.getElementById('post-preview');
    if (!preview) return;

    var chip = preview.querySelector('[data-post-id]');
    var status = preview.querySelector('[data-preview-status]');
    var body = preview.querySelector('[data-preview-body]');
    var emptyState = doc.getElementById('preview-empty');
    var loadingState = doc.getElementById('preview-loading');
    var resultState = doc.getElementById('preview-result');

    /* --- 1. PARSE ------------------------------------------- */
    var params = new URLSearchParams(window.location.search);
    var postId = params.get('post') || params.get('post_id') || params.get('id') || '';

    if (!postId) {
      if (emptyState) emptyState.hidden = false;
      if (loadingState) loadingState.hidden = true;
      if (resultState) resultState.hidden = true;
      if (chip) {
        chip.textContent = 'no post id in link';
        chip.classList.add('chip--idle');
      }
      return;
    }

    if (emptyState) emptyState.hidden = true;
    if (loadingState) loadingState.hidden = false; // show the skeleton while "fetching"
    if (chip) chip.textContent = 'post #' + postId;
    if (status) status.textContent = 'fetching preview…';

    /* --- 2. FETCH (stub) ------------------------------------ */
    function fetchPost(id) {
      /*
      Real implementation once the API is live — the stub below
      mirrors its signature and payload shape:

        var res = await fetch(
          'https://api.agora.example/api/v1/posts/' + encodeURIComponent(id)
        );
        if (!res.ok) throw new Error('Post ' + id + ' not found (' + res.status + ')');
        return res.json();

      Expected payload:
        {
          "id":        "a8f3c2",
          "author":    { "name": "…", "handle": "@…" },
          "body":      "The shared post text…",
          "createdAt": "2026-09-28T10:24:00Z",
          "replies":   12,
          "reposts":   3
        }
      */
      return new Promise(function (resolve) {
        window.setTimeout(function () {
          resolve({
            id: id,
            author: { name: 'A member of the square', handle: '@member' },
            body: null,          // content is rendered inside the app
            createdAt: null,
            replies: 0,
            reposts: 0
          });
        }, 1200);
      });
    }

    /* --- 3. RENDER ------------------------------------------- */
    function renderPreview(post) {
      if (!resultState || !loadingState) return;

      loadingState.hidden = true;
      resultState.hidden = false;

      var author = resultState.querySelector('[data-author]');
      var time = resultState.querySelector('[data-created]');
      var note = resultState.querySelector('[data-preview-note]');

      if (author && post.author) {
        author.textContent = post.author.name + '  ' + post.author.handle;
      }
      if (time) {
        time.textContent = post.createdAt ? 'just now' : 'time arrives with the app';
      }
      if (note) {
        note.textContent = post.body
          ? post.body
          : 'This is a placeholder preview. The full post — author, body, and thread — ' +
            'lives inside the app. Install Agora to read it.';
      }
      if (status) status.textContent = 'preview ready';
    }

    if (status) status.textContent = 'fetching preview…';
    fetchPost(postId).then(renderPreview);
  }

  /* Reveal device captures and the developer portrait only once loaded.
     Pending states preserve the layout until the real assets arrive. */
  function initImages() {
    doc.querySelectorAll('.phone__screen img, .developer-avatar').forEach(function (image) {
      function update() {
        var ready = image.complete && image.naturalWidth > 0;
        image.parentElement.classList.toggle('is-ready', ready);
        image.setAttribute('aria-hidden', String(!ready));
      }
      image.addEventListener('load', update);
      image.addEventListener('error', update);
      update();
    });
  }

  /* ------------------------------------------------------------
     8. AMBIENT EXPERIENCE
     A pointer-only cursor orb, a low-contrast dot matrix, and an
     opt-in Web Audio soundscape. Audio starts from the visitor's
     button tap so browser autoplay rules and user preference are
     respected; the matrix uses the same slow pulse when enabled.
     ------------------------------------------------------------ */
  function initCursor() {
    var finePointer = window.matchMedia && window.matchMedia('(pointer: fine)');
    if (!finePointer || !finePointer.matches || reduceMotion()) return;

    var cursor = doc.createElement('span');
    cursor.className = 'cursor-orb';
    cursor.setAttribute('aria-hidden', 'true');
    doc.body.appendChild(cursor);
    doc.body.classList.add('has-custom-cursor');

    var targetX = -100;
    var targetY = -100;
    var cursorFrame = 0;
    var interactiveSelector = 'a, button, input, select, textarea, summary, [role="button"], [data-cursor="interactive"]';

    function setInteractive(target) {
      var element = target && target.closest ? target.closest(interactiveSelector) : null;
      cursor.classList.toggle('is-hovering', !!element);
    }

    function renderCursor() {
      cursorFrame = 0;
      // Write only the latest pointer position once per refresh. There is no
      // interpolation here, so the custom cursor never trails the pointer.
      cursor.style.transform = 'translate3d(' + targetX + 'px,' + targetY + 'px,0) translate(-50%, -50%)';
    }

    function queueCursorFrame() {
      if (cursorFrame) return;
      cursorFrame = window.requestAnimationFrame(renderCursor);
    }

    function move(event) {
      targetX = event.clientX;
      targetY = event.clientY;
      cursor.classList.add('is-visible');
      setInteractive(event.target);
      queueCursorFrame();
    }

    function hide() {
      cursor.classList.remove('is-visible', 'is-hovering', 'is-pressed');
    }

    // Mouse events are coalesced into one transform write per animation frame.
    doc.addEventListener('mousemove', move, { passive: true });
    doc.addEventListener('pointerdown', function (event) {
      if (event.button === 0) cursor.classList.add('is-pressed');
    }, { passive: true });
    doc.addEventListener('pointerup', function () {
      cursor.classList.remove('is-pressed');
    }, { passive: true });
    doc.addEventListener('pointercancel', function () {
      cursor.classList.remove('is-pressed');
    }, { passive: true });
    window.addEventListener('blur', hide);
    doc.documentElement.addEventListener('mouseleave', hide);
  }

  function initAmbientExperience() {
    var audio = {
      context: null,
      master: null,
      analyser: null,
      data: null,
      enabled: false,
      energy: 0,
      unavailable: false
    };

    function updateSoundButton(button, label) {
      if (!button || !label) return;
      var on = audio.enabled;
      button.classList.toggle('is-on', on);
      button.setAttribute('aria-pressed', String(on));
      button.setAttribute('aria-label', on ? 'Turn ambient sound off' : 'Turn ambient sound on');
      label.textContent = on ? 'sound on' : 'sound off';
    }

    function ensureAudio() {
      if (audio.context) return true;
      var AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) {
        audio.unavailable = true;
        return false;
      }

      try {
        var context = new AudioContext();
        var master = context.createGain();
        var filter = context.createBiquadFilter();
        var analyser = context.createAnalyser();
        var now = context.currentTime;

        master.gain.setValueAtTime(0.0001, now);
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(1050, now);
        filter.Q.setValueAtTime(0.35, now);
        analyser.fftSize = 128;
        analyser.smoothingTimeConstant = 0.9;

        master.connect(filter);
        filter.connect(analyser);
        analyser.connect(context.destination);

        // A very quiet suspended chord: warm sine waves rather than a looped
        // song, so it stays unobtrusive beneath the page and carries no media.
        var notes = [174.61, 261.63, 349.23, 523.25];
        var levels = [0.012, 0.008, 0.005, 0.0025];
        var lfo = context.createOscillator();
        var lfoDepth = context.createGain();
        lfo.type = 'sine';
        lfo.frequency.setValueAtTime(0.045, now);
        lfoDepth.gain.setValueAtTime(4, now);
        lfo.connect(lfoDepth);
        lfo.start(now);

        notes.forEach(function (frequency, index) {
          var oscillator = context.createOscillator();
          var level = context.createGain();
          oscillator.type = index === 0 ? 'sine' : 'triangle';
          oscillator.frequency.setValueAtTime(frequency, now);
          oscillator.detune.setValueAtTime(index * 2 - 3, now);
          level.gain.setValueAtTime(levels[index], now);
          lfoDepth.connect(oscillator.detune);
          oscillator.connect(level);
          level.connect(master);
          oscillator.start(now);
        });

        audio.context = context;
        audio.master = master;
        audio.analyser = analyser;
        audio.data = new Uint8Array(analyser.frequencyBinCount);
        return true;
      } catch (error) {
        audio.unavailable = true;
        return false;
      }
    }

    function setSound(enabled) {
      if (!ensureAudio()) return false;
      var context = audio.context;
      if (context.state === 'suspended') context.resume();

      audio.enabled = enabled;
      var now = context.currentTime;
      audio.master.gain.cancelScheduledValues(now);
      audio.master.gain.setTargetAtTime(enabled ? 0.021 : 0.0001, now, enabled ? 2.4 : 0.4);
      return true;
    }

    function getEnergy() {
      if (!audio.enabled || !audio.analyser || !audio.data) {
        audio.energy *= 0.94;
        return audio.energy;
      }

      audio.analyser.getByteFrequencyData(audio.data);
      var total = 0;
      var count = 0;
      for (var index = 2; index < Math.min(audio.data.length, 18); index += 1) {
        total += audio.data[index];
        count += 1;
      }
      var next = count ? total / count / 255 : 0;
      audio.energy += (next - audio.energy) * 0.08;
      return audio.energy;
    }

    function getPulse(timestamp) {
      var clock = audio.context ? audio.context.currentTime : timestamp / 1000;
      var breathe = 0.5 + (0.5 * Math.sin(clock * Math.PI * 0.09));
      return audio.enabled ? (audio.energy * 0.65) + (breathe * 0.18) : 0;
    }

    function initSoundControl() {
      var button = doc.createElement('button');
      var label = doc.createElement('span');
      button.type = 'button';
      button.className = 'ambient-toggle';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', 'Turn ambient sound on');
      button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 10v4h3l4 3V7l-4 3H4Z"/><path d="M16 9.5a4 4 0 0 1 0 5"/><path d="M18.5 7a7.5 7.5 0 0 1 0 10"/></svg>';
      label.textContent = 'sound off';
      button.appendChild(label);
      doc.body.appendChild(button);

      button.addEventListener('click', function () {
        var next = !audio.enabled;
        if (!setSound(next)) {
          label.textContent = 'sound unavailable';
          button.setAttribute('aria-label', 'Ambient sound unavailable in this browser');
          button.setAttribute('aria-disabled', 'true');
          return;
        }
        updateSoundButton(button, label);
      });

      return { button: button, label: label };
    }

    function initDotMatrix() {
      var canvas = doc.createElement('canvas');
      var context = canvas.getContext('2d');
      if (!context) return;

      canvas.className = 'ambient-dot-matrix';
      canvas.setAttribute('aria-hidden', 'true');
      doc.body.insertBefore(canvas, doc.body.firstChild);

      var width = 0;
      var height = 0;
      var density = 36;
      var columns = 0;
      var rows = 0;
      var dots = [];
      var pixelRatio = 1;

      function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        density = width < 600 ? 30 : 36;
        pixelRatio = Math.min(window.devicePixelRatio || 1, 1.75);
        canvas.width = Math.floor(width * pixelRatio);
        canvas.height = Math.floor(height * pixelRatio);
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        columns = Math.ceil(width / density) + 2;
        rows = Math.ceil(height / density) + 2;
        dots = [];
        for (var row = 0; row < rows; row += 1) {
          for (var column = 0; column < columns; column += 1) {
            dots.push({
              row: row,
              column: column,
              phase: (row * 0.71) + (column * 0.37)
            });
          }
        }
      }

      function draw(timestamp) {
        var time = timestamp / 1000;
        var energy = getEnergy();
        var pulse = getPulse(timestamp);
        context.clearRect(0, 0, width, height);

        dots.forEach(function (dot) {
          var wave = 0.5 + (0.5 * Math.sin((time * 0.22) + dot.phase));
          var driftX = Math.sin((time * 0.28) + dot.phase + dot.row * 0.08) * (1.5 + energy * 7);
          var driftY = Math.cos((time * 0.19) + dot.phase) * (1.5 + energy * 5);
          var x = (dot.column * density) + driftX - density;
          var y = (dot.row * density) + driftY - density;
          var radius = 0.7 + (wave * 0.55) + (pulse * 0.7);
          var alpha = 0.045 + (wave * 0.028) + (pulse * 0.06);
          var color = (dot.column + dot.row) % 4 === 0 ? '96,165,250' : '139,92,246';

          context.beginPath();
          context.fillStyle = 'rgba(' + color + ',' + alpha + ')';
          context.arc(x, y, radius, 0, Math.PI * 2);
          context.fill();
        });

        if (!reduceMotion()) window.requestAnimationFrame(draw);
      }

      resize();
      window.addEventListener('resize', resize, { passive: true });
      draw(0);
    }

    initCursor();
    initSoundControl();
    initDotMatrix();
  }

  var ROTARY_TEAM = [
    {
      name: 'Jayvardhan Bhaskar',
      role: 'Developer',
      photo: '/assets/developer.png',
      contributions: 'Created the code, engineered the backend, and shaped the calm visual system behind Agora.',
      bio: 'Building a quieter, more human public square — one thoughtful detail at a time.'
    },
    {
      name: 'The Product Crew',
      role: 'Design & motion',
      photo: '/assets/agora-logo.svg',
      contributions: 'Turned principles into type, color, interaction, and a visual language with room to breathe.',
      bio: 'A collective of makers who believe clarity is a form of care.'
    },
    {
      name: 'Early Square Members',
      role: 'Testing & belief',
      photo: '/assets/agora-logo.svg',
      contributions: 'Tested the rough edges, asked the useful questions, and helped the square become a place to return to.',
      bio: 'The first people to tap, question, report, and keep showing up.'
    }
  ];

  function initCreditsRotary() {
    var page = doc.querySelector('.credits-rotary');
    if (!page) return;

    var topDisc = page.querySelector('[data-rotary-disc="top"]');
    var bottomDisc = page.querySelector('[data-rotary-disc="bottom"]');
    var topPlate = topDisc ? topDisc.querySelector('[data-rotary-plate]') : null;
    var bottomPlate = bottomDisc ? bottomDisc.querySelector('[data-rotary-plate]') : null;
    var topSegments = topDisc ? topDisc.querySelectorAll('[data-rotary-segment]') : [];
    var bottomSegments = bottomDisc ? bottomDisc.querySelectorAll('[data-rotary-segment]') : [];
    var tagHangers = topDisc ? topDisc.querySelectorAll('[data-rotary-tag]') : [];
    var roleTags = topDisc ? topDisc.querySelectorAll('[data-rotary-role]') : [];
    var nameTag = bottomDisc ? bottomDisc.querySelector('[data-rotary-name-tag]') : null;
    var tagName = bottomDisc ? bottomDisc.querySelector('[data-rotary-tag-name]') : null;
    var count = page.querySelector('[data-rotary-count]');
    var total = page.querySelector('[data-rotary-total]');
    var scrollAffordance = page.querySelector('[data-scroll-affordance]');

    if (!topPlate || !bottomPlate || !topSegments.length || !bottomSegments.length || !tagHangers.length) return;

    var state = {
      memberIndex: 0,
      rotation: 0,
      rotationTarget: 0,
      anchorRotation: 0,
      rotationVelocity: 0,
      tagAngles: Array.prototype.map.call(tagHangers, function () { return 0; }),
      tagVelocities: Array.prototype.map.call(tagHangers, function () { return 0; }),
      snapTimer: 0,
      snapRequested: false,
      lastTime: 0,
      raf: 0,
      transition: 0
    };
    var SEGMENT = 120;
    var WHEEL_DAMPING = 0.05;
    var SNAP_DELAY = 120;
    var SNAP_THRESHOLD = 0.65;
    var teamLength = ROTARY_TEAM.length;
    var TOP_SEGMENT_ANGLES = [40, 280, 160];
    var BOTTOM_SEGMENT_ANGLES = [220, 340, 100];

    if (total) total.textContent = String(teamLength).padStart(2, '0');

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function indexForRotation(rotation) {
      var sector = Math.round(rotation / SEGMENT);
      sector %= teamLength;
      if (sector < 0) sector += teamLength;
      return sector;
    }

    function setSegmentContent(segment, member, index, active) {
      var contribution = segment.querySelector('[data-segment-contributions]');
      var bio = segment.querySelector('[data-segment-bio]');
      var photo = segment.querySelector('[data-rotary-photo]');

      if (contribution) contribution.textContent = member.contributions;
      if (bio) bio.textContent = member.bio;
      if (photo) {
        photo.src = member.photo;
        photo.alt = member.name + ' profile image';
        photo.classList.toggle('is-mark', member.photo.indexOf('agora-logo.svg') !== -1);
      }
      segment.classList.toggle('is-active', active);
    }

    function setMemberText() {
      var member = ROTARY_TEAM[state.memberIndex];

      Array.prototype.forEach.call(topSegments, function (segment, index) {
        setSegmentContent(segment, ROTARY_TEAM[index % teamLength], index, index === state.memberIndex);
      });
      Array.prototype.forEach.call(bottomSegments, function (segment, index) {
        setSegmentContent(segment, ROTARY_TEAM[index % teamLength], index, index === state.memberIndex);
      });

      Array.prototype.forEach.call(roleTags, function (roleTag, index) {
        roleTag.textContent = ROTARY_TEAM[index % teamLength].role;
      });
      Array.prototype.forEach.call(tagHangers, function (tag, index) {
        tag.classList.toggle('is-active', index === state.memberIndex);
      });
      if (tagName) tagName.textContent = member.name;
      if (nameTag) nameTag.setAttribute('aria-label', 'Current member: ' + member.name);
      if (count) count.textContent = String(state.memberIndex + 1).padStart(2, '0');
    }

    function showMember(index, animate) {
      state.memberIndex = (index + teamLength) % teamLength;
      if (!animate) {
        setMemberText();
        return;
      }

      state.transition += 1;
      var transitionId = state.transition;
      topDisc.classList.add('is-changing');
      bottomDisc.classList.add('is-changing');
      window.setTimeout(function () {
        if (transitionId !== state.transition) return;
        setMemberText();
        topDisc.classList.remove('is-changing');
        bottomDisc.classList.remove('is-changing');
      }, 150);
    }

    function updateMemberFromRotation(rotation) {
      var nextIndex = indexForRotation(rotation);
      if (nextIndex !== state.memberIndex) showMember(nextIndex, true);
    }

    function angularDistance(angle) {
      var wrapped = ((angle + 180) % 360 + 360) % 360 - 180;
      return Math.abs(wrapped);
    }

    function updateSegmentVisuals(segments, baseAngles, wheelRotation, activeCenter) {
      Array.prototype.forEach.call(segments, function (segment, index) {
        var content = segment.querySelector('.rotary-segment__content');
        if (!content) return;

        var distance = angularDistance((baseAngles[index] + wheelRotation) - activeCenter);
        var progress = clamp(distance / SEGMENT, 0, 1);
        var eased = progress * progress * (3 - (2 * progress));
        var scale = 1 - (0.4 * eased);
        var opacity = 1 - (0.7 * eased);
        content.style.setProperty('--segment-scale', scale.toFixed(3));
        content.style.setProperty('--segment-opacity', opacity.toFixed(3));
      });
    }

    function render() {
      var topRotation = state.rotation;
      var bottomRotation = -state.rotation;
      topPlate.style.setProperty('--disc-rotation', topRotation + 'deg');
      bottomPlate.style.setProperty('--disc-rotation', bottomRotation + 'deg');
      if (nameTag) nameTag.style.setProperty('--tag-counter-rotation', state.rotation + 'deg');

      updateSegmentVisuals(topSegments, TOP_SEGMENT_ANGLES, topRotation, 40);
      updateSegmentVisuals(bottomSegments, BOTTOM_SEGMENT_ANGLES, bottomRotation, 220);
      Array.prototype.forEach.call(tagHangers, function (tag, index) {
        tag.style.setProperty('--tag-swing-angle', state.tagAngles[index].toFixed(3) + 'deg');
        tag.style.setProperty('--tag-scale', index === state.memberIndex ? '1' : '0.76');
      });
    }

    function queueFrame() {
      if (!state.raf) state.raf = window.requestAnimationFrame(step);
    }

    function calculateSnapTarget() {
      var displacement = state.rotationTarget - state.anchorRotation;
      if (!displacement) return state.anchorRotation;

      var direction = displacement < 0 ? -1 : 1;
      var distance = Math.abs(displacement);
      var completeSegments = Math.floor(distance / SEGMENT);
      var remainder = distance - (completeSegments * SEGMENT);
      var extraSegment = remainder / SEGMENT >= SNAP_THRESHOLD ? 1 : 0;
      return state.anchorRotation + direction * (completeSegments + extraSegment) * SEGMENT;
    }

    function scheduleSnap() {
      window.clearTimeout(state.snapTimer);
      state.snapTimer = window.setTimeout(function () {
        state.snapRequested = true;
        queueFrame();
      }, SNAP_DELAY);
    }

    function step(timestamp) {
      state.raf = 0;
      if (!state.lastTime) state.lastTime = timestamp;
      var elapsed = clamp(timestamp - state.lastTime, 8, 34) / 16.67;
      state.lastTime = timestamp;

      if (state.snapRequested) {
        state.snapRequested = false;
        state.rotationTarget = calculateSnapTarget();
        state.anchorRotation = state.rotationTarget;
        updateMemberFromRotation(state.rotationTarget);
      }

      // A critically damped-ish spring gives the wheel weight while still
      // allowing the trackpad to hand it a deliberate, low-sensitivity turn.
      state.rotationVelocity += (state.rotationTarget - state.rotation) * 0.16 * elapsed;
      state.rotationVelocity *= Math.pow(0.68, elapsed);
      state.rotation += state.rotationVelocity * elapsed;

      // Every role tag has its own delayed pendulum. The CSS applies the
      // exact inverse wheel rotation first, then this small spring swing.
      Array.prototype.forEach.call(tagHangers, function (tag, index) {
        state.tagVelocities[index] += (-state.tagAngles[index] * 0.105 - state.tagVelocities[index] * 0.18) * elapsed;
        state.tagAngles[index] += state.tagVelocities[index] * elapsed;
        if (Math.abs(state.tagAngles[index]) < 0.01 && Math.abs(state.tagVelocities[index]) < 0.01) {
          state.tagAngles[index] = 0;
          state.tagVelocities[index] = 0;
        }
      });

      render();

      var tagsMoving = state.tagAngles.some(function (angle, index) {
        return Math.abs(angle) > 0.01 || Math.abs(state.tagVelocities[index]) > 0.01;
      });
      var moving = Math.abs(state.rotationTarget - state.rotation) > 0.04
        || Math.abs(state.rotationVelocity) > 0.01
        || tagsMoving;
      if (moving) queueFrame();
    }

    function normalizeWheelDelta(event) {
      var delta = event.deltaY;
      if (event.deltaMode === 1) delta *= 16;
      if (event.deltaMode === 2) delta *= window.innerHeight;
      return delta;
    }

    function handleWheel(event) {
      if (event.cancelable) event.preventDefault();
      var delta = normalizeWheelDelta(event);
      if (!delta) return;
      if (scrollAffordance) scrollAffordance.classList.add('is-hidden');

      // Five percent of the physical wheel delta makes fast trackpads feel
      // deliberate instead of throwing the 120-degree wheel across the UI.
      var rotationDelta = clamp(delta * WHEEL_DAMPING, -36, 36);
      state.rotationTarget += rotationDelta;
      scheduleSnap();
      Array.prototype.forEach.call(tagHangers, function (tag, index) {
        var impulse = rotationDelta * (index === state.memberIndex ? 0.16 : 0.08);
        state.tagVelocities[index] = clamp(state.tagVelocities[index] - impulse, -18, 18);
      });
      updateMemberFromRotation(state.rotationTarget);
      queueFrame();
    }

    showMember(0, false);
    render();
    window.addEventListener('wheel', handleWheel, { passive: false });
  }

  /* ------------------------------------------------------------
     Boot
     ------------------------------------------------------------ */
  function boot() {
    initImages();
    initAmbientExperience();
    initCreditsRotary();
    initRouting();
    initMenu();
    initSmoothScroll();
    initReveal();
    initChrome();
    initContactForm();
    initSharedPost();
  }

  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
