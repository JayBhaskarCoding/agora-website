"""Dependency-free launch structure checks. Run with npm test."""
from collections import Counter
from html.parser import HTMLParser
import html as html_module
import json
import math
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = {
    "/assets/home-feed.png": 3,
    "/assets/profile-screen.png": 1,
    "/assets/shared-post-preview.png": 2,
}
PENDING_ASSETS = {
    "/assets/yashvardhan-bhaskar.jpg",
}
LOGO = "/assets/agora-logo.svg"
# Exactly ONE element site-wide downloads the APK: the "Download APK" button on
# download.html. It never pins a build — it ships with GitHub's permanent
# latest-release redirect, which resolves server-side to the newest release's
# app.apk, a real download with no JavaScript and no API quota. app.js only
# overrides it when a release names its asset something else.
#
# Every other "Get the app" CTA is plain page navigation to the download page,
# so the install decision happens on the one page carrying version, size and
# requirements. Authored with the repo's own routing convention so the no-JS
# path works and PJAX treats it like any internal link.
PREFERRED_APK = "app.apk"
RELEASES_PAGE = "https://github.com/JayBhaskarCoding/agora-android/releases/latest"
RELEASE_DOWNLOAD = f"{RELEASES_PAGE}/download/{PREFERRED_APK}"
RELEASE_API = "https://api.github.com/repos/JayBhaskarCoding/agora-android/releases/latest"
RELEASE_PROXY = "/api/latest-release"
DYNAMIC_ATTR = "dynamic-download-btn"
DOWNLOAD_PAGE = "/download.html"
# Pages carrying the one direct-download button.
DYNAMIC_CTAS = Counter(
    {
        "index.html": 0,
        "about.html": 0,
        "download.html": 1,   # the "Download APK" button only
        "shared-post.html": 0,
        "credits.html": 0,
    }
)
# Pages carrying "Get the app" CTAs that navigate to the download page instead.
PAGE_CTAS = Counter(
    {
        "index.html": 4,        # nav CTA, mobile menu, hero, closing panel
        "about.html": 3,        # nav CTA, mobile menu, #get-app panel
        "download.html": 2,     # nav CTA, mobile menu
        "shared-post.html": 2,  # nav CTA, shared-card block button
        "credits.html": 0,
    }
)


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.tags = []
        self.anchors = []
        self.anchor = None
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if tag == "a":
            self.anchor = [attrs, ""]

    def handle_data(self, data):
        if self.anchor is not None:
            self.anchor[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            self.anchors.append(self.anchor)
            self.anchor = None


class LaunchContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {p.name: Page(p) for p in ROOT.glob("*.html")}
        cls.css = (ROOT / "style.css").read_text()

    def test_centralized_branding(self):
        self.assertTrue((ROOT / LOGO.lstrip("/")).is_file())
        for name, page in self.pages.items():
            with self.subTest(page=name):
                marks = [a for tag, a in page.tags if "nav__logo-mark" in a.get("class", "")]
                expected_marks = 1 if name == "credits.html" else 2
                self.assertEqual(len(marks), expected_marks, "Every page needs its visible Agora mark")
                self.assertTrue(all(a.get("src") == LOGO and a.get("alt") == "Agora" for a in marks))
                icons = [a for tag, a in page.tags if tag == "link" and a.get("rel") == "icon"]
                self.assertEqual(icons[0]["href"], LOGO)
                self.assertEqual(icons[0]["type"], "image/svg+xml")

    def test_download_ctas(self):
        """One button downloads the file; every other CTA navigates to the page.

        The "Download APK" button on download.html is the only element carrying
        GitHub's permanent release redirect and the dynamic marker. All other
        "Get the app" CTAs are ordinary internal links to /download.html, so
        they must NOT carry the marker -- or app.js would rewrite them back into
        a direct download -- and SHOULD carry data-page so the router resolves
        them like any other internal link (and PJAX swaps them in place).
        """
        downloading = Counter()
        navigating = Counter()
        for name, page in self.pages.items():
            primary_ids = sum(
                1 for tag, attrs in page.tags if tag == "a" and attrs.get("id") == DYNAMIC_ATTR
            )
            for attrs, text in page.anchors:
                label = " ".join(text.split())
                classes = attrs.get("class", "").split()
                is_cta = "btn--get-app" in classes or label == "Download APK"
                with self.subTest(page=name, label=label):
                    if not is_cta:
                        # Plain page links ("Download" in nav/footer) stay internal.
                        self.assertNotIn(DYNAMIC_ATTR, classes)
                        continue

                    self.assertIn("btn--primary", classes)
                    if label == "Download APK":
                        downloading[name] += 1
                        self.assertEqual(
                            name, "download.html",
                            "only the download page may offer the file directly")
                        self.assertIn(DYNAMIC_ATTR, classes)
                        self.assertEqual(
                            attrs.get("href"), RELEASE_DOWNLOAD,
                            "Authored href must be the permanent direct-download redirect")
                        self.assertNotIn("data-page", attrs,
                                         "Routing must not rewrite the release URL")
                        self.assertNotIn("download", attrs,
                                         "GitHub handles the cross-origin attachment")
                        self.assertNotIn("target", attrs)
                    else:
                        self.assertEqual(label, "Get the app")
                        navigating[name] += 1
                        self.assertEqual(
                            attrs.get("href"), DOWNLOAD_PAGE,
                            "every other CTA must navigate to the download page")
                        self.assertEqual(attrs.get("data-page"), "download")
                        self.assertNotIn(
                            DYNAMIC_ATTR, classes,
                            "a navigating CTA must not be rewritable into a download")
                        self.assertNotIn("id", attrs,
                                         "the primary download id belongs to one element")

            self.assertEqual(
                primary_ids,
                1 if DYNAMIC_CTAS[name] else 0,
                "Exactly one primary id=\"dynamic-download-btn\", and only where a file downloads",
            )
            if name != "download.html":
                self.assertNotIn("download apk", (ROOT / name).read_text().lower())

        self.assertEqual(dict(downloading), {k: v for k, v in DYNAMIC_CTAS.items() if v})
        self.assertEqual(dict(navigating), {k: v for k, v in PAGE_CTAS.items() if v})
        self.assertEqual(sum(downloading.values()), 1,
                         "exactly one element site-wide may download the APK")
        self.assertEqual(sum(navigating.values()), sum(PAGE_CTAS.values()))

    def test_only_the_download_page_exposes_the_asset(self):
        """No page other than download.html may mention the release asset, so a
        visitor cannot end up downloading from somewhere the version, size and
        requirements are not on screen."""
        for name in self.pages:
            html = (ROOT / name).read_text()
            with self.subTest(page=name):
                if name == "download.html":
                    self.assertEqual(html.count(RELEASE_DOWNLOAD), 1)
                    self.assertEqual(html.count(DYNAMIC_ATTR), 2,
                                     "the id and the class on that one button")
                else:
                    self.assertNotIn(RELEASE_DOWNLOAD, html)
                    self.assertNotIn(DYNAMIC_ATTR, html)
                    self.assertNotIn("releases/latest/download", html)
        # app.js still resolves the asset, but only for that one selector.
        app = (ROOT / "app.js").read_text()
        self.assertIn("#dynamic-download-btn, .dynamic-download-btn", app)

    def test_no_hardcoded_release_assets(self):
        """No file may pin a tag/build. The only allowed .apk href is GitHub's
        unpinned latest-release redirect, which tracks new builds by itself."""
        pinned = re.compile(r'href="[^"]*/releases/download/[^"]*"')
        apk_href = re.compile(r'href="([^"]*\.apk)"')
        for name in self.pages:
            html = (ROOT / name).read_text()
            with self.subTest(page=name):
                self.assertIsNone(pinned.search(html), "A /releases/download/<tag>/ href pins a build")
                for href in apk_href.findall(html):
                    self.assertEqual(href, RELEASE_DOWNLOAD)
                self.assertNotIn("app-beta-v2.0", html)
                self.assertNotIn("38 MB", html, "Stale size copy must go")
        app = (ROOT / "app.js").read_text()
        self.assertNotIn("/releases/download/", app, "The asset URL must come from the API")
        self.assertNotIn("app-beta-v2.0", app)

    def test_dynamic_download_wiring(self):
        """The lookup, its fallback chain, and the edge proxy all exist."""
        app = (ROOT / "app.js").read_text()
        for contract in [
            RELEASE_API,                                     # GitHub latest-release endpoint
            "'%s'" % RELEASE_PROXY,                          # same-origin Pages Function first
            "'%s'" % RELEASES_PAGE,                          # release page base URL
            "var PREFERRED_APK_NAME = '%s';" % PREFERRED_APK,  # published asset name
            "RELEASE_PAGE_URL + '/download/' + PREFERRED_APK_NAME",  # permanent redirect
            "name.toLowerCase() === PREFERRED_APK_NAME",     # exact app.apk wins
            "release.fileName.toLowerCase() === PREFERRED_APK_NAME",  # keep permanent href
            "#dynamic-download-btn, .dynamic-download-btn",  # button selector
            "browser_download_url",
            r"/\.apk$/i",
            "fetchReleaseJson(RELEASE_PROXY_URL)",
            "fetchReleaseJson(RELEASE_API_URL)",             # direct GitHub fallback
            "initDynamicDownload();",                        # reruns on every PJAX swap
            "RELEASE_FACTS_SELECTOR",                        # facts refresh without a button
            "!doc.querySelector(RELEASE_FACTS_SELECTOR)) return;",
            "if (isDynamicDownloadLink(link)) return;",      # routing must not clobber hrefs
            "agora.latestRelease",                           # sessionStorage cache key
            "sessionStorage",
            "credentials: 'omit'",
            "AbortController",
            "console.warn",
            "doc.addEventListener('DOMContentLoaded', boot)",
        ]:
            self.assertIn(contract, app)
        self.assertIn("try {", app)
        self.assertIn("catch", app)

        proxy = ROOT / "functions" / "api" / "latest-release.js"
        self.assertTrue(proxy.is_file(), "The proxy keeps visitors off GitHub's 60/hour limit")
        source = proxy.read_text()
        for contract in [
            "export async function onRequestGet",
            "api.github.com/repos/",
            "releases/latest",
            "browser_download_url",
            r"/\.apk$/i",
            "caches.default",
            "cache.put",
            "application/json",
            "GITHUB_TOKEN",
            "const PREFERRED_APK_NAME = '%s';" % PREFERRED_APK,
            "asset.name.toLowerCase() === PREFERRED_APK_NAME",
            "fallback: PERMANENT_DOWNLOAD_URL",  # failures hand back a download, not a page
        ]:
            self.assertIn(contract, source)

    def test_release_metadata_hooks(self):
        """Static release facts remain as no-JS fallbacks but expose refresh hooks."""
        download = (ROOT / "download.html").read_text()
        for hook in ["data-download-tag", "data-download-file", "data-download-size"]:
            self.assertIn(hook, download)
        for name in ["index.html", "shared-post.html"]:
            self.assertIn("data-download-size", (ROOT / name).read_text())
        app = (ROOT / "app.js").read_text()
        for hook in ["'data-download-tag'", "'data-download-file'", "'data-download-size'"]:
            self.assertIn(hook, app)
        # index.html and shared-post.html show the size but no longer carry a
        # download button, so the lookup has to key off the facts themselves or
        # those chips would freeze at their authored fallback forever.
        self.assertIn("[data-download-tag], [data-download-file], [data-download-size]", app)

    def test_contact_links(self):
        for page in self.pages.values():
            contacts = [(a, text) for a, text in page.anchors if a.get("href", "").startswith("mailto:")]
            self.assertTrue(contacts)
            for attrs, text in contacts:
                self.assertEqual(attrs["href"], "mailto:mail@agora.in.net")
                self.assertEqual(text.strip(), "mail@agora.in.net")

    def test_preserved_screenshot_slots(self):
        placements = Counter()
        pending = 0
        for page in self.pages.values():
            for tag, attrs in page.tags:
                if tag == "img" and attrs.get("src") in CAPTURES:
                    placements[attrs["src"]] += 1
                if attrs.get("class") == "phone__pending":
                    pending += 1
        self.assertEqual(dict(placements), CAPTURES)
        self.assertEqual(pending, 6)
        self.assertIn("object-fit: contain", self.css)

    def test_local_assets_and_links(self):
        # Only documented launch captures and the developer portrait may be absent.
        for name, page in self.pages.items():
            for tag, attrs in page.tags:
                for attr in ("src", "href"):
                    url = attrs.get(attr, "")
                    if url.startswith("/"):
                        path = urlsplit(url).path
                        with self.subTest(page=name, url=url):
                            self.assertTrue(
                                path in CAPTURES
                                or path in PENDING_ASSETS
                                or path == "/assets/developer.png"
                                or (ROOT / path.lstrip("/")).is_file()
                            )

    def test_credits_contributors(self):
        page = self.pages["credits.html"]
        source_images = [
            attrs.get("src")
            for tag, attrs in page.tags
            if tag == "img" and "rotary-profile__photo" in attrs.get("class", "")
        ]
        self.assertEqual(
            source_images,
            [
                "/assets/developer.png",
                "/assets/yashvardhan-bhaskar.jpg",
                "/assets/agora-public.jpg",
            ],
        )
        self.assertNotIn("/assets/agora-logo.svg", source_images)
        html = (ROOT / "credits.html").read_text()
        for name in ["Yashvardhan Bhaskar", "The Agora Public", "Design &amp; ideas", "The public"]:
            self.assertIn(name, html)
        self.assertIn("Original maker of this credits screen", html)
        self.assertIn("makes the platform what it is", html)
        name_tags = [
            attrs
            for tag, attrs in page.tags
            if tag == "div" and "rotary-name-tag" in attrs.get("class", "")
        ]
        self.assertEqual(len(name_tags), 3)
        self.assertEqual(
            [attrs.get("data-rotary-name-tag") for attrs in name_tags],
            ["0", "1", "2"],
        )
        self.assertIn("data-rotary-name-tag=\"1\"", html)
        self.assertIn("data-rotary-name-tag=\"2\"", html)
        self.assertIn("--tag-counter-rotation", (ROOT / "app.js").read_text())
        self.assertIn("nameTags.length !== bottomSegments.length", (ROOT / "app.js").read_text())
        self.assertIn("padding: 8px 16px", self.css)
        self.assertIn(".rotary-sign,\n.rotary-name-tag", self.css)
        self.assertIn("@media (max-width: 768px)", self.css)
        self.assertIn("translate(-65%, -65%)", self.css)
        self.assertIn("translate(65%, 65%)", self.css)
        for listener in ["touchstart", "touchmove", "touchend"]:
            self.assertIn("page.addEventListener('" + listener + "'", (ROOT / "app.js").read_text())
        self.assertIn("TOUCH_DAMPING", (ROOT / "app.js").read_text())
        self.assertIn("SNAP_THRESHOLD", (ROOT / "app.js").read_text())

    def test_pjax_and_persistent_audio_contract(self):
        app = (ROOT / "app.js").read_text()
        for contract in [
            "new DOMParser().parseFromString",
            "history.pushState",
            "window.addEventListener('popstate'",
            "currentMain.replaceWith",
            "bootPage();",
            "window.AgoraAudio",
            "master.gain.value = 0",
            "sourceNode.loop = true",
            "sourceNode.start(0)",
            "document.addEventListener('click', firstClickStartsAudio, true)",
            "isPlaying",
        ]:
            self.assertIn(contract, app)

    def test_background_music_contract(self):
        js = (ROOT / "app.js").read_text()
        self.assertIn("var MUSIC_SRC = '/assets/bgMusic.mpeg';", js)
        self.assertIn("sourceNode.loop = true;", js)
        self.assertIn("filter.type = 'lowpass';", js)
        self.assertIn("filter.frequency.setValueAtTime(2200", js)
        self.assertIn("sourceNode.start(0)", js)
        music = ROOT / "assets/bgMusic.mpeg"
        self.assertTrue(music.is_file())
        self.assertGreater(music.stat().st_size, 0)

    def test_shared_flow_is_isolated(self):
        for name, page in self.pages.items():
            for attrs, text in page.anchors:
                path = urlsplit(attrs.get("href", "")).path
                self.assertNotIn(path, ["/shared-post.html", "shared-post.html"])
                self.assertFalse(path.startswith(("/post/", "/p/")))
                self.assertNotEqual(attrs.get("data-page"), "shared")
        self.assertNotIn("How shared links work", (ROOT / "download.html").read_text())
        self.assertNotIn("shared:", (ROOT / "app.js").read_text())
        robots = [a for tag, a in self.pages["shared-post.html"].tags if a.get("name") == "robots"]
        self.assertIn("noindex", robots[0]["content"])
        # External deep-link routes remain intact.
        redirects = (ROOT / "_redirects").read_text()
        for route in ["/post/:id", "/p/:id"]:
            self.assertIn(route, redirects)

    def test_why_agora_links(self):
        home = self.pages["index.html"]
        targets = [a for tag, a in home.tags if a.get("id") == "why-agora"]
        self.assertEqual(len(targets), 1)
        for name, page in self.pages.items():
            links = [(a, text) for a, text in page.anchors if text.strip() == "Why Agora"]
            self.assertTrue(links)
            for attrs, text in links:
                self.assertIn(attrs["href"], ["#why-agora", "/index.html#why-agora"])
            self.assertNotRegex((ROOT / name).read_text(), r'#why["\']')
        rule = re.search(r"#why-agora \{([^}]+)\}", self.css)[1]
        self.assertIn("scroll-margin-top: 5rem", rule)
        self.assertIn("scroll-behavior: smooth", self.css)

    def test_feedback_form_is_wired(self):
        """The About form must actually deliver: validated, announced, sent."""
        about = (ROOT / "about.html").read_text()
        page = self.pages["about.html"]

        form = [a for tag, a in page.tags if a.get("id") == "feedback-form"]
        self.assertEqual(len(form), 1, "About page needs the feedback form")

        # No stale placeholder copy left behind.
        for stale in ["Placeholder form", "no data leaves your browser", "isn\u2019t connected to a server yet"]:
            self.assertNotIn(stale, about)

        # Every validated field is marked and owns an inline error slot.
        for name in ["name", "email", "topic", "message"]:
            self.assertIn('data-validate', about)
            self.assertIn('data-error-for="%s"' % name, about)
            self.assertIn('aria-describedby="fb-%s-error"' % name, about)

        # Submit outcome is announced, not silent.
        status = [a for tag, a in page.tags if a.get("id") == "feedback-status"]
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0].get("role"), "status")
        self.assertEqual(status[0].get("aria-live"), "polite")

        # Spam trap + JS-driven success copy.
        self.assertIn("data-honeypot", about)
        self.assertIn("data-success-note", about)
        self.assertIn("data-button-label", about)

        app = (ROOT / "app.js").read_text()
        function = (ROOT / "functions" / "api" / "contact.js").read_text()
        self.assertIn("fetch('/api/contact'", app, "Form must POST to the Pages Function")
        self.assertIn("CONTACT_EMAIL", app)
        self.assertNotIn("FORM_ENDPOINT", app)
        self.assertNotIn("openMailClient", app)
        self.assertIn("Sending...", app)
        self.assertIn("window.alert", app, "Submission errors need a direct user cue")
        self.assertIn("AbortController", app, "API path must time out")
        self.assertIn("export async function onRequestPost", function)
        self.assertIn("context.env.RESEND_API_KEY", function)
        self.assertIn("https://api.resend.com/emails", function)
        self.assertIn("New Agora Feedback:", function)
        self.assertNotIn('action="mailto:', about)

        for rule in [".field__error", ".form-status--error", ".form-status--ok", ".field--hp"]:
            self.assertIn(rule, self.css, "Form feedback needs styling: %s" % rule)

    def test_creator_and_about_cta(self):
        page = self.pages["about.html"]
        avatars = [a for tag, a in page.tags if a.get("class") == "developer-avatar"]
        self.assertEqual(len(avatars), 1)
        self.assertEqual(avatars[0]["src"], "/assets/developer.png")
        self.assertEqual(avatars[0]["alt"], "Jayvardhan Bhaskar")
        avatar_rule = re.search(r"\.developer-avatar \{([^}]+)\}", self.css)[1]
        self.assertIn("border-radius: 50%", avatar_rule)
        self.assertIn("object-fit: cover", avatar_rule)
        about = (ROOT / "about.html").read_text()
        for obsolete in ["Jay B.", "10+ yrs", "last decade", "specialist", "encrypted synchronization", "No board"]:
            self.assertNotIn(obsolete, about)
        self.assertIn("Jayvardhan Bhaskar", about)
        self.assertIn("App &amp; website developer", about)
        self.assertIn("social media does not", about)
        self.assertIn("suppress voices", about)
        self.assertIn("fun project", about)
        self.assertNotIn("[Developer name]", about)
        self.assertNotIn("[Personal motivation:", about)
        self.assertIn('id="get-app"', about)
        self.assertIn('Bring your voice.', about)
        self.assertIn('color: var(--refuse)', self.css)
        self.assertIn('color: var(--build)', self.css)

    def test_primary_button_label_color(self):
        # Get the app, Download APK, and Send message all use this shared rule.
        # The label is a token now so the light theme can flip it to white ink;
        # the dark value is pinned below to keep the shipped rendering exact.
        primary = re.search(r"\.btn--primary \{([^}]+)\}", self.css)[1]
        self.assertIn("color: var(--on-accent)", primary)
        self.assertIn("--on-accent: #110819;", self.css)
        self.assertIn("background: var(--accent)", primary)
        self.assertNotRegex(self.css, r"\.btn--get-app \{[^}]*color:")
        for page in self.pages.values():
            for tag, attrs in page.tags:
                if "btn--get-app" in attrs.get("class", "").split():
                    self.assertIn("btn--primary", attrs["class"].split())

    def test_theme_contract(self):
        for token in ["--bg: #0A0B0E;", "--surface: #13141D;", "--accent: #8B5CF6;",
                      "--accent-deep: #7C3AED;", "--text: #F3F4F6;", "--text-dim: #9CA3AF;",
                      "--border: rgba(255, 255, 255, 0.08);"]:
            self.assertIn(token, self.css)
        primary = re.search(r"\.btn--primary \{([^}]+)\}", self.css)[1]
        self.assertIn("background: var(--accent)", primary)
        self.assertIn("border-radius: 9999px", primary)
        self.assertIn("backdrop-filter: blur(18px)", self.css)
        self.assertEqual(self.css.count("{"), self.css.count("}"))
        for old_accent in ["#a5f3fc", "#22d3ee", "--emerald", "#fda4af"]:
            self.assertNotIn(old_accent, self.css)

    def test_light_theme_contract(self):
        """Light mode follows the OS; dark stays the default fallback.

        Three things are load-bearing here:
          1. the light palette exists ONLY inside prefers-color-scheme, so an
             engine that ignores the query still gets the dark theme;
          2. the phone mockup and the mask carrier are deliberately NOT
             re-skinned (hardware around dark screenshots / alpha, not colour);
          3. nothing outside the token blocks holds a raw colour, so the switch
             is a variable swap and cannot leave a stranded dark literal.
        """
        self.assertIn("color-scheme: dark;", self.css)

        light = re.search(r"@media \(prefers-color-scheme: light\) \{(.*?)\n\}",
                          self.css, re.S)
        self.assertIsNotNone(light, "no prefers-color-scheme: light block")
        light_block = light.group(1)
        self.assertIn("color-scheme: light;", light_block)

        # A contrast-audited slice of the light palette (WCAG AA on every
        # surface it is paired with; see the audit notes in style.css 1h).
        for token in ["--bg: #F7F9FC;", "--bg-soft: #FAFAFC;", "--surface: #FFFFFF;",
                      "--text: #1A1E23;", "--text-dim: #4B5563;",
                      "--text-faint: #5A6472;", "--accent: #6D28D9;",
                      "--accent-deep: #5B21B6;", "--blue: #1D4ED8;",
                      "--refuse: #BE123C;", "--build: #047857;",
                      "--overlay-rgb: 15, 23, 42;", "--on-accent: #FFFFFF;"]:
            self.assertIn(token, light_block)

        # The glass inversion: white-based translucency becomes dark-based.
        self.assertIn("--overlay-rgb: 255, 255, 255;", self.css)
        self.assertNotIn("--device-hi:", light_block)
        self.assertNotIn("--device-screen:", light_block)
        self.assertNotIn("--mask-solid:", light_block)

        # Every colour outside the two token blocks must be a variable.
        body = re.sub(r"/\*.*?\*/", " ", self.css, flags=re.S)
        body = re.sub(r"(?m)^\s*:root\s*\{.*?^\s*\}", " ", body, flags=re.S)
        self.assertNotRegex(body, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotRegex(body, r"rgba?\(\s*\d")
        # A colour can also hide inside a data URI as %23-encoded hex, where
        # no `#` scan will find it. The select chevron is exactly that case, so
        # the whole URL is a token and each theme supplies its own.
        self.assertNotRegex(body, r"%23[0-9a-fA-F]{3,8}")
        self.assertIn("--select-chevron: url(", self.css)
        self.assertIn("background-image: var(--select-chevron)", self.css)

    def test_device_subtree_does_not_flip(self):
        """The phone screen stays dark in both themes, so anything painted
        inside it must not follow the palette -- otherwise the pending-state
        caption renders dark-on-dark once the OS asks for light mode."""
        light = re.search(r"@media \(prefers-color-scheme: light\) \{(.*?)\n\}",
                          self.css, re.S).group(1)
        for token in ["--device-screen", "--device-ink", "--device-ink-dim",
                      "--device-accent-soft", "--device-hi", "--device-ring-rgb",
                      "--mask-solid"]:
            self.assertIn(token + ":", self.css)
            self.assertNotIn(token + ":", light,
                             f"{token} must not be redefined for the light theme")

        pending = re.search(r"\.phone__pending \{([^}]+)\}", self.css)[1]
        self.assertIn("color: var(--device-ink)", pending)
        small = re.search(r"\.phone__pending small \{([^}]+)\}", self.css)[1]
        self.assertIn("color: var(--device-ink-dim)", small)

    def test_ambient_canvas_follows_theme(self):
        """The dot matrix is painted on a <canvas>, so CSS cannot reach it.

        It has to read the brand channels back out of the stylesheet and
        re-read them when the OS flips scheme, otherwise it keeps painting
        dark-theme dots onto a light page.
        """
        js = (ROOT / "app.js").read_text()
        self.assertIn("getPropertyValue('--blue-rgb')", js)
        self.assertIn("getPropertyValue('--accent-rgb')", js)
        self.assertIn("palette.blue : palette.accent", js)
        self.assertIn("(prefers-color-scheme: light)", js)
        # The draw loop must not inline the palette; the literals may only
        # survive as the named fallbacks used when the tokens are unreadable.
        self.assertNotRegex(js, r"\?\s*'96,165,250'\s*:\s*'139,92,246'")
        self.assertIn("FALLBACK_BLUE", js)
        self.assertIn("FALLBACK_ACCENT", js)

    def test_theme_color_meta_follows_scheme(self):
        """Browser chrome must not stay dark when the page goes light."""
        for name, page in self.pages.items():
            metas = [attrs for tag, attrs in page.tags
                     if tag == "meta" and attrs.get("name") == "theme-color"]
            self.assertTrue(metas, f"{name}: no theme-color meta")
            by_media = {m.get("media"): m.get("content") for m in metas}
            # Unqualified tag stays as the fallback for engines that ignore
            # `media` on theme-color, so chrome is never left undefined.
            self.assertIn(None, by_media, f"{name}: missing unqualified fallback")
            self.assertEqual("#0A0B0E", by_media[None], name)
            self.assertEqual("#0A0B0E", by_media.get("(prefers-color-scheme: dark)"), name)
            self.assertEqual("#F7F9FC", by_media.get("(prefers-color-scheme: light)"), name)


# --------------------------------------------------------------------------
# WCAG 2.1 relative-luminance contrast. Kept inline so the suite stays
# dependency-free; the light theme is only "finished" if it is legible, and
# legibility is a number rather than an opinion.
# --------------------------------------------------------------------------
def _lum(rgb):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _hex(value):
    value = value.strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


class ThemeContrast(unittest.TestCase):
    """Every text/background pairing both themes actually render is measured.

    The LIGHT theme is held to WCAG AA without exception -- it is new work and
    must not ship unreadable text. The DARK theme is held to its *shipped
    baseline*: three pairings sit marginally under AA because --accent and the
    brand gradient stops are pinned verbatim by test_theme_contract and predate
    this work (the token refactor was verified to leave every dark value
    byte-identical). Those are baseline-locked so the palette cannot regress
    unnoticed, rather than being "fixed" by silently redesigning the dark brand.

    Surfaces are limited to the ones the stylesheet really paints: --surface-2
    and --surface-3 exist in the token ramp but appear in no background
    declaration, so grading text against them would invent pairings that never
    render and hide the real ones.
    """

    SURFACES = ["--bg", "--bg-soft", "--surface", "--field-bg"]
    TEXT = ["--text", "--text-dim", "--text-faint", "--text-bright"]
    ACCENTS = ["--accent", "--blue", "--lavender", "--violet-soft",
               "--refuse", "--build"]

    # (foreground token, background) -> measured ratio in the shipped dark theme.
    DARK_BASELINE = {
        ("--accent", "--surface"): 4.33,
        ("--on-gradient", "#8B5CF6"): 4.23,
        ("--on-gradient", "#60A5FA"): 2.54,
    }

    @classmethod
    def setUpClass(cls):
        raw = (ROOT / "style.css").read_text()
        cls.css = re.sub(r"/\*.*?\*/", " ", raw, flags=re.S)
        cls.dark = cls._root(cls.css, light=False)
        light_only = cls._root(cls.css, light=True)
        if not light_only:
            raise unittest.SkipTest(
                "no @media (prefers-color-scheme: light) :root block to audit")
        # The light theme inherits every dark token it does not redefine.
        cls.light = {**cls.dark, **light_only}

    @staticmethod
    def _root(css, light):
        if light:
            block = re.search(
                r"@media \(prefers-color-scheme: light\)\s*\{\s*:root\s*\{(.*?)\n\s*\}\s*\n\}",
                css, re.S).group(1)
        else:
            block = re.search(r"(?m)^:root\s*\{(.*?)^\}", css, re.S).group(1)
        tokens = {}
        for decl in block.split(";"):
            decl = " ".join(decl.split())
            if decl.startswith("--") and ":" in decl:
                key, value = decl.split(":", 1)
                tokens[key.strip()] = value.strip()
        return tokens

    def _value(self, theme, token):
        """Resolve a token to a colour, following var() indirection."""
        value = theme[token]
        for _ in range(8):
            inner = re.search(r"var\((--[a-z0-9-]+)\)", value)
            if not inner:
                break
            value = value.replace(inner.group(0), theme.get(inner.group(1), ""))
        return value.strip()

    def _used_as_text(self, token):
        return re.search(rf"(?<![-\w])color:\s*var\(\s*{re.escape(token)}\s*\)",
                         self.css) is not None

    def _floor(self, theme_name, pair, default):
        """AA for the light theme; the shipped baseline for known dark pairs."""
        if theme_name == "light":
            return default
        return self.DARK_BASELINE.get(pair, default)

    def test_text_tokens_clear_their_threshold(self):
        for name, theme in (("dark", self.dark), ("light", self.light)):
            for ink in self.TEXT + self.ACCENTS:
                # 3:1 (WCAG 1.4.11) when the token is never used as a `color:`,
                # 4.5:1 otherwise. Derived from the stylesheet, not assumed.
                default = 4.5 if (ink in self.TEXT or self._used_as_text(ink)) else 3.0
                for surface in self.SURFACES:
                    fg, bg = self._value(theme, ink), self._value(theme, surface)
                    if not re.match(r"^#[0-9a-fA-F]{6}$", fg) or not re.match(r"^#[0-9a-fA-F]{6}$", bg):
                        continue
                    ratio = _ratio(_hex(fg), _hex(bg))
                    need = self._floor(name, (ink, surface), default)
                    self.assertGreaterEqual(
                        ratio, need - 0.01,
                        f"{name} theme: {ink} ({fg}) on {surface} ({bg}) "
                        f"= {ratio:.2f}:1, needs {need:.2f}:1")

    def test_ink_on_accent_fills(self):
        for name, theme in (("dark", self.dark), ("light", self.light)):
            ink = _hex(self._value(theme, "--on-accent"))
            fill = self._value(theme, "--accent")
            need = self._floor(name, ("--on-accent", fill), 4.5)
            self.assertGreaterEqual(_ratio(ink, _hex(fill)), need - 0.01,
                                    f"{name}: --on-accent on --accent")

            # Ink must clear its threshold at EVERY gradient stop, not just the
            # first: the lightest stop is the one that usually fails.
            stops = re.findall(r"#[0-9a-fA-F]{6}",
                               self._value(theme, "--brand-gradient-ink"))
            self.assertTrue(stops, "brand gradient has no colour stops")
            on_gradient = _hex(self._value(theme, "--on-gradient"))
            for stop in stops:
                need = self._floor(name, ("--on-gradient", stop), 4.5)
                self.assertGreaterEqual(
                    _ratio(on_gradient, _hex(stop)), need - 0.01,
                    f"{name}: --on-gradient on gradient stop {stop}")

    def test_specular_rim_stays_visible_on_saturated_fills(self):
        """The rotary sign/name tag draws its rim ON a saturated gradient, so
        the rim channel must stay bright in both themes.

        Letting it follow --lavender-rgb inverts it into the same violet as the
        gradient stop underneath, which measures 1.00:1 -- an edge that ceases
        to exist. --rim-rgb is pinned bright instead: 5.82:1 in light.

        Dark is baseline-locked at 1.25:1 rather than held to the light bar,
        because pale lavender against the gradient's lightest #60A5FA stop is
        1.32:1 as shipped and that palette is pinned by test_theme_contract.
        """
        floors = {"dark": 1.25, "light": 3.0}
        alpha = 0.88  # as authored on .rotary-sign / .rotary-name-tag
        for name, theme in (("dark", self.dark), ("light", self.light)):
            self.assertIn("--rim-rgb", theme, f"{name}: rim channel missing")
            rim = tuple(int(x) for x in theme["--rim-rgb"].split(","))
            stops = re.findall(r"#[0-9a-fA-F]{6}",
                               self._value(theme, "--brand-gradient-ink"))
            self.assertTrue(stops, "brand gradient has no colour stops")
            for stop in stops:
                fill = _hex(stop)
                painted = tuple(round(alpha * c + (1 - alpha) * f)
                                for c, f in zip(rim, fill))
                ratio = _ratio(painted, fill)
                self.assertGreaterEqual(
                    ratio, floors[name],
                    f"{name}: rim rgb({theme['--rim-rgb']}) at {alpha} on stop "
                    f"{stop} = {ratio:.2f}:1, needs {floors[name]}:1")

        # And the component must consume the channel, not a colour token that
        # would invert underneath it.
        sign = re.search(r"\.rotary-sign,\s*\.rotary-name-tag \{([^}]+)\}",
                         self.css)[1]
        self.assertIn("border: 1px solid rgba(var(--rim-rgb), 0.88)", sign)
        self.assertNotIn("var(--lavender-rgb)", sign)

    def test_select_chevron_clears_non_text_minimum(self):
        """The chevron is an inline SVG, so its stroke cannot hold var() and the
        whole data URI is the token. The dark theme's #9aa8bf measures 2.44:1 on
        white, which is why the light theme supplies a darker one."""
        for name, theme in (("dark", self.dark), ("light", self.light)):
            match = re.search(r"%23([0-9a-fA-F]{6})", theme["--select-chevron"])
            self.assertIsNotNone(match, f"{name}: chevron has no encoded colour")
            field = _hex(self._value(theme, "--field-bg"))
            ratio = _ratio(_hex(match.group(1)), field)
            self.assertGreaterEqual(
                ratio, 3.0,
                f"{name}: select chevron #{match.group(1)} on --field-bg "
                f"= {ratio:.2f}:1, needs 3:1")


# Android Digital Asset Links. Google's verifier fetches exactly
# https://<domain>/.well-known/assetlinks.json and requires HTTP 200 with
# Content-Type: application/json and no redirect; anything else is reported in
# the Play Console as a generic "not associated" error with no detail, so the
# file's location and shape are worth pinning hard.
ASSETLINKS_PATH = ".well-known/assetlinks.json"
ASSETLINKS_URL_PATH = "/.well-known/assetlinks.json"
ANDROID_PACKAGE = "net.agora.app"
SITE_DOMAIN = "agora.in.net"
SHA256_FINGERPRINT = re.compile(r"^[0-9A-F]{2}(?::[0-9A-F]{2}){31}$")


class AssetLinksContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / ASSETLINKS_PATH
        cls.raw = cls.path.read_text() if cls.path.exists() else ""
        cls.statements = json.loads(cls.raw) if cls.raw else []
        cls.redirects = (ROOT / "_redirects").read_text()
        cls.headers_path = ROOT / "_headers"
        cls.headers = cls.headers_path.read_text() if cls.headers_path.exists() else ""

    def test_file_lives_at_the_publish_root(self):
        """The repository root IS the static site (see README "Deploy"), so the
        statement list must sit at root/.well-known/. A copy under public/ is
        served at /public/.well-known/... and the canonical URL then falls
        through the /* catch-all, which answers 200 with index.html -- HTML
        where Android expects JSON, failing verification silently."""
        self.assertTrue(self.path.is_file(),
                        f"{ASSETLINKS_PATH} must exist at the publish root")
        self.assertFalse((ROOT / "public" / ".well-known").exists(),
                         "a stale copy under public/ is unreachable at the canonical URL")
        self.assertFalse((ROOT / "public").exists(),
                         "public/ is dead Vite scaffold; the site publishes from the root")

    def test_statement_list_schema(self):
        self.assertIsInstance(self.statements, list, "assetlinks.json must be a JSON array")
        self.assertEqual(len(self.statements), 1)
        statement = self.statements[0]
        self.assertEqual(statement["relation"],
                         ["delegate_permission/common.handle_all_urls"])
        target = statement["target"]
        self.assertEqual(target["namespace"], "android_app")
        self.assertEqual(target["package_name"], ANDROID_PACKAGE)
        self.assertIn("sha256_cert_fingerprints", target)

    def test_package_name_is_one_agreed_identifier_everywhere(self):
        """The package is a chosen applicationId, NOT the site domain reversed
        (`net.agora.app` reverses to `app.agora.net`), so the old reversal
        heuristic cannot catch a typo any more. What still has to hold is that
        every place the site names the package names the SAME one, and that it
        is a well-formed identifier rather than scaffold filler."""
        parts = ANDROID_PACKAGE.split(".")
        self.assertGreaterEqual(len(parts), 3, "an applicationId needs at least three segments")
        for part in parts:
            self.assertRegex(part, r"^[a-z][a-z0-9_]*$", f"{part!r} is not a valid package segment")
        self.assertNotIn("example", parts, "com.example.* is reserved scaffold filler")
        # assetlinks.json is what Android verifies against; app.js is what the
        # intent:// URI names. If they disagree the button targets an app the
        # statement never authorised, and it fails silently on the exact
        # devices it was built for.
        self.assertEqual(self.statements[0]["target"]["package_name"], ANDROID_PACKAGE)
        app = (ROOT / "app.js").read_text()
        self.assertIn(f"var ANDROID_PACKAGE = '{ANDROID_PACKAGE}';", app,
                      "app.js must build the intent for the same package")
        self.assertIn(f"mail@{SITE_DOMAIN}", app,
                      "and the contact domain is still the canonical one")
        self.assertEqual(SITE_DOMAIN, "agora.in.net")

    def test_release_and_debug_fingerprints_are_both_present(self):
        fingerprints = self.statements[0]["target"]["sha256_cert_fingerprints"]
        self.assertEqual(len(fingerprints), 2,
                         "expected the release and the debug certificate")
        for fp in fingerprints:
            self.assertRegex(fp, SHA256_FINGERPRINT,
                             f"{fp} is not 32 uppercase colon-separated hex pairs")
        self.assertEqual(len(set(fingerprints)), 2, "fingerprints must not repeat")

    def test_no_placeholder_package_survives(self):
        """com.example.agora was scaffold filler; if it ships, the real app
        never verifies and nothing in the Play Console says why."""
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if path.suffix not in {".json", ".html", ".js", ".md", ".xml", ".txt", ".ts"}:
                continue
            try:
                if "com.example.agora" in path.read_text():
                    offenders.append(str(path.relative_to(ROOT)))
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(offenders, [], f"placeholder package name still present in {offenders}")

    def test_response_headers_are_pinned(self):
        """A wrong Content-Type fails verification exactly as hard as a 404."""
        self.assertTrue(self.headers_path.is_file(), "_headers is missing")
        block = re.search(re.escape(ASSETLINKS_URL_PATH) + r"\n((?:[ \t]+[^\n]+\n?)+)",
                          self.headers)
        self.assertIsNotNone(block, f"_headers has no rule for {ASSETLINKS_URL_PATH}")
        headers = block.group(1).lower()
        self.assertIn("content-type: application/json", headers)
        self.assertIn("x-content-type-options: nosniff", headers)

    def test_redirects_do_not_shadow_the_statement_list(self):
        """Real files win over _redirects on Pages, but a rewrite aimed at this
        path would take precedence and hand Android the SPA shell instead."""
        self.assertNotIn(".well-known", self.redirects,
                         "_redirects must not rewrite the assetlinks path")
        # The SPA catch-all must still exist and stay last.
        rules = [ln.strip() for ln in self.redirects.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        self.assertTrue(rules, "_redirects has no rules")
        self.assertTrue(rules[-1].startswith("/*"),
                        "the /* SPA catch-all must remain the final rule")


class SharedPostRouting(unittest.TestCase):
    """/post/<id> deep links must resolve their id from the PATH.

    `_redirects` rewrites /post/:id and /p/:id to shared-post.html with a **200**
    status. A 200 rewrite serves the target file's bytes but never changes the
    browser's address bar, so on a real share link window.location.search is
    EMPTY. Writing ?post=:id on the rewrite destination looks like it fills that
    in; it does not -- the destination query only steers the edge's internal
    file lookup. Parsing the query alone therefore answered "This link doesn't
    include a post id" to every valid deep link in production, while working in
    local dev where the visitor types ?post= by hand.

    The patterns below are lifted out of app.js and compiled here, so these
    tests assert what the route MEANS rather than merely that a regex exists.
    """

    POST_UUID = "0c298d8b-c2f0-4f38-8585-7199f41c7769"
    ROUTES = ("/post/:id", "/p/:id")
    LANDING = "/shared-post.html"

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.html = (ROOT / "shared-post.html").read_text()
        cls.rules = [
            line.split()
            for line in (ROOT / "_redirects").read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        cls.statements = json.loads((ROOT / ASSETLINKS_PATH).read_text())

    # --- helpers -------------------------------------------------------
    def js_regex(self, name):
        """Extract `var NAME = /…/flags;` from app.js and compile it as Python.

        Every pattern the resolver uses sticks to syntax Python's `re` shares
        with JavaScript, so this exercises the real expression.
        """
        match = re.search(r"var %s = (/[^;\n]+);" % name, self.app)
        self.assertIsNotNone(match, f"app.js no longer defines {name}")
        literal = match.group(1)[1:]
        body, _, flags = literal.rpartition("/")
        return re.compile(body, re.IGNORECASE if "i" in flags else 0)

    def section(self, start, end):
        self.assertIn(start, self.app, f"{start} vanished from app.js")
        self.assertIn(end, self.app, f"{end} vanished from app.js")
        return self.app.split(start, 1)[1].split(end, 1)[0]

    # --- routing -------------------------------------------------------
    def test_deep_link_routes_rewrite_to_the_landing_page(self):
        by_source = {rule[0]: rule[1:] for rule in self.rules}
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertIn(route, by_source,
                              "the pretty share route must stay in _redirects")
                destination, *status = by_source[route]
                self.assertEqual(destination, self.LANDING)
                self.assertEqual(status, ["200"],
                                 "a 200 rewrite is what keeps the pretty URL in "
                                 "the address bar -- and what leaves search empty")

    def test_rewrite_destination_carries_no_query_string(self):
        """?post=:id on a 200 destination never reaches the client. Leaving it
        there is how the query-only parser came to look correct."""
        for rule in self.rules:
            with self.subTest(rule=" ".join(rule)):
                self.assertNotIn("?", rule[1],
                                 "a rewrite destination query is dead weight and "
                                 "actively misleading")

    def test_every_local_subresource_is_root_absolute(self):
        """The landing page is served from an arbitrary-depth path (/post/<id>),
        so a relative src would resolve against /post/ and request /post/app.js
        -- which the /* catch-all answers with 200 and index.html. The script
        tag would receive HTML, the page would die silently on pretty links and
        still work at /shared-post.html: the same "passes locally, breaks in
        production" trap as the query-only parser.
        """
        page = Page(ROOT / "shared-post.html")
        offenders = []
        absolute = 0
        for tag, attrs in page.tags:
            for attr in ("src", "href"):
                url = attrs.get(attr)
                if not url or url.startswith(("#", "mailto:", "tel:")):
                    continue
                if url.startswith("/") or re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I):
                    absolute += 1
                    continue
                offenders.append(f"<{tag} {attr}=\"{url}\">")
        self.assertEqual(offenders, [],
                         "relative URLs break when the page is served at /post/<id>")
        self.assertGreater(absolute, 3, "the parser found no subresources at all")
        scripts = {a.get("src") for t, a in page.tags if t == "script"}
        self.assertIn("/app.js", scripts)
        sheets = {a.get("href") for t, a in page.tags
                  if t == "link" and a.get("rel") == "stylesheet"}
        self.assertIn("/style.css", sheets)

    def test_deep_link_rules_precede_the_catch_all(self):
        """`/*` swallows everything below it: a deep-link rule placed after the
        catch-all would silently serve index.html instead of the landing page,
        and the visitor would see the home page with no post at all."""
        sources = [rule[0] for rule in self.rules]
        self.assertEqual(sources.count("/*"), 1, "exactly one SPA catch-all")
        self.assertTrue(sources[-1].startswith("/*"),
                        "the /* SPA fallback must remain the final rule")
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertEqual(sources.count(route), 1)
                self.assertLess(sources.index(route), sources.index("/*"),
                                f"{route} must come BEFORE the catch-all")

    # --- parsing -------------------------------------------------------
    def test_post_id_is_read_from_the_path(self):
        pattern = self.js_regex("POST_PATH_PATTERN")
        for path in (f"/post/{self.POST_UUID}", f"/p/{self.POST_UUID}",
                     "/post/a8f3c2/", "/POST/a8f3c2", "/p/a8f3c2"):
            with self.subTest(path=path):
                self.assertTrue(pattern.search(path), f"{path} must resolve")
        self.assertEqual(pattern.search(f"/post/{self.POST_UUID}").group(1),
                         self.POST_UUID, "the captured segment IS the post id")
        # Must not false-positive on the rest of the site.
        for path in (self.LANDING, "/index.html", "/download.html", "/credits.html",
                     "/support/a8f3c2", "/app/a8f3c2", "/help/a8f3c2",
                     "/post/", "/post-preview/x"):
            with self.subTest(path=path):
                self.assertIsNone(pattern.search(path), f"{path} must NOT resolve")
        # Scoped to the resolver: `location.pathname` occurs all over app.js, so
        # a global assertion passes even with the path capture deleted.
        resolver = self.section("function resolvePostId", "function shortenPostId")
        self.assertIn("resolvePostId(window.location)", self.app)
        self.assertIn("POST_PATH_PATTERN.exec(location.pathname", resolver,
                      "the resolver must actually read the id out of the PATH")

    def test_query_string_survives_only_as_a_fallback(self):
        keys = re.search(r"var POST_QUERY_KEYS = \[([^\]]+)\];", self.app)
        self.assertIsNotNone(keys, "the legacy query fallbacks disappeared")
        self.assertEqual(re.findall(r"'([^']+)'", keys.group(1)),
                         ["post", "post_id", "id"])
        resolver = self.section("function resolvePostId", "function shortenPostId")
        self.assertLess(resolver.index("POST_PATH_PATTERN.exec"),
                        resolver.index("new URLSearchParams"),
                        "the path must be tried BEFORE the query string")

    # --- validation ----------------------------------------------------
    def test_post_id_validation_is_permissive_but_safe(self):
        pattern = self.js_regex("POST_ID_PATTERN")
        for good in (self.POST_UUID, "a8f3c2", "abc", "V1StGXR8_Z5jdHi6B-myT",
                     "dQw4w9WgXcQ=", "9f2c1e7a"):
            with self.subTest(id=good):
                self.assertTrue(pattern.match(good), f"{good} is a plausible id")
        for bad in ("", "ab", "-abc", "a b", "../../etc/passwd", "a/b",
                    "<script>alert(1)</script>", "a" * 129, "%3Cimg%3E",
                    "..%2F..%2Fetc"):
            with self.subTest(id=bad):
                self.assertIsNone(pattern.match(bad), f"{bad!r} must be rejected")

    def test_ids_are_decoded_before_they_are_validated(self):
        """Decoding first is what stops %2F from smuggling a slash past the
        charset test, and a stray % must not throw the whole page."""
        decoder = self.section("function decodeUrlPart", "function resolvePostId")
        self.assertIn("decodeURIComponent", decoder)
        self.assertIn("try", decoder)
        self.assertIn("catch", decoder)
        resolver = self.section("function resolvePostId", "function shortenPostId")
        self.assertIn("decodeUrlPart(pathMatch[1])", resolver)
        self.assertLess(resolver.index("decodeUrlPart"),
                        resolver.index("POST_ID_PATTERN.test"),
                        "decode must happen before validation")

    # --- error state ---------------------------------------------------
    def test_error_state_separates_missing_from_invalid(self):
        """A valid UUID must never see the "no post id" copy, and a genuinely
        empty link must never be told its id is malformed."""
        for status in ("'ok'", "'missing'", "'malformed'"):
            self.assertIn(status, self.app)
        invalid = re.search(r"var EMPTY_MALFORMED_MESSAGE = '([^']+)'", self.app)
        missing = re.search(r"var EMPTY_MISSING_MESSAGE = '([^']+)'", self.app)
        self.assertIsNotNone(invalid)
        self.assertIsNotNone(missing)
        self.assertNotEqual(invalid.group(1), missing.group(1))
        self.assertNotIn("include a post id", invalid.group(1).lower())
        self.assertIn("data-empty-message", self.html,
                      "app.js needs a hook to swap the first sentence")
        branch = self.section("if (resolved.status !== 'ok')", "var postId = resolved.id;")
        # Every state the page can be in has to be settled here, or an error
        # link can leave a previous render on screen behind it.
        for element in ("emptyState", "resultState", "unavailableState", "openInAppRow"):
            self.assertIn(element, branch, f"{element} must be settled in the error branch")
        self.assertNotIn("loadingState", self.app,
                         "the simulated fetch is gone; nothing should still drive a skeleton")

    def test_empty_state_advertises_the_clean_link_shape(self):
        self.assertIn("\u2026/post/xxxxxxxx", self.html)
        self.assertNotIn("shared-post.html?post=xxxxxxxx", self.html,
                         "the copy must teach the shape the app actually shares")

    def test_post_id_is_never_written_with_innerhtml(self):
        """The id is attacker-controlled URL data on a publicly reachable page."""
        body = self.section("function initSharedPost", "function initImages")
        self.assertNotRegex(body, r"innerHTML\s*[+]?=",
                            "URL data must reach the DOM through textContent only")
        self.assertIn("chip.textContent =", body)
        self.assertIn("emptyMessage.textContent =", body)

    def test_chip_truncates_long_ids_but_keeps_the_full_value(self):
        """A 36-character UUID would blow out the mono chip in the flex bar."""
        uuid = self.js_regex("POST_ID_UUID_PATTERN")
        self.assertTrue(uuid.match(self.POST_UUID))
        shortener = self.section("function shortenPostId", "function supportsIntentUrls")
        self.assertRegex(shortener,
                         r"POST_ID_UUID_PATTERN\.test\(id\)\)\s*return id\.slice\(0,\s*8\);",
                         "a full UUID must be shortened, not printed whole into the chip")
        self.assertIn("chip.setAttribute('title'", self.app,
                      "the full id stays reachable for debugging")

    # --- app intent fallback -------------------------------------------
    def test_intent_package_matches_the_asset_links_statement(self):
        """Drift lock: an intent aimed at a stale package silently does nothing
        on a device that has the app installed."""
        declared = re.search(r"var ANDROID_PACKAGE = '([^']+)'", self.app)
        self.assertIsNotNone(declared)
        self.assertEqual(declared.group(1), ANDROID_PACKAGE)
        self.assertEqual(declared.group(1),
                         self.statements[0]["target"]["package_name"],
                         "app.js and assetlinks.json must name the same package")

    def test_app_intent_falls_back_to_the_download_page(self):
        builder = self.section("function buildAppIntentUrl", "function initSharedPost")
        for fragment in ("'intent://'", "scheme=https", "package=",
                         "S.browser_fallback_url=", "/download.html", ";end"):
            self.assertIn(fragment, builder, f"intent URL lost {fragment}")
        self.assertIn("encodeURIComponent(postId)", builder)
        self.assertIn("encodeURIComponent(fallback)", builder)
        self.assertIn("';end;'", builder,
                      "the intent URI must terminate exactly with ;end;")
        self.assertIn("CANONICAL_HOST", builder,
                      "the host is pinned, not derived from location.host: an "
                      "intent built on a *.pages.dev preview could never hand "
                      "off, because the manifest verifies one host only")
        self.assertNotIn("window.location.host", builder)

    def test_canonical_host_matches_the_verified_domain(self):
        """Drift lock, mirroring the package one above: an intent aimed at any
        other host cannot reach the app."""
        declared = re.search(r"var CANONICAL_HOST = '([^']+)'", self.app)
        self.assertIsNotNone(declared, "the intent host constant vanished")
        self.assertEqual(declared.group(1), SITE_DOMAIN)

    def test_intent_row_is_authored_hidden_and_user_agent_gated(self):
        """The app is Android-only, so the row is authored hidden and revealed
        only there. intent:// is narrower still -- Chromium-on-Android -- and
        every other Android browser gets the verified App Link instead, so the
        button is never a dead link on any platform."""
        self.assertRegex(self.html, r'id="open-in-app-row"[^>]*hidden')
        link = re.search(r"<a[^>]*data-open-intent-btn[^>]*>", self.html)
        self.assertIsNotNone(link, "the Open in the app link disappeared")
        self.assertIn(f'href="{DOWNLOAD_PAGE}"', link.group(0),
                      "the authored href is the safe stub: the row is hidden "
                      "until app.js replaces it")
        # The renamed hook has to be the ONLY one. A leftover attribute or a
        # stale selector in app.js would silently stop matching, and the button
        # would keep its plain href forever without anything failing loudly.
        self.assertNotIn("data-open-in-app", self.html)
        self.assertNotIn("data-open-in-app", self.app)
        self.assertIn("[data-open-intent-btn]", self.app,
                      "app.js must select the hook the markup actually carries")
        gate = self.section("function supportsIntentUrls", "function buildAppIntentUrl")
        self.assertIn("android", gate)
        self.assertIn("firefox", gate, "Gecko does not implement intent://")
        self.assertIn("return false", gate)

    def test_every_id_init_shared_post_looks_up_exists_on_the_page(self):
        """Each getElementById here is a contract between two files. Renaming one
        side is exactly how a button silently stops working: the lookup returns
        null, every `if (row && btn)` guard degrades to a no-op, the page still
        renders, and every source-level assertion still passes. So bind them."""
        body = self.section("function initSharedPost", "function initImages")
        ids = sorted(set(re.findall(r"getElementById\('([^']+)'\)", body)))
        self.assertTrue(ids, "no getElementById calls found; the anchor is stale")
        for element_id in ids:
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html,
                              f"app.js looks up #{element_id} but shared-post.html "
                              "does not author it")
        self.assertIn("open-in-app-row", ids,
                      "the open-in-app row must be one of the lookups")

    def test_the_open_in_app_row_is_gated_to_the_platform_that_has_the_app(self):
        """Two different gates, and they must not be conflated: isAndroid()
        decides whether the row EXISTS for this visitor, supportsIntentUrls()
        decides which URI it gets. Offering the row on iOS or desktop would
        promise an app the device cannot install; offering intent:// to Gecko
        would hand it a scheme it ignores entirely."""
        reveal = self.section("if (openInAppRow && openIntentBtn", "openInAppRow.hidden = false;")
        # Naming both builders is not enough: the choice has to land on the
        # element, or the row appears with its authored stub href and every
        # visitor gets sent to the download page instead of their post.
        self.assertRegex(reveal,
                         r"openIntentBtn\.setAttribute\('href',\s*supportsIntentUrls\(\)",
                         "the platform choice must be written to the button's href")
        self.assertIn("isAndroid()", reveal,
                      "the row must only appear where the app can exist")
        self.assertIn("supportsIntentUrls()", reveal,
                      "and only Chromium should get the intent:// URI")
        self.assertIn("buildAppWebUrl(postId)", reveal,
                      "other Android browsers must still get a working link")

        android = self.section("function isAndroid", "function buildAppWebUrl")
        self.assertIn("/android/i", android)

        web = self.section("function buildAppWebUrl", "function initSharedPost")
        self.assertIn("CANONICAL_HOST", web,
                      "the App Link host must be the verified one, not the "
                      "deployment the visitor happens to be on")
        self.assertIn("/post/", web, "and the path the manifest declares")
        self.assertIn("encodeURIComponent(postId)", web)


if __name__ == "__main__":
    unittest.main()


FUNCTION_PATH = ROOT / "functions" / "post" / "[id].js"


class SharedPostCard(unittest.TestCase):
    """The shared-post page must say WHO posted, rendered on the server.

    A chat app scrapes a pasted link the moment it is sent and never runs
    JavaScript, so anything that has to appear in the link preview must be in
    the very first response. That is why the author card is rendered by
    functions/post/[id].js rather than fetched by app.js: the same Supabase
    lookup that fills og:title also writes the card into the HTML, so first
    paint, no-JS visitors and scrapers all see the same author.

    What the page must never show is the post itself. It is the install prompt,
    not the reader. The allow-lists below are that contract, restated as data:
    widening a query has to mean editing a test.
    """

    POST_COLUMNS = {"id", "user_id", "created_at"}
    PROFILE_COLUMNS = {"handle", "first_name", "last_name", "avatar_url"}
    # `profiles` is world-readable under RLS, so anyone holding the anon key --
    # which ships inside every APK -- can already read these. None of it is
    # needed to draw an avatar, so none of it may be requested here.
    FORBIDDEN_COLUMNS = {
        "email", "dob", "gender", "fcm_token", "current_device_id",
        "active_session_id", "password_changed_at",
        # Product boundary rather than a privacy one: no body, no media, no counts.
        "content", "image_urls", "media_urls", "likes", "comments",
    }
    HOOKS = ("data-author", "data-handle", "data-monogram", "data-avatar",
             "data-avatar-frame", "data-first-name")
    RETIRED_HOOKS = ("data-created", "data-preview-body", "data-preview-status",
                     "data-preview-note")

    @classmethod
    def setUpClass(cls):
        cls.fn = FUNCTION_PATH.read_text()
        cls.html = (ROOT / "shared-post.html").read_text()
        cls.css = (ROOT / "style.css").read_text()
        cls.app = (ROOT / "app.js").read_text()
        cls.page = Page(ROOT / "shared-post.html")
        cls.redirects = [
            line.split()
            for line in (ROOT / "_redirects").read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    # --- helpers -------------------------------------------------------
    def elements_with(self, attribute):
        return [(tag, attrs) for tag, attrs in self.page.tags if attribute in attrs]

    def element_with_id(self, element_id):
        found = [(tag, attrs) for tag, attrs in self.page.tags
                 if attrs.get("id") == element_id]
        self.assertEqual(len(found), 1, f"expected exactly one #{element_id}")
        return found[0]

    def constant(self, name):
        match = re.search(r"^const %s = '([^']*)';$" % name, self.fn, re.MULTILINE)
        self.assertIsNotNone(match, f"functions/post/[id].js no longer defines {name}")
        return match.group(1)

    def number_constant(self, name):
        match = re.search(r"^const %s = (\d+);$" % name, self.fn, re.MULTILINE)
        self.assertIsNotNone(match, f"functions/post/[id].js no longer defines {name}")
        return int(match.group(1))

    def helper_body(self, name):
        match = re.search(r"^(?:async )?function %s\([\s\S]*?\n\}$" % name, self.fn, re.MULTILINE)
        self.assertIsNotNone(match, f"functions/post/[id].js no longer defines {name}()")
        return match.group(0)

    # --- the authored markup -------------------------------------------
    def test_the_author_card_is_visible_without_javascript(self):
        # Authored visible on purpose: the generic member IS a truthful card for
        # every path the Function does not serve (/p/<id>, ?post=, local dev),
        # so a visitor with scripts off still gets an answer rather than a hole.
        _tag, attrs = self.element_with_id("preview-result")
        self.assertNotIn("hidden", attrs,
                         "#preview-result must be server-rendered into view, not "
                         "revealed by a script")

    def test_the_h1_is_personalised_and_grammatical_by_default(self):
        match = re.search(r"<h1>([\s\S]*?)</h1>", self.html)
        self.assertIsNotNone(match, "the shared-card h1 disappeared")
        heading = match.group(1)
        self.assertRegex(heading, r"It looks like\s+<span data-first-name>",
                         "the hook belongs in the h1's own sentence")
        # The authored default and the injected fallback must be the same word,
        # or an unenriched page and an enriched page with no first name would
        # read differently -- and the fallback has to be lowercase, because it
        # sits mid-sentence.
        fallback = self.constant("FIRST_NAME_FALLBACK")
        self.assertEqual(fallback, fallback.lower(),
                         "a capitalised fallback is a grammar bug mid-sentence")
        self.assertIn(f'<span data-first-name>{fallback}</span>', self.html)

    def test_the_schema_first_name_placeholder_is_never_injected(self):
        # profiles.first_name is `text default 'User'`, so the literal word
        # "User" is what every member who never chose a name has stored.
        self.assertEqual(self.constant("PLACEHOLDER_FIRST_NAME"), "user")
        normalizer = self.helper_body("normalizeAuthor")
        self.assertIn("PLACEHOLDER_FIRST_NAME", normalizer)
        self.assertIn("toLowerCase()", normalizer,
                      "the comparison must ignore casing")
        self.assertIn("firstName", normalizer,
                      "the first name has to survive normalisation separately "
                      "from the full display name")
        injector = self.helper_body("injectAuthor")
        self.assertIn("data-first-name", injector)
        self.assertIn("FIRST_NAME_FALLBACK", injector,
                      "a missing first name must fall back, never inject ''")

    def test_the_greeting_does_not_assume_the_visitor_lacks_the_app(self):
        """The old h1 ended "but you don't have the app installed yet!" -- which
        this page cannot know, and which told a visitor who DOES have the app
        that they were wrong before offering them any way in."""
        for stale in ("shared an Agora post with you",
                      "don&rsquo;t have the app installed yet",
                      "don't have the app installed yet"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.html)
        heading = re.search(r"<h1>([\s\S]*?)</h1>", self.html).group(1)
        self.assertRegex(heading, r"It looks like\s+<span data-first-name>someone</span>\s+"
                                  r"shared a post with you\.",
                         "the greeting keeps the first-name hook and drops the "
                         f"assumption, got: {' '.join(heading.split())}")

    def test_the_head_copy_matches_the_reworded_greeting(self):
        """The h1, <title>, description and social tags all describe the same
        page; rewording one and leaving the rest is how a chat preview ends up
        contradicting the page it links to."""
        title = re.search(r"<title>([^<]*)</title>", self.html).group(1)
        self.assertEqual(title, "Someone shared a post with you — Agora",
                         "the title follows the site's '<page> — Agora' pattern")
        for attr, key in (("property", "og:title"), ("name", "twitter:title")):
            with self.subTest(tag=key):
                match = re.search(
                    r'<meta[^>]*%s\s*=\s*"%s"[^>]*content="([^"]*)"' % (attr, re.escape(key)),
                    self.html)
                self.assertIsNotNone(match, f"{key} disappeared")
                self.assertEqual(match.group(1), "Someone shared a post with you")
        for stale in ("shared an Agora post", "Get the Android app to read the post"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.html)

    def test_the_open_in_app_row_lives_in_the_hero_not_under_the_fold(self):
        hero = self.html.split('<section class="shared-card"', 1)[1].split("</section>", 1)[0]
        self.assertIn('id="open-in-app-row"', hero,
                      "the row belongs beside 'Get the app', where a visitor "
                      "who already has it will actually see it")
        self.assertIn("Already have the app?", hero)
        self.assertIn("Open this post in Agora", hero)
        self.assertIn("data-open-intent-btn", hero)
        after_preview = self.html.split('id="post-preview"', 1)[1]
        self.assertNotIn("open-in-app-row", after_preview,
                         "and it must not ALSO sit in the preview card")
        self.assertEqual(len(re.findall(r"data-open-intent-btn", self.html)), 1,
                         "moving the button must not leave the old one behind: "
                         "two buttons that open the same post is one too many")

    def test_the_retired_card_row_left_no_dead_css(self):
        self.assertNotIn(".post-preview__actions", self.css,
                         "the card row is gone; its layout rule went with it")
        self.assertIn(".shared-card__have-app {", self.css,
                      "the new row needs its own rule")
        block = self.css.split(".shared-card__have-app {", 1)[1].split("}", 1)[0]
        self.assertIn("flex-wrap: wrap", block, "the label and button must wrap on a narrow phone")
        self.assertIn("justify-content: center", block, "the hero is centred")
        self.assertNotRegex(block, r"#[0-9A-Fa-f]{3,8}\b",
                            "a literal colour here would not invert in light mode")
        self.assertNotRegex(block, r"\brgba?\(\s*\d", "same: use an --*-rgb token")

    def test_the_gone_state_is_authored_hidden(self):
        _tag, attrs = self.element_with_id("preview-unavailable")
        self.assertIn("hidden", attrs,
                      "the deleted-post note only appears when Supabase says so")

    def test_the_simulated_fetch_state_is_retired(self):
        self.assertEqual(self.elements_with("data-preview-status"), [])
        for page in ROOT.glob("*.html"):
            with self.subTest(page=page.name):
                self.assertNotIn("preview-loading", page.read_text(),
                                 "the fake 1200 ms fetch is gone; nothing should "
                                 "still render a loading state")
        self.assertNotIn(".skeleton", self.css,
                         "the shimmer primitive died with the fake fetch")
        self.assertNotIn("shimmer", self.css)

    def test_every_injection_hook_the_function_writes_exists_exactly_once(self):
        for hook in self.HOOKS:
            with self.subTest(hook=hook):
                self.assertEqual(len(self.elements_with(hook)), 1,
                                 f"{hook} must appear once: the Function injects "
                                 "by hook, and a duplicate would get only the first")

    def test_the_avatar_degrades_to_a_monogram(self):
        images = self.elements_with("data-avatar")
        self.assertEqual(len(images), 1)
        tag, attrs = images[0]
        self.assertEqual(tag, "img")
        # Authored hidden: the server unhides it only with a real https src, so
        # a missing avatar shows the initial instead of a broken-image glyph.
        self.assertIn("hidden", attrs)
        self.assertEqual(attrs.get("alt"), "",
                         "decorative: the member's name is right beside it")
        self.assertEqual(attrs.get("referrerpolicy"), "no-referrer",
                         "a third-party avatar must not learn who shared the link")
        self.assertIn("width", attrs)
        self.assertIn("height", attrs,
                      "intrinsic size, so the card cannot jump when it loads")
        self.assertNotIn("src", attrs,
                         "src is written by the Function only, once it has a real "
                         "https avatar; authoring one would paint a stranger")
        frames = self.elements_with("data-avatar-frame")
        self.assertEqual(len(frames), 1)
        monograms = self.elements_with("data-monogram")
        self.assertEqual(len(monograms), 1)
        self.assertEqual(monograms[0][1].get("aria-hidden"), "true",
                         "the initial is a stand-in for the picture, not content")

    def test_no_post_content_hook_survives(self):
        for hook in self.RETIRED_HOOKS:
            with self.subTest(hook=hook):
                self.assertEqual(self.elements_with(hook), [],
                                 f"{hook} belonged to the simulated payload")
                self.assertNotIn(f"[{hook}]", self.app,
                                 "app.js must not query a hook the card no longer has")

    def test_the_page_never_offers_a_reading_time_or_counts(self):
        preview = self.html.split('id="post-preview"', 1)[1]
        for word in ("likes", "replies", "reposts", "views"):
            with self.subTest(word=word):
                self.assertNotRegex(preview, re.compile(r">\s*[^<]*\b%s\b" % word, re.I),
                                    "the page proves a person posted; it does not "
                                    "publish engagement numbers")

    # --- the Function's privacy boundary --------------------------------
    def test_the_column_allow_lists_are_exact(self):
        self.assertEqual(set(self.constant("POST_COLUMNS").split(",")), self.POST_COLUMNS)
        self.assertEqual(set(self.constant("PROFILE_COLUMNS").split(",")), self.PROFILE_COLUMNS)

    def test_only_allow_listed_columns_are_ever_selected(self):
        # Every select list is assembled from the two constants, so the only way
        # to widen what leaves the database is to widen the allow-list -- which
        # the test above fails on. Asserting the OPERATION avoids the trap of
        # grepping the whole file, where the Function's own explanatory comment
        # legitimately names the columns it refuses to read.
        found = list(re.finditer(r"select=", self.fn))
        self.assertEqual(len(found), 3, "expected the embedded, plain and profile queries")
        for match in found:
            window = self.fn[match.start():match.start() + 220]
            with self.subTest(window=window[:60]):
                self.assertIn("encodeURIComponent(", window,
                              "a select list must be URL-encoded before it is sent")
                self.assertRegex(window, r"POST_COLUMNS|PROFILE_COLUMNS",
                                 "a select list must come from the allow-list constants")
                for column in self.FORBIDDEN_COLUMNS:
                    self.assertNotRegex(window, re.compile(r"\b%s\b" % column),
                                        f"{column} must never be requested")

    def test_the_ambiguous_foreign_key_is_named_explicitly(self):
        # posts.user_id carries TWO foreign keys to profiles, and PostgREST
        # refuses an ambiguous embed. The hint has to keep matching the real
        # constraint name, or every preview silently loses its author.
        self.assertEqual(self.constant("PROFILE_FK_HINT"), "fk_posts_user_id")
        self.assertIn("profiles!${PROFILE_FK_HINT}", self.fn)
        # ...and because a renamed constraint would break it, the plain query
        # has to remain as a fallback rather than the only path.
        self.assertIn("catch (embedError)", self.fn)

    # --- the Function's injection safety --------------------------------
    def test_every_value_written_into_the_html_is_escaped(self):
        for name in ("setMeta", "setTitle", "setText", "setAvatarImage"):
            with self.subTest(helper=name):
                self.assertIn("escapeHtml(", self.helper_body(name),
                              f"{name} writes database text into HTML; it must escape")

    def test_escaping_covers_the_attribute_breaking_characters(self):
        body = self.helper_body("escapeHtml")
        for char, entity in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"),
                             ('"', "&quot;"), ("'", "&#39;")):
            with self.subTest(char=char):
                self.assertIn(entity, body,
                              f"{char} must become {entity}: display names land in "
                              "element text, in attributes and in og: tags")
        # & first, or every later entity gets double-escaped.
        self.assertLess(body.index("&amp;"), body.index("&lt;"))

    def test_avatars_must_be_absolute_https_urls(self):
        body = self.helper_body("cleanImageUrl")
        self.assertIn("https:", body, "an http:// or javascript: avatar is refused")
        self.assertIn("2048", body, "an unbounded URL is a smuggled payload")

    def test_a_non_uuid_id_never_reaches_the_database(self):
        pattern = re.search(r"^const UUID_PATTERN = /([^;\n]+)/i;$", self.fn, re.MULTILINE)
        self.assertIsNotNone(pattern, "the id guard vanished")
        compiled = re.compile(pattern.group(1), re.IGNORECASE)
        self.assertTrue(compiled.pattern.startswith("^") and compiled.pattern.endswith("$"),
                        "the guard must be anchored, or a suffix of a UUID passes")
        self.assertTrue(compiled.match("a3a7d592-6a5e-4108-b102-3c5a9c2d40a0"))
        for bad in ("a3a7d592-6a5e-4108-b102-3c5a9c2d40a0 OR 1=1", "a8f3c2",
                    "../../etc/passwd", ""):
            with self.subTest(bad=bad):
                self.assertIsNone(compiled.match(bad))
        # ...and the guard has to hand back the static page, not an error.
        guard = self.fn.split("UUID_PATTERN.test", 1)[1][:220]
        self.assertIn("context.next()", guard)

    # --- the Function's failure behaviour -------------------------------
    def handler_body(self, name):
        match = re.search(r"export async function %s\(context\) \{([\s\S]*?)\n\}$" % name,
                          self.fn, re.MULTILINE)
        self.assertIsNotNone(match, f"functions/post/[id].js no longer exports {name}")
        return match.group(1)

    def test_no_failure_path_can_return_an_error_page(self):
        # A shared link that 500s is worse than a generic card. Every unhappy
        # outcome has to fall through to the static asset instead.
        #
        # Counted as real statements, not as the bare string: the header comment
        # also names context.next(), so counting that would let a fallback be
        # deleted while the total still looked right.
        statements = re.findall(r"^\s*.*return context\.next\(\);", self.fn, re.MULTILINE)
        statements = [line for line in statements if not line.strip().startswith("//")]
        self.assertEqual(len(statements), 2,
                         "expected next() for a non-UUID id and as the handler's "
                         f"final fall-through, got {statements}")

        handler = self.handler_body("onRequestGet")
        self.assertTrue(handler.rstrip().endswith("return context.next();"),
                        "the handler must END by falling through to the static "
                        "page, so an unexpected throw cannot become a 500")
        self.assertIn("try {", handler)
        self.assertIn("catch (error)", handler,
                      "buildResponse is awaited inside a try: a rendering bug "
                      "must degrade, not break the link")
        self.assertIn("console.error", handler)
        self.assertNotRegex(self.fn, r"status:\s*5\d\d")
        self.assertNotIn("onRequestPost", self.fn)

        head = self.handler_body("onRequestHead")
        self.assertIn("await onRequestGet(context)", head,
                      "HEAD must produce the same tags as GET, body aside")
        self.assertIn("new Response(null", head)

    def test_the_lookup_is_time_boxed_so_first_paint_cannot_hang(self):
        timeout = self.number_constant("SUPABASE_TIMEOUT_MS")
        self.assertLessEqual(timeout, 2000,
                             "this response blocks first paint; a slow Supabase "
                             "must cost the avatar, not the page")
        self.assertGreater(timeout, 0)
        body = self.helper_body("fetchPostAuthor")
        self.assertIn("AbortController", body)
        # Assert the live statement inside a real finally block: a bare
        # "clearTimeout" substring still passes when the call is disabled.
        settled = re.search(r"\} finally \{([\s\S]*?)\n  \}", body)
        self.assertIsNotNone(settled, "the abort timer must be cleared on every path")
        self.assertIn("if (timer) clearTimeout(timer);", settled.group(1),
                      "guarded only by whether a timer was created")
        self.assertIn("'unconfigured'", body,
                      "no credentials means serve the static page, not an error")

    def test_the_response_is_edge_cached_but_browser_revalidated(self):
        ttl = self.number_constant("EDGE_TTL_SECONDS")
        self.assertEqual(ttl, 300)
        self.assertIn("max-age=0", self.fn,
                      "a browser must re-ask, so a deleted post disappears")
        self.assertIn("s-maxage=${EDGE_TTL_SECONDS}", self.fn,
                      "the edge may hold it: scrapers hit this within seconds")
        self.assertIn("stale-while-revalidate", self.fn)

    def test_head_requests_are_answered_rather_than_rejected(self):
        self.assertIn("export async function onRequestHead", self.fn,
                      "a scraper probing HEAD must not get a 405")

    def test_the_landing_page_matches_the_rewrite_destination(self):
        self.assertEqual(self.constant("LANDING_PAGE"), "/shared-post.html")
        destinations = {rule[0]: rule[1] for rule in self.redirects}
        self.assertEqual(destinations["/post/:id"], self.constant("LANDING_PAGE"),
                         "the Function has to fetch the same file _redirects serves")

    def test_the_short_alias_delegates_rather_than_duplicates(self):
        alias_path = ROOT / "functions" / "p" / "[id].js"
        self.assertTrue(alias_path.is_file(),
                        "/p/<id> is a documented route; it needs a Function too")
        alias = alias_path.read_text()
        self.assertIn("export { onRequestGet, onRequestHead } from '../post/[id].js';",
                      alias, "the alias must delegate to the long route's handlers")
        # The point of delegating: a second copy of the lookup would drift, and
        # the two routes would start disagreeing about who posted.
        for marker in ("SUPABASE_TIMEOUT_MS", "fetchPostAuthor", "escapeHtml",
                       "POST_COLUMNS", "PROFILE_COLUMNS", "UUID_PATTERN"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, alias,
                                 f"{marker} redefined here would be a second, "
                                 "diverging implementation")
        # The alias is still a route in its own right, so when the Function
        # declines the static fall-through has to remain.
        destinations = {rule[0]: rule[1] for rule in self.redirects}
        self.assertEqual(destinations["/p/:id"], self.constant("LANDING_PAGE"))

    def test_og_url_is_canonical_so_an_alias_makes_one_preview_not_two(self):
        # Chat apps deduplicate previews by og:url. If /p/<id> advertised itself,
        # the same post shared both ways would render two different cards.
        body = self.helper_body("describePost")
        self.assertIn("`/post/${postId}`", body,
                      "og:url must name the canonical route, not the request path")
        self.assertNotIn("`/p/", body)

    def test_every_absolute_url_is_pinned_to_the_canonical_host(self):
        """agora.in.net, auth-agora.info and auth-agora.online all serve this
        same Pages project. Deriving og:url from the request therefore lets one
        post publish three different canonical URLs depending on which host the
        share link used -- and since chat apps key their preview cache on
        og:url, the same post renders as unrelated cards in one thread. So the
        Function must pin its own origin, not echo the request's."""
        self.assertEqual(self.constant("CANONICAL_ORIGIN"), f"https://{SITE_DOMAIN}")
        body = self.helper_body("canonicalUrl")
        self.assertIn("CANONICAL_ORIGIN", body,
                      "the helper must resolve against the pinned origin")
        self.assertNotIn("request", body, "and must not consult the request at all")
        described = self.helper_body("describePost")
        self.assertIn("canonicalUrl(", described,
                      "og:url and the fallback og:image both go through the pin")
        # Sharing a body with one canonicalUrl() call is not enough: a bare
        # FALLBACK_OG_IMAGE is root-relative, and a scraper resolves og:image
        # against nothing, so the preview silently loses its image.
        self.assertIn("canonicalUrl(FALLBACK_OG_IMAGE)", described,
                      "og:image must be absolute too")
        self.assertEqual(described.count("canonicalUrl("), 2,
                         "both emitted URLs go through the pin, and nothing else "
                         "in describePost should")
        self.assertNotRegex(described, r"(?<!canonicalUrl\()FALLBACK_OG_IMAGE",
                            "the fallback image must never be emitted bare")
        self.assertNotIn("absoluteUrl", self.fn,
                         "the request-origin helper is gone: leaving it in place "
                         "invites the next tag to be built from the wrong host")
        self.assertNotRegex(described, r"\brequest\b",
                            "describePost no longer needs the request")
        # The alias must not become a second canonical URL either.
        self.assertIn("url: canonicalUrl(`/post/${postId}`)", described)

    def test_the_og_fallback_image_exists(self):
        fallback = self.constant("FALLBACK_OG_IMAGE")
        self.assertTrue(fallback.startswith("/assets/"))
        self.assertTrue((ROOT / fallback.lstrip("/")).is_file(),
                        f"{fallback} is promised as og:image but is not in the repo")
        self.assertTrue(fallback.endswith(".jpg"),
                        "chat apps do not render an SVG og:image reliably")

    # --- what app.js is still allowed to do -----------------------------
    def test_app_js_never_renders_the_author(self):
        # The server owns the card. A client-side write would clobber the real
        # author with the generic fallback on every deep link.
        self.assertNotIn("data-author", self.app)
        self.assertNotIn("data-handle", self.app)
        self.assertNotIn("data-monogram", self.app)
        self.assertNotIn("data-first-name", self.app,
                         "the h1 is personalised server-side; a client write "
                         "would race it and lose")
        self.assertNotIn("api.agora.example", self.app, "the stub API host is gone")
        self.assertNotIn("renderPreview", self.app)
        self.assertNotIn("fetchPost", self.app)

    def test_app_js_only_trusts_an_avatar_that_really_painted(self):
        match = re.search(r"^  function initAvatarFallback\([\s\S]*?\n  \}$",
                          self.app, re.MULTILINE)
        self.assertIsNotNone(match, "the avatar load/error handler vanished")
        body = match.group(0)
        self.assertIn("addEventListener('load'", body)
        self.assertIn("addEventListener('error'", body)
        self.assertIn("naturalWidth", body,
                      "complete alone is not enough: a broken image reports it too")
        self.assertIn("getAttribute('src')", body,
                      "with no src there is nothing to settle and the initial stands")
        self.assertIn("initAvatarFallback(preview)", self.app,
                      "the handler has to be wired into the shared-post boot")

    def test_the_avatar_card_is_styled_and_cannot_escape_its_circle(self):
        for selector in (".post-preview__avatar", ".post-preview__avatar-img",
                         ".post-preview__monogram", ".post-preview__who",
                         ".post-preview__handle", ".post-preview__posted"):
            with self.subTest(selector=selector):
                self.assertIn(selector + " {", self.css,
                              f"{selector} is authored in shared-post.html but unstyled")
        frame = self.css.split(".post-preview__avatar {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: 50%", frame)
        self.assertIn("overflow: hidden", frame,
                      "a rectangular photo must be clipped to the circle")
        self.assertIn("flex: none", frame, "the avatar must not squash under a long name")
        image = self.css.split(".post-preview__avatar-img {", 1)[1].split("}", 1)[0]
        self.assertIn("object-fit: cover", image)
        who = self.css.split(".post-preview__who {", 1)[1].split("}", 1)[0]
        self.assertIn("min-width: 0", who,
                      "without it a long handle pushes the avatar out of the flex row")
        # The initial has to disappear once a real face is on top of it, or a
        # transparent avatar shows a letter through the member's photo.
        self.assertIn(".post-preview__avatar.has-avatar .post-preview__monogram", self.css)
        # Token-only: the light theme redefines these variables and nothing else.
        for block in (frame, image, who):
            self.assertNotRegex(block, r"#[0-9A-Fa-f]{3,8}\b",
                                "a literal colour here would not invert in light mode")
            self.assertNotRegex(block, r"\brgba?\(\s*\d", "same: use an --*-rgb token")

    def test_the_error_branch_still_hides_every_card_state(self):
        branch = self.app.split("if (resolved.status !== 'ok')", 1)[1] \
                     .split("var postId = resolved.id;", 1)[0]
        for element in ("emptyState", "resultState", "unavailableState", "openInAppRow"):
            with self.subTest(element=element):
                self.assertIn(element, branch,
                              f"{element} must be settled, or a bad link can leave "
                              "the previous render on screen")

def visible_text(html):
    """What a visitor can actually read: no tags, no attributes, no comments,
    no script or style bodies. Attributes are dropped on purpose -- the download
    button's href is allowed to name github.com (that is the mechanism), while
    the copy beside it is not."""
    text = re.sub(r"<!--[\s\S]*?-->", " ", html)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]*>", " ", text)
    # A visitor reads "&", not "&amp;" -- decode so assertions match the copy
    # as rendered rather than as escaped.
    return html_module.unescape(text)


SERVED_SUFFIXES = {".html", ".js", ".css", ".json", ".svg"}


class ReleaseStatusCopy(unittest.TestCase):
    """v1.0 shipped. The site must read as a released product, and must not
    name the place the APK is fetched from -- while still fetching it from
    there, because that is the resilient path the download depends on."""

    @classmethod
    def setUpClass(cls):
        cls.raw = {p.name: p.read_text() for p in ROOT.glob("*.html")}
        cls.download = cls.raw["download.html"]
        cls.app = (ROOT / "app.js").read_text()
        cls.readme = (ROOT / "README.md").read_text()

    # --- GitHub is infrastructure, not copy ------------------------------
    def test_no_page_names_github_in_visible_copy(self):
        for name, html in self.raw.items():
            with self.subTest(page=name):
                text = visible_text(html)
                self.assertNotIn("github", text.lower(),
                                 "visitors should not be told where the APK is "
                                 "hosted; the file should just download")

    def test_the_download_mechanism_survived_the_copy_change(self):
        """The counter-guard: "remove references to GitHub" must not be
        over-applied into removing the download itself. Exactly one element
        still carries GitHub's permanent release redirect, because that URL
        resolves to the newest release with no API call and no rate limit."""
        page = Page(ROOT / "download.html")
        carriers = [a for t, a in page.tags
                    if "releases/latest/download/app.apk" in (a.get("href") or "")]
        self.assertEqual(len(carriers), 1,
                         "one button downloads the file; if this is 0 the copy "
                         "sweep broke the download, if it is >1 every CTA "
                         "downloads instead of navigating")
        self.assertIn("dynamic-download-btn", carriers[0].get("class", ""))
        self.assertEqual(carriers[0].get("id"), "dynamic-download-btn")
        # The lookup chain still runs, so the button tracks the newest release.
        self.assertIn("api.github.com/repos/JayBhaskarCoding/agora-android/releases/latest", self.app)
        self.assertIn("/api/latest-release", self.app,
                      "the server-side proxy is still first in the chain")

    # --- released, not pre-launch ----------------------------------------
    def test_the_android_app_reads_as_shipped_not_pre_launch(self):
        stale = ["android beta", "ahead of launch", "prepared for launch",
                 "device capture coming soon", "no waitlist", "try the current agora"]
        for name, html in self.raw.items():
            text = visible_text(html).lower()
            for phrase in stale:
                with self.subTest(page=name, phrase=phrase):
                    self.assertNotIn(phrase, text,
                                     "v1.0 is released; this reads as pre-launch")

    def test_ios_and_desktop_are_still_honestly_marked_as_future(self):
        """The sweep must not delete a statement that is still true: there is
        no iOS or desktop client, and saying otherwise would be worse than the
        pre-launch wording it replaced."""
        for name in ("index.html", "download.html", "about.html"):
            with self.subTest(page=name):
                text = visible_text(self.raw[name])
                self.assertRegex(text, r"iOS\s*&\s*desktop\s*—\s*coming soon",
                                 "the footer must still say iOS/desktop are not out")

    def test_the_release_is_announced_where_a_visitor_decides(self):
        text = visible_text(self.download)
        self.assertIn("Now available on Android", text,
                      "the download page eyebrow is the first thing read")
        self.assertRegex(text, r"Agora is out for Android",
                         "and the lead must say the app exists")
        self.assertIn("out now", visible_text(self.raw["index.html"]),
                      "the footer status line should agree")

    def test_no_page_claims_ios_or_desktop_is_available(self):
        """The footers honestly say iOS and desktop are still coming. A body
        sentence claiming otherwise would contradict that inside the same
        viewport -- and would simply be false, which is worse than the
        pre-launch wording this sweep removed. So every sentence that names
        either platform has to frame it as future."""
        future = re.compile(r"coming soon|workbench|not yet|planned|on the way|in progress",
                            re.I)
        seen = 0
        for name, html in self.raw.items():
            for sentence in re.split(r"(?<=[.!?])\s+", visible_text(html)):
                sentence = " ".join(sentence.split())
                if not re.search(r"\biOS\b|\bdesktop\b", sentence):
                    continue
                seen += 1
                with self.subTest(page=name, sentence=sentence[:80]):
                    self.assertTrue(future.search(sentence),
                                    "names iOS/desktop without marking it as future")
        self.assertGreaterEqual(seen, 4,
                                "the three footers and the download caveat should "
                                "still be there; 0 means the splitter broke")

    # --- one identity, everywhere ----------------------------------------
    def test_no_superseded_identity_survives_in_served_files(self):
        """`net.in.agora` was the earlier pin and `auth-agora.*` are alias
        domains that all serve this same project. Neither may be emitted by
        anything the site serves: a stale package in the intent URI fails
        silently, and a stale host in a social tag splits one post into two
        preview cards."""
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts:
                continue
            if path.suffix not in SERVED_SUFFIXES and path.name not in {"_redirects", "_headers"}:
                continue
            try:
                body = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for stale in ("net.in.agora", "auth-agora", "com.example.agora"):
                if stale in body:
                    offenders.append(f"{path.relative_to(ROOT)}: {stale}")
        self.assertEqual(offenders, [], "superseded identity still served")

    def test_the_readme_verifies_the_package_that_actually_ships(self):
        """The README's adb commands are how this gets debugged on a device.
        Pointing them at a retired package makes the verification steps
        silently check nothing."""
        self.assertNotIn("net.in.agora", self.readme)
        self.assertIn(f"verify-app-links --re-verify {ANDROID_PACKAGE}", self.readme)
        self.assertIn(f"get-app-links {ANDROID_PACKAGE}", self.readme)
        self.assertIn(f"package={ANDROID_PACKAGE}", self.readme,
                      "the documented intent:// example must name the live package")


class CreditsRotaryGeometry(unittest.TestCase):
    """The credits screen is pure geometry, and geometry fails silently.

    A role sign hung from the wrong sector still renders, still swings, still
    highlights -- it just describes the wrong person. A detail block placed by
    its top-left corner still renders; it just runs off the viewport when the
    copy is a line longer than the layout assumed. Neither throws, so both are
    asserted here rather than left to a visual review.
    """

    SEGMENT = 120.0
    PAD = 24
    # Viewports the layout has to survive, desktop and narrow.
    DESKTOP = [(1920, 1080), (1600, 900), (1440, 900), (1366, 768), (1280, 800),
               (1024, 768), (900, 1200), (820, 1180)]
    MOBILE = [(390, 844), (414, 896), (360, 640), (375, 812), (768, 1024), (480, 800)]

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "style.css").read_text()
        cls.html = (ROOT / "credits.html").read_text()
        cls.app = (ROOT / "app.js").read_text()

    # --- helpers -------------------------------------------------------
    def block(self, selector, after=0):
        """The declaration body of the FIRST rule matching selector at/after
        `after`, so a mobile override can be read separately from the base."""
        start = self.css.index(selector, after)
        brace = self.css.index("{", start)
        end = self.css.index("}", brace)
        return self.css[brace + 1:end], end

    def decl(self, body, prop):
        match = re.search(r"(?:^|[;\s])" + re.escape(prop) + r":\s*([^;]+);", body)
        return match.group(1).strip() if match else None

    def pct(self, body, prop):
        value = self.decl(body, prop)
        self.assertIsNotNone(value, f"{prop} is not declared")
        return float(value.rstrip("%"))

    def mobile_offset(self):
        return self.css.index("@media (max-width: 768px)")

    def segment_angle(self, disc, index):
        body, _ = self.block(
            f'.rotary-disc--{disc} .rotary-segment[data-rotary-segment="{index}"]')
        return float(self.decl(body, "--segment-angle").rstrip("deg"))

    def sector_offset(self, disc):
        body, _ = self.block(f".rotary-disc--{disc} ")
        return float(self.decl(body, "--sector-offset").rstrip("deg"))

    def disc_rule(self, disc, mobile):
        selector = f".rotary-disc--{disc} {{"
        if mobile:
            try:
                body, _ = self.block(selector, self.mobile_offset())
                return body
            except ValueError:
                pass          # the narrow block may not override this wheel
        body, _ = self.block(selector)
        return body

    def disc_diameter(self, w, h, mobile):
        """--rotary-disc-size: min(<factor>vmin, <cap>px), read from the sheet.

        Hardcoding `min(140vmin, 1400px)` here would let the CSS resize the
        wheels and the assertions keep passing against the old numbers."""
        if mobile:
            try:
                body, _ = self.block(".rotary-disc {", self.mobile_offset())
            except ValueError:
                body, _ = self.block(".rotary-disc {")
        else:
            body, _ = self.block(".rotary-disc {")
        factor, cap = re.search(
            r"min\(\s*([\d.]+)vmin,\s*([\d.]+)px\s*\)",
            self.decl(body, "--rotary-disc-size")).groups()
        return min(min(w, h) * float(factor) / 100, float(cap))

    def hub(self, disc, w, h, mobile):
        """Where the wheel's centre actually lands, from its own CSS.

        Each disc is pinned flush to a viewport corner, so its untransformed
        centre is half a disc in from that corner; the `translate()` then moves
        it. The corner pinning is declared once on the base rule and inherited
        by the narrow-screen override, which only re-declares the translate --
        so the two have to be read from different rules.

        Reading the translate is what makes a hub nudged onto the wrong corner
        a test failure instead of a silent change in composition."""
        base = self.disc_rule(disc, False)
        d = self.disc_diameter(w, h, mobile)
        if disc == "top":
            self.assertEqual((self.decl(base, "top"), self.decl(base, "left")), ("0", "0"),
                             "the upper wheel must stay pinned to the top-left corner")
            centre_x, centre_y = d / 2, d / 2
        else:
            self.assertEqual((self.decl(base, "right"), self.decl(base, "bottom")), ("0", "0"),
                             "the lower wheel must stay pinned to the bottom-right corner")
            centre_x, centre_y = w - d / 2, h - d / 2

        body = self.disc_rule(disc, mobile)
        # decl() returns the VALUE only, so match the translate() itself.
        tx, ty = re.search(r"translate\(\s*([-\d.]+)%,\s*([-\d.]+)%\s*\)",
                           self.decl(body, "transform")).groups()
        return centre_x + float(tx) / 100 * d, centre_y + float(ty) / 100 * d

    # --- 1. the sector geometry -----------------------------------------
    def test_segment_angles_are_exactly_120_apart_and_match_the_active_sector(self):
        """The wheel settles one 120-degree step per member, so segment i must
        sit at sector_offset -/+ 120i (minus on the upper wheel, which turns the
        other way). Get this wrong and the snap lands between two contributors,
        or the emphasis fades in on the wrong one."""
        for disc, direction in (("top", -1), ("bottom", +1)):
            offset = self.sector_offset(disc)
            for i in range(3):
                with self.subTest(disc=disc, segment=i):
                    want = (offset + direction * self.SEGMENT * i) % 360
                    self.assertAlmostEqual(self.segment_angle(disc, i), want, places=2)

    def test_the_two_wheels_share_their_step_and_differ_only_by_direction(self):
        self.assertEqual(self.sector_offset("top"), 40.0)
        self.assertEqual(self.sector_offset("bottom"), 220.0)
        self.assertAlmostEqual((self.sector_offset("bottom") - self.sector_offset("top")) % 360,
                               180.0, places=2,
                               msg="the hubs are opposite corners, so the active "
                                   "sectors must be opposite too or the two "
                                   "detail blocks land on the same side")

    def test_app_js_reads_the_geometry_from_css_instead_of_duplicating_it(self):
        """The angles used to exist in four places: --segment-angle in the CSS,
        two hardcoded JS arrays, and two literal active-centre arguments. A
        drifted copy does not throw -- it just emphasises the wrong
        contributor."""
        for stale in ("TOP_SEGMENT_ANGLES = [", "BOTTOM_SEGMENT_ANGLES = [",
                      "topRotation, 40)", "bottomRotation, 220)"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.app,
                                 "the geometry must come from the stylesheet")
        self.assertIn("readAngleDegrees(segment, '--segment-angle')", self.app)
        self.assertIn("readAngleDegrees(topDisc, '--sector-offset')", self.app)
        self.assertIn("readAngleDegrees(bottomDisc, '--sector-offset')", self.app)
        gate = re.search(r"if \(anglesReadable\) \{([\s\S]*?)\n      \}", self.app)
        self.assertIsNotNone(gate,
                         "the emphasis calls must be gated on the read succeeding")
        for call in ("updateSegmentVisuals(topSegments, TOP_SEGMENT_ANGLES, "
                     "topRotation, TOP_ACTIVE_CENTER);",
                     "updateSegmentVisuals(bottomSegments, BOTTOM_SEGMENT_ANGLES, "
                     "bottomRotation, BOTTOM_ACTIVE_CENTER);"):
            self.assertIn(call, gate.group(1),
                          f"{call} escaped the guard")
        self.assertIn("var anglesReadable = TOP_ACTIVE_CENTER !== null\n"
                      "      && BOTTOM_ACTIVE_CENTER !== null", self.app,
                      "the guard must actually test the values it reads")

    # --- 2. role signs belong to their own sector ------------------------
    def test_each_role_sign_lives_inside_its_own_segment(self):
        """The structural fix. Two of the three signs used to be authored a full
        120 degrees away from the sector they described. Hanging each sign from
        its own segment makes that impossible: it inherits --segment-angle."""
        for i in range(3):
            article = re.search(
                r'<article[^>]*data-rotary-segment="%d"[^>]*>([\s\S]*?)</article>' % i,
                self.html)
            self.assertIsNotNone(article, f"segment {i} vanished")
            self.assertIn(f'data-rotary-tag="{i}"', article.group(1),
                          f"the role sign for index {i} is not inside segment {i}")
            for other in range(3):
                if other != i:
                    self.assertNotIn(f'data-rotary-tag="{other}"', article.group(1),
                                     "a sign crossed over into another sector")
        self.assertNotIn("rotary-tag-track", self.html,
                         "the sibling track that let them drift is gone")
        self.assertNotIn("rotary-tag-track", self.css, "and so is its dead rule")

    def test_no_per_index_hanger_coordinates_survive(self):
        """Hand-authored top/left per sign is the bug class, not just the bug."""
        self.assertNotRegex(self.css, r"\.rotary-sign-hanger\[data-rotary-tag=")
        body, _ = self.block(".rotary-sign-hanger {")
        self.assertEqual(self.decl(body, "top"), "50%")
        # The sign hangs out along its sector's own 0-degree axis, so a single
        # `left` is the whole orbit radius.
        self.assertAlmostEqual(self.pct(body, "left") - 50, 49.7, delta=0.2,
                               msg="base orbit radius moved off the rim the one "
                                   "correctly-placed sign already used")
        mobile, _ = self.block(".rotary-sign-hanger {", self.mobile_offset())
        self.assertAlmostEqual(self.pct(mobile, "left") - 50, 41.2, delta=0.2)

    def test_the_sign_counter_rotates_both_ancestors(self):
        """It sits inside a rotated segment inside a rotated plate. Subtracting
        only the plate leaves it tilted by its own sector angle."""
        body, _ = self.block(".rotary-sign-hanger {")
        transform = self.decl(body, "transform")
        self.assertIn("--segment-angle", transform)
        self.assertIn("--disc-rotation", transform)
        self.assertIn("--tag-swing-angle", transform, "the pendulum swing must survive")
        self.assertEqual(self.decl(body, "transform-origin"), "50% 0",
                         "the pivot is the cord, not the sign's centre")

    # --- 3. detail blocks are centre-anchored ---------------------------
    def test_detail_blocks_are_centre_anchored_not_corner_hung(self):
        """A corner-hung block lands wherever its own height puts it, so one
        extra line of bio shoves the whole block into the status bar. Centring
        it makes the landing point a function of two numbers only."""
        body, _ = self.block(".rotary-segment__content {")
        transform = self.decl(body, "transform")
        self.assertTrue(transform.startswith("translate(-50%, -50%)"),
                        f"the centring translate must come first, got: {transform}")
        self.assertIn("--segment-angle", transform)
        self.assertIn("--disc-rotation", transform)
        self.assertEqual(self.decl(body, "transform-origin"), "center")

    def test_both_wheels_share_one_detail_block_offset(self):
        """The only thing that should separate the two blocks is the wheel's own
        --sector-offset. Two independently tuned offsets is how they ended up on
        the same side of the screen."""
        base, _ = self.block(".rotary-segment__content {")
        for modifier in (".rotary-segment__content--contribution {",
                         ".rotary-segment__content--profile {"):
            body, _ = self.block(modifier)
            self.assertIsNone(self.decl(body, "top"), f"{modifier} re-tunes top")
            self.assertIsNone(self.decl(body, "left"), f"{modifier} re-tunes left")
        self.assertEqual((self.pct(base, "left"), self.pct(base, "top")), (88.0, 48.0))

    def test_segments_no_longer_clip_their_content(self):
        """The upper wheel clipped its sectors to a 120-degree wedge, which cut
        the contribution copy on every narrow viewport (its corners reach 64-78
        degrees against a 60-degree limit) and would have cut the rim-mounted
        sign too."""
        body, _ = self.block(".rotary-segment {")
        self.assertNotIn("clip-path", body)
        self.assertNotIn("overflow: hidden", body)
        self.assertNotIn(".rotary-disc--bottom .rotary-segment {", self.css,
                         "the bottom wheel's clip-cancel override is now redundant")

    def test_the_sector_lines_do_not_paint_over_the_copy(self):
        lines, _ = self.block(".rotary-disc__sector-track::before {")
        content, _ = self.block(".rotary-segment__content {")
        self.assertLess(int(self.decl(lines, "z-index")), int(self.decl(content, "z-index")),
                        "decorative radial lines were drawing across the text")

    # --- 4. the solved placement, re-derived -----------------------------
    def _metrics(self, w, h, d, mobile):
        """Block sizes modelled from the authored clamp() chains, with the text
        heights rounded UP so a passing assertion still has margin."""
        if mobile:
            cw = min(168, 0.32 * w)
            ch = math.ceil(152 / max(1, cw / 5.4)) * 17.6 + 8
            pw = min(168, 0.32 * w)
            ph = max(70, min(0.15 * d, 100)) + 12 + math.ceil(96 / max(1, pw / 5.2)) * 16.0
        else:
            cw = min(480, 0.37 * d)
            fs = max(15.2, min(0.018 * d, 21.6))
            ch = math.ceil(152 / max(1, cw / (fs * 0.505))) * fs * 1.65 + 8
            pw = min(336, 0.30 * d)
            bfs = max(13.1, min(0.012 * d, 16.8))
            ph = (max(110, min(0.14 * d, 210)) + min(24, max(14.4, 0.015 * d))
                  + math.ceil(96 / max(1, pw / (bfs * 0.505))) * bfs * 1.55)
        return (cw, ch), (pw, ph)

    def _landing(self, w, h, mobile, which, left, top, bw, bh):
        d = self.disc_diameter(w, h, mobile)
        hub_x, hub_y = self.hub(which, w, h, mobile)
        hub = (hub_x, hub_y)
        sector = math.radians(self.sector_offset(which))
        vx, vy = (left - 50) / 100 * d, (top - 50) / 100 * d
        cx = hub[0] + vx * math.cos(sector) - vy * math.sin(sector)
        cy = hub[1] + vx * math.sin(sector) + vy * math.cos(sector)
        return cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2

    def test_detail_blocks_land_inside_the_safe_area_on_every_viewport(self):
        """The whole point of solving for the offsets instead of eyeballing them.
        Recomputes each block's landing box from the CSS actually on disk and
        fails if it reaches past an edge, under the header, or into the status
        bar. Before the fix this failed on 8 of 9 viewports."""
        base, _ = self.block(".rotary-segment__content {")
        mobile, _ = self.block(".rotary-segment__content {", self.mobile_offset())
        cases = [(w, h, False, self.pct(base, "left"), self.pct(base, "top"), 68, 76)
                 for w, h in self.DESKTOP]
        cases += [(w, h, True, self.pct(mobile, "left"), self.pct(mobile, "top"), 58, 100)
                  for w, h in self.MOBILE]
        for w, h, mob, left, top, header, status in cases:
            d = self.disc_diameter(w, h, mob)
            (cw, chh), (pw, phh) = self._metrics(w, h, d, mob)
            for which, bw, bh in (("top", cw, chh), ("bottom", pw, phh)):
                x0, y0, x1, y1 = self._landing(w, h, mob, which, left, top, bw, bh)
                with self.subTest(viewport=f"{w}x{h}", mobile=mob, block=which):
                    self.assertGreaterEqual(x0, self.PAD, "runs off the left edge")
                    self.assertLessEqual(x1, w - self.PAD, "runs off the right edge")
                    self.assertGreaterEqual(y0, header + 10, "collides with the header")
                    self.assertLessEqual(y1, h - status - 10, "collides with the status bar")

    def test_the_two_blocks_occupy_opposite_zones(self):
        """Descriptions belong to the upper-left hub, photo and bio to the
        lower-right. If both landed on the same side the composition would read
        as one crowded corner."""
        base, _ = self.block(".rotary-segment__content {")
        w, h = 1440, 900
        d = self.disc_diameter(w, h, False)
        (cw, chh), (pw, phh) = self._metrics(w, h, d, False)
        tx, ty, _, _ = self._landing(w, h, False, "top", self.pct(base, "left"),
                                     self.pct(base, "top"), cw, chh)
        bx, by, _, _ = self._landing(w, h, False, "bottom", self.pct(base, "left"),
                                     self.pct(base, "top"), pw, phh)
        self.assertLess(tx + cw / 2, w / 2, "the description block is not upper-left")
        self.assertLess(ty + chh / 2, h / 2, "the description block is not upper-left")
        self.assertGreater(bx + pw / 2, w / 2, "the profile block is not lower-right")
        self.assertGreater(by + phh / 2, h / 2, "the profile block is not lower-right")


class CreditsWaveMatrix(unittest.TestCase):
    """The credits screen's one animated background layer."""

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "style.css").read_text()
        cls.app = (ROOT / "app.js").read_text()
        cls.body = cls.app.split("function initWaveMatrix()", 1)[1].split("\n  function bootPage", 1)[0]

    def test_the_static_texture_it_replaces_is_gone(self):
        self.assertNotIn(".credits-rotary-page::before", self.css,
                         "two grids on one page is exactly the noise this replaced")
        self.assertIn(".credits-wave-matrix {", self.css)
        body = self.css.split(".credits-wave-matrix {", 1)[1].split("}", 1)[0]
        self.assertIn("position: fixed", body)
        self.assertIn("pointer-events: none", body, "it must never eat a wheel event")
        self.assertNotIn("pointer-events: auto", body,
                         "an earlier `auto` in the same block wins the cascade")
        self.assertLessEqual(int(re.search(r"z-index:\s*(\d+)", body).group(1)), 0,
                             "it has to sit under main.credits-rotary (z-index 1)")

    def test_it_only_exists_on_the_credits_screen(self):
        self.assertIn("doc.body.classList.contains('credits-rotary-page')", self.body)
        boot = self.app.split("function bootPage()", 1)[1].split("\n  }", 1)[0]
        calls = [line.strip() for line in boot.split("\n")
                 if "initWaveMatrix();" in line]
        self.assertEqual(len(calls), 1,
                         f"expected exactly one live call, got {calls}")
        self.assertFalse(calls[0].startswith("//"),
                         "the call is commented out; counting a substring "
                         "counts a comment")

    def test_it_is_torn_down_when_the_page_is_left(self):
        """A fixed full-viewport canvas that survives the swap would paint over
        every other page."""
        self.assertIn("waveMatrixCleanup()", self.body)
        self.assertIn("removeEventListener('resize'", self.body)
        self.assertIn("removeChild(canvas)", self.body)
        self.assertIn("canvas.isConnected", self.body,
                      "the draw loop must stop itself once detached")
        self.assertIn("if (waveMatrixCleanup) return;", self.body,
                      "and must not stack a second canvas on a re-run")

    def test_it_follows_the_theme_instead_of_hardcoding_colour(self):
        self.assertIn("getPropertyValue('--violet-soft-rgb')", self.body)
        self.assertIn("getPropertyValue('--blue-rgb')", self.body)
        self.assertIn("prefers-color-scheme: light", self.body,
                      "a mid-session scheme flip has to re-read the palette")
        # Assert on the PAINT CALL SITES. The regex has to exclude the helper's
        # own declaration -- `function stroke(points, color, alpha)` matches the
        # same shape as a call and its `color` parameter is not a channel.
        declaration = "function stroke(points, color, alpha) {"
        self.assertIn(declaration, self.body)
        call_body = self.body.replace(declaration, "")
        callsites = re.findall(r"stroke\(points,\s*([^,]+),", call_body)
        self.assertEqual(len(callsites), 2,
                         f"expected a row pass and a column pass, got {callsites}")
        for expression in callsites:
            self.assertIn("palette.", expression,
                          f"painted with {expression!r}, not a theme channel")
        self.assertIn("context.strokeStyle = 'rgba(' + color + ','", self.body,
                      "the helper must build its colour from the channel it is given")

    def test_it_stays_subtle_enough_to_read_through(self):
        alphas = [float(a) for a in re.findall(r"(0\.\d+) \+ \((?:drift|cross) \* (0\.\d+)\)", self.body)
                  for a in a]
        self.assertTrue(alphas, "no alpha ramps found; the parser is stale")
        self.assertLessEqual(max(alphas), 0.09,
                             "the mesh must sit behind the copy, not compete with it")

    def test_reduced_motion_gets_one_frame_and_no_loop(self):
        self.assertIn("if (!reduceMotion()) window.requestAnimationFrame(draw);", self.body,
                      "the loop must be gated on reduced motion")
        self.assertIn("if (reduceMotion()) {", self.body,
                      "and a paused canvas still needs one frame on a scheme change")

    def test_the_buffer_is_capped_like_the_other_canvas(self):
        self.assertIn("Math.min(window.devicePixelRatio || 1, 1.75)", self.body)
        self.assertIn("context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)", self.body)
        self.assertIn("addEventListener('resize', resize", self.body)
