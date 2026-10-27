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
     6b. Contact flow     — the three-step category / identity / message wizard
     7. Shared-post       — URL param parsing + post preview stub
     8. Ambient layer      — custom cursor, streaming music, the background mesh
     9. Dynamic download  — newest GitHub release APK for every CTA
     10. Email hydration  — addresses assembled at runtime, never in the markup
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
    home: '/',
    download: '/download',
    about: '/about',
    credits: '/credits',
    contact: '/contact',
    privacy: '/privacy',
    terms: '/terms'
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

  // Explicit mapping: assets and enriched /post/:id or /p/:id routes must never
  // be treated as static page aliases.
  var PAGE_FILES = {
    '/': '/index.html', '/about': '/about.html', '/download': '/download.html',
    '/contact': '/contact.html', '/credits': '/credits.html',
    '/shared-post': '/shared-post.html', '/privacy': '/privacy.html', '/terms': '/terms.html'
  };

  function canonicalPath(url) {
    var path = url.pathname || '/';
    if (path === '/index.html') return '/';
    var clean = path.replace(/\.html$/, '').replace(/\/$/, '') || '/';
    return Object.prototype.hasOwnProperty.call(PAGE_FILES, clean) ? clean : path;
  }

  var initialUrlNormalized = false;

  function normalizeInitialUrl() {
    if (initialUrlNormalized) return;
    initialUrlNormalized = true;
    var url = new URL(window.location.href);
    var clean = canonicalPath(url);
    if (clean !== url.pathname) {
      window.history.replaceState(window.history.state, '', clean + url.search + url.hash);
    }
  }

  function fetchPage(url, options) {
    return fetch(url.href, options).then(function (response) {
      // Python's static server knows the file, not the clean route. Retry only a
      // real 404 and only for a known static page; history still uses url, never
      // this implementation-detail URL. Preserve the query, omit the fragment.
      var file = PAGE_FILES[canonicalPath(url)];
      if (response.status === 404 && file && file !== url.pathname) {
        var fallback = new URL(file + url.search, url.origin);
        return fetch(fallback.href, options);
      }
      return response;
    });
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
        ? new URL('/' + href, window.location.href)
        : new URL(href, window.location.href);
    } catch (error) {
      return null;
    }
    if (url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) return null;
    url.pathname = canonicalPath(url);
    if (!Object.prototype.hasOwnProperty.call(PAGE_FILES, url.pathname)) return null;
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
    // Do not leave the policy's canonical URL attached after a PJAX departure.
    var currentCanonical = doc.querySelector('link[rel="canonical"]');
    var nextCanonical = parsed.querySelector('link[rel="canonical"]');
    if (currentCanonical) currentCanonical.remove();
    if (nextCanonical) doc.head.appendChild(nextCanonical.cloneNode(true));
    var nextDescription = parsed.querySelector('meta[name="description"]');
    var currentDescription = doc.querySelector('meta[name="description"]');
    if (nextDescription && currentDescription) currentDescription.setAttribute('content', nextDescription.getAttribute('content') || '');
  }

  function routeTo(url, pushHistory) {
    url = new URL(url.href);
    url.pathname = canonicalPath(url);
    var targetPath = canonicalPath(url);
    var currentUrl = new URL(window.location.href);
    // User navigation to the address already displayed must not fetch or push.
    // popstate is different: the URL has changed but the DOM may still be old.
    if (pushHistory && targetPath === canonicalPath(currentUrl)) {
      scrollToRouteHash(url.hash);
      return Promise.resolve();
    }
    // Compare against the hydrated DOM route, not only location.pathname:
    // popstate updates the address bar before this handler runs.
    if (targetPath === routerState.currentPath && url.search === currentUrl.search) {
      scrollToRouteHash(url.hash);
      return Promise.resolve();
    }
    if (routerState.navigating) return Promise.resolve();

    routerState.navigating = true;
    if (routerState.abortController) routerState.abortController.abort();
    routerState.abortController = typeof AbortController === 'function' ? new AbortController() : null;
    doc.documentElement.classList.add('is-pjax-loading');

    return fetchPage(url, {
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
    // Leave same-page anchors and query links to native browser behavior.
    // Never turn them into a PJAX swap or another history entry ourselves.
    if (canonicalPath(url) === canonicalPath(new URL(window.location.href))) return;
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

    /* Drop the menu state when resizing up to the desktop layout.

       Guarded, like every other matchMedia call in this file -- this one was not,
       and the placement is what made it expensive. It runs in bootPage(), which is
       deliberately OUTSIDE boot()'s try/catch so that a real hydration failure is
       never swallowed. So in any environment without matchMedia the throw landed
       here and took out everything after it: the menu, smooth scrolling, the reveal
       animations, the header chrome, the contact flow AND the contact form -- while
       the ambient layer, wrapped above, carried on working perfectly. That is
       exactly the inverted priority the wrapper exists to prevent, in the other half
       of boot(). Found by driving the contact flow in jsdom, which has no
       matchMedia; nothing about the page looked wrong until a click did nothing. */
    if (typeof window.matchMedia !== 'function') return;
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
  /* Assembled rather than written out. This one only ever reaches the DOM as text
     inside an error message, never as markup, so Cloudflare's edge parser would
     not touch it -- but keeping the literal out of EVERY served file is what makes
     "no raw address in the site" a claim a test can check with one grep instead of
     a list of exceptions. */
  var CONTACT_EMAIL = ['mail', 'agora.in.net'].join('@');
  var SUBMIT_TIMEOUT = 12000;                // ms before we give up on the API

  /* Set by initSignalFlow(), read by the form wiring below, so a gate step can hand
     a validated form to the flow instead of posting it. A closure variable rather
     than a custom DOM event because both halves live in this one IIFE and an event
     would only add a boundary between them. Null on every page that has no flow. */
  var signalFlow = null;

  function initContactForm() {
    /* Every form carrying the marker, not one hardcoded id. The contact page has two
       -- the identity gate and the message form -- and they share one validation
       machinery, so wiring them from a list is what stops the gate growing its own
       half-copy of the rules that then drifts. */
    Array.prototype.forEach.call(doc.querySelectorAll('form[data-contact-form]'), wireContactForm);
  }

  function wireContactForm(form) {
    // Resolved from the form's own attributes: the identity gate has a status line
    // but no success panel, and looking either up by a fixed id would send one
    // form's messages to the other's slot.
    var statusId = form.getAttribute('data-status');
    var successId = form.getAttribute('data-success');
    var status = statusId ? doc.getElementById(statusId) : null;
    var success = successId ? doc.getElementById(successId) : null;
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
        // Only reachable when the topic is the editable one: the four fixed
        // categories fill and lock it in step 1, so it cannot be empty there.
        return value.trim() ? '' : 'Add a topic so it reaches the right inbox.';
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
      var topicValue = topic ? (topic.value || '').trim() : '';
      return {
        name: (form.elements.name.value || '').trim(),
        email: (form.elements.email.value || '').trim(),
        topic: topicValue,
        /* Was `topic.options[topic.selectedIndex].text`, which throws on an <input>
           because it has no options -- a TypeError inside the submit handler, after
           validation had already passed, so the message would have died silently at
           the last step. The topic is an input now: readonly and category-filled for
           the four fixed categories, freely typed for "Anything else". Either way its
           value IS its label, so both fields carry the same string and the Function's
           `topicLabel || topic` picks it up unchanged. */
        topicLabel: topicValue,
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

      /* A gate step, not a submission. Validation has already passed by here, so
         this is the point to hand the collected identity to the flow and move on --
         posting it would send a message with no content in it. */
      if (form.hasAttribute('data-signal-advance') && signalFlow) {
        signalFlow.advance(form);
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
     6b. THE THREE-STEP CONTACT FLOW  (contact.html only)

     Category, then identity, then message. Three panels, one section, and exactly
     one of them is in the document flow at a time -- the other two are `hidden`,
     which puts them out of the tab order and out of the accessibility tree rather
     than merely styling them away. A panel that is only visually hidden is a panel
     a keyboard visitor still has to tab through to get past.

     This owns state; it does not own validation. Both forms are wired by
     initContactForm() from the same rule table, and the gate step hands its
     validated values back here through the `signalFlow` slot instead of posting
     them -- so there is one set of rules and one submit path per form.
     ------------------------------------------------------------ */
  function initSignalFlow() {
    var root = doc.querySelector('[data-signal]');
    if (!root) return;

    var panels = root.querySelectorAll('[data-signal-step]');
    var dots = root.querySelectorAll('[data-signal-dot]');
    var identity = doc.getElementById('signal-identity');
    var message = doc.getElementById('feedback-form');
    var success = doc.getElementById('feedback-success');
    if (!panels.length || !identity || !message) return;

    var ANYTHING_ELSE = 'Anything else';
    var state = { category: '' };

    // Whether the visitor corrected step 3's carried-over identity directly. If
    // they did, a later pass through step 2 must not silently overwrite the
    // correction; if they did not, step 2 stays authoritative.
    var edited = { name: false, email: false };
    ['name', 'email'].forEach(function (key) {
      var input = message.elements[key];
      if (input) input.addEventListener('input', function () { edited[key] = true; });
    });

    function panelFor(n) {
      for (var i = 0; i < panels.length; i += 1) {
        if (parseInt(panels[i].getAttribute('data-signal-step'), 10) === n) return panels[i];
      }
      return null;
    }

    function show(n) {
      Array.prototype.forEach.call(panels, function (panel) {
        var on = parseInt(panel.getAttribute('data-signal-step'), 10) === n;
        panel.hidden = !on;
        panel.classList.toggle('is-current', on);
      });
      Array.prototype.forEach.call(dots, function (dot) {
        var at = parseInt(dot.getAttribute('data-signal-dot'), 10);
        dot.classList.toggle('is-current', at === n);
        dot.classList.toggle('is-done', at < n);
      });
      var named = root.querySelector('[data-signal-category]');
      if (named) named.textContent = state.category || 'your message';

      /* Move focus to the new panel's heading. Without this, focus stays on the
         control that was clicked -- which is now inside a hidden panel, so a
         keyboard visitor is left focused on nothing and a screen reader announces
         no change at all. The headings carry tabindex="-1" for exactly this. */
      var target = panelFor(n);
      var heading = target ? target.querySelector('[tabindex="-1"]') : null;
      if (heading && typeof heading.focus === 'function') heading.focus();
    }

    function applyCategory() {
      var topic = message.elements.topic;
      if (!topic) return;
      var hint = doc.querySelector('[data-topic-hint]');
      var locked = state.category !== ANYTHING_ELSE;
      topic.value = locked ? state.category : '';
      /* readOnly, NOT disabled -- and the distinction is the whole bug class here.
         A disabled control is omitted from FormData, so a locked topic would
         silently vanish from the submission and the Function would reject the
         message for a missing field, at the last step, after the visitor had
         written the whole thing. readOnly keeps it in the payload and keeps it
         focusable for a screen reader while still refusing edits. */
      topic.readOnly = locked;
      topic.classList.toggle('is-locked', locked);
      if (locked) {
        topic.setAttribute('aria-readonly', 'true');
        topic.removeAttribute('placeholder');
        if (hint) hint.textContent = 'Set by the category you chose in step 1.';
      } else {
        topic.removeAttribute('aria-readonly');
        topic.placeholder = 'What is this regarding?';
        if (hint) hint.textContent = 'Type anything — this becomes the subject line.';
      }
    }

    function restart() {
      state.category = '';
      edited.name = false;
      edited.email = false;
      message.reset();
      // showSuccess() hid the form and revealed the panel; undo both, or a second
      // message would have nowhere to be written.
      message.hidden = false;
      if (success) success.hidden = true;
      applyCategory();
      show(1);
    }

    // Step 1: the whole card is the control, so it is a <button> rather than a div
    // with a click handler and a nested link -- clicking anywhere on it works, it is
    // reachable by keyboard, and there is no second, smaller target to miss.
    Array.prototype.forEach.call(root.querySelectorAll('[data-category]'), function (card) {
      card.addEventListener('click', function () {
        state.category = card.getAttribute('data-category') || '';
        applyCategory();
        show(parseInt(card.getAttribute('data-signal-goto'), 10) || 2);
      });
    });

    Array.prototype.forEach.call(root.querySelectorAll('[data-signal-back]'), function (button) {
      button.addEventListener('click', function () {
        show(parseInt(button.getAttribute('data-signal-back'), 10) || 1);
      });
    });

    Array.prototype.forEach.call(root.querySelectorAll('[data-signal-restart]'), function (button) {
      button.addEventListener('click', restart);
    });

    applyCategory();

    signalFlow = {
      /* Called by the gate form's submit handler once its own validation has
         passed. Carries the identity into step 3 and leaves it editable. */
      advance: function (form) {
        ['name', 'email'].forEach(function (key) {
          var from = form.elements[key];
          var to = message.elements[key];
          if (from && to && !edited[key]) to.value = from.value;
        });
        show(parseInt(form.getAttribute('data-signal-advance'), 10) || 3);
      },
      reset: restart
    };
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
    var fallback = window.location.origin + '/download';
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
    var finePointer = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)');
    if (!finePointer || !finePointer.matches || reduceMotion()) return;

    /* One disturbance field and one filter host for the lifetime of the
       document. PJAX replaces <main> and the header, never <body>, so both
       survive a swap -- and the guard makes a second boot a no-op rather than
       a second sprite. */
    var lens = doc.querySelector('.cursor-lens');
    if (!lens) {
      lens = doc.createElement('span');
      lens.className = 'cursor-lens';
      lens.setAttribute('aria-hidden', 'true');
      doc.body.appendChild(lens);
    }
    installLiquidFilter();
    if (lens.getAttribute('data-cursor-ready') === 'true') {
      doc.body.classList.add('has-custom-cursor');
      return;
    }
    lens.setAttribute('data-cursor-ready', 'true');
    doc.body.classList.add('has-custom-cursor');

    var state = { x: -100, y: -100, tx: -100, ty: -100, frame: 0 };
    /* The one thing that changes on a hovered control: the aim ring widens a
       little. Nothing on the page itself is measured, transformed or
       recoloured, so a heading or a link cannot pop, shift or re-letter under
       the pointer. */
    var targetSelector = 'a, button, .btn, .nav__link, input, select, textarea, [role="button"]';

    function paint() {
      state.frame = 0;
      /* The field is 1:1 with the pointer. There is no interpolation here: a
         lerp is a permanent, visible lag between the native pointer and the
         distortion, and it is worst exactly when the visitor is trying to aim
         at a small target. rAF still coalesces moves to one write per frame,
         and the write is a compositor-only translate3d on a fixed element. */
      state.x = state.tx;
      state.y = state.ty;
      lens.style.transform = 'translate3d(' + state.x.toFixed(2) + 'px,' +
        state.y.toFixed(2) + 'px,0) translate(-50%, -50%)';
    }

    function queue() {
      if (state.frame) return;
      state.frame = window.requestAnimationFrame(paint);
    }

    function move(event) {
      if (event.pointerType === 'touch') return;
      state.tx = event.clientX;
      state.ty = event.clientY;
      lens.classList.add('is-visible');
      var overTarget = !!(event.target && event.target.closest
        && event.target.closest(targetSelector));
      lens.classList.toggle('is-target', overTarget);
      queue();
    }

    function hide() {
      lens.classList.remove('is-visible', 'is-target', 'is-pressed');
    }

    function installLiquidFilter() {
      if (doc.getElementById('agora-liquid')) return;
      var SVG_NS = 'http://www.w3.org/2000/svg';
      function node(name, attrs) {
        var el = doc.createElementNS(SVG_NS, name);
        for (var key in attrs) {
          if (Object.prototype.hasOwnProperty.call(attrs, key)) {
            el.setAttribute(key, attrs[key]);
          }
        }
        return el;
      }
      var svg = node('svg', {
        'class': 'cursor-lens-defs',
        'aria-hidden': 'true',
        focusable: 'false',
        width: '0',
        height: '0'
      });
      var filter = node('filter', {
        id: 'agora-liquid',
        x: '-25%', y: '-25%', width: '150%', height: '150%',
        'color-interpolation-filters': 'sRGB'
      });
      /* fractalNoise around the 0.5 midpoint becomes a smooth displacement
         field: red/green deviations pull the backdrop in opposite directions,
         so the pixels under and around the pointer flow like a slow liquid.
         The blur rounds off the noise first; the displacement scale is what a
         visitor reads as the strength of the disturbance. */
      filter.appendChild(node('feTurbulence', {
        type: 'fractalNoise',
        baseFrequency: '0.018 0.026',
        numOctaves: '2',
        seed: '7',
        result: 'warp'
      }));
      filter.appendChild(node('feGaussianBlur', {
        'in': 'warp', stdDeviation: '0.7', result: 'soft'
      }));
      filter.appendChild(node('feDisplacementMap', {
        'in': 'SourceGraphic', 'in2': 'soft',
        scale: '24',
        xChannelSelector: 'R',
        yChannelSelector: 'G'
      }));
      svg.appendChild(filter);
      doc.body.appendChild(svg);
    }

    doc.addEventListener('pointermove', move, { passive: true });
    doc.addEventListener('pointerdown', function (event) {
      if (event.button === 0) lens.classList.add('is-pressed');
    }, { passive: true });
    doc.addEventListener('pointerup', function () {
      lens.classList.remove('is-pressed');
    }, { passive: true });
    doc.addEventListener('pointercancel', function () {
      lens.classList.remove('is-pressed');
    }, { passive: true });
    window.addEventListener('blur', hide);
    doc.documentElement.addEventListener('pointerleave', hide);

    /* If the OS flips reduced-motion mid-session, give the native cursor back
       immediately instead of waiting for a reload. */
    var motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    function applyMotionPreference() {
      if (motionQuery && motionQuery.matches) {
        doc.body.classList.remove('has-custom-cursor');
        hide();
        if (state.frame) window.cancelAnimationFrame(state.frame);
        state.frame = 0;
        state.x = state.y = state.tx = state.ty = -100;
      } else {
        doc.body.classList.add('has-custom-cursor');
      }
    }
    if (motionQuery) {
      if (typeof motionQuery.addEventListener === 'function') {
        motionQuery.addEventListener('change', applyMotionPreference);
      } else if (typeof motionQuery.addListener === 'function') {
        motionQuery.addListener(applyMotionPreference); // Safari < 14
      }
    }
  }

  function initAmbientExperience() {
    // This manager is created once per document and deliberately lives outside
    // <main>. PJAX swaps the page shell, but this graph and source keep running.
    if (window.AgoraAudio) return;

    var MUSIC_SRC = '/assets/bgMusic.mpeg';
    var TARGET_VOLUME = 0.075;

    /* ---- background music, as a plain streaming <audio> element -------------
       There is no Web Audio API left in this file: no AudioContext, no
       AnalyserNode, no createMediaElementSource, no getByteFrequencyData, and no
       bass/mid/treble/onset/pitch analysis.

       That architecture was the 10-15 minute delay. It fetched the entire track as
       an ArrayBuffer and ran decodeAudioData on it, so not one sample could play
       until all ~12MB had arrived AND decoded into roughly 40MB of PCM. On a phone
       on a mobile connection that is minutes. It also explains the other symptom --
       the track appearing to start when you clicked through to another page --
       because a navigation re-ran boot(), and by then the bytes had finally landed.

       A streaming <audio preload="auto"> starts once the browser has a few hundred
       kilobytes, keeps downloading in the background, and costs zero per-frame work.
       Removing the analysis is therefore also the credits-wheel fix: there is no
       getByteFrequencyData plus per-bin pitch loop running 60 times a second any
       more, on any page.

       One trade, stated plainly because it is audible. The old graph ran the track
       through a 2200Hz lowpass and a compressor on the way to the destination. Those
       nodes need an AudioContext, so they are gone and the track now plays as
       authored rather than softly filtered. Volume moves onto the element at the same
       0.075 the master gain used. */
    var audio = {
      el: null,
      isPlaying: false,
      starting: false,
      startPromise: null,
      unavailable: false,
      userMuted: false,      // the toggle was used; autoplay must never override it
      autoplayTried: false,  // canplay fires more than once
      unlockBound: false,
      unlockFired: false
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

    function createAudioElement() {
      if (audio.el) return audio.el;
      var el = doc.createElement('audio');
      el.src = MUSIC_SRC;
      el.loop = true;
      /* preload="auto" is the whole point: begin fetching immediately and let the
         browser start playback from a partial download. "metadata" or "none" would
         leave the visitor on a silent page until some other event nudged it, which
         is the behaviour being fixed. */
      el.preload = 'auto';
      el.volume = TARGET_VOLUME;
      // No native controls -- .ambient-toggle is the only transport, and a second
      // unsynchronised one would contradict it. aria-hidden and tabindex -1 because
      // a decorative loop is not content and must not be a tab stop.
      el.setAttribute('aria-hidden', 'true');
      el.setAttribute('tabindex', '-1');

      // State is driven by the element's own events rather than by the promise, so
      // a stall, a seek or an OS-level interruption is reflected in the toggle.
      el.addEventListener('playing', function () {
        audio.isPlaying = true;
        audio.starting = false;
        updateSoundButton();
      });
      el.addEventListener('pause', function () {
        audio.isPlaying = false;
        audio.starting = false;
        updateSoundButton();
      });
      // A missing or undecodable asset must degrade to "sound unavailable" rather
      // than leave the toggle claiming it is off-but-working.
      el.addEventListener('error', function () { markUnavailable(); });
      el.addEventListener('canplay', function () {
        // Attempt as soon as the stream is ready. Browsers reject this without a
        // prior gesture, and that rejection is what arms the unlock listeners --
        // it is the policy working as designed, not a fault to surface.
        if (audio.autoplayTried || audio.userMuted || audio.isPlaying) return;
        audio.autoplayTried = true;
        attemptPlay('autoplay');
      });

      /* Appended rather than left detached. A detached <audio> does still play in
         most engines, but preload priority for a node that is not in the document
         is engine-dependent, and "start streaming immediately" is the entire point
         of this rewrite -- so it goes in the DOM, invisible and unfocusable.

         The PJAX router only ever replaces <header> and <main>, so a direct child
         of <body> survives every swap. That is how the mesh canvas works too, and
         why neither of them needs a teardown closure: audio.el stays valid across
         navigation, so this runs once per session and never re-creates the element
         (which would restart the track on every page change). */
      if (doc.body && el.parentNode !== doc.body) doc.body.appendChild(el);

      audio.el = el;
      return el;
    }

    /* The one place play() is called. Returns a promise of a BOOLEAN rather than
       rejecting on a policy block, because "the browser said not yet" and "the
       track is broken" need different handling and the old single rejection path
       conflated them -- a blocked autoplay marked the music unavailable, which then
       suppressed the very gesture that would have started it. */
    function attemptPlay(reason) {
      var el = audio.el;
      if (!el || audio.unavailable) return Promise.resolve(false);
      if (!el.paused) {
        audio.isPlaying = true;
        updateSoundButton();
        return Promise.resolve(true);
      }
      audio.starting = true;
      var promise;
      try {
        promise = el.play();
      } catch (error) {
        // Engines old enough to return undefined from play() throw synchronously.
        audio.starting = false;
        markUnavailable();
        return Promise.resolve(false);
      }
      if (!promise || typeof promise.then !== 'function') {
        audio.starting = false;
        audio.isPlaying = !el.paused;
        updateSoundButton();
        return Promise.resolve(audio.isPlaying);
      }
      return promise.then(function () {
        audio.isPlaying = true;
        audio.starting = false;
        updateSoundButton();
        return true;
      }).catch(function (error) {
        audio.starting = false;
        if (error && error.name === 'NotAllowedError') {
          // Autoplay policy. Keep the element warm and wait for a gesture.
          if (!audio.unlockFired) bindUnlock();
          return false;
        }
        markUnavailable();   // NotSupportedError, a 404, a decode failure
        return false;
      });
    }

    function startMusic() {
      if (audio.unavailable) return Promise.reject(new Error('Background music is unavailable.'));
      if (audio.isPlaying) return Promise.resolve(true);
      if (audio.starting && audio.startPromise) return audio.startPromise;
      createAudioElement();
      // An explicit start is by definition not a mute, whatever the toggle did before.
      audio.userMuted = false;
      audio.startPromise = attemptPlay('explicit').then(function (started) {
        audio.startPromise = null;
        updateSoundButton();
        return started;
      });
      return audio.startPromise;
    }

    function stopMusic() {
      audio.userMuted = true;   // an explicit stop must survive every later gesture
      audio.starting = false;
      audio.startPromise = null;
      var el = audio.el;
      if (!el) {
        audio.isPlaying = false;
        updateSoundButton();
        return;
      }
      try {
        el.pause();
      } catch (error) {
        // A pause on an already-paused element is harmless; swallow rather than
        // let a decorative control take the page down.
      }
      audio.isPlaying = false;
      updateSoundButton();
    }

    function toggleMusic() {
      if (audio.isPlaying) {
        stopMusic();
        return Promise.resolve(false);
      }
      return startMusic().then(function (started) {
        updateSoundButton();
        return started;
      });
    }

    /* ---- the first-gesture unlock ------------------------------------------
       Browsers block unmuted autoplay until the user has interacted, so the track
       cannot simply be started on load. What it CAN do is be ready, and then start
       on the first gesture of any kind -- not only on a link, which is why the old
       version looked like the music was tied to navigation.

       Capture phase, passive, on BOTH window and document, for five event types.
       Capture runs before any page handler can stopPropagation, so a gesture
       consumed by the credits wheel, the mobile menu or a form still unlocks the
       audio; passive guarantees this never costs a scroll frame, which matters
       because `wheel` is in the list and the credits screen is entirely
       gesture-driven. */
    var UNLOCK_EVENTS = ['pointerdown', 'touchstart', 'wheel', 'keydown', 'click'];

    function unbindUnlock() {
      if (!audio.unlockBound) return;
      audio.unlockBound = false;
      UNLOCK_EVENTS.forEach(function (type) {
        window.removeEventListener(type, onFirstGesture, true);
        doc.removeEventListener(type, onFirstGesture, true);
      });
    }

    function bindUnlock() {
      if (audio.unlockBound || audio.unavailable || audio.unlockFired) return;
      audio.unlockBound = true;
      UNLOCK_EVENTS.forEach(function (type) {
        window.addEventListener(type, onFirstGesture, { capture: true, passive: true });
        doc.addEventListener(type, onFirstGesture, { capture: true, passive: true });
      });
    }

    function onFirstGesture(event) {
      // Bound on window AND document, so one gesture invokes this twice; the flag
      // makes it idempotent and the listeners come off on the first call.
      if (audio.unlockFired) return;
      audio.unlockFired = true;
      unbindUnlock();

      var target = event && event.target;
      // The mute toggle is itself a gesture. Starting the track only for the
      // toggle's own handler to stop it a millisecond later is a wasted play() and
      // an audible blip, so disarm and let the toggle speak.
      if (target && target.closest && target.closest('.ambient-toggle')) return;
      if (audio.userMuted) return;    // an explicit mute always wins over autoplay
      attemptPlay('gesture');
    }

    /* One stable manager for the whole document, never recreated when the PJAX
       router replaces a page's <main>.

       The analysis members are gone with the graph they read from: getBands,
       getEnergy, getPulse, getSpectrum and SPECTRUM_BANDS existed to feed the mesh
       and the credits wheels, the mesh was disconnected from them last round, and
       this round removes the wheels' reactivity too. What is left is a transport. */
    window.AgoraAudio = {
      start: startMusic,
      stop: stopMusic,
      toggle: toggleMusic,
      get isPlaying() { return audio.isPlaying; },
      get isMuted() { return audio.userMuted; }
    };

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
    /* ---- the one background mesh, for the whole site ----------------------
       A jittered grid triangulated into a low-poly field. Its motion has two
       parts that are deliberately kept apart:

         * a FLOW FIELD -- three octaves of plane waves with constant
           wavelengths, constant speeds and constant amplitudes. It runs at the
           same strength whether the music is playing, paused, or absent, so the
           background is never static and never changes character when audio
           starts.
         * RIPPLES -- discrete droplets dropped where the audio says something
           happened. They expand as concentric rings and fade out toward the
           screen edges. They are events, not a level: a piano keystroke makes
           one droplet, not a screen-wide distortion.

       The topology (which diagonal each cell splits along, and how far each
       vertex sits off the lattice) is hashed from (row, column) once per resize,
       so it is identical every frame. A triangulation recomputed per frame would
       boil, and Bowyer-Watson on ~600 moving points is not survivable on a phone.

       There used to be two canvases here -- a square dot matrix site-wide and a
       sine wave mesh on the credits screen alone. They doubled the frame cost and
       read as moire where they crossed. This is the only one.               */
    /* ---- the one background mesh, for the whole site ----------------------
       A jittered grid triangulated into a low-poly field, displaced by multi-octave
       value noise and lit by its own crests.

       It is NOT connected to the audio engine. Nothing in here reads the
       AnalyserNode, a frequency array, or any band metric, and there is no code path
       by which it could: the field is a pure function of position and an integrated
       clock. That is a deliberate change of contract -- the mesh used to be driven by
       bass, treble, onset, pitch and centroid -- and it buys three things at once.
       The animation is identical whether the music is playing, paused, muted or
       unsupported; a page that never opens the credits screen never runs the audio
       analysis at all, because the wheel driver is the only remaining consumer and it
       early-returns off that page; and the frame has no branch in it that depends on
       a value coming from another subsystem.

       The topology (which diagonal each cell splits along, and how far each vertex
       sits off the lattice) is hashed from (row, column) once per resize, so it is
       identical every frame. A triangulation recomputed per frame would boil, and
       Bowyer-Watson on ~600 moving points is not survivable on a phone.         */
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
      var FALLBACK_NODE = '167,139,250';
      var FALLBACK_HI = '196,181,253';
      var FALLBACK_GLOW = '124,58,237';
      var FALLBACK_LINE = '139,92,246';
      var FALLBACK_INK = 1;

      /* The vertex glow. The review asked for bloom via `shadowBlur` or a soft
         gradient fill; this is the gradient fill, and the choice is not aesthetic.
         At ~600 vertices and 60fps, per-vertex shadowBlur is 36,000 of the most
         expensive calls a 2D context has per second, and it is re-rasterised every
         frame because the vertices move. makeGlowSprite() bakes the same radial
         falloff into an off-screen canvas once per colour and drawGlow() blits it --
         identical picture, and the reason no shadowBlur assignment appears anywhere
         in this file. Bloom and spread are both well up from the 0.42/1.9 the mesh
         carried while it was a faint texture, because it is now meant to pop. */
      /* Bloom is back down to a soft edge rather than a halo. There has never been
         a literal shadowBlur in this file -- at ~600 vertices and 60fps that is
         36,000 of the most expensive calls a 2D context has per second -- so "remove
         the heavy glow" means turning THIS down. makeGlowSprite() bakes the same
         radial falloff into an off-screen canvas once per colour and drawGlow()
         blits it, which is why the glow can be retuned from one constant instead of
         from a per-frame API cost. */
      var MESH_GLOW_BLOOM = 0.30;
      var MESH_GLOW_SPREAD = 1.8;

      /* ---- elevation-bucketed opacity --------------------------------------
         Opacity follows wave height: a flat patch of the field sits at the
         baseline, a crest lifts toward the top of the band, a trough sinks toward
         the bottom. This is what makes the motion readable at all -- at a uniform
         0.10 a line moving 20px is very hard to see, whereas the same line
         brightening as it rises gives the eye a shading cue, and it is why the
         baseline can be dimmer than a flat-alpha mesh needed to be.

         Quantised into FIVE buckets rather than computed per element, and that is
         a performance decision with a hard edge to it. A stroke carries one
         strokeStyle, so per-edge opacity would mean one beginPath/stroke pair per
         edge -- ~1700 of them a frame -- and the state changes alone would drop
         frames on the credits screen, which is the least able to afford it. Five
         bands means five strokeStyle assignments and five strokes for the whole
         lattice. The same applies to the vertices: five globalAlpha changes
         instead of ~600.

         Five is also enough. The step between adjacent bands is ~0.04 of alpha on
         lines and ~0.07 on vertices, which is below the just-noticeable difference
         for a 1px stroke at these levels, so the quantisation is invisible while
         the shading it produces is not. */
      /* The normalised fBm sum is bell-shaped well inside its theoretical +-1: over
         336,000 vertex samples its standard deviation is 0.264 and its 1st/99th
         percentiles are -0.57/+0.64. Dividing the elevation by 2*amplitude -- i.e.
         assuming the field reaches its extremes -- therefore wastes the outer bands:
         measured, bands 0 and 4 held 0.7% and 1.5% of vertices while band 2 held
         54.6%, so the specified 0.03 trough and 0.24 crest were effectively dead
         code and the shading collapsed to three levels.

         ELEVATION_SPREAD rescales against the range the field ACTUALLY occupies. At
         0.50 the occupancy is 11.8 / 26.1 / 28.8 / 19.2 / 14.1 percent with 5.9%
         clipping at the ends -- both extremes are states the mesh really visits, the
         baseline band still holds the most, and the clipping is what makes a peak
         read as a peak rather than stretching the ramp so thin that nothing arrives.
         Going further (0.35) flattens it to 22/21/20/16/21 with 18.5% clipped, which
         is posterisation rather than shading.

         This touches brightness only. The displacement is untouched, so the tear
         budget and the geometry are exactly as they were. */
      var ELEVATION_SPREAD = 0.50;
      var ELEVATION_BUCKETS = 5;
      // trough -> crest. Index 2 is the flat baseline the brief specifies.
      var LINE_ALPHAS = [0.03, 0.07, 0.10, 0.16, 0.24];
      var DOT_ALPHAS = [0.06, 0.11, 0.18, 0.26, 0.35];
      var DOT_RADII = [1.50, 1.62, 1.75, 1.87, 2.00];

      /* ---- the flow field --------------------------------------------------
         Multi-octave value noise (fBm), sampled in three dimensions: x, y, and a
         time axis that advances slowly enough to read as morphing rather than
         boiling. On top of that the domain is ADVECTED -- the sample point drifts
         across the noise -- which is what turns morphing-in-place into flow. Both
         together are what make it read as liquid: advection alone slides a rigid
         pattern, morphing alone makes the field pulse where it stands.

         Value noise rather than Simplex because it needs one hash per corner and two
         lerps per axis instead of a skew, an unskew and a gradient table, and at this
         scale the difference is invisible. Its known weakness -- faint alignment
         along the lattice axes -- is suppressed here by the advection, which means
         the sample grid is never stationary relative to the texel grid.

         Every quantity below is a CONSTANT and both movers are INTEGRATED, so there
         is no path by which the field can jump:

           driftX += NOISE_DRIFT_X * dt;
           noiseTime += NOISE_TIME_SCALE * dt;

         This is the lesson from the version this replaced, which computed its phase
         as `time * k * speed` with k derived from the dominant pitch. Every pitch
         change moved the phase by `time * dk * speed` -- 239 radians after a minute
         open, so the whole field teleported, worse the longer the page stayed up.
         Integrating is continuous by construction whatever the rate does, and there
         is no audio left to perturb the rate anyway. */
      var NOISE_OCTAVES = 4;
      var NOISE_LACUNARITY = 1.92;   // frequency multiplier per octave
      var NOISE_GAIN = 0.5;          // amplitude multiplier per octave
      var NOISE_TEXEL = 560;         // px per texel of the base octave
      var NOISE_SCALE = 1 / NOISE_TEXEL;   // px to noise units
      var NOISE_TIME_SCALE = 0.155;  // noise units of morph per second
      var NOISE_DRIFT_X = 240;       // px/s the domain is advected in +x
      var NOISE_DRIFT_Y = -84;       // and in -y, so it does not slide on rails
      var NOISE_AMP = 0.42;          // of a cell, summed across all octaves
      var NOISE_SEED = 41.3;         // dx and dy sample decorrelated regions

      // A frame gap must never become a position jump: a backgrounded tab hands
      // back a several-second timestamp.
      var MAX_FRAME_DT = 0.05;

      /* The lattice's integrity budget. A vertex may move, but if two neighbours
         close the gap between them the triangles they share invert -- the wireframe
         equivalent of the mesh tearing, invisible in a diff and only mildly visible
         on screen, which is exactly the combination that ships.

         What matters is the GRADIENT of the displacement field, not its magnitude:
         adjacent vertices riding the same broad swell move together and cannot cross
         however far they travel. Jitter is the expensive term because its wavelength
         IS one cell, so it spends 2*JITTER unconditionally.

         The condition is a real one from analysis, not a heuristic. A map
         x -> x + u(x) is injective and orientation-preserving whenever the operator
         norm of the displacement gradient is under 1, and the Frobenius norm bounds
         the operator norm -- so summing the squares of the four partials and taking
         the root gives a sufficient condition for "no triangle inverts". Adding
         2*JITTER covers the one term that is not a smooth field.

         TEAR_LIMIT is 0.75 against that threshold of 1.0, i.e. a 25% allowance. The
         bound is a worst case over phases that essentially never align -- it assumes
         every octave's corners sit at opposite extremes and all four partials peak at
         the same vertex -- and the harness measures what actually happens: 0 inverted
         triangles in 231,420 sampled cells, minimum signed area 81% of a cell. So the
         allowance is belt-and-braces over a bound that is itself ~3x pessimistic, and
         the empirical measurement is the real guard.

         test_the_tear_budget_covers_every_term recomputes the sum from these
         constants, so any amplitude or octave-count bump fails there. */
      var JITTER = 0.06;
      var TEAR_LIMIT = 0.75;
      var QUINTIC_PEAK_SLOPE = 3.75;   // 1.875 (fade' max) * 2 (corner range -1..1)
      var NOISE_DX_RATIO = 0.62;       // dx is deliberately smaller than dy

      function fade(t) {
        // Perlin's improved quintic: C2, so the second derivative does not snap at
        // texel boundaries. A cubic or linear interpolant leaves a faint grid pulsing
        // through the motion -- precisely the artefact this is meant to avoid.
        return t * t * t * ((t * ((t * 6) - 15)) + 10);
      }

      function toUnit(h) {
        // Low 16 bits folded to -1..1, which is where hash2 keeps its entropy.
        return ((h & 0xffff) / 0x7fff) - 1;
      }

      function vnoise(x, y, z) {
        var ix = Math.floor(x);
        var iy = Math.floor(y);
        var iz = Math.floor(z);
        var u = fade(x - ix);
        var v = fade(y - iy);
        var w = fade(z - iz);
        var x1 = ix + 1;
        var y1 = iy + 1;
        var z1 = iz + 1;
        /* The four (x, y) pairs are hashed once and then mixed with each of the two
           z faces, so a corner costs 12 mixes instead of the naive 16.

           The mix has to be a real hash and not a bitwise shortcut. An earlier draft
           of this wrote `(h00 ^ iz) & 0xffff`, which looks equivalent and is not: iz
           is a small integer, so XOR only touches the lowest handful of bits and
           corner values for z and z+1 come out nearly identical. The time axis then
           barely varies and the morph degenerates into banding -- the exact artefact
           the quintic interpolant is there to prevent, reintroduced one level up.
           hash2(h, iz) runs the full mixer, so consecutive texels are independent. */
        var h00 = hash2(ix, iy);
        var h10 = hash2(x1, iy);
        var h01 = hash2(ix, y1);
        var h11 = hash2(x1, y1);
        var n000 = toUnit(hash2(h00, iz));
        var n100 = toUnit(hash2(h10, iz));
        var n010 = toUnit(hash2(h01, iz));
        var n110 = toUnit(hash2(h11, iz));
        var n001 = toUnit(hash2(h00, z1));
        var n101 = toUnit(hash2(h10, z1));
        var n011 = toUnit(hash2(h01, z1));
        var n111 = toUnit(hash2(h11, z1));
        var nx00 = n000 + (u * (n100 - n000));
        var nx10 = n010 + (u * (n110 - n010));
        var nx01 = n001 + (u * (n101 - n001));
        var nx11 = n011 + (u * (n111 - n011));
        var nxy0 = nx00 + (v * (nx10 - nx00));
        var nxy1 = nx01 + (v * (nx11 - nx01));
        return nxy0 + (w * (nxy1 - nxy0));
      }

      function fbm(x, y, z) {
        var sum = 0;
        var amp = 1;
        var freq = 1;
        var norm = 0;
        for (var o = 0; o < NOISE_OCTAVES; o += 1) {
          sum += amp * vnoise(x * freq, y * freq, z * freq);
          norm += amp;
          amp *= NOISE_GAIN;
          freq *= NOISE_LACUNARITY;
        }
        return sum / norm;
      }

      function readPalette() {
        try {
          var styles = window.getComputedStyle(doc.documentElement);
          // Computed custom properties come back with the source spacing, e.g.
          // "12, 34, 56"; the canvas wants a bare "r,g,b" triple. Deliberately not
          // one of the real palette values -- a test asserts that no light-theme
          // triple appears anywhere in this file, and an example in a comment would
          // trip it for no reason.
          var node = (styles.getPropertyValue('--mesh-node-rgb') || '').replace(/\s+/g, '');
          var hi = (styles.getPropertyValue('--mesh-node-hi-rgb') || '').replace(/\s+/g, '');
          var glow = (styles.getPropertyValue('--mesh-glow-rgb') || '').replace(/\s+/g, '');
          var line = (styles.getPropertyValue('--mesh-line-rgb') || '').replace(/\s+/g, '');
          var ink = parseFloat(styles.getPropertyValue('--mesh-ink'));
          return {
            node: node || FALLBACK_NODE,
            hi: hi || FALLBACK_HI,
            glow: glow || FALLBACK_GLOW,
            line: line || FALLBACK_LINE,
            // One dial for how hard the whole layer presses on the page, so a theme
            // can match PRESENCE rather than numbers. The alphas below are authored
            // for the dark canvas the review asked to pop against; on off-white the
            // same alphas over the deepened light-theme channels would print a
            // lavender graph over the content, so light scales them back.
            ink: isFinite(ink) && ink > 0 ? Math.min(ink, 1) : FALLBACK_INK
          };
        } catch (error) {
          return {
            node: FALLBACK_NODE, hi: FALLBACK_HI, glow: FALLBACK_GLOW,
            line: FALLBACK_LINE, ink: FALLBACK_INK
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
      var spacing = 54;
      var columns = 0;
      var rows = 0;
      var pixelRatio = 1;
      var pts = null;        // per-frame vertex positions, rows*columns*2
      var lights = null;     // per-vertex normalised elevation, 0..1
      var vbuck = null;      // per-vertex bucket index
      var ebuck = null;      // per-edge bucket index, in the enumeration order below
      var edgeCap = 0;
      var jitterX = null;    // per-vertex, fixed at resize
      var jitterY = null;
      var flips = null;      // per-cell: which diagonal that cell splits along
      var amplitude = 22;    // NOISE_AMP * spacing, in px

      /* State that must persist across frames. The two advection offsets and the
         morph clock are integrated, and `lastTimestamp` is what makes the first
         frame's dt zero instead of the whole page age. */
      var lastTimestamp = 0;
      var driftX = 0;
      var driftY = 0;
      var noiseTime = 0;

      function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        // A triangulated field reads denser than the square grid it replaced --
        // three edges per cell instead of two -- so the cell is coarser than the old
        // matrix's 30/36px while carrying MORE structure. At 54px a 1440x900
        // viewport gets ~600 vertices, ~550 triangles and ~1700 edges.
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
        lights = new Float32Array(vertices);
        vbuck = new Uint8Array(vertices);
        // rows + columns + one diagonal per cell, enumerated in exactly the order
        // the stroke passes below walk them, so an index agrees between the two.
        edgeCap = (rows * (columns - 1)) + (columns * (rows - 1)) + ((rows - 1) * (columns - 1));
        ebuck = new Uint8Array(Math.max(0, edgeCap));
        jitterX = new Float32Array(vertices);
        jitterY = new Float32Array(vertices);
        flips = new Uint8Array(Math.max(0, cells));
        amplitude = spacing * NOISE_AMP;

        /* Deterministic jitter from a hash of (row, column). Not Math.random(): the
           topology has to survive from frame to frame, and a jitter recomputed per
           frame would make the whole mesh boil. It is deliberately gentle -- 0.06 of
           a cell -- because jitter is the one term whose wavelength is a single cell,
           which makes it the most expensive thing in the tear budget and the first
           place an "organic" tweak turns into a shredding lattice. The random
           diagonal lean carries most of the organic character for none of that cost,
           because a diagonal is a topology choice rather than a displacement. */
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

      function bucketOf(elevation) {
        var b = (elevation * ELEVATION_BUCKETS) | 0;   // |0 floors, and elevation is >= 0
        return b > (ELEVATION_BUCKETS - 1) ? ELEVATION_BUCKETS - 1 : b;
      }

      function edgeBucket(i, j) {
        // The mean of the two endpoints, so an edge straddling a boundary takes the
        // band its middle is in rather than flickering between two as the wave
        // passes -- which is what a max() or a first-endpoint rule would do.
        return bucketOf((lights[i] + lights[j]) * 0.5);
      }

      function draw(timestamp) {
        // A PJAX swap may have detached us between frames; stop rather than keep
        // painting an invisible canvas for the rest of the session.
        if (!canvas.isConnected) return;

        if (!lastTimestamp) lastTimestamp = timestamp;
        var dt = clamp((timestamp - lastTimestamp) / 1000, 0, MAX_FRAME_DT);
        lastTimestamp = timestamp;

        // Integrated, never `timestamp * rate`. See the flow-field comment.
        // Neither of these is wrapped: at 240px/s it takes 24 hours to reach 37,000
        // noise texels, and a double still resolves the fractional part to ~1e-12
        // there, so a wrap would cost a visible seam to solve a problem that does not
        // arrive.
        driftX += NOISE_DRIFT_X * dt;
        driftY += NOISE_DRIFT_Y * dt;
        noiseTime += NOISE_TIME_SCALE * dt;

        context.clearRect(0, 0, width, height);

        var row;
        var column;
        var bucket;   // declared: the IIFE is 'use strict', so an implicit global
                      // in the loop headers below would be a ReferenceError on the
                      // very first frame, and `node --check` cannot see that.
        var index = 0;
        for (row = 0; row < rows; row += 1) {
          for (column = 0; column < columns; column += 1) {
            var i = (row * columns) + column;
            var gx = ((column - 1) * spacing) + jitterX[i];
            var gy = ((row - 1) * spacing) + jitterY[i];

            /* Sample the advected domain. The two axes read regions NOISE_SEED apart
               so dx and dy are decorrelated: sampling the same region for both would
               make every vertex travel along one diagonal instead of looping.

               The MINUS sign is the whole direction of travel, and it is worth
               deriving because this is the third time a sign in this file has been
               backwards. A feature sitting at noise coordinate N appears on screen
               where the sample coordinate equals N:

                 (gx - driftX) * NOISE_SCALE = N   ->   gx = N/NOISE_SCALE + driftX

               so d(gx)/d(driftX) = +1 and the feature moves in +x as driftX grows.
               With a plus sign it is gx = N/NOISE_SCALE - driftX and the whole field
               runs LEFT -- which reads identically frame to frame and is wrong, and
               which a shift search over positive lags only reports as "stationary"
               because the correct lag was outside the range being searched.

               Earlier instances of the same mistake: `sin(k*x + w*t)` in the layer
               this replaced, and `sin(time*0.23 + column*0.17)` in the idle drift of
               the version after that -- which was the loudest term in silence, so the
               one wave every visitor saw travelled backwards. */
            var nx = (gx - driftX) * NOISE_SCALE;
            var ny = (gy - driftY) * NOISE_SCALE;
            var dy = fbm(nx, ny, noiseTime) * amplitude;
            var dx = fbm(nx + NOISE_SEED, ny + NOISE_SEED, noiseTime) * amplitude * NOISE_DX_RATIO;

            pts[index] = gx + dx;
            pts[index + 1] = gy + dy;
            index += 2;

            /* Brightness rides the surface's own height, which is free -- dy is
               already computed -- and it is what makes the undulation legible rather
               than merely present. It reads as light falling across a moving sheet:
               crests catch it, troughs fall away. With no audio left to drive
               contrast, this is where the contrast comes from. */
            lights[i] = clamp(0.5 + (dy / (2 * amplitude * ELEVATION_SPREAD)), 0, 1);
            vbuck[i] = bucketOf(lights[i]);
          }
        }

        /* ---- the triangulated wireframe, in five elevation bands -----------
           Three edge families per cell: its top, its left, and one diagonal.

           Every edge is emitted as its own two-point segment rather than as part of
           a contiguous polyline, and that is a deliberate trade. Rows used to be one
           polyline each, which was the cheapest possible structure -- but a polyline
           can only carry one strokeStyle, and opacity now varies along the row as the
           wave passes under it. So the choice is five strokes over ~1700 individual
           segments, or ~1700 strokes over five alphas. The first is what this does.
           Path operations are cheap appends to the current path; strokes are the
           expensive part, and there are still only five of them.

           The buckets are assigned in ONE pass before drawing, in exactly the order
           the five passes walk the edges, so an index into ebuck agrees between the
           two. Recomputing the bucket inside each pass would be five times the
           arithmetic for nothing. */
        var edgeIndex = 0;
        for (row = 0; row < rows; row += 1) {
          var rowBase = row * columns;
          for (column = 0; column < columns - 1; column += 1) {
            ebuck[edgeIndex++] = edgeBucket(rowBase + column, rowBase + column + 1);
          }
        }
        for (column = 0; column < columns; column += 1) {
          for (row = 0; row < rows - 1; row += 1) {
            ebuck[edgeIndex++] = edgeBucket((row * columns) + column, ((row + 1) * columns) + column);
          }
        }
        for (row = 0; row < rows - 1; row += 1) {
          var cellBase = row * (columns - 1);
          for (column = 0; column < columns - 1; column += 1) {
            var corner = (row * columns) + column;
            ebuck[edgeIndex++] = flips[cellBase + column]
              ? edgeBucket(corner, corner + columns + 1)
              : edgeBucket(corner + 1, corner + columns);
          }
        }

        context.lineWidth = 1;
        for (bucket = 0; bucket < ELEVATION_BUCKETS; bucket += 1) {
          context.strokeStyle = 'rgba(' + palette.line + ','
            + (LINE_ALPHAS[bucket] * palette.ink).toFixed(4) + ')';
          context.beginPath();

          var k = 0;
          for (row = 0; row < rows; row += 1) {
            var rb = row * columns;
            for (column = 0; column < columns - 1; column += 1) {
              if (ebuck[k++] !== bucket) continue;
              var p0 = (rb + column) * 2;
              context.moveTo(pts[p0], pts[p0 + 1]);
              context.lineTo(pts[p0 + 2], pts[p0 + 3]);
            }
          }
          for (column = 0; column < columns; column += 1) {
            for (row = 0; row < rows - 1; row += 1) {
              if (ebuck[k++] !== bucket) continue;
              var p1 = ((row * columns) + column) * 2;
              context.moveTo(pts[p1], pts[p1 + 1]);
              context.lineTo(pts[p1 + (columns * 2)], pts[p1 + (columns * 2) + 1]);
            }
          }
          for (row = 0; row < rows - 1; row += 1) {
            var cb = row * (columns - 1);
            for (column = 0; column < columns - 1; column += 1) {
              if (ebuck[k++] !== bucket) continue;
              // Both corners must be the SAME pair the bucket pass classified, or an
              // edge gets stroked at its neighbour's opacity. flips picks the
              // top-left -> bottom-right diagonal; otherwise it is the other one,
              // which starts at top-RIGHT. A first draft drew both from top-left,
              // which is invisible in the source and wrong on screen.
              var c0 = (row * columns) + column;
              var lean = flips[cb + column];
              var da = lean ? c0 : (c0 + 1);
              var db = lean ? (c0 + columns + 1) : (c0 + columns);
              context.moveTo(pts[da * 2], pts[da * 2 + 1]);
              context.lineTo(pts[db * 2], pts[db * 2 + 1]);
            }
          }
          context.stroke();
        }

        /* Vertices on top of the wireframe, also bucketed: five globalAlpha changes
           and five radii instead of ~600 of each. Radius rides the same band as
           alpha, so a crest is both brighter and slightly larger, which is how a
           shaded surface reads rather than how a dimming overlay reads.

           Which sprite a vertex uses stays STATIC -- one in four gets the brighter
           texture, decided by its lattice position and never changed. A version of
           this switched sprite on a moving threshold, and vertices popped between
           two baked textures as a crest passed under them; that popping reads as
           flicker no matter how smooth the geometry is. Bucket boundaries could in
           principle do the same thing, which is the real cost of quantising, but a
           band crossing changes alpha by ~0.07 on a 1.9px dot -- below the
           just-noticeable difference -- where a sprite swap changes its texture. */
        if (sprites.node && sprites.hi) {
          for (bucket = 0; bucket < ELEVATION_BUCKETS; bucket += 1) {
            var dotSize = DOT_RADII[bucket] * 2 * MESH_GLOW_SPREAD;
            var dotHalf = dotSize / 2;
            context.globalAlpha = DOT_ALPHAS[bucket] * palette.ink;
            for (row = 0; row < rows; row += 1) {
              for (column = 0; column < columns; column += 1) {
                var vi = (row * columns) + column;
                if (vbuck[vi] !== bucket) continue;
                var q = vi * 2;
                context.drawImage((((column + row) % 4) === 0) ? sprites.hi : sprites.node,
                  pts[q] - dotHalf, pts[q + 1] - dotHalf, dotSize, dotSize);
              }
            }
            context.globalAlpha = 1;
          }
        } else {
          // No 2D context for the off-screen sprite, so there is nothing to blit.
          // drawGlow already carries the plain-arc fallback; this cannot happen when
          // the main canvas has a context, but the guard is why it has one.
          for (row = 0; row < rows; row += 1) {
            for (column = 0; column < columns; column += 1) {
              var wi = (row * columns) + column;
              var wq = wi * 2;
              var hi = ((column + row) % 4) === 0;
              drawGlow(context, null, hi ? palette.hi : palette.node, pts[wq], pts[wq + 1],
                DOT_RADII[vbuck[wi]], DOT_ALPHAS[vbuck[wi]] * palette.ink, MESH_GLOW_SPREAD);
            }
          }
        }

        if (!reduceMotion()) window.requestAnimationFrame(draw);
      }

      resize();
      window.addEventListener('resize', resize, { passive: true });

      // Follow the OS if the scheme flips mid-session. A paused canvas (the
      // reduced-motion path draws a single frame and never loops) will not repaint
      // by itself, so nudge one frame through in that case.
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

    /* Build the element now so the browser starts fetching during page load rather
       than on the first gesture, and arm the unlock listeners immediately. Waiting
       for the autoplay attempt to be rejected before arming them would miss a
       visitor who scrolls before `canplay` fires -- and that scroll is exactly the
       gesture meant to start the track. */
    createAudioElement();
    bindUnlock();

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

      // Each name plate lives inside its own rotated sector. Counter the whole
      // bottom-wheel rotation in JS; CSS also subtracts that sector's fixed
      // base angle, keeping every plate on the rim and perfectly horizontal.
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
      /* One frame delta, measured BEFORE lastTime is advanced. The previous
         version advanced lastTime first and then subtracted it again, so dt was
         always zero -> clamped to the 8ms floor on every frame, and the spring
         ran at half speed on a 60Hz display and one third on 144Hz. */
      var frameMs = clamp(timestamp - state.lastTime, 8, 34);
      state.lastTime = timestamp;
      var elapsed = frameMs / 16.67;

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
      var dt = frameMs / 1000;
      var error = state.rotationTarget - state.rotation;
      var acceleration = (error * SPRING_STIFFNESS) - (state.rotationVelocity * SPRING_DAMPING);
      state.rotationVelocity = clamp(
        state.rotationVelocity + (acceleration * dt),
        -MAX_ANGULAR_VELOCITY, MAX_ANGULAR_VELOCITY
      );
      state.rotation += state.rotationVelocity * dt;

      /* This loop publishes nothing to the background canvas, and that is
         deliberate. Scrolling used to inject its angular velocity into the mesh
         through a module-level slot; the credits screen is the heaviest page on
         the site -- two large rotating discs, masks and rim gradients composited
         over a full-viewport canvas -- and adding a per-vertex radial wave field
         driven by gesture on top of that is what made it stutter. The mesh is now
         identical on every page and completely independent of scroll input, so
         this loop's only job is the wheel. */

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
     10. EMAIL HYDRATION

     No literal email address appears anywhere in this site's HTML, and that is
     deliberate. Cloudflare's Email Address Obfuscation rewrites raw addresses at
     the edge into

       <a href="/cdn-cgi/l/email-protection#..." class="__cf_email__"
          data-cfemail="...">[email protected]</a>

     and that breaks twice here. The rewritten href is a relative Cloudflare path,
     which the PJAX router treats as an internal navigation and fetches -- so
     clicking the address performs a page swap instead of opening the mail client.
     And the replacement markup is written into the parsed document, so a shell
     fetched during a swap can carry obfuscated anchors that nothing ever decodes.

     So addresses live in data attributes and are assembled at runtime, on boot and
     after every navigation. Nothing at the edge has a pattern to match.

     The second half is defensive rather than decorative: if an address ever does
     reach the HTML -- a hand edit, a cached shell from before this change -- this
     also finds the anchor Cloudflare produced, decodes it and restores a working
     mailto. Decoding is not a hack; data-cfemail is the address XORed against its
     own first byte, which is a stable public format.
     ------------------------------------------------------------ */
  function decodeCfEmail(encoded) {
    if (!encoded || !/^[0-9a-f]+$/i.test(encoded)) return '';
    if (encoded.length % 2 || encoded.length < 4) return '';
    var key = parseInt(encoded.substr(0, 2), 16);
    var out = '';
    for (var i = 2; i < encoded.length; i += 2) {
      out += String.fromCharCode(parseInt(encoded.substr(i, 2), 16) ^ key);
    }
    // A decode with no @ in it is a malformed payload rather than an address, and
    // painting that into the page would be worse than leaving the anchor alone.
    return out.indexOf('@') > 0 ? out : '';
  }

  function hydrateEmailLinks(scope) {
    var root = scope || doc;
    if (!root || typeof root.querySelectorAll !== 'function') return;

    /* Repair anything Cloudflare already rewrote. Runs first, so a repaired anchor
       that also carries data-email-* attributes is then normalised by the pass
       below rather than being left half-migrated. */
    Array.prototype.forEach.call(
      root.querySelectorAll('a.__cf_email__, a[href*="/cdn-cgi/l/email-protection"]'),
      function (node) {
        var decoded = decodeCfEmail(node.getAttribute('data-cfemail'));
        if (!decoded) return;
        node.setAttribute('href', 'mailto:' + decoded);
        node.removeAttribute('data-cfemail');
        node.classList.remove('__cf_email__');
        node.textContent = decoded;
      });

    // Assemble the authored ones.
    Array.prototype.forEach.call(
      root.querySelectorAll('[data-email-user][data-email-domain]'),
      function (node) {
        var user = (node.getAttribute('data-email-user') || '').trim();
        var domain = (node.getAttribute('data-email-domain') || '').trim();
        // Reject an @ in either half: that means someone put a whole address in one
        // attribute, which is exactly the literal this exists to prevent.
        if (!user || !domain || user.indexOf('@') !== -1 || domain.indexOf('@') !== -1) return;
        var address = user + '@' + domain;
        var href = 'mailto:' + address;
        var subject = node.getAttribute('data-email-subject');
        if (subject) href += '?subject=' + encodeURIComponent(subject);
        node.setAttribute('href', href);
        /* data-email-label means "keep the copy I wrote" -- the category cards want
           to say "Press inquiry", not recite the address. Without it the visible
           text IS the address, which is what the footer and the bio want. */
        if (!node.hasAttribute('data-email-label')) node.textContent = address;
      });
  }

  /* ------------------------------------------------------------
     Boot and PJAX page hydration
     ------------------------------------------------------------ */
  function bootPage() {
    /* Before initRouting, deliberately: an unhydrated email anchor has no href at
       all, and a hydrated one has a mailto: href that getInternalPageUrl already
       excludes. Either way the router cannot mistake it for an internal link -- but
       hydrating first means there is no window in which a click lands on an anchor
       with no destination. bootPage runs once at boot and again after every PJAX
       swap, which is exactly the two moments new markup can arrive. */
    hydrateEmailLinks();
    initImages();
    initCreditsRotary();
    initRouting();
    // After initRouting: syncPageLinks rewrites a[data-page] hrefs, and the
    // download CTAs must keep the release URL that wins this ordering.
    initDynamicDownload();
    initMenu();
    initSmoothScroll();
    initReveal();
    initChrome();
    // Before initContactForm: the gate step's submit handler consults the flow, and
    // while that only happens on a click, wiring in dependency order means a future
    // change cannot make the order start to matter.
    initSignalFlow();
    initContactForm();
    initSharedPost();
  }

  function boot() {
    normalizeInitialUrl();
    /* Ambient audio/cursor/mesh are initialized once; everything below is safe to
       rerun after the router swaps a page shell.

       The ambient layer is wrapped because it is DECORATIVE and it runs FIRST.
       Anything it throws -- a browser without <audio>, without matchMedia, a canvas
       that refuses a 2D context -- would otherwise abort boot()
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
