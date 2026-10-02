/* ============================================================
   AGORA — app.js
   Vanilla JS, zero dependencies. Powers all four pages:
     · index.html         (home)
     · shared-post.html   (shared-link landing)
     · download.html      (downloads)
     · about.html         (about the creator)

   Contents:
     1. Link routing      — flat multi-page navigation
     2. Mobile menu       — toggle, a11y state, esc/outside close
     3. Smooth scrolling  — header-offset aware, reduced-motion safe
     4. Reveal on scroll  — IntersectionObserver entrance animations
     5. Chrome            — header scroll state, active nav, year
     6. Feedback form     — validation + submit (endpoint or mail client)
     7. Shared-post       — URL param parsing + post preview stub
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
    about: '/about.html'
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
     Validates properly, then delivers the message one of two ways:

       · ENDPOINT — set FORM_ENDPOINT below (or data-endpoint="…"
         on the form) to POST JSON to Formspree, Web3Forms, your
         own /api/feedback, …  Expects a 2xx response.
       · MAILTO   — with no endpoint configured, the message is
         handed to the visitor's mail client, addressed to
         CONTACT_EMAIL. Nothing is silently dropped.

     Both paths end in the same accessible success panel.
     ------------------------------------------------------------ */
  var FORM_ENDPOINT = '';                    // e.g. 'https://formspree.io/f/abcdwxyz'
  var CONTACT_EMAIL = 'mail@agora.in.net';
  var SUBMIT_TIMEOUT = 12000;                // ms before we give up on the endpoint

  function initContactForm() {
    var form = doc.getElementById('feedback-form');
    if (!form) return;

    var success = doc.getElementById('feedback-success');
    var status = doc.getElementById('feedback-status');
    var button = form.querySelector('[data-submit]');
    var label = button ? button.querySelector('[data-button-label]') : null;
    var endpoint = form.getAttribute('data-endpoint') || FORM_ENDPOINT;
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
      if (label) label.textContent = busy ? 'Sending…' : idleLabel;
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

    function postFeedback(url, payload) {
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = window.setTimeout(function () {
        if (controller) controller.abort();
      }, SUBMIT_TIMEOUT);

      return fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller ? controller.signal : undefined
      }).then(function (response) {
        if (!response.ok) throw friendly('The server refused the message (HTTP ' + response.status + ').');
        return response.text().catch(function () { return ''; });   // many endpoints reply with an empty body
      }).then(function () {
        window.clearTimeout(timer);
        return true;
      }, function (error) {
        window.clearTimeout(timer);
        if (error && error.friendly) throw error;
        if (error && error.name === 'AbortError') throw friendly('That took too long. Please try again.');
        throw friendly('We couldn\'t reach the server. Check your connection and try again.');
      });
    }

    function openMailClient(payload) {
      var subject = '[Agora] ' + payload.topicLabel;
      var body = 'Name: ' + payload.name + '\n' +
        'Email: ' + payload.email + '\n' +
        'Topic: ' + payload.topicLabel + '\n\n' +
        payload.message + '\n\n' +
        '— sent from ' + payload.page;
      window.location.href = 'mailto:' + CONTACT_EMAIL +
        '?subject=' + encodeURIComponent(subject) +
        '&body=' + encodeURIComponent(body);
    }

    function showSuccess(mode) {
      var note = success ? success.querySelector('[data-success-note]') : null;
      if (note) {
        note.textContent = mode === 'mailto'
          ? 'Your mail app should be open with the message ready to send to ' + CONTACT_EMAIL +
            '. If nothing opened, write to us directly below.'
          : 'Your message is on its way — a human reads every one of these.';
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
        showSuccess('sent');
        return;
      }

      var payload = collect();
      setBusy(true);

      if (!endpoint) {
        openMailClient(payload);
        setBusy(false);
        showSuccess('mailto');
        return;
      }

      postFeedback(endpoint, payload).then(function () {
        setBusy(false);
        showSuccess('sent');
      }, function (error) {
        setBusy(false);
        setStatus(error && error.message
          ? error.message
          : 'Something went wrong. Please try again, or email ' + CONTACT_EMAIL + '.', 'error');
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
     Boot
     ------------------------------------------------------------ */
  function boot() {
    initImages();
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
