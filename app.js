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
     6. Feedback form     — placeholder submit (no backend yet)
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
     6. FEEDBACK FORM (placeholder)
     No backend yet — the form validates, "sends", and confirms.
     ------------------------------------------------------------ */
  function initContactForm() {
    var form = doc.getElementById('feedback-form');
    if (!form) return;

    var success = doc.getElementById('feedback-success');
    var button = form.querySelector('button[type="submit"]');

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;

      button.disabled = true;
      button.textContent = 'Sending…';

      /* TODO: wire up the real endpoint, e.g.
         var payload = Object.fromEntries(new FormData(form).entries());
         fetch('/api/feedback', {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify(payload)
         });
      */
      window.setTimeout(function () {
        form.hidden = true;
        if (success) success.hidden = false;
      }, 900);
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
