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
     8. Ambient layer      — custom cursor, soundscape, the background mesh
     9. Dynamic download  — newest GitHub release APK for every CTA
     10. Wheel reactivity — bass/onset/treble drive the wheels themselves
   ============================================================ */

(function agoraApp() {
  'use strict';

  var doc = document;
  var reduceMotion = function () {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  };

  /* Shared by the credits wheel and the background mesh. This used to be a
     private helper inside initCreditsRotary, which is fine until a second
     section needs it: the mesh called clamp() from its own draw loop and threw a
     ReferenceError on every frame, silently killing the animation. `node --check`
     cannot see that and neither can a source grep -- only running it can. */
  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  /* ---- pre-rendered glow ---------------------------------------------------
     The design review asked for `shadowBlur` 8-12 on every matrix dot and mesh
     node. shadowBlur is one of the most expensive things a 2D context can do,
     and between the dot matrix and the wave mesh that is on the order of two
     thousand of them per frame -- on a phone that is a dropped-frame machine.

     A radial-gradient sprite, rendered once per colour and blitted with
     drawImage, is the same picture for a small fraction of the cost: no gradient
     construction and no blur pass inside the frame loop. GLOW_SPREAD is how much
     bloom surrounds the dot, expressed in dot radii -- 3.4 reads as the
     shadowBlur 8-12 the review asked for at these dot sizes.                */
  var GLOW_SPRITE_SIZE = 64;
  var GLOW_SPREAD = 3.4;

  function makeGlowSprite(coreRgb, glowRgb, bloom) {
    var sprite = doc.createElement('canvas');
    sprite.width = GLOW_SPRITE_SIZE;
    sprite.height = GLOW_SPRITE_SIZE;
    var ctx = sprite.getContext('2d');
    if (!ctx) return null;
    var c = GLOW_SPRITE_SIZE / 2;
    var gradient = ctx.createRadialGradient(c, c, 0, c, c, c);
    /* `bloom` scales how far the halo reaches past the dot's own disc, and how
       bright it is. 1 is the original shadowBlur 8-12 look; the calibrated
       value the matrix now uses is well under that, because a dot that lights
       up its whole neighbourhood reads as glare and competes with the copy.
       The stops are clamped ascending -- a compressed bloom must never produce
       an out-of-order addColorStop, which browsers silently ignore. */
    var k = typeof bloom === 'number' ? bloom : 1;
    gradient.addColorStop(0, 'rgba(' + coreRgb + ',1)');
    gradient.addColorStop(Math.min(0.9, 0.06 + (0.1 * k)), 'rgba(' + coreRgb + ',0.92)');
    gradient.addColorStop(Math.min(0.94, 0.08 + (0.17 * k)),
      'rgba(' + glowRgb + ',' + (0.6 * k).toFixed(3) + ')');
    gradient.addColorStop(Math.min(0.97, 0.12 + (0.5 * k)),
      'rgba(' + glowRgb + ',' + (0.14 * k).toFixed(3) + ')');
    gradient.addColorStop(1, 'rgba(' + glowRgb + ',0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, GLOW_SPRITE_SIZE, GLOW_SPRITE_SIZE);
    return sprite;
  }

  function drawGlow(context, sprite, coreRgb, x, y, radius, alpha, spread) {
    if (!sprite) {          // no 2D context for the sprite: fall back to a dot
      context.beginPath();
      context.fillStyle = 'rgba(' + coreRgb + ',' + alpha.toFixed(4) + ')';
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
      return;
    }
    var size = radius * 2 * (typeof spread === 'number' ? spread : GLOW_SPREAD);
    context.globalAlpha = alpha;
    context.drawImage(sprite, x - (size / 2), y - (size / 2), size, size);
    context.globalAlpha = 1;
  }

  /* ---- the wheel's spin, published to the background mesh ----------------
     Scrolling has to ripple the mesh even with the music muted or paused, and
     the canvas lives in a different section from the rotary physics -- so the
     angular velocity is published here rather than passed down a call chain
     that does not exist. `at` is the timestamp of the last write: the rotary's
     frame loop STOPS once the wheel settles, which would otherwise freeze the
     last ripple on screen forever. readSpin() decays by age instead, so the
     mesh returns to calm on its own as the wheel locks onto a contributor. */
  var wheelSpin = { velocity: 0, at: -1e9 };
  var SPIN_DECAY_MS = 260;      // e-folding time for a ripple dying away
  var SPIN_REFERENCE = 420;     // deg/s that counts as a full-strength ripple

  function readSpin(now) {
    var age = Math.max(0, now - wheelSpin.at);
    return wheelSpin.velocity * Math.exp(-age / SPIN_DECAY_MS);
  }

  /* One place that asks the audio facade for its band metrics, so the mesh
     and the wheels all degrade identically when the
     facade is absent, older than getBands(), or throws. */
  var IDLE_BANDS = { bass: 0, mid: 0, treble: 0, onset: 0, pitch: 0.5, centroid: 0.5 };

  function readBands() {
    var api = window.AgoraAudio;
    if (!api || typeof api.getBands !== 'function') return IDLE_BANDS;
    try {
      return api.getBands() || IDLE_BANDS;
    } catch (error) {
      return IDLE_BANDS;
    }
  }

  /* Deterministic 32-bit hash, used for the mesh's per-vertex jitter and its
     per-cell diagonal flip. Math.imul keeps the products inside 32-bit integer
     range; without it they exceed 2^53 and the low bits -- the only ones that
     look random -- are lost, which shows up as a mesh whose triangles all lean
     the same way and whose jitter repeats in visible bands. */
  function hash2(a, b) {
    var h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return (h ^ (h >>> 16)) >>> 0;
  }

  /* ---- scroll shockwaves ----------------------------------------------------
     Continuous scrolling ripples the mesh through the spin velocity above, but
     a committed contributor is a discrete impact and deserves a discrete ring.
     The rings live here, at module scope, because the rotary physics and the
     canvas are separate sections with no call chain between them -- the same
     reason wheelSpin lives here. The mesh ages them out; nothing else reads
     them. Capped so a long fling cannot grow the list without bound. */
  var MESH_PULSE_MAX = 6;
  var MESH_PULSE_SPEED = 900;    // px/s the ring expands at
  var MESH_PULSE_LIFE = 1100;    // ms before a ring is dropped
  var MESH_PULSE_LIFT = 20;      // px of displacement at full strength
  var meshPulses = [];
  var NO_PULSES = [];            // shared empty result: no allocation when idle

  function pushMeshPulse(strength) {
    if (meshPulses.length >= MESH_PULSE_MAX) meshPulses.shift();
    meshPulses.push({
      at: window.performance && window.performance.now
        ? window.performance.now()
        : Date.now(),
      x: window.innerWidth * 0.5,
      y: window.innerHeight * 0.5,
      strength: clamp(strength, 0, 1)
    });
  }

  function activePulses(now) {
    if (!meshPulses.length) return NO_PULSES;
    var out = [];
    for (var i = meshPulses.length - 1; i >= 0; i -= 1) {
      var age = now - meshPulses[i].at;
      if (age > MESH_PULSE_LIFE) {
        meshPulses.splice(i, 1);   // drop on read: there is no reaper loop
        continue;
      }
      var t = age / MESH_PULSE_LIFE;
      out.push({
        x: meshPulses[i].x,
        y: meshPulses[i].y,
        radius: (age / 1000) * MESH_PULSE_SPEED,
        // The band widens as it expands, so the ring smears out rather than
        // staying a hard circle shrinking to nothing.
        sigma2: 2 * Math.pow(90 + (t * 190), 2),
        strength: meshPulses[i].strength * (1 - t) * MESH_PULSE_LIFT
      });
    }
    return out.length ? out : NO_PULSES;
  }

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

  var routerState = {
    bound: false,
    navigating: false,
    abortController: null,
    currentPath: ''
  };
  var menuState = { bound: false };
  var chromeState = { bound: false };
  var revealObserver = null;

  function getHashTarget(hash) {
    try {
      return doc.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (error) {
      return null;
    }
  }

  function canonicalPath(url) {
    var path = url.pathname || '/index.html';
    if (path === '/' || path === '') return '/index.html';
    return path;
  }

  function syncPageLinks() {
    var links = doc.querySelectorAll('a[data-page]');
    Array.prototype.forEach.call(links, function (link) {
      // The download page's APK button is owned by initDynamicDownload: its
      // href is the newest release asset (or GitHub's permanent latest-release
      // redirect), so page routing must never rewrite it to /download.html.
      // Every other CTA is a plain page link and SHOULD be resolved here.
      if (isDynamicDownloadLink(link)) return;
      var target = PAGE_MAP[link.getAttribute('data-page')];
      if (target) link.setAttribute('href', target);
    });
  }

  function getInternalPageUrl(link) {
    var href = link.getAttribute('href');
    if (!href || href === '#' || link.hasAttribute('download') || link.target === '_blank') return null;
    if (/^(mailto:|tel:|javascript:)/i.test(href)) return null;

    var url;
    try {
      // A hash-only Why Agora link on a secondary page should still land on
      // the home section; on the home page initSmoothScroll owns it instead.
      url = /^#/.test(href) && !getHashTarget(href)
        ? new URL('/index.html' + href, window.location.href)
        : new URL(href, window.location.href);
    } catch (error) {
      return null;
    }
    if (url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) return null;
    if (!/(^|\/)([^/]+\.html?)$/i.test(url.pathname) && url.pathname !== '/') return null;
    if (/\.apk$/i.test(url.pathname)) return null;
    return url;
  }

  function scrollToRouteHash(hash) {
    if (!hash) {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      return;
    }
    var target = getHashTarget(hash);
    if (!target) return;
    window.setTimeout(function () {
      target.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
    }, 40);
  }

  function readPageShell(parsed) {
    var main = parsed.querySelector('main') || parsed.querySelector('[data-page-content]');
    var header = parsed.querySelector('body > header') || parsed.querySelector('header');
    if (!main) throw new Error('The requested page has no primary content wrapper.');
    return { main: main, header: header };
  }

  function updateDocumentShell(parsed, shell) {
    var currentMain = doc.querySelector('main') || doc.querySelector('[data-page-content]');
    var currentHeader = doc.querySelector('body > header') || doc.querySelector('header');
    if (!currentMain) throw new Error('The current page has no primary content wrapper.');

    if (currentHeader && shell.header) currentHeader.replaceWith(shell.header.cloneNode(true));
    currentMain.replaceWith(shell.main.cloneNode(true));

    var keepCursor = doc.body.classList.contains('has-custom-cursor');
    doc.body.className = parsed.body.getAttribute('class') || '';
    if (keepCursor) doc.body.classList.add('has-custom-cursor');
    doc.documentElement.classList.remove('menu-open');

    var nextTitle = parsed.querySelector('title');
    if (nextTitle) doc.title = nextTitle.textContent;
    var nextDescription = parsed.querySelector('meta[name="description"]');
    var currentDescription = doc.querySelector('meta[name="description"]');
    if (nextDescription && currentDescription) currentDescription.setAttribute('content', nextDescription.getAttribute('content') || '');
  }

  function routeTo(url, pushHistory) {
    var targetPath = canonicalPath(url);
    var currentUrl = new URL(window.location.href);
    // Compare against the hydrated DOM route, not only location.pathname:
    // popstate updates the address bar before this handler runs.
    if (targetPath === routerState.currentPath && url.search === currentUrl.search) {
      if (pushHistory && url.hash !== currentUrl.hash) window.history.pushState({}, '', url.href);
      scrollToRouteHash(url.hash);
      return Promise.resolve();
    }
    if (routerState.navigating) return Promise.resolve();

    routerState.navigating = true;
    if (routerState.abortController) routerState.abortController.abort();
    routerState.abortController = typeof AbortController === 'function' ? new AbortController() : null;
    doc.documentElement.classList.add('is-pjax-loading');

    return fetch(url.href, {
      headers: { 'X-Requested-With': 'PJAX' },
      signal: routerState.abortController ? routerState.abortController.signal : undefined
    }).then(function (response) {
      if (!response.ok) throw new Error('Navigation failed (' + response.status + ').');
      return response.text();
    }).then(function (markup) {
      var parsed = new DOMParser().parseFromString(markup, 'text/html');
      var shell = readPageShell(parsed);
      updateDocumentShell(parsed, shell);
      if (pushHistory) window.history.pushState({ pjax: true }, '', url.href);
      routerState.currentPath = targetPath;
      bootPage();
      scrollToRouteHash(url.hash);
    }).catch(function (error) {
      if (error && error.name === 'AbortError') return;
      // A static fallback keeps the site navigable if a host blocks PJAX.
      window.location.assign(url.href);
    }).finally(function () {
      routerState.navigating = false;
      routerState.abortController = null;
      doc.documentElement.classList.remove('is-pjax-loading');
    });
  }

  function handleRouterClick(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var link = event.target.closest ? event.target.closest('a') : null;
    if (!link) return;
    var url = getInternalPageUrl(link);
    if (!url) return;
    event.preventDefault();
    routeTo(url, true);
  }

  function initRouting() {
    syncPageLinks();
    if (routerState.currentPath) return;
    routerState.currentPath = canonicalPath(new URL(window.location.href));
    if (routerState.bound) return;
    routerState.bound = true;
    doc.addEventListener('click', handleRouterClick);
    window.addEventListener('popstate', function () {
      routeTo(new URL(window.location.href), false);
    });
  }

  /* ------------------------------------------------------------
     2. MOBILE MENU
     ------------------------------------------------------------ */
  function setMenu(open) {
    var toggle = doc.querySelector('.nav__toggle');
    var menu = doc.querySelector('.mobile-menu');
    if (!toggle || !menu) return;
    toggle.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
    menu.classList.toggle('is-open', open);
    // Freeze the page behind the open menu (prevents scroll-through on phones).
    doc.documentElement.classList.toggle('menu-open', open);
  }

  function initMenu() {
    var toggle = doc.querySelector('.nav__toggle');
    var menu = doc.querySelector('.mobile-menu');
    if (!toggle || !menu) return;

    if (!toggle.dataset.menuBound) {
      toggle.dataset.menuBound = 'true';
      toggle.addEventListener('click', function () {
        var currentMenu = doc.querySelector('.mobile-menu');
        setMenu(!(currentMenu && currentMenu.classList.contains('is-open')));
      });
    }
    if (!menu.dataset.menuBound) {
      menu.dataset.menuBound = 'true';
      menu.addEventListener('click', function (event) {
        if (event.target.closest('a')) setMenu(false);
      });
    }

    if (menuState.bound) return;
    menuState.bound = true;
    doc.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setMenu(false);
    });
    doc.addEventListener('click', function (event) {
      var currentMenu = doc.querySelector('.mobile-menu');
      if (!currentMenu || !currentMenu.classList.contains('is-open')) return;
      if (!event.target.closest('.site-header')) setMenu(false);
    });

    // Drop the menu state when resizing up to the desktop layout.
    var desktop = window.matchMedia('(min-width: 769px)');
    var onBreakpoint = function (event) {
      if (event.matches) setMenu(false);
    };
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpoint);
    else if (desktop.addListener) desktop.addListener(onBreakpoint);
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
    if (revealObserver) {
      revealObserver.disconnect();
      revealObserver = null;
    }
    if (!items.length) return;

    if (reduceMotion() || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-visible'); });
      return;
    }

    revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var delay = parseInt(el.getAttribute('data-reveal-delay') || '0', 10);
        if (delay) el.style.transitionDelay = delay + 'ms';
        el.classList.add('is-visible');
        revealObserver.unobserve(el);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -7% 0px' });

    items.forEach(function (el) { revealObserver.observe(el); });
  }

  /* ------------------------------------------------------------
     5. CHROME
     Header border on scroll · active nav link · footer year.
     ------------------------------------------------------------ */
  function initChrome() {
    var onScroll = function () {
      var header = doc.querySelector('.site-header');
      if (header) header.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    onScroll();
    if (!chromeState.bound) {
      chromeState.bound = true;
      window.addEventListener('scroll', onScroll, { passive: true });
    }

    // "/" and "/index.html" are both home; other pages map by filename.
    var path = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();
    var pageKey = (path === 'index.html' || path === '') ? 'home' : path.replace(/\.html$/, '');
    Array.prototype.forEach.call(doc.querySelectorAll('[data-nav-key]'), function (link) {
      link.classList.toggle('is-active', link.getAttribute('data-nav-key') === pageKey);
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

       1. PARSE  — resolve the post id from the URL (see below)
       2. RENDER — the author card, already in the HTML
       3. OFFER  — the Android intent link, where it resolves

     Step 2 is server-side. functions/post/[id].js looks the post
     up in Supabase and writes the author into shared-post.html
     before it is sent, which is what puts the avatar in the first
     paint, keeps the card correct with JavaScript off, and — the
     reason it cannot be done here — fills the og:* tags that a
     chat app scrapes without ever running a script.

     So this function never fetches the post. It reacts to what the
     server rendered, and only decides the states the server cannot
     see: no id, an unreadable id, and the intent link.

     ---- WHY THE ID COMES FROM THE PATH, NOT THE QUERY ----
     Share links are pretty: /post/<id>, plus the short /p/<id>.
     `_redirects` rewrites both to /shared-post.html with a **200**
     status. A 200 rewrite serves the target file's bytes but never
     changes the browser's address bar, so on /post/<id> the script
     sees exactly this:

         location.pathname === '/post/<id>'
         location.search   === ''          <-- always empty

     Writing ?post=:id on the rewrite destination looks like it
     should fill that in. It does not: the destination query only
     steers the edge's internal file lookup and never reaches the
     client. Reading the query string alone therefore answered
     "This link doesn't include a post id" to every real share link
     in production, while working perfectly in local dev (where the
     visitor types ?post= by hand).

     So: the PATH is the source of truth, and the query string
     survives only as a fallback for the legacy
     /shared-post.html?post=… shape and for local dev, where
     `python3 -m http.server` does not process `_redirects` at all.
     ------------------------------------------------------------ */

  // Path routes that carry a post id. Keep in sync with `_redirects`.
  var POST_PATH_PATTERN = /\/(?:post|p)\/([^/?#]+)\/?$/i;
  // Legacy query fallbacks, in precedence order.
  var POST_QUERY_KEYS = ['post', 'post_id', 'id'];
  /* Deliberately permissive — UUIDs, short hex ids, nanoid and base64url all
     pass — while rejecting traversal, separators, punctuation-only junk and
     absurd lengths. Tested AFTER percent-decoding, so a %2F can never smuggle
     a slash past the charset check. */
  var POST_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._=-]{2,127}$/;
  var POST_ID_UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  // Must stay equal to target.package_name in .well-known/assetlinks.json.
  var ANDROID_PACKAGE = 'net.agora.app';
  /* The App Links host the APK verifies against. Pinned rather than derived
     from location.host on purpose: an intent built on a *.pages.dev preview or
     on localhost could never hand off to the app, because the manifest only
     declares this host -- so the intent would fail with no fallback at all.
     The browser_fallback_url below stays origin-relative, because that one
     SHOULD land on whichever deployment the visitor is actually on. */
  var CANONICAL_HOST = 'agora.in.net';

  var EMPTY_MISSING_MESSAGE = 'This link doesn\u2019t include a post id.';
  var EMPTY_MALFORMED_MESSAGE = 'That link\u2019s post id doesn\u2019t look valid.';

  function decodeUrlPart(raw) {
    try {
      return decodeURIComponent(raw);
    } catch (error) {
      // A stray "%" throws URIError. Keep the raw text so it fails validation
      // and lands on the "not valid" state instead of killing the script.
      return raw;
    }
  }

  /* Resolves the post id from a Location.
     Returns { status: 'ok'|'missing'|'malformed', id, raw, source }.
     The first candidate that passes validation wins, so an unreadable path
     segment never masks a usable ?post= value. */
  function resolvePostId(location) {
    var candidates = [];

    // PATH first — a 200 rewrite leaves search empty, see the note above.
    var pathMatch = POST_PATH_PATTERN.exec(location.pathname || '');
    if (pathMatch) candidates.push({ value: decodeUrlPart(pathMatch[1]), source: 'path' });

    var params = new URLSearchParams(location.search || '');
    for (var i = 0; i < POST_QUERY_KEYS.length; i++) {
      var queryValue = params.get(POST_QUERY_KEYS[i]);
      if (queryValue) candidates.push({ value: queryValue, source: 'query' });
    }

    if (!candidates.length) return { status: 'missing', id: '', raw: '', source: '' };

    var rejected = '';
    for (var j = 0; j < candidates.length; j++) {
      if (POST_ID_PATTERN.test(candidates[j].value)) {
        return {
          status: 'ok',
          id: candidates[j].value,
          raw: candidates[j].value,
          source: candidates[j].source
        };
      }
      if (!rejected) rejected = candidates[j].value;
    }
    return { status: 'malformed', id: '', raw: rejected, source: '' };
  }

  /* A full UUID (36 characters) would blow out the mono chip, so the chip shows
     the leading group and keeps the whole value in its tooltip. */
  function shortenPostId(id) {
    if (!id) return '';
    if (POST_ID_UUID_PATTERN.test(id)) return id.slice(0, 8);
    return id.length > 12 ? id.slice(0, 8) + '\u2026' : id;
  }

  /* intent:// is Chromium-on-Android only: it asks Android to hand this
     verified App Link to the app and, when the app is missing, to open
     S.browser_fallback_url instead. Gecko ignores intent:// completely, so the
     button is revealed only where it genuinely works — everywhere else the
     regular "Get the app" CTA already covers the visitor. */
  function supportsIntentUrls() {
    var ua = (window.navigator && window.navigator.userAgent) || '';
    if (!/android/i.test(ua)) return false;
    if (/firefox|fxios|focus/i.test(ua)) return false;
    return /chrome|crios|chromium|samsungbrowser|edga|edgios|opr\/|opra/i.test(ua);
  }

  function buildAppIntentUrl(postId) {
    /* If the app is installed, Android hands this post straight to
       net.agora.app. If it is not, Chrome for Android follows
       S.browser_fallback_url to the download page instead of showing an
       error -- which is the whole reason this is an intent:// URL rather than
       a plain https link.

       postId still goes through encodeURIComponent even though the intent
       syntax would take it raw: resolvePostId's charset permits '=', which is
       a delimiter inside an intent URI. For a UUID the encoding is a no-op, so
       the emitted string is byte-identical either way. */
    var fallback = window.location.origin + '/download.html';
    return 'intent://' + CANONICAL_HOST + '/post/' + encodeURIComponent(postId) +
      '#Intent;scheme=https;package=' + ANDROID_PACKAGE +
      ';S.browser_fallback_url=' + encodeURIComponent(fallback) + ';end;';
  }

  /* The avatar is a third-party URL — Supabase Storage, or a Google CDN for
     members who signed in with Google — so it can be slow, blocked by a
     network, or deleted after the page was cached. The frame always paints the
     member's initial underneath, and the image is only trusted once it has
     really loaded; a failure leaves the initial in place instead of a
     broken-image glyph. */
  function initAvatarFallback(scope) {
    var frame = scope.querySelector('[data-avatar-frame]');
    var image = scope.querySelector('[data-avatar]');
    if (!frame || !image || !image.getAttribute('src')) return;

    function settle(loaded) {
      image.hidden = !loaded;
      frame.classList.toggle('has-avatar', loaded);
    }

    if (image.complete && image.naturalWidth > 0) {
      settle(true);
      return;
    }
    image.addEventListener('load', function () { settle(true); });
    image.addEventListener('error', function () { settle(false); });
  }

  /* The app is Android-only, so "already have the app?" is worth asking only
     there. Deliberately broader than supportsIntentUrls(): Android hands a
     verified App Link to the app in EVERY browser, while intent:// is a
     Chromium extension that Gecko ignores completely. */
  function isAndroid() {
    var ua = (window.navigator && window.navigator.userAgent) || '';
    return /android/i.test(ua);
  }

  /* For Android browsers with no intent:// support. This is the same verified
     App Link the app declares, so the OS offers the app instead of the browser
     rendering the page again. */
  function buildAppWebUrl(postId) {
    return 'https://' + CANONICAL_HOST + '/post/' + encodeURIComponent(postId);
  }

  function initSharedPost() {
    var preview = doc.getElementById('post-preview');
    if (!preview) return;

    var chip = preview.querySelector('[data-post-id]');
    var emptyState = doc.getElementById('preview-empty');
    var emptyMessage = emptyState ? emptyState.querySelector('[data-empty-message]') : null;
    var unavailableState = doc.getElementById('preview-unavailable');
    var resultState = doc.getElementById('preview-result');
    var openInAppRow = doc.getElementById('open-in-app-row');
    var openIntentBtn = openInAppRow ? openInAppRow.querySelector('[data-open-intent-btn]') : null;

    /* --- 1. PARSE ------------------------------------------- */
    var resolved = resolvePostId(window.location);

    if (resolved.status !== 'ok') {
      // Only a genuinely absent or unreadable id reaches this branch. A valid
      // /post/<uuid> deep link never does — that was the production bug.
      var missing = resolved.status === 'missing';
      if (emptyMessage) {
        emptyMessage.textContent = missing ? EMPTY_MISSING_MESSAGE : EMPTY_MALFORMED_MESSAGE;
      }
      if (emptyState) emptyState.hidden = false;
      if (resultState) resultState.hidden = true;
      if (unavailableState) unavailableState.hidden = true;
      if (openInAppRow) openInAppRow.hidden = true;
      if (chip) {
        // textContent only, never innerHTML: the id is attacker-controlled
        // URL data and this page is publicly reachable with any path.
        chip.textContent = missing ? 'no post id in link' : shortenPostId(resolved.raw);
        chip.classList.add('chip--idle');
        chip.removeAttribute('title');
      }
      return;
    }

    var postId = resolved.id;

    // The author card is left exactly as the server rendered it: on /post/<id>
    // that is the real member, on a deleted post it is the "no longer
    // available" note, and on any path the Function does not serve it is the
    // honest generic fallback. Only the id-dependent states are ours to set.
    if (emptyState) emptyState.hidden = true;
    if (chip) {
      chip.textContent = 'post #' + shortenPostId(postId);
      chip.classList.remove('chip--idle');   // resolved: leave the idle styling behind
      chip.setAttribute('title', 'Post ' + postId + ' — id read from the link ' + resolved.source);
    }
    initAvatarFallback(preview);

    /* "Already have the app?" Only Android gets the row, since that is the
       only platform the app exists on. Chromium gets the intent:// URI, which
       is the reliable path and carries its own browser_fallback_url. Other
       Android browsers implement neither intent:// nor that fallback, but they
       do follow a verified App Link -- so they get the plain https post URL and
       Android does the handoff. Nowhere is the button a dead link, and nowhere
       does it promise an app the device cannot have. */
    if (openInAppRow && openIntentBtn && isAndroid()) {
      openIntentBtn.setAttribute('href', supportsIntentUrls()
        ? buildAppIntentUrl(postId)
        : buildAppWebUrl(postId));
      openInAppRow.hidden = false;
    }

  }

  /* Reveal device captures and profile portraits only once loaded.
     Pending states preserve the layout until the real assets arrive. */
  function initImages() {
    doc.querySelectorAll('.phone__screen img, .developer-avatar, .rotary-profile__photo').forEach(function (image) {
      function update() {
        var ready = image.complete && image.naturalWidth > 0;
        var frame = image.parentElement;
        if (frame) {
          frame.classList.toggle('is-ready', ready);
          if (frame.hasAttribute('data-rotary-photo-frame')) {
            frame.setAttribute('aria-label', image.alt + (ready ? '' : ' — portrait pending'));
          }
        }
        image.setAttribute('aria-hidden', String(!ready));
      }
      image.addEventListener('load', update);
      image.addEventListener('error', update);
      update();
    });
  }

  /* ------------------------------------------------------------
     8. AMBIENT EXPERIENCE
     A pointer-only cursor orb, a low-contrast dot matrix, and a
     softly filtered looping background track. The first document click
     satisfies autoplay policy and starts the persistent Web Audio source;
     the matrix uses the same pulse.
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
    // This manager is created once per document and deliberately lives outside
    // <main>. PJAX swaps the page shell, but this graph and source keep running.
    if (window.AgoraAudio) return;

    var MUSIC_SRC = '/assets/bgMusic.mpeg';
    var TARGET_VOLUME = 0.075;
    var audio = {
      context: null,
      source: null,
      master: null,
      filter: null,
      compressor: null,
      analyser: null,
      data: null,
      buffer: null,
      bufferPromise: null,
      rawDataPromise: null,
      starting: false,
      isPlaying: false,
      energy: 0,
      unavailable: false
    };
    var soundControl = { button: null, label: null };

    function updateSoundButton() {
      var button = soundControl.button;
      var label = soundControl.label;
      if (!button || !label) return;
      if (audio.unavailable) {
        button.classList.remove('is-on');
        button.setAttribute('aria-pressed', 'false');
        button.setAttribute('aria-label', 'Background music unavailable');
        label.textContent = 'sound unavailable';
        return;
      }
      button.classList.toggle('is-on', audio.isPlaying);
      button.setAttribute('aria-pressed', String(audio.isPlaying));
      button.setAttribute('aria-label', audio.isPlaying ? 'Turn background music off' : 'Turn background music on');
      label.textContent = audio.isPlaying ? 'sound on' : 'sound off';
    }

    function markUnavailable() {
      audio.unavailable = true;
      audio.starting = false;
      audio.isPlaying = false;
      updateSoundButton();
    }

    function createAudioGraph() {
      if (audio.context) return true;
      var AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) {
        markUnavailable();
        return false;
      }

      try {
        var context = new AudioContext();
        var master = context.createGain();
        var filter = context.createBiquadFilter();
        var compressor = context.createDynamicsCompressor();
        var analyser = context.createAnalyser();
        var now = context.currentTime;

        // Set the gain before any node is connected or the source starts. This
        // prevents a decoded buffer from leaking at full volume for one frame.
        master.gain.value = 0;
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(2200, now);
        filter.Q.setValueAtTime(0.25, now);
        compressor.threshold.setValueAtTime(-24, now);
        compressor.knee.setValueAtTime(18, now);
        compressor.ratio.setValueAtTime(3, now);
        compressor.attack.setValueAtTime(0.035, now);
        compressor.release.setValueAtTime(0.45, now);
        /* 2048 rather than 128: bin width drops from ~344Hz to ~21.5Hz at
           44.1kHz, which is what makes a 20-200Hz bass band and a dominant-pitch
           reading meaningful at all -- at 128 the whole bass band was one bin.

           Smoothing 0.35 rather than 0.9. The analyser's smoothing is a running
           average over previous frames, so a high value is exactly what turns a
           piano keystroke into a slow swell; at 0.35 a strike registers on the
           next animation frame. It is not 0 -- that would make the visuals
           jitter on every sample instead of tracking notes. */
        analyser.fftSize = 2048;
        analyser.smoothingTimeConstant = 0.35;

        master.connect(filter);
        filter.connect(compressor);
        compressor.connect(analyser);
        analyser.connect(context.destination);

        audio.context = context;
        audio.master = master;
        audio.filter = filter;
        audio.compressor = compressor;
        audio.analyser = analyser;
        audio.data = new Uint8Array(analyser.frequencyBinCount);
        return true;
      } catch (error) {
        markUnavailable();
        return false;
      }
    }

    function loadMusicBuffer() {
      if (audio.buffer) return Promise.resolve(audio.buffer);
      if (audio.bufferPromise) return audio.bufferPromise;

      var rawData = audio.rawDataPromise || fetch(MUSIC_SRC).then(function (response) {
        if (!response.ok) throw new Error('Music request failed (' + response.status + ').');
        return response.arrayBuffer();
      });
      audio.rawDataPromise = rawData;
      audio.bufferPromise = rawData.then(function (arrayBuffer) {
        if (!arrayBuffer || !audio.context) throw new Error('Audio buffer is unavailable.');
        return audio.context.decodeAudioData(arrayBuffer);
      }).then(function (buffer) {
        audio.buffer = buffer;
        return buffer;
      }).catch(function (error) {
        audio.bufferPromise = null;
        audio.rawDataPromise = null;
        markUnavailable();
        throw error;
      });

      return audio.bufferPromise;
    }

    function startMusic() {
      if (audio.unavailable) return Promise.reject(new Error('Background music is unavailable.'));
      if (audio.isPlaying) return Promise.resolve(true);
      if (audio.starting) return audio.startPromise;
      if (!createAudioGraph()) return Promise.reject(new Error('Audio is unavailable.'));

      audio.starting = true;
      audio.startPromise = Promise.resolve(audio.context.state === 'suspended'
        ? audio.context.resume()
        : true).then(function () {
        return loadMusicBuffer();
      }).then(function (buffer) {
        if (audio.isPlaying) return true;

        var sourceNode = audio.context.createBufferSource();
        sourceNode.buffer = buffer;
        sourceNode.loop = true;
        sourceNode.connect(audio.master);

        // The master gain was initialized at zero before this source exists.
        // Start the loop only after the safe graph is fully connected.
        sourceNode.start(0);
        audio.source = sourceNode;
        audio.isPlaying = true;
        audio.starting = false;

        var now = audio.context.currentTime;
        audio.master.gain.cancelScheduledValues(now);
        audio.master.gain.setTargetAtTime(TARGET_VOLUME, now, 2.8);
        updateSoundButton();
        return true;
      }).catch(function (error) {
        audio.starting = false;
        if (audio.context && audio.context.state === 'closed') markUnavailable();
        throw error;
      });

      return audio.startPromise;
    }

    function stopMusic() {
      if (!audio.context || !audio.master || !audio.isPlaying) return;

      var now = audio.context.currentTime;
      var sourceNode = audio.source;
      audio.isPlaying = false;
      audio.master.gain.cancelScheduledValues(now);
      audio.master.gain.setTargetAtTime(0, now, 0.35);
      audio.source = null;
      if (sourceNode) {
        try {
          sourceNode.stop(now + 1);
        } catch (error) {
          // A source can already be ending when the toggle is pressed.
        }
      }
      updateSoundButton();
    }

    function toggleMusic() {
      if (audio.isPlaying) {
        stopMusic();
        return Promise.resolve(false);
      }
      return startMusic().then(function () {
        updateSoundButton();
        return true;
      });
    }

    // Expose one stable manager for the whole document. It is never recreated
    // when a page's <main> is replaced by the PJAX router.
    /* ---- spectrum tap ----------------------------------------------------
       getEnergy() already reduces the analyser to a single bass-weighted number.
       That suits the dot matrix, but it is too coarse to drive a mesh: every row
       would move together and nothing would read as frequency. This splits the
       SAME FFT into log-spaced bands so different parts of the grid respond to
       different parts of the track.

       Log spacing because the analyser's bins are linear in Hz while music is
       not -- the low bands carry the beat and need only a few bins each, the
       high ones need many just to cover one octave.

       Exposed on the existing facade rather than duplicated: these close over
       the audio graph, and a second graph would drift out of sync with the
       track that is actually playing.                                       */
    var SPECTRUM_BANDS = 8;
    var spectrum = [];
    var spectrumBins = null;
    for (var bandIndex = 0; bandIndex < SPECTRUM_BANDS; bandIndex += 1) spectrum.push(0);

    function buildSpectrumBins(binCount) {
      var bins = [];
      var first = 1;                       // bin 0 is DC offset, not signal
      var last = Math.max(first + SPECTRUM_BANDS, Math.floor(binCount * 0.62));
      for (var i = 0; i < SPECTRUM_BANDS; i += 1) {
        var from = first + (Math.pow(i / SPECTRUM_BANDS, 1.9) * (last - first));
        var to = first + (Math.pow((i + 1) / SPECTRUM_BANDS, 1.9) * (last - first));
        var start = Math.min(binCount - 1, Math.floor(from));
        var end = Math.min(binCount, Math.max(start + 1, Math.floor(to)));
        bins.push([start, end]);
      }
      return bins;
    }

    /* ---- bass / mid / treble / onset / pitch -----------------------------
       Band edges are declared in HZ and converted to bins from the context's
       real sample rate and fftSize. Hardcoding indices is how a "bass" band
       silently becomes a low-mid band: bin 9 is 194Hz at 44.1kHz and 211Hz at
       48kHz, and nothing about the visuals would tell you the difference. */
    var BAND_BASS_HZ = [20, 200];
    var BAND_MID_HZ = [200, 3200];
    var BAND_TREBLE_HZ = [3200, 12000];

    /* Music sits far below full scale in a byte spectrum -- a quiet piano
       passage averages around 0.1 -- so a linear mapping produces almost no
       movement and the canvas looks broken rather than quiet. pow(v, 0.6)
       lifts the low end hard (0.1 becomes 0.25) while still compressing peaks,
       and the per-band gain brings a normal passage into the visible range.
       Treble gets the most gain because it carries the least energy. */
    var SENSITIVITY_EXPONENT = 0.6;
    var BASS_GAIN = 1.55;
    var MID_GAIN = 1.9;
    var TREBLE_GAIN = 2.7;
    var ONSET_GAIN = 7.5;
    var ONSET_DECAY = 0.86;     // per frame: a strike spikes, then fades fast

    var bandBins = null;
    var previousMid = 0;
    var bands = {
      bass: 0, mid: 0, treble: 0, onset: 0,
      pitch: 0.5, centroid: 0.5, computedAt: -1e9
    };

    function buildBandBins(binCount) {
      var rate = (audio.context && audio.context.sampleRate) || 44100;
      var fft = (audio.analyser && audio.analyser.fftSize) || 2048;
      function binFor(hz) {
        var b = Math.round((hz * fft) / rate);
        if (b < 1) return 1;                       // bin 0 is DC offset
        return b > binCount - 1 ? binCount - 1 : b;
      }
      return {
        bass: [binFor(BAND_BASS_HZ[0]), binFor(BAND_BASS_HZ[1])],
        mid: [binFor(BAND_MID_HZ[0]), binFor(BAND_MID_HZ[1])],
        treble: [binFor(BAND_TREBLE_HZ[0]), binFor(BAND_TREBLE_HZ[1])]
      };
    }

    function shape(value, gain) {
      return clamp(Math.pow(clamp(value, 0, 1), SENSITIVITY_EXPONENT) * gain, 0, 1);
    }

    function bandAverage(data, range) {
      var total = 0;
      var count = 0;
      for (var i = range[0]; i < range[1]; i += 1) { total += data[i]; count += 1; }
      return count ? (total / count) / 255 : 0;
    }

    function computeBands() {
      /* Once per frame however many consumers ask. Three canvases each calling
         getByteFrequencyData would be wasteful, but worse: the onset delta is
         frame-over-frame, so computing it twice in one tick would halve the
         spike the second caller sees. */
      var stamp = window.performance && window.performance.now
        ? window.performance.now() : Date.now();
      if (stamp - bands.computedAt < 8) return bands;
      bands.computedAt = stamp;

      if (!audio.isPlaying || !audio.analyser || !audio.data) {
        bands.bass *= 0.9; bands.mid *= 0.9; bands.treble *= 0.9;
        bands.onset *= ONSET_DECAY;
        previousMid *= 0.9;
        return bands;
      }

      audio.analyser.getByteFrequencyData(audio.data);
      if (!bandBins) bandBins = buildBandBins(audio.data.length);
      var data = audio.data;

      var rawBass = bandAverage(data, bandBins.bass);
      var rawMid = bandAverage(data, bandBins.mid);
      var rawTreble = bandAverage(data, bandBins.treble);

      /* Onset is the frame-over-frame RISE in mid energy, floored at zero so a
         note decaying is never mistaken for a note striking. The envelope holds
         the spike for a few frames: one frame is shorter than the eye can
         register, and a keystroke's visual should outlast the sample window. */
      var rise = Math.max(0, rawMid - previousMid);
      previousMid = rawMid;
      bands.onset = Math.max(clamp(rise * ONSET_GAIN, 0, 1), bands.onset * ONSET_DECAY);

      // Attack fast, release slower: snap onto a note, ease off it.
      bands.bass += (shape(rawBass, BASS_GAIN) - bands.bass)
        * (shape(rawBass, BASS_GAIN) > bands.bass ? 0.5 : 0.14);
      bands.mid += (shape(rawMid, MID_GAIN) - bands.mid)
        * (shape(rawMid, MID_GAIN) > bands.mid ? 0.5 : 0.14);
      bands.treble += (shape(rawTreble, TREBLE_GAIN) - bands.treble)
        * (shape(rawTreble, TREBLE_GAIN) > bands.treble ? 0.55 : 0.16);

      /* Dominant pitch and spectral centroid, over the mid+treble range. Both
         are reported 0..1 on a LOG scale because pitch perception is
         logarithmic: a linear map would spend most of its range on the top
         octave and a climbing melody would look pinned near 1. */
      var lo = bandBins.mid[0];
      var hi = bandBins.treble[1];
      var peak = -1;
      var peakBin = lo;
      var weighted = 0;
      var totalEnergy = 0;
      for (var b = lo; b < hi; b += 1) {
        var v = data[b];
        if (v > peak) { peak = v; peakBin = b; }
        weighted += v * Math.log(b + 1);
        totalEnergy += v;
      }
      var logLo = Math.log(lo + 1);
      var logSpan = Math.log(hi + 1) - logLo;
      bands.pitch = clamp((Math.log(peakBin + 1) - logLo) / logSpan, 0, 1);
      var centroidBin = totalEnergy ? Math.exp(weighted / totalEnergy) - 1 : lo;
      bands.centroid = clamp((Math.log(centroidBin + 1) - logLo) / logSpan, 0, 1);
      return bands;
    }

    function getBands() {
      var b = computeBands();
      /* A copy, not the live object. computeBands mutates ONE instance in place
         -- that is what makes the per-frame cache work -- so returning it would
         let a caller's snapshot silently change underneath them between reads.
         Internal callers go through readBands() once per frame and use it
         immediately, so the copy costs three small objects a frame and removes
         a footgun from the public facade. */
      return {
        bass: b.bass, mid: b.mid, treble: b.treble,
        onset: b.onset, pitch: b.pitch, centroid: b.centroid
      };
    }

    function getSpectrum() {
      var i;
      if (!audio.isPlaying || !audio.analyser || !audio.data) {
        // Decay rather than snap to zero, so stopping the track eases the mesh
        // back into its silent drift instead of dropping it in a single frame.
        for (i = 0; i < SPECTRUM_BANDS; i += 1) spectrum[i] *= 0.9;
        return spectrum;
      }
      audio.analyser.getByteFrequencyData(audio.data);
      if (!spectrumBins) spectrumBins = buildSpectrumBins(audio.data.length);
      for (i = 0; i < SPECTRUM_BANDS; i += 1) {
        var range = spectrumBins[i];
        var total = 0;
        var count = 0;
        for (var bin = range[0]; bin < range[1]; bin += 1) {
          total += audio.data[bin];
          count += 1;
        }
        var next = count ? total / count / 255 : 0;
        // Attack fast, release slow: the mesh snaps onto a beat and eases off it,
        // which is how the eye reads a visual as being driven by sound rather
        // than merely moving at the same time as it.
        spectrum[i] += (next - spectrum[i]) * (next > spectrum[i] ? 0.42 : 0.11);
      }
      return spectrum;
    }

    window.AgoraAudio = {
      start: startMusic,
      stop: stopMusic,
      toggle: toggleMusic,
      get isPlaying() { return audio.isPlaying; },
      getEnergy: getEnergy,
      getPulse: getPulse,
      getSpectrum: getSpectrum,
      getBands: getBands,
      SPECTRUM_BANDS: SPECTRUM_BANDS
    };

    /* Broadband loudness, for consumers that want one number. Derived from the
       same shaped bands everything else uses rather than from a second pass over
       raw bins: at fftSize 128 the old bin 2-17 window covered roughly
       0.7-5.8kHz, and at 2048 the same indices would cover 43-366Hz. Keeping the
       indices would have silently turned "energy" into "bass". */
    function getEnergy() {
      if (!audio.isPlaying || !audio.analyser || !audio.data) {
        audio.energy *= 0.94;
        return audio.energy;
      }
      var b = computeBands();
      var next = (b.bass * 0.5) + (b.mid * 0.35) + (b.treble * 0.15);
      audio.energy += (next - audio.energy) * 0.12;
      return audio.energy;
    }

    function getPulse(timestamp) {
      var clock = audio.context ? audio.context.currentTime : timestamp / 1000;
      var breathe = 0.5 + (0.5 * Math.sin(clock * Math.PI * 0.09));
      return audio.isPlaying ? (audio.energy * 0.65) + (breathe * 0.18) : 0;
    }

    function initSoundControl() {
      var button = doc.createElement('button');
      var label = doc.createElement('span');
      button.type = 'button';
      button.className = 'ambient-toggle';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', 'Turn background music on');
      button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 10v4h3l4 3V7l-4 3H4Z"/><path d="M16 9.5a4 4 0 0 1 0 5"/><path d="M18.5 7a7.5 7.5 0 0 1 0 10"/></svg>';
      label.textContent = 'sound off';
      button.appendChild(label);
      doc.body.appendChild(button);
      soundControl.button = button;
      soundControl.label = label;

      button.addEventListener('click', function () {
        // The capture-phase first-click listener may already be starting the
        // track. Do not interpret that same first click as an immediate stop.
        if (!audio.isPlaying) {
          startMusic().then(updateSoundButton).catch(function () {
            markUnavailable();
          });
          return;
        }
        stopMusic();
      });
      updateSoundButton();
    }

    /* ---- the one background mesh, for the whole site ----------------------
       A jittered grid triangulated into a low-poly field, displaced by waves
       that travel left to right and driven by the audio analysis.

       There used to be two overlapping grids: a square dot matrix on every page
       and a sine wave mesh on the credits screen alone. On credits they sat on
       top of each other, doubled the frame cost, and read as moire rather than
       as depth. This is now the only canvas the site creates.

       A jittered grid rather than a true Delaunay, deliberately. The topology
       (which diagonal each cell splits along, and how far each vertex is nudged
       off the lattice) is hashed from its (row, column) once per resize, so it
       is identical every frame. A triangulation recomputed per frame would boil
       -- the vertices move, so the triangles would flip constantly -- and
       re-running Bowyer-Watson on ~900 moving points is not something a phone
       survives. Visually the two are indistinguishable at this opacity.     */
    function initAmbientMesh() {
      var canvas = doc.createElement('canvas');
      var context = canvas.getContext('2d');
      if (!context) return;

      canvas.className = 'ambient-mesh';
      canvas.setAttribute('aria-hidden', 'true');
      doc.body.insertBefore(canvas, doc.body.firstChild);

      // Colours are read back out of the stylesheet's dedicated mesh channels
      // rather than hardcoded, so the layer tracks the active theme instead of
      // painting dark-mode indigo onto a light page. The fallbacks are the dark
      // theme's real values, so an unreadable custom property degrades to the
      // intended palette rather than to black.
      var FALLBACK_NODE = '147,112,255';
      var FALLBACK_HI = '190,210,255';
      var FALLBACK_GLOW = '124,92,255';
      var FALLBACK_LINE = '120,95,255';

      var MESH_GLOW_BLOOM = 0.42;   // minimal glow: a soft edge, not a halo
      var MESH_GLOW_SPREAD = 1.9;   // sprite covers radius * 2 * this

      /* Keeping the lattice from tearing -- a SPATIAL-FREQUENCY budget, not an
         amplitude one, and the difference is the whole reason the waves can be
         as large as they are.

         Two neighbouring vertices cross only when their displacements DIFFER by
         more than the gap between them. A smooth swell cannot do that however
         large it gets: the Gaussian front has a standard deviation around 230px,
         four cells wide, so adjacent vertices ride it almost identically and the
         field is free to heave by a third of a cell. Capping the front's
         amplitude the way an earlier draft did bought no safety at all and threw
         away most of the motion.

         What CAN tear the lattice are the sharp terms. The per-vertex jitter's
         wavelength is exactly one cell, so it spends 2*JITTER of the budget
         unconditionally. The travelling sine's wavelength shrinks as the dominant
         pitch rises: a sine of amplitude A and wavenumber k moves one neighbour
         past the next by at most A*k*spacing, so it is safe while
         A <= (TEAR_LIMIT - 2*JITTER) / k. k is known per frame, which means the
         ceiling is computed from the wavelength the audio actually asked for
         rather than guessed at -- a bright passage gets finer ripples AND a lower
         amplitude ceiling, which is what a real membrane does.

         Both bounds are verified by running the mesh and measuring the signed
         area of all ~550 triangles, in silence and at full scale; see
         test_the_displacement_budget_holds_the_lattice_together. */
      var JITTER = 0.12;        // per-vertex, fixed at resize
      var TEAR_LIMIT = 0.45;    // how far a vertex may move past its neighbour

      var WAVE_SPEED = 210;     // px/s phase speed of the travelling sine
      var FRONT_SPEED = 260;    // px/s: the localized crest sweeping in +x
      var FRONT_PAD = 420;      // px of off-screen lead-in and lead-out

      function readPalette() {
        try {
          var styles = window.getComputedStyle(doc.documentElement);
          // Computed custom properties come back with the source spacing, e.g.
          // "109, 40, 217"; the canvas wants a bare "r,g,b" triple.
          var node = (styles.getPropertyValue('--mesh-node-rgb') || '').replace(/\s+/g, '');
          var hi = (styles.getPropertyValue('--mesh-node-hi-rgb') || '').replace(/\s+/g, '');
          var glow = (styles.getPropertyValue('--mesh-glow-rgb') || '').replace(/\s+/g, '');
          var line = (styles.getPropertyValue('--mesh-line-rgb') || '').replace(/\s+/g, '');
          return {
            node: node || FALLBACK_NODE,
            hi: hi || FALLBACK_HI,
            glow: glow || FALLBACK_GLOW,
            line: line || FALLBACK_LINE
          };
        } catch (error) {
          return {
            node: FALLBACK_NODE, hi: FALLBACK_HI,
            glow: FALLBACK_GLOW, line: FALLBACK_LINE
          };
        }
      }

      var palette = readPalette();
      var sprites = buildSprites(palette);

      function buildSprites(p) {
        return {
          node: makeGlowSprite(p.node, p.glow, MESH_GLOW_BLOOM),
          hi: makeGlowSprite(p.hi, p.glow, MESH_GLOW_BLOOM)
        };
      }

      var width = 0;
      var height = 0;
      var spacing = 62;
      var columns = 0;
      var rows = 0;
      var pixelRatio = 1;
      var pts = null;        // per-frame vertex positions, rows*columns*2
      var jitterX = null;    // per-vertex, fixed at resize
      var jitterY = null;
      var flips = null;      // per-cell: which diagonal that cell splits along

      function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        // A triangulated field reads denser than the square grid it replaced --
        // three edges per cell instead of two -- so the cell is coarser than the
        // old matrix's 30/36px while carrying MORE structure. At 54px a 1440x900
        // viewport gets ~600 vertices, ~550 triangles and ~1700 edges, which is
        // the "richly filled" end of readable without ~2600 blits a frame.
        spacing = width < 600 ? 38 : 54;
        pixelRatio = Math.min(window.devicePixelRatio || 1, 1.75);
        canvas.width = Math.floor(width * pixelRatio);
        canvas.height = Math.floor(height * pixelRatio);
        canvas.style.width = width + 'px';
        canvas.style.height = height + 'px';
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        // One spare cell each way, so vertices displaced off the edge still have
        // neighbours to be joined to and the mesh never shows a ragged border.
        columns = Math.ceil(width / spacing) + 3;
        rows = Math.ceil(height / spacing) + 3;

        var vertices = rows * columns;
        var cells = (rows - 1) * (columns - 1);
        pts = new Float32Array(vertices * 2);
        jitterX = new Float32Array(vertices);
        jitterY = new Float32Array(vertices);
        flips = new Uint8Array(Math.max(0, cells));

        /* Deterministic jitter from a hash of (row, column). Not Math.random():
           the topology has to survive from frame to frame, and a jitter
           recomputed per frame would make the whole mesh boil. The high and low
           halves of the hash drive x and y, so the two axes are uncorrelated. */
        for (var i = 0; i < vertices; i += 1) {
          var h = hash2(i % columns, (i - (i % columns)) / columns);
          jitterX[i] = (((h & 0xffff) / 0xffff) - 0.5) * 2 * JITTER * spacing;
          jitterY[i] = (((h >>> 16) / 0xffff) - 0.5) * 2 * JITTER * spacing;
        }
        // Which diagonal each cell uses, hashed so the lean varies organically
        // instead of settling into a checkerboard or one uniform lattice.
        for (var c = 0; c < flips.length; c += 1) {
          flips[c] = hash2(c, 0x5f3a7c11) & 1;
        }
      }

      function draw(timestamp) {
        // A PJAX swap may have detached us between frames; stop rather than keep
        // painting an invisible canvas for the rest of the session.
        if (!canvas.isConnected) return;

        var time = timestamp / 1000;
        var b = readBands();

        /* Scroll coupling is exclusive to the credits screen. Nothing else
           publishes a spin, so readSpin() would already return ~0 -- but the
           body class is checked explicitly anyway, because a PJAX swap away from
           credits leaves the last velocity in the slot and it must not keep
           rippling a page that has no wheels on it. */
        var credits = doc.body.classList.contains('credits-rotary-page');
        var spin = credits ? readSpin(timestamp) : 0;
        var spinWave = clamp(Math.abs(spin) / SPIN_REFERENCE, 0, 1);
        var spinDir = spin < 0 ? -1 : 1;

        context.clearRect(0, 0, width, height);

        /* ---- the left-to-right wave field ---------------------------------
           Every travelling term here is phased (k*x - w*t). A crest satisfies
           x = (phase + w*t)/k, so it moves in +x as time grows. The opposite
           sign is the mistake to avoid: it looks identical frame to frame and
           sweeps right to left.

           Two components, because one is not enough to read as propagation. A
           continuous sine gives the whole field a direction of travel, and a
           localized Gaussian front sweeping the width gives the eye a crest to
           follow -- that is what makes the motion legible as a wave crossing
           the screen rather than as surface shimmer.                        */
        var kx = 0.0062 + (b.pitch * 0.019);   // pitch shifts the wavelength
        var travel = time * (kx * WAVE_SPEED);
        var period = width + (FRONT_PAD * 2);
        var front = ((time * FRONT_SPEED) % period) - FRONT_PAD;
        var frontSigma = Math.max(120, width * 0.16);
        var frontSigma2 = 2 * frontSigma * frontSigma;

        /* Amplitudes, split by how sharp each term is.

           The smooth ones are generous precisely because smoothness is what keeps
           them safe. The front is the term the eye follows: a localized crest
           crossing the whole width every ~9s, which is what makes the motion read
           as a wave travelling through the field rather than as the field
           shimmering in place. It is present at full strength with the music OFF,
           because the site boots muted and a background that only moves once you
           press play is a background that looks broken. */
        var driftAmp = spacing * 0.10;
        var frontAmp = spacing * (0.20 + (b.bass * 0.18) + (b.onset * 0.24));
        var spinAmp = spacing * 0.22 * spinWave;

        // The sharp one, capped against its own wavenumber for the reason above.
        var sineAmp = Math.min((TEAR_LIMIT - (2 * JITTER)) / kx,
          spacing * ((0.30 * b.bass) + (0.18 * b.treble)));

        // Shockwave rings the credits wheels push on a committed contributor.
        var pulses = activePulses(timestamp);
        var pulseCount = pulses.length;

        var row;
        var column;
        var index = 0;
        for (row = 0; row < rows; row += 1) {
          for (column = 0; column < columns; column += 1) {
            var i = (row * columns) + column;
            var gx = ((column - 1) * spacing) + jitterX[i];
            var gy = ((row - 1) * spacing) + jitterY[i];

            var wave = Math.sin((gx * kx) - travel + (gy * 0.0022));
            var fd = gx - front;
            var packet = Math.exp(-(fd * fd) / frontSigma2);

            // Idle drift keeps the background alive with the music off; every
            // audio term below is MULTIPLIED by its band, so silence cancels it
            // exactly rather than leaving a wobble that ignores the mute button.
            /* Every phase here is (spatial term) - (time term), the +x
               convention. The idle drift used to be written the other way round
               -- sin(time*0.23 + column*0.17) -- which is a crest satisfying
               column = (C - 0.23*t)/0.17, so it walked LEFT. It was also the
               loudest term in silence, which is the site's default state, so the
               one wave every visitor saw with the music off travelled backwards.
               Measuring the trough's drift over 620 frames is what found it; no
               amount of reading the source did. */
            var dy = (Math.sin((column * 0.17) + (row * 0.41) - (time * 0.23)) * driftAmp)
              + (wave * sineAmp)
              - (packet * frontAmp);
            var dx = (Math.cos((column * 0.37) - (time * 0.19)) * driftAmp * 0.5)
              + (wave * sineAmp * 0.45);

            for (var p = 0; p < pulseCount; p += 1) {
              var pulse = pulses[p];
              var pdx = gx - pulse.x;
              var pdy = gy - pulse.y;
              var pd = Math.sqrt((pdx * pdx) + (pdy * pdy));
              var ring = pd - pulse.radius;
              var lift = Math.exp(-(ring * ring) / pulse.sigma2) * pulse.strength;
              dy -= lift;
              if (pd > 0.001) dx += (pdx / pd) * lift * 0.35;
            }

            if (spinWave > 0.001) {
              // Radial from the middle of the screen, and the direction follows
              // the sign of the spin so scrolling up and down travel oppositely.
              var sx = gx - (width * 0.5);
              var sy = gy - (height * 0.5);
              var sd = Math.sqrt((sx * sx) + (sy * sy));
              var sPhase = (sd * 0.012) - (time * 3.1 * spinDir);
              dy += Math.sin(sPhase) * spinAmp;
              dx += Math.cos(sPhase) * spinAmp * 0.4;
            }

            pts[index] = gx + dx;
            pts[index + 1] = gy + dy;
            index += 2;
          }
        }

        /* ---- the triangulated wireframe -----------------------------------
           Three edge families per cell: its top, its left, and one diagonal.
           Rows and columns are contiguous polylines; the diagonals are not, so
           they go in as individual segments but share the column pass's single
           beginPath/stroke.

           Two stroke calls for the whole grid. A stroke per edge would be ~3400
           of them a frame, and the state changes alone would not survive a
           phone -- the same reason the vertices are blitted from one sprite
           instead of being given individual shadowBlur values.            */
        var rowAlpha = Math.min(0.18, 0.15 + (b.treble * 0.02) + (b.onset * 0.01));
        var colAlpha = Math.min(0.2, 0.16 + (b.treble * 0.025) + (b.onset * 0.015));
        context.lineWidth = 1;

        context.strokeStyle = 'rgba(' + palette.line + ',' + rowAlpha.toFixed(4) + ')';
        context.beginPath();
        for (row = 0; row < rows; row += 1) {
          var rowBase = row * columns * 2;
          for (column = 0; column < columns; column += 1) {
            var o = rowBase + (column * 2);
            if (column === 0) context.moveTo(pts[o], pts[o + 1]);
            else context.lineTo(pts[o], pts[o + 1]);
          }
        }
        context.stroke();

        // Columns a step brighter than rows, so the field keeps some depth
        // instead of reading as one flat lattice. Both stay inside 0.15-0.20.
        context.strokeStyle = 'rgba(' + palette.line + ',' + colAlpha.toFixed(4) + ')';
        context.beginPath();
        for (column = 0; column < columns; column += 1) {
          for (row = 0; row < rows; row += 1) {
            var v = ((row * columns) + column) * 2;
            if (row === 0) context.moveTo(pts[v], pts[v + 1]);
            else context.lineTo(pts[v], pts[v + 1]);
          }
        }
        for (row = 0; row < rows - 1; row += 1) {
          var cellBase = row * (columns - 1);
          for (column = 0; column < columns - 1; column += 1) {
            var a = ((row * columns) + column) * 2;
            var br = ((row * columns) + column + 1) * 2;
            var bl = (((row + 1) * columns) + column) * 2;
            var d = (((row + 1) * columns) + column + 1) * 2;
            if (flips[cellBase + column]) {
              context.moveTo(pts[a], pts[a + 1]);
              context.lineTo(pts[d], pts[d + 1]);
            } else {
              context.moveTo(pts[br], pts[br + 1]);
              context.lineTo(pts[bl], pts[bl + 1]);
            }
          }
        }
        context.stroke();

        /* Vertices on top of the wireframe. 1.5px to 2.2px, 0.25 to 0.30 alpha.
           With the whole field capped that low, the visible contrast has to come
           from somewhere else -- so a vertex's alpha and radius ride the
           travelling crest. The wave is legible as a bright band sweeping left
           to right without any element of it exceeding its ceiling. */
        for (row = 0; row < rows; row += 1) {
          for (column = 0; column < columns; column += 1) {
            var q = ((row * columns) + column) * 2;
            var x = pts[q];
            var fx = x - front;
            var near = Math.exp(-(fx * fx) / frontSigma2);
            var w = 0.5 + (0.5 * Math.sin((x * kx) - travel));
            var radius = Math.min(2.2, 1.5 + (w * 0.35) + (b.bass * 0.2) + (near * 0.15));
            var alpha = Math.min(0.3,
              0.25 + (w * 0.02) + (near * 0.03) + (b.onset * 0.02) + (b.treble * 0.01));
            var highlight = ((column + row) % 4) === 0 || near > 0.75;

            drawGlow(context, highlight ? sprites.hi : sprites.node,
              highlight ? palette.hi : palette.node,
              x, pts[q + 1], radius, alpha, MESH_GLOW_SPREAD);
          }
        }

        if (!reduceMotion()) window.requestAnimationFrame(draw);
      }

      resize();
      window.addEventListener('resize', resize, { passive: true });

      // Follow the OS if the scheme flips mid-session. A paused canvas (the
      // reduced-motion path draws a single frame and never loops) will not
      // repaint by itself, so nudge one frame through in that case.
      function onSchemeChange() {
        palette = readPalette();
        sprites = buildSprites(palette);   // the glow is baked with the palette
        if (reduceMotion()) {
          draw(window.performance && window.performance.now ? window.performance.now() : 0);
        }
      }

      if (typeof window.matchMedia === 'function') {
        var schemeQuery = window.matchMedia('(prefers-color-scheme: light)');
        if (typeof schemeQuery.addEventListener === 'function') {
          schemeQuery.addEventListener('change', onSchemeChange);
        } else if (typeof schemeQuery.addListener === 'function') {
          schemeQuery.addListener(onSchemeChange); // Safari < 14
        }
      }

      draw(0);
    }

    initCursor();
    initSoundControl();
    initAmbientMesh();

    /* Preload bytes without touching the AudioContext. The first click below
       resumes/creates the context and starts the already-persistent loop.

       The `typeof fetch` guard is less about old browsers than about the SHAPE of
       the failure. The `.catch()` below can only handle a rejected promise; if
       `fetch` is not a function the call throws a ReferenceError synchronously,
       before there is a promise to catch on. And because initAmbientExperience()
       runs first in boot(), that one throw used to abort boot() outright -- taking
       routing, the menu, the contact form and the credits screen down with it.
       A missing decorative layer has to cost the decoration, not the page. */
    audio.rawDataPromise = typeof fetch === 'function' ? fetch(MUSIC_SRC).then(function (response) {
      if (!response.ok) throw new Error('Music request failed (' + response.status + ').');
      return response.arrayBuffer();
    }).catch(function () {
      audio.rawDataPromise = null;
      return null;
    }) : null;

    function firstClickStartsAudio() {
      document.removeEventListener('click', firstClickStartsAudio, true);
      startMusic().catch(function () {
        if (audio.context && audio.context.state === 'closed') markUnavailable();
      });
    }
    document.addEventListener('click', firstClickStartsAudio, true);
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
      name: 'Yashvardhan Bhaskar',
      role: 'Design & ideas',
      photo: '/assets/yashvardhan-bhaskar.jpg',
      contributions: 'Original maker of this credits screen, turning its visual language, motion, and sense of space into something people can feel.',
      bio: 'A designer and idea innovator — the original maker of this credits screen.'
    },
    {
      name: 'The Agora Public',
      role: 'The public',
      photo: '/assets/agora-public.jpg',
      contributions: 'For everyone who uses Agora, tests it in the real world, and makes the platform what it is through every visit and conversation.',
      bio: 'The people who use, question, and return to Agora — the reason this public square exists.'
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
    var nameTags = bottomDisc ? bottomDisc.querySelectorAll('[data-rotary-name-tag]') : [];
    var count = page.querySelector('[data-rotary-count]');
    var total = page.querySelector('[data-rotary-total]');
    var scrollAffordance = page.querySelector('[data-scroll-affordance]');

    if (!topPlate || !bottomPlate || !topSegments.length || !bottomSegments.length || !tagHangers.length || nameTags.length !== bottomSegments.length) return;

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
      transition: 0,
      touchActive: false,
      touchMoved: false,
      touchStartY: 0,
      touchLastY: 0,
      touchLastTime: 0,
      touchVelocity: 0
    };
    var SEGMENT = 120;

    /* --- input sensitivity ------------------------------------------------
       How much of the physical gesture reaches the wheel. The old 0.05 meant a
       single mouse notch (deltaY 100) turned the wheel 5 degrees, so reaching
       one 120-degree sector took ~24 notches: that is the "excessive dead
       space" feeling. 0.11 puts it at ~11 degrees per notch.                */
    var WHEEL_DAMPING = 0.11;
    var WHEEL_MAX_STEP = 45;      // one event can never throw it past a sector
    var TOUCH_DAMPING = 0.92;     // was 0.78: a 120-degree sector now takes
                                  // ~130px of drag instead of ~155px
    var TOUCH_MAX_STEP = 40;
    var TOUCH_FLING_VELOCITY = 0.72;

    /* --- snapping ---------------------------------------------------------
       Two thresholds. A hesitant drag still has to pass half a sector before it
       commits, so the wheel never jumps under a hand that is still deciding; a
       fast scroll commits at 26%, which is what removes the dead space without
       making the wheel feel trigger-happy. COMMIT_BOOST_MS is how long a fast
       input keeps that quicker threshold armed.                            */
    var SNAP_DELAY = 90;          // was 120
    var SNAP_THRESHOLD = 0.5;     // was 0.65
    var SNAP_THRESHOLD_FAST = 0.26;
    var COMMIT_BOOST_MS = 240;
    var FAST_WHEEL_DELTA = 60;    // a wheel event above this counts as "hard"

    /* --- the spring -------------------------------------------------------
       Critically damped on purpose: damping == 2*sqrt(stiffness) is the exact
       boundary at which the wheel returns to its target as fast as possible
       WITHOUT overshooting. Under-damped and it wobbles past the contributor
       and settles back; over-damped and it crawls in. Critically damped it
       decays exponentially -- fast while the error is large, automatically
       easing off as it arrives -- which is the "slows down and cleanly locks
       into place" behaviour, with no separate ease-out stage to tune.

       All three constants are per SECOND, not per frame, and the integrator
       below works in seconds. The previous version multiplied by a frame count
       normalised to 16.67ms, which is frame-rate dependent: the same flick
       settled noticeably differently on a 144Hz display than on a 60Hz one. */
    var SPRING_STIFFNESS = 132;
    var SPRING_DAMPING = 2 * Math.sqrt(SPRING_STIFFNESS);
    var MAX_ANGULAR_VELOCITY = 760;   // deg/s ceiling: hard scrolls stay bounded
    var SETTLE_ANGLE = 0.02;          // inside this, lock exactly onto the target
    var SETTLE_VELOCITY = 0.6;        // so the wheel never idles a hair off

    /* How long the arriving block's ease-up plays. Must equal the
       rotary-arrive animation duration in style.css. */
    var ARRIVAL_MS = 420;

    // A fast input arms the quicker snap threshold for a short window.
    var commitBoostUntil = 0;

    function nowMs() {
      return window.performance && window.performance.now
        ? window.performance.now() : Date.now();
    }

    function armCommitBoost() {
      commitBoostUntil = nowMs() + COMMIT_BOOST_MS;
    }
    var teamLength = ROTARY_TEAM.length;

    /* The sector geometry lives in the stylesheet -- --segment-angle on each
       segment, --sector-offset on each disc -- so read it back from there.

       These were two hardcoded arrays plus two literal centres (40 and 220),
       i.e. a third and fourth copy of numbers the CSS already owns. Copies
       drift, and a drifted copy does not throw: it quietly puts the scale and
       opacity emphasis on the wrong contributor while the wheel still turns,
       still snaps, and still looks like it works. Deriving them means the CSS
       is the only place a sector angle can be wrong. */
    function readAngleDegrees(element, property) {
      if (!element || typeof window.getComputedStyle !== 'function') return null;
      var value = parseFloat(window.getComputedStyle(element).getPropertyValue(property));
      return isFinite(value) ? value : null;
    }

    function segmentAngles(segments) {
      return Array.prototype.map.call(segments, function (segment) {
        return readAngleDegrees(segment, '--segment-angle');
      });
    }

    var TOP_SEGMENT_ANGLES = segmentAngles(topSegments);
    var BOTTOM_SEGMENT_ANGLES = segmentAngles(bottomSegments);
    var TOP_ACTIVE_CENTER = readAngleDegrees(topDisc, '--sector-offset');
    var BOTTOM_ACTIVE_CENTER = readAngleDegrees(bottomDisc, '--sector-offset');

    /* If the stylesheet cannot be read (very old engine, computed styles
       unavailable), skip the JS emphasis entirely rather than guess. The
       .rotary-segment.is-active rule still scales and fades the settled
       segment correctly on its own, so this degrades instead of misplacing. */
    var anglesReadable = TOP_ACTIVE_CENTER !== null
      && BOTTOM_ACTIVE_CENTER !== null
      && TOP_SEGMENT_ANGLES.concat(BOTTOM_SEGMENT_ANGLES).every(function (angle) {
        return angle !== null;
      });

    // Every detail block, so an arrival marker can be cleared from all of them
    // before being set on the one that is arriving. A marker left behind by a
    // rapid series of sector changes would keep that block animating forever.
    var allContents = [];
    [topSegments, bottomSegments].forEach(function (segments) {
      Array.prototype.forEach.call(segments, function (segment) {
        var content = segment.querySelector('.rotary-segment__content');
        if (content) allContents.push(content);
      });
    });

    if (total) total.textContent = String(teamLength).padStart(2, '0');

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
      Array.prototype.forEach.call(nameTags, function (tag, index) {
        // Name labels are static DOM content; only their emphasis follows the
        // settled member so rotation can never rewrite or replace the name.
        tag.classList.toggle('is-active', index === state.memberIndex);
      });
      if (count) count.textContent = String(state.memberIndex + 1).padStart(2, '0');
    }

    function showMember(index, animate) {
      state.memberIndex = (index + teamLength) % teamLength;

      /* Nothing in the copy is rewritten when the wheel settles. Each segment
         permanently owns its member -- setSegmentContent maps segment index to
         member index -- so the only things that actually change are the
         .is-active classes and the 01/02/03 counter.

         The old version dimmed EVERY block to nothing, waited 190ms, "swapped"
         text that was already correct, and faded back. That hid a no-op and
         blinked the whole screen on every sector change, fighting the per-frame
         emphasis the spring is already ramping smoothly. So: update the classes
         and the counter immediately, with no timer to drift out of sync, and
         animate the one thing that genuinely changed -- which block arrived. */
      setMemberText();
      if (!animate) return;

      state.transition += 1;
      var transitionId = state.transition;

      /* A committed contributor is a physical impact, so it drives a shockwave
         ring into the background mesh. Strength tracks how hard the wheel was
         moving on arrival: a fling lands louder than a gentle snap. Called only
         on the animated path, so the initial showMember(0, false) at boot does
         not detonate a ring on a screen nobody has touched. */
      pushMeshPulse(0.55 + (Math.abs(state.rotationVelocity) / MAX_ANGULAR_VELOCITY));

      allContents.forEach(function (content) { content.classList.remove('is-arriving'); });

      var arriving = [topSegments[state.memberIndex], bottomSegments[state.memberIndex]]
        .map(function (segment) {
          return segment ? segment.querySelector('.rotary-segment__content') : null;
        })
        .filter(function (content) { return !!content; });

      arriving.forEach(function (content) {
        // Reflow between removing and re-adding, so stepping through sectors
        // faster than the animation plays restarts it instead of skipping it.
        void content.offsetWidth;
        content.classList.add('is-arriving');
      });

      window.setTimeout(function () {
        if (transitionId !== state.transition) return;
        arriving.forEach(function (content) { content.classList.remove('is-arriving'); });
      }, ARRIVAL_MS);
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

      // Each bottom label lives inside its own rotated sector. Counter the
      // whole bottom-wheel rotation in JS; CSS also subtracts that sector's
      // fixed base angle, keeping every name perfectly horizontal.
      Array.prototype.forEach.call(nameTags, function (tag, index) {
        tag.style.setProperty('--tag-counter-rotation', (-bottomRotation) + 'deg');
        tag.classList.toggle('is-active', index === state.memberIndex);
      });

      if (anglesReadable) {
        updateSegmentVisuals(topSegments, TOP_SEGMENT_ANGLES, topRotation, TOP_ACTIVE_CENTER);
        updateSegmentVisuals(bottomSegments, BOTTOM_SEGMENT_ANGLES, bottomRotation, BOTTOM_ACTIVE_CENTER);
      }
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
      // A hard scroll commits early; a slow, deliberate drag still has to pass
      // the resting threshold so the wheel cannot jump under a hesitant hand.
      var threshold = nowMs() < commitBoostUntil ? SNAP_THRESHOLD_FAST : SNAP_THRESHOLD;

      var direction = displacement < 0 ? -1 : 1;
      var distance = Math.abs(displacement);
      var completeSegments = Math.floor(distance / SEGMENT);
      var remainder = distance - (completeSegments * SEGMENT);
      var extraSegment = remainder / SEGMENT >= threshold ? 1 : 0;
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

      /* Critically damped spring, integrated in SECONDS so the settle is
         identical at 60Hz and 144Hz. Acceleration is the pull toward the target
         minus a drag proportional to velocity; at damping == 2*sqrt(stiffness)
         the error decays exponentially with no overshoot, so the wheel is fast
         while the gap is large and eases itself into the sector as it closes. */
      var dt = clamp(timestamp - state.lastTime, 8, 34) / 1000;
      var error = state.rotationTarget - state.rotation;
      var acceleration = (error * SPRING_STIFFNESS) - (state.rotationVelocity * SPRING_DAMPING);
      state.rotationVelocity = clamp(
        state.rotationVelocity + (acceleration * dt),
        -MAX_ANGULAR_VELOCITY, MAX_ANGULAR_VELOCITY
      );
      state.rotation += state.rotationVelocity * dt;

      /* Publish the spin so both canvases can ripple from it. Scrolling has to
         move the mesh with the music muted or paused, and the canvases are not
         reachable from here through any call chain -- so the velocity goes via a
         module-level slot. readSpin() decays it by AGE, which matters because
         this loop stops the moment the wheel settles and would otherwise leave
         the last ripple frozen on screen forever. */
      wheelSpin.velocity = state.rotationVelocity;
      wheelSpin.at = timestamp;

      /* Lock exactly onto the target once it is close and slow, so the spring
         does not asymptote forever and idle a hair off-sector.

         This must test the error AFTER the integration above, and must run before
         the stop test at the end of the frame. Testing the pre-integration error
         lets the loop exit one frame early: a frame arrives with error 0.025 (so
         no lock), integrates down to 0.0198, and the stop test below then sees
         "close enough" and quits -- freezing the wheel at 119.98 degrees instead
         of 120. Invisible to the eye, but it is the difference between a wheel
         that locks and one that merely stops. */
      if (Math.abs(state.rotationTarget - state.rotation) < SETTLE_ANGLE
        && Math.abs(state.rotationVelocity) < SETTLE_VELOCITY) {
        state.rotation = state.rotationTarget;
        state.rotationVelocity = 0;
      }

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
      var moving = Math.abs(state.rotationTarget - state.rotation) > 0.02
        || Math.abs(state.rotationVelocity) > SETTLE_VELOCITY
        || tagsMoving;
      if (moving) queueFrame();
    }

    function normalizeWheelDelta(event) {
      var delta = event.deltaY;
      if (event.deltaMode === 1) delta *= 16;
      if (event.deltaMode === 2) delta *= window.innerHeight;
      return delta;
    }

    function applyRotationDelta(rotationDelta) {
      if (!rotationDelta) return;
      state.rotationTarget += rotationDelta;
      Array.prototype.forEach.call(tagHangers, function (tag, index) {
        var impulse = rotationDelta * (index === state.memberIndex ? 0.16 : 0.08);
        state.tagVelocities[index] = clamp(state.tagVelocities[index] - impulse, -18, 18);
      });
      queueFrame();
    }

    function hideScrollAffordance() {
      if (scrollAffordance) scrollAffordance.classList.add('is-hidden');
    }

    function handleWheel(event) {
      if (event.cancelable) event.preventDefault();
      var delta = normalizeWheelDelta(event);
      if (!delta) return;
      hideScrollAffordance();

      var rotationDelta = clamp(delta * WHEEL_DAMPING, -WHEEL_MAX_STEP, WHEEL_MAX_STEP);
      // A hard notch arms the quicker snap threshold so one firm flick advances
      // a whole sector instead of needing the user to keep scrolling into it.
      if (Math.abs(delta) >= FAST_WHEEL_DELTA) armCommitBoost();
      applyRotationDelta(rotationDelta);
      scheduleSnap();
    }

    function isInteractiveTouch(event) {
      var target = event.target;
      return !!(target && target.closest && target.closest('a, button, input, select, textarea, [data-cursor="interactive"]'));
    }

    function handleTouchStart(event) {
      if (event.touches.length !== 1 || isInteractiveTouch(event)) {
        state.touchActive = false;
        return;
      }

      var touch = event.touches[0];
      var now = window.performance && window.performance.now ? window.performance.now() : Date.now();
      window.clearTimeout(state.snapTimer);
      state.snapRequested = false;
      state.touchActive = true;
      state.touchMoved = false;
      state.touchStartY = touch.clientY;
      state.touchLastY = touch.clientY;
      state.touchLastTime = now;
      state.touchVelocity = 0;
    }

    function handleTouchMove(event) {
      if (!state.touchActive || event.touches.length !== 1) return;
      if (event.cancelable) event.preventDefault();

      var touch = event.touches[0];
      var now = window.performance && window.performance.now ? window.performance.now() : Date.now();
      var elapsed = Math.max(1, now - state.touchLastTime);
      var verticalDelta = state.touchLastY - touch.clientY;
      state.touchLastY = touch.clientY;
      state.touchLastTime = now;
      state.touchVelocity = verticalDelta / elapsed;
      if (Math.abs(touch.clientY - state.touchStartY) > 4) {
        state.touchMoved = true;
        hideScrollAffordance();
      }

      // Finger-up is the same direction as scrolling down: it advances the
      // wheel. The accumulated target is evaluated by the shared 65% snap rule.
      applyRotationDelta(clamp(verticalDelta * TOUCH_DAMPING, -TOUCH_MAX_STEP, TOUCH_MAX_STEP));
      if (Math.abs(state.touchVelocity) >= TOUCH_FLING_VELOCITY) armCommitBoost();
    }

    function finishTouch(event) {
      if (!state.touchActive) return;
      if (event.cancelable) event.preventDefault();

      if (state.touchMoved) {
        var displacement = state.rotationTarget - state.anchorRotation;
        var distance = Math.abs(displacement);
        var velocity = Math.abs(state.touchVelocity);

        // A short, fast flick gets the same 65% commitment as a long drag.
        // A slow drag below that threshold is handed back to the current snap.
        if (velocity >= TOUCH_FLING_VELOCITY && distance < SEGMENT * SNAP_THRESHOLD) {
          var direction = state.touchVelocity < 0 ? -1 : 1;
          var remaining = (SEGMENT * SNAP_THRESHOLD) - distance + 0.5;
          applyRotationDelta(direction * remaining);
        }
        scheduleSnap();
        queueFrame();
      }

      state.touchActive = false;
      state.touchMoved = false;
      state.touchVelocity = 0;
    }

    showMember(0, false);
    render();
    page.addEventListener('wheel', handleWheel, { passive: false });
    page.addEventListener('touchstart', handleTouchStart, { passive: false });
    page.addEventListener('touchmove', handleTouchMove, { passive: false });
    page.addEventListener('touchend', finishTouch, { passive: false });
    page.addEventListener('touchcancel', finishTouch, { passive: false });
  }

  /* ------------------------------------------------------------
     9. DYNAMIC DOWNLOAD LINK
     Exactly ONE element on the whole site downloads the APK: the
     "Download APK" button on download.html, marked
     .dynamic-download-btn / id="dynamic-download-btn". Every other
     "Get the app" CTA is ordinary page navigation to
     /download.html, authored href="/download.html"
     data-page="download", so the install decision happens on the one
     page that can carry the version, size and requirements next to
     it. Those links are also PJAX-routed like any internal link.

     That single button ships in the HTML with GitHub's permanent
     latest-release redirect as its href:

       …/agora-android/releases/latest/download/app.apk

     GitHub resolves that path server-side to the matching asset of
     the newest release, so the file downloads with no JavaScript,
     no API call, and no rate limit — and it never goes stale when a
     new build ships. It is also what stays in place whenever the
     lookup below fails (dead network, 403/429 rate limit, non-JSON
     response, release with no .apk).

     The lookup is therefore an enhancement, not the load-bearing
     path. It does two things the permanent redirect cannot:
       · resolve the exact asset when a release names its file
         something other than app.apk (older builds such as
         app-release-v1.apk), where the redirect would 404
       · refresh the version/filename/size facts, which appear on
         download.html and also on the home and shared-post pages

     Lookup order, cheapest and most reliable first:
       1. sessionStorage   — one call per tab, reused across PJAX swaps
       2. /api/latest-release — same-origin Pages Function, edge cached
       3. api.github.com   — direct, in case the Function is unavailable
     ------------------------------------------------------------ */
  var DOWNLOAD_BUTTON_SELECTOR = '#dynamic-download-btn, .dynamic-download-btn';
  // Version facts are shown on pages that no longer carry a download button
  // (the home closing panel and the shared-post card both quote the size), so
  // the lookup has to run for these too, not only for the button.
  var RELEASE_FACTS_SELECTOR = '[data-download-tag], [data-download-file], [data-download-size]';
  var RELEASE_PROXY_URL = '/api/latest-release';
  var RELEASE_API_URL = 'https://api.github.com/repos/JayBhaskarCoding/agora-android/releases/latest';
  var RELEASE_PAGE_URL = 'https://github.com/JayBhaskarCoding/agora-android/releases/latest';
  // Release assets are published as app.apk, which is what makes the
  // permanent redirect below work. Keep this in sync with the release process.
  var PREFERRED_APK_NAME = 'app.apk';
  var RELEASE_DOWNLOAD_URL = RELEASE_PAGE_URL + '/download/' + PREFERRED_APK_NAME;
  var RELEASE_TIMEOUT = 8000;                 // ms before a lookup is abandoned
  var RELEASE_CACHE_KEY = 'agora.latestRelease';
  var RELEASE_CACHE_TTL = 15 * 60 * 1000;     // sessionStorage freshness window
  var RELEASE_RETRY_COOLDOWN = 5 * 60 * 1000; // pause after a failed lookup

  var releaseState = { data: null, request: null, failedAt: 0 };

  function isDynamicDownloadLink(element) {
    if (!element || !element.classList || !element.getAttribute) return false;
    return element.classList.contains('dynamic-download-btn')
      || element.id === 'dynamic-download-btn'
      || element.hasAttribute('data-dynamic-download');
  }

  function readReleaseCache() {
    try {
      var raw = window.sessionStorage.getItem(RELEASE_CACHE_KEY);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (!cached || typeof cached.url !== 'string' || !cached.url) return null;
      if (Date.now() - (Number(cached.cachedAt) || 0) > RELEASE_CACHE_TTL) return null;
      return cached;
    } catch (error) {
      return null;   // private browsing / disabled storage: just re-fetch
    }
  }

  function writeReleaseCache(release) {
    try {
      window.sessionStorage.setItem(RELEASE_CACHE_KEY, JSON.stringify(release));
    } catch (error) {
      // Quota or permission errors are not worth surfacing to the visitor.
    }
  }

  /**
   * Choose the asset to install. An exact `app.apk` always wins (that is the
   * published name, and the one the permanent redirect resolves); otherwise
   * the first asset whose name or download URL ends in .apk is used, so older
   * releases named e.g. app-release-v1.apk still resolve.
   */
  function pickApkAsset(release) {
    var assets = release && Object.prototype.toString.call(release.assets) === '[object Array]'
      ? release.assets
      : [];
    var firstApk = null;
    for (var i = 0; i < assets.length; i++) {
      var asset = assets[i];
      if (!asset) continue;
      var name = typeof asset.name === 'string' ? asset.name : '';
      var url = typeof asset.browser_download_url === 'string' ? asset.browser_download_url : '';
      if (name.toLowerCase() === PREFERRED_APK_NAME) return asset;
      if (!firstApk && (/\.apk$/i.test(name) || /\.apk$/i.test(url))) firstApk = asset;
    }
    return firstApk;
  }

  function normalizeRelease(payload) {
    // The proxy answers { ok, release }; the GitHub API answers the release itself.
    var release = payload && payload.release && payload.release.assets ? payload.release : payload;
    if (!release || typeof release !== 'object') return null;

    var asset = pickApkAsset(release);
    var url = asset && typeof asset.browser_download_url === 'string' ? asset.browser_download_url.trim() : '';
    // Anything that is not an https asset URL is treated as "no APK found".
    if (!/^https:\/\/[^\s]+\.apk$/i.test(url)) return null;

    var fileName = asset && typeof asset.name === 'string' && asset.name
      ? asset.name
      : decodeURIComponent(url.split('/').pop() || 'agora.apk');

    return {
      url: url,
      fileName: fileName,
      size: Number(asset && asset.size) || 0,
      tag: typeof release.tag_name === 'string' ? release.tag_name : '',
      name: typeof release.name === 'string' ? release.name : '',
      publishedAt: typeof release.published_at === 'string' ? release.published_at : '',
      htmlUrl: typeof release.html_url === 'string' && release.html_url ? release.html_url : RELEASE_PAGE_URL
    };
  }

  function fetchReleaseJson(url) {
    // Reject rather than throw: a synchronous exception here would escape the
    // promise chain below and take the rest of bootPage() down with it.
    if (typeof fetch !== 'function') return Promise.reject(new Error('fetch is unavailable.'));

    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = controller ? window.setTimeout(function () { controller.abort(); }, RELEASE_TIMEOUT) : null;

    return fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/vnd.github+json, application/json;q=0.9' },
      signal: controller ? controller.signal : undefined,
      // Cross-origin to GitHub: never send cookies, never let a CDN serve a
      // stale body, and let a 403/404/429 surface as an error we can catch.
      credentials: 'omit',
      cache: 'no-store'
    }).then(function (response) {
      if (!response.ok) throw new Error('Release lookup failed for ' + url + ' (' + response.status + ').');
      var type = response.headers && response.headers.get ? (response.headers.get('content-type') || '') : '';
      // A static host answering /api/latest-release with its 404 HTML page
      // must not be mistaken for release data.
      if (type.toLowerCase().indexOf('json') === -1) throw new Error('Release lookup returned a non-JSON response.');
      return response.json();
    }).then(normalizeRelease).finally(function () {
      if (timer) window.clearTimeout(timer);
    });
  }

  function loadLatestRelease() {
    if (releaseState.data) return Promise.resolve(releaseState.data);
    if (releaseState.request) return releaseState.request;

    var cached = readReleaseCache();
    if (cached) {
      releaseState.data = cached;
      return Promise.resolve(cached);
    }

    // A failure is remembered briefly. PJAX route swaps re-run bootPage, and
    // re-hitting an API that just rate-limited us on every click only makes
    // the cooldown longer — the fallback hrefs are perfectly usable meanwhile.
    if (releaseState.failedAt && Date.now() - releaseState.failedAt < RELEASE_RETRY_COOLDOWN) {
      return Promise.resolve(null);
    }

    var request = fetchReleaseJson(RELEASE_PROXY_URL)
      .catch(function () {
        // Proxy missing (local dev server), rate limited, or offline: try GitHub.
        return fetchReleaseJson(RELEASE_API_URL);
      })
      .then(function (release) {
        if (!release) throw new Error('The latest release has no downloadable .apk asset.');
        release.cachedAt = Date.now();
        releaseState.data = release;
        releaseState.failedAt = 0;
        writeReleaseCache(release);
        return release;
      })
      .catch(function (error) {
        // Fail graceful: every CTA keeps its authored href — GitHub's
        // permanent /releases/latest/download/app.apk redirect — so the click
        // still downloads the newest build with no API involved.
        releaseState.failedAt = Date.now();
        if (window.console && window.console.warn) {
          window.console.warn('Agora: release lookup failed; download buttons keep the permanent GitHub redirect.', error);
        }
        return null;
      });

    releaseState.request = request;
    // Clear the in-flight guard once settled so a later visit can retry.
    request.then(function () { releaseState.request = null; }, function () { releaseState.request = null; });
    return request;
  }

  function formatReleaseSize(bytes) {
    var size = Number(bytes) || 0;
    if (size <= 0) return '';
    var mb = size / (1024 * 1024);
    if (mb < 1) return '≈' + Math.max(1, Math.round(size / 1024)) + ' KB';
    return '≈' + (mb >= 10 ? String(Math.round(mb)) : String(Math.round(mb * 10) / 10)) + ' MB';
  }

  function describeRelease(release) {
    var parts = [];
    if (release.tag) parts.push(release.tag);
    if (release.fileName) parts.push(release.fileName);
    var size = formatReleaseSize(release.size);
    if (size) parts.push(size);
    return 'Download Agora for Android — ' + (parts.join(' · ') || 'latest release') + '.';
  }

  function applyReleaseToPage(release) {
    if (!release || !release.url) return;

    try {
      // When the newest release publishes app.apk, the permanent redirect the
      // HTML already carries is the better href: it re-resolves at click time,
      // so a build shipped mid-session is picked up without a cache refresh.
      // Only override it when the release names its asset something else,
      // because the redirect would 404 for that file.
      var keepPermanent = release.fileName.toLowerCase() === PREFERRED_APK_NAME;
      var buttons = doc.querySelectorAll(DOWNLOAD_BUTTON_SELECTOR);
      Array.prototype.forEach.call(buttons, function (button) {
        var current = button.getAttribute('href');
        var target = keepPermanent && current === RELEASE_DOWNLOAD_URL ? current : release.url;
        button.setAttribute('href', target);
        button.setAttribute('data-apk-url', target);
        if (release.tag) button.setAttribute('data-apk-tag', release.tag);
        // A tooltip is enough to confirm the exact build; the visible label
        // ("Get the app" / "Download APK") is part of the design contract.
        button.setAttribute('title', describeRelease(release));
        button.classList.add('is-release-linked');
      });

      // Version facts on download.html (and the size chip on home) are authored
      // as static fallbacks; each is refreshed only if a hook exists.
      var facts = {
        'data-download-tag': release.tag || release.name || '',
        'data-download-file': release.fileName || '',
        'data-download-size': formatReleaseSize(release.size)
      };
      Object.keys(facts).forEach(function (attribute) {
        if (!facts[attribute]) return;
        Array.prototype.forEach.call(doc.querySelectorAll('[' + attribute + ']'), function (node) {
          node.textContent = facts[attribute];
        });
      });

      doc.documentElement.classList.add('has-release-link');
    } catch (error) {
      if (window.console && window.console.warn) {
        window.console.warn('Agora: could not update the download buttons.', error);
      }
    }
  }

  function initDynamicDownload() {
    try {
      if (!doc.querySelector(DOWNLOAD_BUTTON_SELECTOR)
        && !doc.querySelector(RELEASE_FACTS_SELECTOR)) return;

      // PJAX swaps the header/main and re-runs bootPage, so re-apply from the
      // in-memory or sessionStorage cache first — no extra network round trip.
      if (!releaseState.data) releaseState.data = readReleaseCache();
      if (releaseState.data) {
        applyReleaseToPage(releaseState.data);
        return;
      }

      loadLatestRelease().then(function (release) {
        // A route swap may have replaced the buttons while the fetch was in
        // flight; applyReleaseToPage queries the live DOM, so this is safe.
        if (release) applyReleaseToPage(release);
      });
    } catch (error) {
      // Upgrading the links is a progressive enhancement: never let it break
      // page boot. The authored permanent-redirect hrefs stay clickable.
      if (window.console && window.console.warn) {
        window.console.warn('Agora: dynamic download setup failed; keeping the permanent GitHub redirect links.', error);
      }
    }
  }

  /* ------------------------------------------------------------
     10. WHEEL REACTIVITY
     Bass swells the wheels, a piano onset flares the dashed outer
     ring and the spokes, treble makes the rim ticks and the tags glint.

     This needs its own loop. The rotary's frame loop stops as soon as
     the wheel settles -- correct for the physics, useless for anything
     driven by the music, since a bass pulse has to keep breathing on a
     wheel that is not moving.
     ------------------------------------------------------------ */
  var wheelReactivityCleanup = null;

  function initWheelReactivity() {
    var wanted = doc.body.classList.contains('credits-rotary-page');

    if (!wanted) {
      if (wheelReactivityCleanup) wheelReactivityCleanup();
      return;
    }
    // Already driving; bootPage re-ran after a PJAX swap that stayed here.
    if (wheelReactivityCleanup) return;

    var discs = doc.querySelectorAll('.rotary-disc');
    if (!discs.length) return;

    var alive = true;
    var last = { bass: -1, onset: -1, treble: -1 };

    function write(bass, onset, treble) {
      Array.prototype.forEach.call(discs, function (disc) {
        disc.style.setProperty('--wheel-bass', bass);
        disc.style.setProperty('--wheel-onset', onset);
        disc.style.setProperty('--wheel-treble', treble);
      });
    }

    wheelReactivityCleanup = function () {
      alive = false;
      write('0', '0', '0');      // leave the wheels static, not mid-pulse
      wheelReactivityCleanup = null;
    };

    /* A bass-driven scale IS motion, so reduced motion gets the zeros written
       once and no loop at all -- the same bargain the canvases already strike. */
    if (reduceMotion()) {
      write('0', '0', '0');
      return;
    }

    function frame() {
      if (!alive) return;
      // A PJAX swap detached the wheels: stop driving elements nobody can see.
      if (!doc.body.contains(discs[0])) { alive = false; return; }

      var b = readBands();
      /* Quantised to 1/255th before comparing. Writing a custom property
         invalidates style for the whole subtree, and with the music off all
         three sit at 0 -- an unquantified write would cost a style
         recalculation of both wheels, every frame, forever, to set the same
         three numbers again. */
      var bass = Math.round(b.bass * 255) / 255;
      var onset = Math.round(b.onset * 255) / 255;
      var treble = Math.round(b.treble * 255) / 255;
      if (bass !== last.bass || onset !== last.onset || treble !== last.treble) {
        last.bass = bass;
        last.onset = onset;
        last.treble = treble;
        write(bass.toFixed(3), onset.toFixed(3), treble.toFixed(3));
      }
      window.requestAnimationFrame(frame);
    }

    frame();
  }

  /* ------------------------------------------------------------
     Boot and PJAX page hydration
     ------------------------------------------------------------ */
  function bootPage() {
    initImages();
    initCreditsRotary();
    // After initCreditsRotary, on every swap rather than once per session: this
    // is torn down on the way OUT of the credits page as well as rebuilt on the
    // way in, so the wheels keep pulsing in step with the mesh instead of the
    // custom properties going stale on a returned-to page. The mesh itself is
    // NOT here -- it is global and is built once, in initAmbientExperience.
    initWheelReactivity();
    initRouting();
    // After initRouting: syncPageLinks rewrites a[data-page] hrefs, and the
    // download CTAs must keep the release URL that wins this ordering.
    initDynamicDownload();
    initMenu();
    initSmoothScroll();
    initReveal();
    initChrome();
    initContactForm();
    initSharedPost();
  }

  function boot() {
    /* Ambient audio/cursor/mesh are initialized once; everything below is safe to
       rerun after the router swaps a page shell.

       The ambient layer is wrapped because it is DECORATIVE and it runs FIRST.
       Anything it throws -- a browser without fetch, without AudioContext, without
       matchMedia, a canvas that refuses a 2D context -- would otherwise abort boot()
       before bootPage() and leave the visitor with a page whose navigation, menu and
       credits screen are all dead but whose background is fine. That is precisely
       backwards. The same reasoning is why initDynamicDownload catches around its own
       setup; this makes it structural rather than something each section remembers. */
    try {
      initAmbientExperience();
    } catch (error) {
      if (window.console && window.console.warn) {
        window.console.warn('Agora: the ambient layer failed to start; the page itself is unaffected.', error);
      }
    }
    bootPage();
    scrollToRouteHash(window.location.hash);
  }

  if (doc.readyState === 'loading') {
    doc.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
