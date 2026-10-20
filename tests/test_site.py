"""Dependency-free launch structure checks. Run with npm test."""
from collections import Counter
from html.parser import HTMLParser
import json
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
ANDROID_PACKAGE = "net.in.agora"
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

    def test_package_name_matches_the_site_domain(self):
        """Catches a transposed or typo'd applicationId: the package is the
        site domain reversed, and that domain is the one used for contact
        links throughout the repo."""
        self.assertEqual(".".join(reversed(ANDROID_PACKAGE.split("."))), SITE_DOMAIN)
        self.assertIn(f"mail@{SITE_DOMAIN}", (ROOT / "app.js").read_text())

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
        for element in ("emptyState", "resultState", "unavailableState", "actionsState"):
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

    def test_intent_row_is_authored_hidden_and_user_agent_gated(self):
        """intent:// is Chromium-on-Android only. Gecko ignores it, so the row
        must stay hidden there -- and its authored href must never be dead."""
        self.assertRegex(self.html, r'id="preview-actions"[^>]*hidden')
        link = re.search(r"<a[^>]*data-open-in-app[^>]*>", self.html)
        self.assertIsNotNone(link, "the Open in the app link disappeared")
        self.assertIn(f'href="{DOWNLOAD_PAGE}"', link.group(0),
                      "pre-JS the link must still lead somewhere useful")
        gate = self.section("function supportsIntentUrls", "function buildAppIntentUrl")
        self.assertIn("android", gate)
        self.assertIn("firefox", gate, "Gecko does not implement intent://")
        self.assertIn("return false", gate)


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
             "data-avatar-frame")
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
        for element in ("emptyState", "resultState", "unavailableState", "actionsState"):
            with self.subTest(element=element):
                self.assertIn(element, branch,
                              f"{element} must be settled, or a bad link can leave "
                              "the previous render on screen")
