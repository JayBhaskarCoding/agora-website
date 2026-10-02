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
     6. Feedback form     — validation + submit (endpoint or mail client)
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
    var currentX = targetX;
    var currentY = targetY;
    var interactiveSelector = 'a, button, input, select, textarea, summary, [role="button"], [data-cursor="interactive"]';

    function setInteractive(target) {
      var element = target && target.closest ? target.closest(interactiveSelector) : null;
      cursor.classList.toggle('is-hovering', !!element);
    }

    function move(event) {
      if (event.pointerType && event.pointerType !== 'mouse' && event.pointerType !== 'pen') return;
      targetX = event.clientX;
      targetY = event.clientY;
      cursor.classList.add('is-visible');
      setInteractive(event.target);
    }

    function hide() {
      cursor.classList.remove('is-visible', 'is-hovering', 'is-pressed');
    }

    function frame() {
      // Keep a tiny amount of easing without the laggy trail of a slow
      // interpolation; the orb should feel attached to the pointer.
      currentX += (targetX - currentX) * 0.78;
      currentY += (targetY - currentY) * 0.78;
      cursor.style.transform = 'translate3d(' + currentX + 'px,' + currentY + 'px,0) translate(-50%, -50%)';
      window.requestAnimationFrame(frame);
    }

    doc.addEventListener('pointermove', move, { passive: true });
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
    window.requestAnimationFrame(frame);
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

  function initCreditsPhysics() {
    var stage = doc.getElementById('credits-physics');
    if (!stage) return;

    var line = stage.querySelector('[data-credits-wiggle]');
    var svg = stage.querySelector('.credits-physics__svg');
    var gearNodes = stage.querySelectorAll('[data-credits-gear]');
    var tags = stage.querySelectorAll('[data-credits-tag]');
    if (!line || !gearNodes.length) return;

    var VIEWBOX_WIDTH = 1200;
    var VIEWBOX_HEIGHT = 360;
    var points = 32;
    var state = {
      targetScroll: window.scrollY || window.pageYOffset || 0,
      visualScroll: window.scrollY || window.pageYOffset || 0,
      lastScroll: window.scrollY || window.pageYOffset || 0,
      lineOffset: 0,
      lineVelocity: 0,
      lastTime: 0,
      raf: 0
    };

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function pathFor(scrollPosition, offset) {
      var path = '';
      var linePoints = [];

      for (var index = 0; index < points; index += 1) {
        var progress = index / (points - 1);
        var x = progress * VIEWBOX_WIDTH;
        var envelope = Math.sin(Math.PI * progress);
        var base = 246
          + Math.sin(progress * Math.PI * 2.2) * 31
          + Math.sin(progress * Math.PI * 5.2 + 0.4) * 11;
        var travelingWave = Math.sin(progress * Math.PI * 5.4 + scrollPosition * 0.005) * offset * envelope;
        var secondaryWave = Math.sin(progress * Math.PI * 9 + scrollPosition * 0.002) * offset * 0.18 * envelope;
        var y = base + travelingWave + secondaryWave;
        linePoints.push({ x: x, y: y });
      }

      path = 'M ' + linePoints[0].x.toFixed(2) + ' ' + linePoints[0].y.toFixed(2);
      for (var pointIndex = 1; pointIndex < linePoints.length; pointIndex += 1) {
        var previous = linePoints[pointIndex - 1];
        var current = linePoints[pointIndex];
        var midpoint = (previous.x + current.x) / 2;
        path += ' C ' + midpoint.toFixed(2) + ' ' + previous.y.toFixed(2)
          + ' ' + midpoint.toFixed(2) + ' ' + current.y.toFixed(2)
          + ' ' + current.x.toFixed(2) + ' ' + current.y.toFixed(2);
      }
      return path;
    }

    function updateTags(scrollPosition) {
      var totalLength;
      try {
        totalLength = line.getTotalLength();
      } catch (error) {
        return;
      }
      if (!totalLength) return;

      var stageRect = stage.getBoundingClientRect();
      var svgRect = svg ? svg.getBoundingClientRect() : stageRect;
      var scale = Math.min(svgRect.width / VIEWBOX_WIDTH, svgRect.height / VIEWBOX_HEIGHT);
      var offsetX = (svgRect.left - stageRect.left) + ((svgRect.width - VIEWBOX_WIDTH * scale) / 2);
      var offsetY = (svgRect.top - stageRect.top) + ((svgRect.height - VIEWBOX_HEIGHT * scale) / 2);

      Array.prototype.forEach.call(tags, function (tag) {
        var progress = parseFloat(tag.getAttribute('data-credits-tag')) || 0;
        var distance = (progress * totalLength + scrollPosition * 0.18) % totalLength;
        if (distance < 0) distance += totalLength;
        var point = line.getPointAtLength(distance);
        tag.style.left = ((offsetX + point.x * scale) / stageRect.width * 100).toFixed(3) + '%';
        tag.style.top = ((offsetY + point.y * scale) / stageRect.height * 100).toFixed(3) + '%';
      });
    }

    function updateGears(scrollPosition) {
      Array.prototype.forEach.call(gearNodes, function (gear) {
        var direction = gear.getAttribute('data-credits-gear') === 'counter-clockwise' ? -1 : 1;
        var centerX = direction < 0 ? 992 : 208;
        var centerY = 136;
        var translation = direction < 0 ? -307 : 307;
        var rotation = scrollPosition * 0.22 * direction;
        // Move the two circles together so their dashed edges interlock,
        // then rotate each around its own local hub.
        gear.setAttribute('transform', 'translate(' + translation + ' 0) rotate(' + rotation.toFixed(2) + ' ' + centerX + ' ' + centerY + ')');
      });
    }

    function render() {
      line.setAttribute('d', pathFor(state.visualScroll, state.lineOffset));
      updateGears(state.visualScroll);
      updateTags(state.visualScroll);
    }

    function queueFrame() {
      if (!state.raf) state.raf = window.requestAnimationFrame(step);
    }

    function step(timestamp) {
      state.raf = 0;
      if (!state.lastTime) state.lastTime = timestamp;
      var elapsed = clamp(timestamp - state.lastTime, 8, 34) / 16.67;
      state.lastTime = timestamp;

      var scrollGap = state.targetScroll - state.visualScroll;
      state.visualScroll += scrollGap * (1 - Math.pow(0.78, elapsed));

      // A damped spring: scrolling kicks the string, then stiffness pulls it
      // back while friction quietly removes the energy.
      state.lineVelocity += (-state.lineOffset * 0.11 - state.lineVelocity * 0.16) * elapsed;
      state.lineOffset += state.lineVelocity * elapsed;
      if (Math.abs(state.lineOffset) < 0.005 && Math.abs(state.lineVelocity) < 0.005) {
        state.lineOffset = 0;
        state.lineVelocity = 0;
      }

      render();

      var stillMoving = Math.abs(state.targetScroll - state.visualScroll) > 0.08
        || Math.abs(state.lineOffset) > 0.01
        || Math.abs(state.lineVelocity) > 0.01;
      if (stillMoving) queueFrame();
    }

    function handleScroll() {
      var nextScroll = window.scrollY || window.pageYOffset || 0;
      var delta = nextScroll - state.lastScroll;
      state.targetScroll = nextScroll;
      state.lastScroll = nextScroll;
      // Clamp a wheel/touch flick so a single large jump stays playful rather
      // than throwing the line outside the card.
      state.lineVelocity = clamp(state.lineVelocity + clamp(delta * 0.055, -18, 18), -24, 24);
      queueFrame();
    }

    render();
    if (reduceMotion()) return;
    window.addEventListener('scroll', handleScroll, { passive: true });
    queueFrame();
  }

  /* ------------------------------------------------------------
     Boot
     ------------------------------------------------------------ */
  function boot() {
    initImages();
    initAmbientExperience();
    initCreditsPhysics();
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
