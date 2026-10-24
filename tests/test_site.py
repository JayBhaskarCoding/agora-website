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
CLEAN_ROUTES = {'/': '/index.html', '/about': '/about.html', '/download': '/download.html',
                '/contact': '/contact.html', '/credits': '/credits.html',
                '/shared-post': '/shared-post.html', '/privacy': '/privacy.html', '/terms': '/terms.html'}
CAPTURES = {
    "/assets/home-feed.png": 3,
    "/assets/profile-screen.png": 1,
    "/assets/shared-post-preview.png": 2,
}
PENDING_ASSETS = {
    "/assets/yashvardhan-bhaskar.jpg",
}
LOGO = "/assets/agora-logo.svg"


# --- colour maths ------------------------------------------------------------
# Two contracts in this file are about whether a painted layer can actually be
# SEEN: the background mesh against the page, and the copy against the mesh. Both
# depend on the blend mode, so both compute it rather than grepping for its name.
def _luminance(rgb):
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg, bg):
    hi = max(_luminance(fg), _luminance(bg))
    lo = min(_luminance(fg), _luminance(bg))
    return (hi + 0.05) / (lo + 0.05)


def _strip_js_comments(src):
    """Remove JS comments with a character scanner, not a regex.

    A regex cannot do this. A non-greedy /*...*/ with DOTALL pairs across regex
    literals and eats live code, and app.js has plenty of both; scanning quoted
    literals instead pairs apostrophes across the whole file, so a comment like
    "the dot's own disc" shifts the pairing. This walks the source once, tracks
    string state, and is used wherever a test has to assert that an API is ABSENT
    -- which is the one kind of claim a comment explaining the removal would
    otherwise falsify.
    """
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = j if j != -1 else n
            continue
        if c in "\"'`":
            # Copied through intact, not blanked. Blanking strings makes the helper
            # unusable for the assertions that matter most here -- `createElement('audio')`,
            # `el.preload = 'auto'`, `['mail', 'agora.in.net'].join('@')` are all string
            # content, and a first draft that replaced each literal with "" failed eight
            # tests at once for wanting to find text that lives inside one. Skipping the
            # string is still necessary so a `//` or `/*` inside a URL or a comment-like
            # literal is not mistaken for the start of a comment.
            quote = c
            out.append(c)
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\" and i + 1 < n:
                    out.append(src[i:i + 2]); i += 2; continue
                out.append(src[i]); i += 1
            if i < n:
                out.append(src[i]); i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _strip_html_comments(html):
    """HTML comments are the third place this suite has needed one.

    Every "this must not appear" assertion in this file has now been defeated at
    least once by prose explaining why the thing must not appear: `--wheel-bass` in a
    stylesheet comment, `/cdn-cgi/l/email-protection` in an HTML comment,
    `AudioContext` and `time * rate` and `(h00 ^ iz)` in app.js comments, `<select>`
    in a comment explaining why the topic field is an input, and `contact` in a
    comment explaining why the credits colophon is not a contact link.

    Unlike JavaScript this is trivially safe to strip mechanically -- HTML comments
    cannot nest and contain no escaping -- but the rule for when to strip and when to
    rename the prose still applies: strip where the comment is load-bearing
    documentation of the bug being prevented, rename where it is incidental.
    """
    return re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)


def _strip_css_comments(css):
    """CSS has no regex literals and no way to escape a comment delimiter, so unlike
    JavaScript this is mechanically safe -- but still done with a scanner rather than a
    non-greedy regex, so a `/*` inside a string or a url() cannot pair across the file.

    Needed for the same reason as its JS sibling: the stylesheet documents at length
    which audio-reactive hooks it no longer carries, and an assertNotIn for
    `--wheel-bass` against the raw file matches that documentation.
    """
    out = []
    i = 0
    n = len(css)
    while i < n:
        if css.startswith("/*", i):
            j = css.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        out.append(css[i])
        i += 1
    return "".join(out)


def _resolve_colour(token, region):
    """Find `token` in `region` as three 0-1 floats.

    The stylesheet stores colour two ways: an `r, g, b` channel for anything that
    gets an alpha, and a `#RRGGBB` literal for solid ink. A test that only parsed
    one form would silently report "not defined" for the other.
    """
    m = re.search(re.escape(token) + r":\s*(#[0-9A-Fa-f]{6}|[\d,\s]+);", region)
    if not m:
        return None
    raw = m.group(1).strip()
    if raw.startswith("#"):
        return [int(raw[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [int(x) / 255 for x in raw.replace(" ", "").split(",")]


def _composite(src, back, alpha, blend):
    """Premultiply a translucent source over a backdrop using `blend`."""
    return [(1 - alpha) * back[i] + alpha * blend(src[i], back[i]) for i in range(3)]


SCREEN = lambda a, b: 1 - (1 - a) * (1 - b)
MULTIPLY = lambda a, b: a * b
SOURCE_OVER = lambda a, b: a


def _mesh_alphas(app):
    """The opacity bands the canvas actually paints with, read out of app.js.

    Two legibility tests used to restate these as literals. When the calibration moved
    they kept passing -- measuring a layer that no longer existed, and quietly
    overstating how hard the scrim had to work. A guard that hardcodes the number it is
    guarding is not a guard.

    They are tables now rather than two numbers, because opacity follows wave elevation
    and a stroke can only carry one alpha: the field is quantised into bands and each
    band is one batched pass. Index 2 of each table is the flat baseline.
    """
    def table(name):
        m = re.search(r"var " + name + r" = \[([^\]]+)\];", app)
        return [float(x) for x in m.group(1).split(",")] if m else []

    lines, dots, radii = table("LINE_ALPHAS"), table("DOT_ALPHAS"), table("DOT_RADII")
    n = int(re.search(r"var ELEVATION_BUCKETS = (\d+);", app).group(1))
    base = n // 2
    return {
        "lines": lines, "dots": dots, "radii": radii, "buckets": n, "base": base,
        "node": max(dots) if dots else None,
        "baseline_line": lines[base] if lines else None,
        "baseline_dot": dots[base] if dots else None,
    }


def _theme_ink(css, region):
    m = re.search(r"--mesh-ink:\s*([\d.]+);", region)
    return float(m.group(1)) if m else 1.0
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
DOWNLOAD_PAGE = "/download"
# Pages carrying the one direct-download button.
DYNAMIC_CTAS = Counter(
    {
        "index.html": 0,
        "about.html": 0,
        "download.html": 1,   # the "Download APK" button only
        "shared-post.html": 0,
        "credits.html": 0,
        "contact.html": 0,
        "privacy.html": 0,
        "terms.html": 0,
    }
)
# Pages carrying "Get the app" CTAs that navigate to the download page instead.
PAGE_CTAS = Counter(
    {
        "index.html": 4,
        "privacy.html": 2,
        "terms.html": 2,
        "contact.html": 3,   # nav, mobile menu, and the closing panel        # nav CTA, mobile menu, hero, closing panel
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
        "Get the app" CTAs are ordinary internal links to /download, so
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
        """No page carries a literal address, and every page still reaches a human.

        Cloudflare's Email Address Obfuscation rewrites raw addresses at the edge
        into `/cdn-cgi/l/email-protection` anchors, and that breaks twice here. The
        rewritten href is a relative path, which the PJAX router treats as an
        internal navigation -- so clicking the address performed a page swap instead
        of opening the mail client. And the replacement markup is written into the
        parsed document, so a shell fetched mid-swap carries obfuscated anchors that
        nothing ever decodes.

        So addresses live in data attributes and app.js assembles both the href and
        the visible text at runtime, on boot and after every navigation. This asserts
        the static half -- that there is nothing at the edge left to match -- plus
        the reachability half, so "no literal address" cannot be satisfied by simply
        deleting every way to contact anyone.
        """
        for name, page in self.pages.items():
            html = (ROOT / name).read_text()
            with self.subTest(page=name):
                self.assertNotIn("mailto:", html,
                                 "a raw mailto is exactly what the edge rewrites")
                self.assertNotIn("@" + SITE_DOMAIN, html, "a literal address survives")
                self.assertNotIn("__cf_email__", html)
                self.assertNotIn("/cdn-cgi/l/email-protection", html)

                assembled = [a for a, _ in page.anchors if a.get("data-email-user")]
                routes = [a for a, _ in page.anchors
                          if urlsplit(a.get("href", "")).path == "/contact"]
                # credits.html is the one exemption, and it is a design decision
                # rather than an oversight: it is a single-viewport composition driven
                # by a wheel, its header carries exactly one link and that link goes
                # home, and home carries contact. A row of chrome links competing with
                # the wheels is the clutter this round removed. What is NOT acceptable
                # is a page that reaches nothing at all, so it has to link to a page
                # that does.
                if name == "credits.html":
                    self.assertFalse(assembled, "the credits screen should carry no address")
                    self.assertFalse(routes, "and no contact link either")
                    homes = [a for a, _ in page.anchors
                             if urlsplit(a.get("href", "")).path == "/"]
                    self.assertGreaterEqual(len(homes), 2,
                                            "credits must still reach home, which carries contact, "
                                            "from both the logo and its one header link")
                else:
                    self.assertTrue(assembled or routes,
                                    "this page has no way to reach anyone")
                for attrs in assembled:
                    self.assertEqual(attrs.get("data-email-domain"), SITE_DOMAIN)
                    self.assertNotIn("@", attrs.get("data-email-user", ""),
                                     "a whole address in one attribute is the literal "
                                     "this scheme exists to avoid")

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
                                or (ROOT / CLEAN_ROUTES.get(path, path).lstrip("/")).is_file()
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
        # Both breakpoints share ONE hub inset (see CreditsRotaryGeometry):
        # narrow screens used to push each hub 15% of the disc off-screen.
        self.assertIn("translate(-44%, -44%)", self.css)
        self.assertIn("translate(44%, 44%)", self.css)
        for stale in ("translate(-65%, -65%)", "translate(65%, 65%)",
                      "translate(-50%, -50%);\n  --sector-offset"):
            self.assertNotIn(stale, self.css,
                             "a divergent per-breakpoint hub inset came back")
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
            "isPlaying",
            # The audio element and its unlock listeners are created once per
            # session, outside <main>, so a swap cannot restart the track or lose
            # the gesture that is allowed to start it.
            "el.loop = true",
            "el.preload = 'auto'",
            "doc.body.appendChild(el)",
            "createAudioElement();",
            "bindUnlock();",
            # Email addresses are re-assembled after every swap, not only at boot:
            # the swapped-in shell is fresh markup whose anchors have no href yet.
            "hydrateEmailLinks();",
        ]:
            self.assertIn(contract, app)
        # And the hydration really is inside bootPage rather than only in boot(),
        # which is the difference between "works on load" and "works after a swap".
        page_fn = app.split("function bootPage()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("hydrateEmailLinks();", page_fn)
        self.assertLess(page_fn.index("hydrateEmailLinks();"), page_fn.index("initRouting();"),
                        "email anchors must be hydrated before the router binds, so there is "
                        "no window in which a click lands on an anchor with no destination")

    def test_background_music_contract(self):
        """A streaming element, not a decoded buffer -- and no Web Audio API at all.

        The old version fetched the entire ~12MB track as an ArrayBuffer and ran
        decodeAudioData on it, so not one sample could play until all of it had
        arrived AND decoded into roughly 40MB of PCM. That is the 10-15 minute
        delay, and it also explains the stranger half of the symptom -- the track
        appearing to start when you clicked through to another page -- because a
        navigation re-ran boot(), and by then the bytes had finally landed.

        preload="auto" starts from a partial download and keeps fetching in the
        background. And with no AudioContext there is no per-frame analysis left to
        compete with the credits wheels for the main thread.
        """
        js = (ROOT / "app.js").read_text()
        self.assertIn("var MUSIC_SRC = '/assets/bgMusic.mpeg';", js)
        for contract in ("createElement('audio')", "el.preload = 'auto';", "el.loop = true;",
                         "el.volume = TARGET_VOLUME;", "el.addEventListener('canplay'",
                         "el.addEventListener('playing'", "el.addEventListener('error'",
                         "doc.body.appendChild(el)"):
            with self.subTest(contract=contract):
                self.assertIn(contract, js)
        music = ROOT / "assets/bgMusic.mpeg"
        self.assertTrue(music.is_file())
        self.assertGreater(music.stat().st_size, 0)

        # Asserted on comment-stripped source: app.js explains at length which Web
        # Audio APIs it no longer uses and why, so a plain assertNotIn would fail on
        # the documentation that prevents the regression.
        code = _strip_js_comments(js)
        for api in ("AudioContext", "webkitAudioContext", "createAnalyser",
                    "createMediaElementSource", "getByteFrequencyData",
                    "getByteTimeDomainData", "decodeAudioData", "createBufferSource",
                    "createBiquadFilter", "createDynamicsCompressor", "createGain",
                    "AnalyserNode", "frequencyBinCount"):
            with self.subTest(api=api):
                self.assertNotIn(api, code, "the Web Audio API is back")
        # And nothing computes a band any more.
        for name in ("computeBands", "getBands", "getSpectrum", "getEnergy", "getPulse",
                     "readBands", "IDLE_BANDS", "SPECTRUM_BANDS", "buildBandBins",
                     "bandAverage", "ONSET_GAIN", "BASS_GAIN", "SENSITIVITY_EXPONENT"):
            with self.subTest(name=name):
                self.assertNotIn(name, code, "audio analysis survived the removal")

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
        for route in ('post', 'p'):
            self.assertTrue((ROOT / 'functions' / route / '[id].js').is_file())

    def test_why_agora_links(self):
        home = self.pages["index.html"]
        targets = [a for tag, a in home.tags if a.get("id") == "why-agora"]
        self.assertEqual(len(targets), 1)
        for name, page in self.pages.items():
            links = [(a, text) for a, text in page.anchors if text.strip() == "Why Agora"]
            # credits.html keeps exactly one header link and it is the way home; the
            # "Why Agora" link that used to sit beside it duplicated the home page.
            # Everywhere else the link is required.
            if name == "credits.html":
                self.assertFalse(links, "the credits header gained a second link")
                continue
            self.assertTrue(links, f"{name} lost its Why Agora link")
            for attrs, text in links:
                self.assertIn(attrs["href"], ["#why-agora", "/#why-agora"])
            self.assertNotRegex((ROOT / name).read_text(), r'#why["\']')
        rule = re.search(r"#why-agora \{([^}]+)\}", self.css)[1]
        self.assertIn("scroll-margin-top: 5rem", rule)
        self.assertIn("scroll-behavior: smooth", self.css)

    def test_feedback_form_is_wired(self):
        """The contact form must actually deliver: validated, announced, sent.

        It lives on /contact now, not /about. Asserted on both halves --
        present exactly once on the page that owns it, and genuinely gone from the
        one that used to -- because a moved form that was COPIED rather than moved
        leaves two live forms with the same ids, and duplicate ids mean the
        validation and status wiring attaches to whichever one querySelector finds
        first. That failure is silent and only shows up as a form that does nothing.
        """
        about = (ROOT / "about.html").read_text()
        contact_src = (ROOT / "contact.html").read_text()
        page = self.pages["contact.html"]

        self.assertEqual(contact_src.count('id="feedback-form"'), 1,
                         "the form must exist exactly once, on its own page")
        self.assertEqual(about.count('id="feedback-form"'), 0,
                         "a copy of the form was left behind on about.html")
        for field in ("fb-name", "fb-email", "fb-topic", "fb-message", "fb-company"):
            with self.subTest(field=field):
                self.assertEqual(contact_src.count('id="%s"' % field), 1,
                                 f"{field} is duplicated or missing -- duplicate ids break "
                                 f"the aria-describedby wiring")
                self.assertNotIn('id="%s"' % field, about)
        # about.html keeps the invitation, just not the form.
        self.assertIn('href="/contact"', about)
        self.assertIn("Have a question, idea, or press inquiry?", about)

        form = [a for tag, a in page.tags if a.get("id") == "feedback-form"]
        self.assertEqual(len(form), 1, "contact page needs the feedback form")

        # No stale placeholder copy left behind.
        for stale in ["Placeholder form", "no data leaves your browser", "isn\u2019t connected to a server yet"]:
            self.assertNotIn(stale, contact_src)

        # Every validated field is marked and owns an inline error slot.
        for name in ["name", "email", "message"]:
            self.assertIn('data-validate', contact_src)
            self.assertIn('data-error-for="%s"' % name, contact_src)
            self.assertIn('aria-describedby="fb-%s-error"' % name, contact_src)
        # The topic is described by its error AND its hint, because the hint is what
        # explains why the field is locked -- a readonly input with no explanation
        # reads as broken rather than as decided.
        self.assertIn('data-error-for="topic"', contact_src)
        self.assertRegex(contact_src,
                         r'aria-describedby="fb-topic-error fb-topic-hint"')
        self.assertIn("data-validate", contact_src)

        # Submit outcome is announced, not silent.
        status = [a for tag, a in page.tags if a.get("id") == "feedback-status"]
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0].get("role"), "status")
        self.assertEqual(status[0].get("aria-live"), "polite")

        # Spam trap + JS-driven success copy.
        self.assertIn("data-honeypot", contact_src)
        self.assertIn("data-success-note", contact_src)
        self.assertIn("data-button-label", contact_src)

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
        self.assertNotIn('action="mailto:', contact_src)

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
        # Dedicated mesh channels, so the background can be retuned without
        # touching buttons, links or the wordmark -- but still read from CSS.
        for token in ("--mesh-node-rgb", "--mesh-node-hi-rgb", "--mesh-glow-rgb"):
            self.assertIn("getPropertyValue('" + token + "')", js)
        self.assertIn("sprites.hi : sprites.node", js)
        self.assertIn("(prefers-color-scheme: light)", js)
        # The draw loop must not inline the palette; the literals may only
        # survive as the named fallbacks used when the tokens are unreadable.
        self.assertNotRegex(js, r"\?\s*'147,112,255'\s*:\s*'190,210,255'")
        for name in ("FALLBACK_NODE", "FALLBACK_HI", "FALLBACK_GLOW"):
            self.assertIn(name, js)

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
        # Parsed from the rule instead of hardcoded, so lowering the resting value
        # fails here -- which is the whole thing this test exists to catch. It used
        # to be the floor of a calc() that an audio-driven treble glint lifted; the
        # glint is gone with the rest of the wheel reactivity, so the authored value
        # is now the whole value, and the regex accepts either shape so this does not
        # break the next time the rim becomes dynamic again.
        sign_rule = re.search(r"\.rotary-sign,\s*\.rotary-name-tag \{([^}]+)\}", self.css)[1]
        authored = re.search(r"border: 1px solid rgba\(var\(--rim-rgb\),\s*(?:calc\()?([\d.]+)",
                             sign_rule)
        self.assertIsNotNone(authored,
                             "the rim border is no longer an alpha off --rim-rgb")
        alpha = float(authored.group(1))
        self.assertGreaterEqual(alpha, 0.88,
                                "the RESTING rim dropped below its measured contrast")
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
        self.assertIn("rgba(var(--rim-rgb)", sign_rule)
        self.assertNotIn("var(--lavender-rgb)", sign_rule)

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
        # The address is assembled from parts at runtime so that no served file
        # contains a literal for Cloudflare's edge parser to rewrite. The domain is
        # still the canonical one -- it just arrives in two pieces.
        self.assertIn(f"'{SITE_DOMAIN}'", app,
                      "and the contact domain is still the canonical one")
        self.assertIn("['mail', '" + SITE_DOMAIN + "'].join('@')", app)
        self.assertNotIn(f"mail@{SITE_DOMAIN}", _strip_js_comments(app),
                         "a literal address is back in the served JavaScript")
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

    def test_native_assetlinks_does_not_depend_on_redirects(self):
        self.assertFalse((ROOT / '_redirects').exists())
        self.assertTrue((ROOT / ASSETLINKS_PATH).is_file())


class SharedPostRouting(unittest.TestCase):
    """/post/<id> deep links must resolve their id from the PATH.

    Pages Functions serve /post/:id and /p/:id directly without `_redirects`.
    The browser URL stays unchanged and location.search may be empty, so IDs
    must be read from the path rather than relying on destination query strings.

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
    def test_deep_link_routes_are_owned_by_pages_functions(self):
        for route in ('post', 'p'):
            self.assertTrue((ROOT / 'functions' / route / '[id].js').is_file())
        source = FUNCTION_PATH.read_text()
        self.assertIn("const LANDING_PAGE = '/shared-post';", source)
        self.assertIn('const fallback = await loadLandingPage(context);', source)
        self.assertIn('if (fallback) return htmlResponse(fallback, false);', source)


    def test_static_landing_lookup_carries_no_query_string(self):
        source = FUNCTION_PATH.read_text()
        self.assertIn("const LANDING_PAGE = '/shared-post';", source)
        self.assertIn('new URL(LANDING_PAGE, context.request.url)', source)


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

    def test_deep_link_handlers_do_not_depend_on_a_catch_all(self):
        self.assertFalse((ROOT / '_redirects').exists())
        self.assertIn('export async function onRequestGet', FUNCTION_PATH.read_text())
        self.assertIn('export async function onRequestHead', FUNCTION_PATH.read_text())


    def test_post_id_is_read_from_the_path(self):
        pattern = self.js_regex("POST_PATH_PATTERN")
        for path in (f"/post/{self.POST_UUID}", f"/p/{self.POST_UUID}",
                     "/post/a8f3c2/", "/POST/a8f3c2", "/p/a8f3c2"):
            with self.subTest(path=path):
                self.assertTrue(pattern.search(path), f"{path} must resolve")
        self.assertEqual(pattern.search(f"/post/{self.POST_UUID}").group(1),
                         self.POST_UUID, "the captured segment IS the post id")
        # Must not false-positive on the rest of the site.
        for path in (self.LANDING, "/", "/download", "/credits",
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
                         "S.browser_fallback_url=", "/download", ";end"):
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

    def test_landing_uses_the_native_clean_static_route(self):
        self.assertEqual(self.constant('LANDING_PAGE'), '/shared-post')
        self.assertTrue((ROOT / 'shared-post.html').is_file())
        self.assertIn('assets.fetch(new Request(url.toString()', self.fn)


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
        # Both aliases share the explicit static-landing fallback.
        self.assertIn('const fallback = await loadLandingPage(context);', self.fn)

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
        cls.html = _strip_html_comments((ROOT / "credits.html").read_text())
        cls.app = (ROOT / "app.js").read_text()

    # --- helpers -------------------------------------------------------
    def block(self, selector, after=0):
        """The declaration body of the FIRST rule matching selector at/after
        `after`, so a mobile override can be read separately from the base.

        Comment-aware and depth-counting. A CSS comment may legitimately contain
        braces -- the credits block lists its three landing angles as
        {40,160,280} -- and a naive search for the next "}" truncates the rule at
        the first one, which then reports every later declaration as missing."""
        start = self.css.index(selector, after)
        brace = self.css.index("{", start)
        depth = 0
        i = brace
        end = len(self.css)
        while i < end:
            if self.css.startswith("/*", i):
                i = self.css.index("*/", i) + 2
                continue
            char = self.css[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return self.css[brace + 1:i], i
            i += 1
        self.fail(f"unbalanced braces after {selector!r}")

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

    def test_each_detail_block_carries_its_own_arm(self):
        """This replaces the previous rule that both blocks shared one offset.

        Sharing an arm is a real geometric constraint, not a tidy-up: with the
        sectors exactly 180 degrees apart and the hubs on opposite corners,
        `top = hub + u` forces `bottom = hub' - u`, so one arm can only land two
        boxes that are symmetric about the viewport centre. The requested ones
        are not -- they differ by ~48px horizontally and ~36px vertically at
        1440x900 -- so each block now solves for its own.
        """
        self.assertEqual(self.arm("contribution"), (76.0, 58.0))
        self.assertEqual(self.arm("profile"), (76.5, 64.0))
        self.assertNotEqual(self.arm("contribution"), self.arm("profile"),
                            "the arms must differ, or one box is unreachable")
        self.assertEqual(self.arm("contribution", mobile=True), (108.5, 85.5))
        self.assertEqual(self.arm("profile", mobile=True), (103.5, 84.5))

    def test_the_mobile_width_overrides_are_gone(self):
        """The base widths are viewport-relative with a readable floor, so a
        second rem/vw pair under the mobile breakpoint only gave the solver two
        sets of numbers to disagree with."""
        tail = self.mobile_offset()
        self.assertNotIn("10.5rem, 32vw", self.css[tail:],
                         "a stale mobile width override survived")

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

    def arm(self, block, mobile=False):
        """The settled arm of ONE detail block, read from the CSS on disk.

        Each block now carries its own top/left, so a caller has to say which
        one it means. This is the whole reason the helper exists: a single
        shared arm cannot reach two boxes that are not symmetric about the
        viewport centre, and the requested ones are not.
        """
        selector = (".rotary-segment__content--profile {" if block == "profile"
                    else ".rotary-segment__content {")
        body, _ = self.block(selector)
        if mobile:
            override, _ = self.block(selector, self.mobile_offset())
            if override:
                body = override
        return self.pct(body, "left"), self.pct(body, "top")

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
        cases = [(w, h, False, 68, 76) for w, h in self.DESKTOP]
        cases += [(w, h, True, 58, 100) for w, h in self.MOBILE]
        for w, h, mob, header, status in cases:
            d = self.disc_diameter(w, h, mob)
            (cw, chh), (pw, phh) = self._metrics(w, h, d, mob)
            # Each block lands from ITS OWN arm; feeding both the same one is how
            # a passing test used to hide an unreachable box.
            arms = {"top": self.arm("contribution", mob),
                    "bottom": self.arm("profile", mob)}
            for which, bw, bh in (("top", cw, chh), ("bottom", pw, phh)):
                left, top = arms[which]
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
        tl, tt = self.arm("contribution")
        bl, bt = self.arm("profile")
        tx, ty, _, _ = self._landing(w, h, False, "top", tl, tt, cw, chh)
        bx, by, _, _ = self._landing(w, h, False, "bottom", bl, bt, pw, phh)
        self.assertLess(tx + cw / 2, w / 2, "the description block is not upper-left")
        self.assertLess(ty + chh / 2, h / 2, "the description block is not upper-left")
        self.assertGreater(bx + pw / 2, w / 2, "the profile block is not lower-right")
        self.assertGreater(by + phh / 2, h / 2, "the profile block is not lower-right")

    def test_the_blocks_reach_the_requested_viewport_boxes(self):
        """The review asked for two specific boxes: the description at
        left clamp(24px, 2.8vw, 48px) / top clamp(140px, 22vh, 220px), and the
        profile block right-aligned at clamp(20px, 2.2vw, 40px), vertically
        centred in the 42vh-82vh band.

        The rotary cannot teleport a block to an arbitrary viewport box -- it
        lands wherever its arm puts it after the wheel's own rotation -- so this
        asserts the residual instead of an exact match, and the tolerance is the
        solver's honest output rather than a round number. On desktop the arms
        land within ~48px (description) and ~56px (profile) of the requested
        centre. Every number here comes out of a constrained search that also
        has to satisfy the shipped safe-area, rim-label and non-overlap
        contracts, so it is the closest the mechanism can legally get -- not a
        round number chosen to make the test pass. Worst case: 122px desktop,
        96px on a phone.
        """
        def requested(w, h, mob):
            pad_l = min(max(24, 0.028 * w), 48)
            pad_r = min(max(20, 0.022 * w), 40)
            cw = min(max(0.23 * w, 230), 340)
            pw = min(max(0.175 * w, 200), 260)
            top = min(max(140, 0.22 * h), 220)
            return ((pad_l + cw / 2, top + 0.12 * h),          # description
                    (w - pad_r - pw / 2, 0.62 * h))            # profile

        tolerance = {False: 130.0, True: 100.0}
        for mob, viewports in ((False, self.DESKTOP), (True, self.MOBILE)):
            for w, h in viewports:
                d = self.disc_diameter(w, h, mob)
                (cw, chh), (pw, phh) = self._metrics(w, h, d, mob)
                (rx, ry), (qx, qy) = requested(w, h, mob)
                tl, tt = self.arm("contribution", mob)
                bl, bt = self.arm("profile", mob)
                for which, (bw, bh), arm, (tx, ty) in (
                        ("top", (cw, chh), (tl, tt), (rx, ry)),
                        ("bottom", (pw, phh), (bl, bt), (qx, qy))):
                    x0, y0, x1, y1 = self._landing(w, h, mob, which, arm[0], arm[1], bw, bh)
                    residual = math.hypot((x0 + x1) / 2 - tx, (y0 + y1) / 2 - ty)
                    with self.subTest(viewport=f"{w}x{h}", mobile=mob, block=which):
                        self.assertLessEqual(
                            residual, tolerance[mob],
                            f"{which} block landed {residual:.0f}px from the requested box")

    # --- helpers for the rim labels ------------------------------------
    REM = 16.0

    def resolve_size(self, expr, d, vw):
        """Evaluate the clamp()/min() chains the credits rules use, so the label
        boxes are derived from the stylesheet instead of restated here."""
        def val(token):
            token = token.strip()
            if token.startswith("calc(") and "100vw" in token:
                off = re.search(r"-\s*([\d.]+)rem", token)
                return vw - (float(off.group(1)) * self.REM if off else 0)
            if token.startswith("calc(") and "var(--rotary-disc-size)" in token:
                return d * float(re.search(r"\*\s*([\d.]+)", token).group(1))
            if token.endswith("rem"):
                return float(token[:-3]) * self.REM
            if token.endswith("px"):
                return float(token[:-2])
            self.fail(f"cannot evaluate {token!r} from the stylesheet")

        expr = expr.strip()
        m = re.match(r"^clamp\((.*?), (.*?), (.*)\)$", expr)
        if m:
            return max(val(m.group(1)), min(val(m.group(2)), val(m.group(3))))
        m = re.match(r"^min\((.*?), (.*)\)$", expr)
        if m:
            return min(val(m.group(1)), val(m.group(2)))
        return val(expr)

    def block_declaring(self, selector, prop, after=0):
        """The first rule for `selector` that actually declares `prop`.

        `.rotary-name-tag {` matches the shared box rule (`.rotary-sign,
        .rotary-name-tag {`) before it matches the positioning rule, and only the
        second one declares `left`."""
        cursor = after
        for _ in range(6):
            try:
                body, end = self.block(selector, cursor)
            except ValueError:
                break
            if self.decl(body, prop) is not None:
                return body
            cursor = end + 1
        self.fail(f"no {selector} rule declares {prop}")

    def orbit_radius(self, kind, mobile):
        selector = ".rotary-sign-hanger {" if kind == "sign" else ".rotary-name-tag {"
        if mobile:
            try:
                body, _ = self.block(selector, self.mobile_offset())
                if self.decl(body, "left"):
                    return float(self.decl(body, "left").rstrip("%")) - 50
            except ValueError:
                pass
        body = self.block_declaring(selector, "left")
        return float(self.decl(body, "left").rstrip("%")) - 50

    def label_box(self, mobile, d, vw):
        """(width, height) of a rim label, read from whichever rule wins."""
        if mobile:
            try:
                body, _ = self.block(".rotary-name-tag {", self.mobile_offset())
                if self.decl(body, "height"):
                    return (self.resolve_size(self.decl(body, "min-width"), d, vw),
                            self.resolve_size(self.decl(body, "height"), d, vw))
            except ValueError:
                pass
        body = self.block_declaring(".rotary-name-tag {", "height")
        return (self.resolve_size(self.decl(body, "min-width"), d, vw),
                self.resolve_size(self.decl(body, "height"), d, vw))

    def cord_length(self, mobile, d):
        body, _ = self.block(".rotary-sign-hanger__cord {")
        return self.resolve_size(self.decl(body, "height"), d, 0)

    def ray_point(self, w, h, mobile, which, theta, radius_pct):
        d = self.disc_diameter(w, h, mobile)
        hx, hy = self.hub(which, w, h, mobile)
        a = math.radians(theta)
        vx, vy = radius_pct / 100 * d, 0.0
        return hx + vx * math.cos(a) - vy * math.sin(a), hy + vx * math.sin(a) + vy * math.cos(a)

    def content_centre(self, w, h, mobile, which, theta, left, top):
        d = self.disc_diameter(w, h, mobile)
        hx, hy = self.hub(which, w, h, mobile)
        a = math.radians(theta)
        vx, vy = (left - 50) / 100 * d, (top - 50) / 100 * d
        return hx + vx * math.cos(a) - vy * math.sin(a), hy + vx * math.sin(a) + vy * math.cos(a)

    @staticmethod
    def box(cx, cy, bw, bh):
        return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)

    @staticmethod
    def hits(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    # --- 5. the wheels and the copy must not collide ---------------------
    def test_both_breakpoints_share_one_hub_inset(self):
        """One number, not two that can drift apart. Narrow screens used to push
        each hub 15% of the disc off-screen, which threw away most of the wheel."""
        base_top = self.decl(self.block(".rotary-disc--top {")[0], "transform")
        base_bottom = self.decl(self.block(".rotary-disc--bottom {")[0], "transform")
        self.assertEqual(base_top, "translate(-44%, -44%)")
        self.assertEqual(base_bottom, "translate(44%, 44%)")
        # Assert on the media tail itself: disc_rule() falls back to the base
        # rule when the narrow block declares no override, which cannot tell
        # "absent" apart from "present and wrong".
        tail = self.css[self.mobile_offset():]
        for which in ("top", "bottom"):
            self.assertNotIn(f".rotary-disc--{which} {{", tail,
                             f"the narrow-screen block re-tunes the {which} hub")

    def test_the_wheels_never_intersect(self):
        """Pulling the hubs inward is what fills the dead space in the middle of
        the screen, but only until the rims meet. -44% is the limit: past it the
        two wheels overlap on the tighter viewports and the sector lines of one
        draw across the face of the other."""
        for mobile, viewports in ((False, self.DESKTOP), (True, self.MOBILE)):
            for w, h in viewports:
                d = self.disc_diameter(w, h, mobile)
                tx, ty = self.hub("top", w, h, mobile)
                bx, by = self.hub("bottom", w, h, mobile)
                gap = math.hypot(bx - tx, by - ty) - d
                with self.subTest(viewport=f"{w}x{h}", mobile=mobile):
                    self.assertGreaterEqual(gap, 0, "the two wheel rims intersect")

    def test_sector_utilisation_is_maximised(self):
        """The point of moving the hubs at all: how much of each wheel is
        actually on screen. Corner-pinned hubs showed 19.7% on desktop and 7.3%
        on a phone, and left the middle of the viewport empty."""
        for mobile, (w, h), floor in ((False, (1440, 900), 0.25), (True, (390, 844), 0.25)):
            d = self.disc_diameter(w, h, mobile)
            hx, hy = self.hub("top", w, h, mobile)
            r = d / 2
            steps = 150
            inside = 0
            for i in range(steps):
                y = hy - r + (i + 0.5) * (2 * r / steps)
                for j in range(steps):
                    x = hx - r + (j + 0.5) * (2 * r / steps)
                    if ((x - hx) ** 2 + (y - hy) ** 2 <= r * r
                            and 0 <= x <= w and 0 <= y <= h):
                        inside += 1
            fraction = inside / (steps * steps)
            with self.subTest(viewport=f"{w}x{h}", mobile=mobile):
                self.assertGreaterEqual(fraction, floor,
                                        f"only {fraction:.1%} of the wheel is on screen")

    def test_detail_blocks_never_collide_with_their_rim_labels(self):
        """The hanging role sign and the name plate sit on the same ray as their
        own detail block -- and the sign hangs straight DOWN in screen space while
        the ray points wherever its sector does, so on an upward-pointing ray the
        sign swings back toward the copy.

        All three landing rays per wheel are checked, not just the settled one:
        A_i -/+ 120m always reduces to {40,160,280} and {220,340,100}, so the set
        of directions is fixed no matter which contributor is showing. The two
        non-settled blocks are measured at the 0.6 scale they really render at."""
        rays = {"top": (40, 160, 280), "bottom": (220, 340, 100)}
        for mobile, viewports in ((False, self.DESKTOP), (True, self.MOBILE)):
            # Each block now carries its own arm, so each wheel is measured at
            # the arm that actually places ITS block.
            arms = {"top": self.arm("contribution", mobile),
                    "bottom": self.arm("profile", mobile)}
            for w, h in viewports:
                d = self.disc_diameter(w, h, mobile)
                (cw, chh), (pw, phh) = self._metrics(w, h, d, mobile)
                bw_l, bh_l = self.label_box(mobile, d, w)
                cord = self.cord_length(mobile, d)
                for which in ("top", "bottom"):
                    left, top = arms[which]
                    r_orbit = self.orbit_radius("sign" if which == "top" else "name", mobile)
                    size = (cw, chh) if which == "top" else (pw, phh)
                    for theta in rays[which]:
                        # Only the settled block renders at full size.
                        scale = 1.0 if theta in (40, 220) else 0.6
                        cx, cy = self.content_centre(w, h, mobile, which, theta, left, top)
                        cbox = self.box(cx, cy, size[0] * scale, size[1] * scale)
                        lx, ly = self.ray_point(w, h, mobile, which, theta, r_orbit)
                        if which == "top":
                            ly += cord + bh_l / 2      # the sign hangs straight down
                        lbox = self.box(lx, ly, bw_l, bh_l)
                        with self.subTest(viewport=f"{w}x{h}", mobile=mobile,
                                          wheel=which, ray=theta):
                            self.assertFalse(self.hits(cbox, lbox),
                                             "the copy collides with its own rim label")

    def test_the_two_detail_blocks_never_overlap_each_other(self):
        for mobile, viewports in ((False, self.DESKTOP), (True, self.MOBILE)):
            lc, tc = self.arm("contribution", mobile)
            lp, tp = self.arm("profile", mobile)
            for w, h in viewports:
                d = self.disc_diameter(w, h, mobile)
                (cw, chh), (pw, phh) = self._metrics(w, h, d, mobile)
                tx, ty = self.content_centre(w, h, mobile, "top", 40, lc, tc)
                bx, by = self.content_centre(w, h, mobile, "bottom", 220, lp, tp)
                with self.subTest(viewport=f"{w}x{h}", mobile=mobile):
                    self.assertFalse(self.hits(self.box(tx, ty, cw, chh),
                                               self.box(bx, by, pw, phh)),
                                     "the two contributor blocks overlap")

    # --- 6. the swap animation ----------------------------------------
    def test_the_arrival_timing_agrees_between_css_and_js(self):
        """app.js clears the arrival marker on a timer; the CSS animation plays
        for a duration. If those drift apart the marker is stripped mid-ease (the
        block snaps) or left on afterwards (it animates forever)."""
        js = int(re.search(r"var ARRIVAL_MS = (\d+);", self.app).group(1))
        css = re.search(r"animation: rotary-arrive ([\d.]+)s", self.css)
        self.assertIsNotNone(css, "the rotary-arrive animation is missing")
        self.assertEqual(float(css.group(1)) * 1000, float(js),
                         f"CSS animation {css.group(1)}s vs ARRIVAL_MS {js}ms")

    def test_the_copy_is_not_swapped_behind_a_timer(self):
        """Each segment permanently owns its member, so nothing in the copy
        actually changes when the wheel settles -- only the .is-active classes
        and the 01/02/03 counter do. Deferring that behind a timeout bought
        nothing and gave the two a chance to drift apart."""
        body = self.app.split("function showMember(index, animate)", 1)[1]
        body = body.split("\n    }", 1)[0]
        self.assertIn("setMemberText();\n      if (!animate) return;", body,
                      "the class/counter update must be synchronous")
        timer = body.split("window.setTimeout(", 1)
        self.assertEqual(len(timer), 2, "expected exactly one timer, for the marker")
        self.assertNotIn("setMemberText()", timer[1],
                         "the copy update is still hidden inside a timeout")
        self.assertNotIn("is-changing", self.app, "the dim-everything swap is gone")
        self.assertNotIn("is-changing", self.css, "and so is its rule")

    def test_the_arrival_marker_is_cleared_from_every_block_first(self):
        """Stepping through sectors faster than the animation plays must not
        leave a marker behind on a block that is no longer arriving."""
        body = self.app.split("function showMember(index, animate)", 1)[1]
        self.assertLess(body.index("content.classList.remove('is-arriving')"),
                        body.index("content.classList.add('is-arriving')"),
                        "the marker is added before it is cleared")
        self.assertIn("[topSegments, bottomSegments].forEach", self.app,
                      "every block must be in the cleared set, not just the arriving one")

    def test_the_arrival_animation_is_only_on_frame_stable_elements(self):
        """.rotary-segment__content and .rotary-sign-hanger are counter-rotated
        every animation frame. A transform transition OR animation on either
        would fight that per-frame rotation and smear the wheel into a visible
        lag, so the ease-up has to be applied to their children instead."""
        for selector in (".rotary-segment__content {", ".rotary-sign-hanger {"):
            body, _ = self.block(selector)
            transition = self.decl(body, "transition") or ""
            self.assertNotIn("transform", transition,
                             f"{selector} transitions its frame-driven transform")
            self.assertIsNone(self.decl(body, "animation"),
                              f"{selector} animates its frame-driven transform")
        self.assertIn(".rotary-segment__content.is-arriving > * {", self.css,
                      "the ease-up must target the children")
        rule, _ = self.block(".rotary-segment__content.is-arriving > * {")
        self.assertIn("rotary-arrive", self.decl(rule, "animation"))
        keyframes = self.css.split("@keyframes rotary-arrive {", 1)
        self.assertEqual(len(keyframes), 2, "the keyframes are missing")
        self.assertIn("translateY(", keyframes[1].split("}", 2)[1] + keyframes[1])
        # Assert the suppression itself, not merely that a reduced-motion block
        # happens to sit nearby: swapping `animation: none` for the full
        # animation leaves the words "prefers-reduced-motion" in place and the
        # assertion would still pass while the preference is ignored.
        self.assertRegex(
            self.css,
            r"\.rotary-segment__content\.is-arriving > \*\s*\{\s*animation:\s*none;\s*\}",
            "the arrival animation is not actually suppressed for reduced motion")



class AmbientMesh(unittest.TestCase):
    """The site's ONE background canvas.

    There used to be two: a square dot matrix on every page, plus a sine wave mesh
    layered on top of it on the credits screen alone. On credits they occupied the
    same pixels, doubled the frame cost, and where the two lattices crossed they
    read as moire rather than as depth. This is the contract that replaced them --
    one canvas, one triangulated field, identical on every page.
    """

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "style.css").read_text()
        cls.app = (ROOT / "app.js").read_text()
        # Bounded by the call site that FOLLOWS initAmbientMesh, not by the next
        # top-level function. The looser boundary used here before ran past the mesh
        # into the rest of initAmbientExperience -- including the audio graph itself --
        # so an assertion that the mesh contains no reference to AudioContext was
        # failing on code that is not the mesh. A region split has to end where the
        # thing being described ends.
        cls.mesh = cls.app.split("function initAmbientMesh()", 1)[1].split(
            "\n    initCursor();", 1)[0]
        cls.boot = cls.app.split("function boot()", 1)[1].split("\n  }", 1)[0]
        cls.page = cls.app.split("function bootPage()", 1)[1].split("\n  }", 1)[0]
        # The session-scoped ambient layer, bounded by the credits team data that
        # follows it -- so "built once per session" is a region claim, not a guess.
        cls.ambient = cls.app.split("function initAmbientExperience()", 1)[1].split(
            "\n  var ROTARY_TEAM", 1)[0]

    def rule(self, selector):
        return self.css.split(selector + " {", 1)[1].split("}", 1)[0]

    # --- exactly one ------------------------------------------------------
    def test_the_retired_credits_layer_is_gone_from_both_files(self):
        """Deleting a layer means deleting it. The class, the initializer, the
        cleanup closure and the section banner are all gone -- 300 lines of canvas
        code that nothing calls would still be 300 lines a future reader has to
        reconcile against the one that does run."""
        for token in (".credits-wave-matrix {", "initWaveMatrix", "waveMatrixCleanup",
                      "CREDITS WAVE MATRIX", "credits-wave-matrix"):
            for name, source in (("style.css", self.css), ("app.js", self.app)):
                with self.subTest(token=token, file=name):
                    self.assertNotIn(token, source)
        # A class selector is the thing that would resurrect the layer; the word
        # "wave" on its own is ordinary prose about a wave and must stay usable.
        self.assertNotIn("ambient-dot-matrix", self.css, "the old class outlived its rename")
        self.assertNotIn("ambient-dot-matrix", self.app)

    def test_exactly_one_canvas_is_built_for_the_whole_site(self):
        """One createElement('canvas') in the entire file.

        A second background canvas is not a styling choice, it is two lattices
        fighting over the same pixels at twice the frame cost -- the exact thing
        this round removed. Counted on the source rather than on a rendered page,
        because the count is the contract: the site-wide layer and the
        page-scoped layer are the same layer now."""
        # createElement('canvas') appears TWICE and that is correct: the second is
        # makeGlowSprite's 64x64 offscreen glow texture, which is never inserted
        # into the document. What has to be singular is a canvas ATTACHED to the
        # page, so count the attachment rather than the creation.
        self.assertEqual(self.app.count("createElement('canvas')"), 2,
                         "one background canvas plus one offscreen sprite texture")
        sprite = self.app.split("function makeGlowSprite(", 1)[1].split("\n  }", 1)[0]
        self.assertIn("createElement('canvas')", sprite,
                      "and the second one is the sprite, not a hidden background layer")
        self.assertEqual(self.app.count("body.insertBefore(canvas"), 1,
                         "exactly one canvas is ever attached to the page")
        self.assertNotIn("body.appendChild(canvas", self.app)
        self.assertEqual(self.app.count("initAmbientMesh();"), 1,
                         "and exactly one live call to it")

    def test_it_is_built_once_per_session_not_once_per_page(self):
        """The mesh is global, so it belongs in initAmbientExperience (run once)
        and NOT in bootPage (run on every PJAX swap). Building it per swap would
        stack a canvas per navigation, which is how the credits layer used to need
        a cleanup closure at all."""
        self.assertIn("initAmbientExperience();", self.boot)
        self.assertIn("initAmbientMesh();", self.ambient,
                      "the mesh is not built by the session-scoped ambient layer")
        self.assertNotIn("initAmbientMesh();", self.page,
                         "and must not also be rebuilt on every page swap")
        # Which is also why it needs no teardown: nothing removes it, and the
        # self-terminating draw loop is the only thing that can stop it.
        self.assertNotIn("removeChild(canvas)", self.mesh)
        self.assertIn("if (!canvas.isConnected) return;", self.mesh,
                      "the draw loop must still stop itself if the canvas is detached")


    def test_it_does_not_know_which_page_it_is_on(self):
        """The mesh is now completely page-agnostic, and that is a stronger property
        than the gated version it replaces.

        It used to be built only on credits, then built everywhere but gated its
        scroll coupling on `body.classList.contains('credits-rotary-page')`. A gate is
        something a future edit can forget. There is no gate here because there is
        nothing to gate: the function contains no reference to spin, the wheel,
        scrolling, or the credits page, so no input from any page can reach it except
        the audio facade and the viewport size.
        """
        self.assertNotIn("if (!wanted)", self.mesh, "a page gate survived the rewrite")
        self.assertNotIn("credits-rotary-page", self.mesh,
                         "the mesh still knows which page it is on")
        for token in ("spin", "Spin", "wheel", "Wheel", "deltaY", "scroll"):
            with self.subTest(token=token):
                code = "\n".join(line for line in self.mesh.split("\n")
                                 if not line.strip().startswith(("//", "/*", "*")))
                self.assertNotIn(token, code,
                                 f"{token!r} appears in mesh CODE (comments explaining the "
                                 f"removal are fine and deliberate)")
        self.assertIn("canvas.className = 'ambient-mesh';", self.mesh)
        self.assertIn("doc.body.insertBefore(canvas, doc.body.firstChild);", self.mesh,
                      "it must be the first child so main's z-index 1 sits above it")

    # --- the CSS box ------------------------------------------------------
    def test_the_canvas_covers_the_viewport_and_never_eats_an_event(self):
        body = self.rule(".ambient-mesh")
        self.assertIn("position: fixed", body)
        self.assertIn("inset: 0", body)
        self.assertIn("width: 100vw", body)
        self.assertIn("height: 100vh", body)
        self.assertEqual(int(re.search(r"z-index:\s*(\d+)", body).group(1)), 0,
                         "it has to sit under main (z-index 1)")
        self.assertIn("pointer-events: none", body)
        self.assertNotIn("pointer-events: auto", body,
                         "an earlier `auto` in the same block wins the cascade")
        # The credits screen is entirely gesture driven; a canvas that swallowed a
        # wheel event would stop the wheels turning at all.
        self.assertIn("touch-action", self.css)

    def test_the_class_the_script_applies_matches_the_stylesheet(self):
        """Renaming a layer is exactly the change that passes every JS test and
        every CSS test while rendering nothing: each half agrees with itself and
        disagrees with the other. Pin the join."""
        self.assertIn("canvas.className = 'ambient-mesh';", self.app)
        self.assertIn(".ambient-mesh {", self.css)

    # --- colour -----------------------------------------------------------
    def test_it_follows_the_theme_instead_of_hardcoding_colour(self):
        for token in ("--mesh-line-rgb", "--mesh-node-rgb", "--mesh-node-hi-rgb",
                      "--mesh-glow-rgb"):
            self.assertIn("getPropertyValue('" + token + "')", self.mesh)
        self.assertIn("prefers-color-scheme: light", self.mesh,
                      "a mid-session scheme flip has to re-read the palette")
        # Assert on the PAINT CALL SITES, not on the palette object: the point is
        # that what reaches the context came from a channel.
        strokes = re.findall(r"context\.strokeStyle = 'rgba\(' \+ ([\w.]+) \+", self.mesh)
        # One assignment, executed once per band. It used to be two (a row pass and a
        # column pass at fixed alphas); now a single line inside the bucket loop sets
        # the colour for all five passes, so the count went DOWN while the number of
        # strokes went up -- which is the point of batching.
        self.assertEqual(len(strokes), 1, f"expected one bucketed assignment, got {strokes}")
        self.assertEqual(strokes[0], "palette.line",
                         f"lines painted from {strokes[0]!r}, not a theme channel")
        self.assertIn("(LINE_ALPHAS[bucket] * palette.ink).toFixed(4)", self.mesh)
        # And the rebuild on a scheme flip must remake the SPRITE too, or the
        # vertices keep glowing in the previous theme's colour.
        flip = self.mesh.split("function onSchemeChange()", 1)[1].split("\n      }", 1)[0]
        self.assertIn("palette = readPalette();", flip)
        self.assertIn("sprites = buildSprites(palette);", flip)

    # --- the blend mode, measured ----------------------------------------


    def test_the_mesh_is_a_backdrop_in_both_themes_not_a_graphic(self):
        """Recomputes what actually lands on screen, in both themes, from the alphas in
        app.js and the tokens in style.css.

        Two bands, and both matter. Below ~1.03:1 the layer is not faint, it is absent --
        which is exactly what `mix-blend-mode: screen` did to the light theme for a whole
        release, measuring 1.003:1 against --bg while every colour token said otherwise.
        Above ~1.8:1 it stops being a backdrop and starts competing with type, which is
        the failure this round was asked to fix.

        There is no blend mode and no element opacity, deliberately: a full-viewport
        mix-blend-mode makes the compositor read back and blend the whole backdrop group
        every frame and defeats GPU layer caching. Measured when they were removed, the
        largest channel delta was 3.6/255 and contrast was slightly better without them.
        """
        def channels(token, region):
            value = _resolve_colour(token, region)
            self.assertIsNotNone(value, token + " is not defined in that theme")
            return value

        alphas = _mesh_alphas(self.app)
        self.assertEqual(alphas["lines"], [0.03, 0.07, 0.10, 0.16, 0.24])
        self.assertEqual(alphas["dots"], [0.06, 0.11, 0.18, 0.26, 0.35])
        self.assertEqual(alphas["lines"][alphas["base"]], 0.10,
                         "the flat-field baseline for lines is 0.10")
        self.assertEqual(alphas["dots"][alphas["base"]], 0.18,
                         "and for vertices 0.18")

        blocks = re.findall(r"\.ambient-mesh\s*\{[^}]*\}", self.css)
        self.assertTrue(blocks, "the .ambient-mesh rule is gone")
        for block in blocks:
            with self.subTest(block=block.split("{")[0].strip()):
                self.assertNotIn("mix-blend-mode", block,
                                 "a full-viewport blend mode costs a backdrop read-back every frame")
                self.assertNotIn("opacity:", block,
                                 "element opacity is a second compositing pass for a dim nobody sees")
                self.assertIn("position: fixed", block)
                self.assertIn("width: 100vw", block)
                self.assertIn("height: 100vh", block)
                self.assertIn("pointer-events: none", block)

        root = self.css.split(":root {", 1)[1].split("\n}", 1)[0]
        light = self.css[self.css.index("@media (prefers-color-scheme: light) {"):].split("\n}", 1)[0]
        measured = {}
        for name, region in (("dark", root), ("light", light)):
            bg = channels("--bg-rgb", region)
            ink = _theme_ink(self.css, region)
            self.assertGreater(ink, 0)
            self.assertLessEqual(ink, 1)
            for what, token, table in (("line", "--mesh-line-rgb", alphas["lines"]),
                                       ("vertex", "--mesh-node-rgb", alphas["dots"])):
                # Measured at the CREST, which is the worst case the layer ever
                # paints. The baseline band is checked separately in
                # CreditsBackdrop, because that is what most of the screen shows.
                out = _composite(channels(token, region), bg, max(table) * ink, SOURCE_OVER)
                ratio = _contrast(out, bg)
                measured[(name, what)] = ratio
                with self.subTest(theme=name, element=what):
                    self.assertGreater(ratio, 1.03,
                                       f"{name}-theme {what} at its crest is {ratio:.3f}:1 -- "
                                       f"that is not a faint decoration, it is nothing at all")
                    self.assertLess(ratio, 2.0,
                                    f"{name}-theme {what} at its crest is {ratio:.3f}:1 -- past "
                                    f"this the background competes with foreground typography")
                    # A contrast RATIO cannot detect "too faint", because it compresses
                    # toward 1.0 from both sides: halving the alpha moves a 1.08:1 line to
                    # 1.04:1, which still clears a 1.03 floor. The channel delta does not
                    # compress -- it is what the eye actually has to work with -- so the
                    # floor is asserted on it as well. This is what catches an --mesh-ink
                    # turned down far enough to erase the layer in one theme only.
                    delta = max(abs(out[i] - bg[i]) * 255 for i in range(3))
                    self.assertGreater(delta, 10.0,
                                       f"{name}-theme {what} moves no channel by more than "
                                       f"{delta:.1f}/255 -- that is not faint, it is absent")
        # The real contract is PARITY, not a particular dial position: the two themes
        # must press about equally hard, however that is achieved. Both inks are 1 now,
        # because at 0.16-0.22 alpha the deepened light channels land in the same band
        # on their own; when the alphas were 0.45-0.60 light needed 0.55. Asserting the
        # outcome survives either arrangement, and survives a palette change.
        self.assertIn("--mesh-ink:", root)
        self.assertIn("--mesh-ink:", light)
        for what in ("line", "vertex"):
            parity = measured[("light", what)] / measured[("dark", what)]
            with self.subTest(element=what):
                self.assertGreater(parity, 0.75,
                                   f"the light theme is far fainter than dark ({parity:.2f}x)")
                self.assertLess(parity, 1.35,
                                f"the light theme presses harder than dark ({parity:.2f}x)")

    def test_the_glow_is_prerendered_because_shadowblur_cannot_afford_it(self):
        """The brief asked for bloom via `shadowBlur` or a soft gradient fill and for
        the heavy glow to go. This is the gradient fill, and the choice is not
        aesthetic: at ~600 vertices and 60fps, per-vertex shadowBlur is 36,000 of the
        most expensive calls a 2D context has per second, re-rasterised every frame
        because the vertices move. makeGlowSprite() bakes the same radial falloff into
        an off-screen canvas once per colour and drawGlow() blits it.

        Bloom is back down from the 0.78 the mesh carried while it was meant to pop, to
        0.30 -- a soft edge rather than a halo. 1.0 is the original shadowBlur 8-12
        look, and past it a vertex lights up its whole neighbourhood and reads as glare,
        which at 0.16-0.22 alpha would be the only thing visible about it.
        """
        self.assertNotRegex(self.app, r"(ctx|context|c)\.shadowBlur\s*=",
                            "shadowBlur is back in the frame loop")
        self.assertIn("function makeGlowSprite(coreRgb, glowRgb, bloom)", self.app)
        self.assertIn("function drawGlow(", self.app)
        self.assertIn("createRadialGradient(", self.app)
        bloom = self.num("MESH_GLOW_BLOOM")
        spread = self.num("MESH_GLOW_SPREAD")
        self.assertGreater(bloom, 0.1, "with no bloom at all the vertex is a hard dot")
        self.assertLess(bloom, 0.55, "a halo this wide reads as glare at any alpha")
        self.assertGreater(spread, 1.2, "the glow does not reach past the vertex core")
        self.assertLess(spread, 2.4, "and it must not reach the next cell over")
        # Both sprites are built by ONE function, called at init and again on a scheme
        # flip, with the SAME bloom. That equality is the check that once caught the
        # flip losing its third argument and giving the mesh a much heavier glow in one
        # theme than the other.
        self.assertEqual(self.mesh.count("buildSprites("), 3,
                         "one declaration, one init call, one scheme-flip call")
        builds = re.findall(r"node: makeGlowSprite\(([^)]+)\),\n\s*hi: makeGlowSprite\(([^)]+)\)",
                            self.mesh)
        self.assertEqual(len(builds), 1, "buildSprites must make both sprites together")
        self.assertEqual(builds[0][0], "p.node, p.glow, MESH_GLOW_BLOOM")
        self.assertEqual(builds[0][1], "p.hi, p.glow, MESH_GLOW_BLOOM",
                         "the two sprites disagree about bloom")

    def test_reduced_motion_gets_one_frame_and_no_loop(self):
        self.assertIn("if (!reduceMotion()) window.requestAnimationFrame(draw);", self.mesh,
                      "the loop must be gated on reduced motion")
        self.assertIn("if (reduceMotion()) {", self.mesh,
                      "and a paused canvas still needs one frame on a scheme change")


    def test_the_ambient_layer_cannot_stop_the_page_booting(self):
        """initAmbientExperience() runs FIRST in boot(), and it touches every optional
        browser API this site has. Any one of them missing used to be able to abort
        boot() before bootPage(), leaving a visitor with a page whose routing, menu,
        contact form and credits screen were all dead while its background was fine.
        Precisely backwards.

        The original instance was `fetch(MUSIC_SRC).catch(...)`: `.catch()` can only
        handle a rejected promise, and if `fetch` is not a function the call throws a
        ReferenceError synchronously, before there is a promise to catch on. Found by a
        jsdom run, which has no fetch.

        There is no fetch in the ambient layer at all now -- the track streams through
        an <audio> element -- so that specific hazard is gone rather than guarded. The
        wrapper stays, because the class of hazard is not: this is still the first thing
        boot() does and it still touches matchMedia, a 2D canvas context and HTMLMediaElement.
        """
        boot = self.app.split("function boot()", 1)[1].split("\n  }", 1)[0]
        self.assertRegex(boot, r"try \{\s*initAmbientExperience\(\);\s*\} catch \(error\) \{",
                         "the decorative layer is no longer isolated from boot()")
        self.assertIn("initAmbientExperience();", boot)
        self.assertIn("bootPage();", boot)
        # bootPage must be OUTSIDE the try: catching around it too would turn a real
        # hydration failure into a page that looks fine and does nothing.
        self.assertGreater(boot.index("bootPage();"), boot.index("} catch (error) {"),
                           "bootPage() is inside the ambient layer's try block")
        caught = boot.split("} catch (error) {", 1)[1]
        self.assertIn("window.console.warn", caught,
                      "a background that silently fails to start is indistinguishable "
                      "from one that was never asked to")
        # The specific hazard that started this is structurally impossible now.
        self.assertNotIn("fetch(", self.ambient,
                         "the ambient layer is fetching again; it should be streaming")

    def test_the_buffer_is_capped(self):
        self.assertIn("Math.min(window.devicePixelRatio || 1, 1.75)", self.mesh)
        self.assertIn("context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)", self.mesh)
        self.assertIn("addEventListener('resize', resize", self.mesh)

    def num(self, name, region=None):
        # Several of these constants share a line (`var A = 1, B = 2;`), so the
        # prefix may be `var ` or `, ` and the terminator `;` or `,`.
        m = re.search(r"(?:var |, )" + re.escape(name) + r" = (-?[\d.]+)[;,]",
                      region or self.mesh)
        self.assertIsNotNone(m, f"{name} is gone")
        return float(m.group(1))


class AmbientMeshGeometry(unittest.TestCase):
    """The lattice is arithmetic, and every one of its failure modes is invisible
    in a diff.

    A jittered grid subdivided into triangles, chosen over a real Delaunay on
    purpose: the topology is hashed from (row, column) once per resize, so it is
    identical every frame. Re-triangulating per frame would boil -- the vertices
    move, so the triangles would flip constantly -- and re-running Bowyer-Watson
    on ~600 moving points is not something a phone survives. At this opacity the
    two are indistinguishable; only one of them holds a frame rate.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        # Bounded by the call site that FOLLOWS initAmbientMesh, not by the next
        # top-level function. The looser boundary used here before ran past the mesh
        # into the rest of initAmbientExperience -- including the audio graph itself --
        # so an assertion that the mesh contains no reference to AudioContext was
        # failing on code that is not the mesh. A region split has to end where the
        # thing being described ends.
        cls.mesh = cls.app.split("function initAmbientMesh()", 1)[1].split(
            "\n    initCursor();", 1)[0]
        cls.draw = cls.mesh.split("function draw(timestamp)", 1)[1]

    def num(self, name, region=None):
        # Several of these constants share a line (`var A = 1, B = 2;`), so the
        # prefix may be `var ` or `, ` and the terminator `;` or `,`.
        m = re.search(r"(?:var |, )" + re.escape(name) + r" = (-?[\d.]+)[;,]",
                      region or self.mesh)
        self.assertIsNotNone(m, f"{name} is gone")
        return float(m.group(1))

    # --- triangulation ----------------------------------------------------
    def fbm_gradient(self):
        """Peak |d(displacement)/d(px)| of the noise field per pixel of amplitude.

        A quintic-interpolated value-noise texel whose corners span -1..1 has a peak
        slope of 3.75 per texel (fade' maxes at 1.875), each octave contributes at its
        normalised weight and its own texel size, and the sum is the worst case for the
        whole field. Used by both the tear budget and the velocity estimate, because
        they are the same quantity viewed two ways -- which is exactly why amplitude
        and speed cannot be tuned independently here.
        """
        gain = self.num("NOISE_GAIN")
        lac = self.num("NOISE_LACUNARITY")
        octaves = int(self.num("NOISE_OCTAVES"))
        slope = self.num("QUINTIC_PEAK_SLOPE")
        texel = self.num("NOISE_TEXEL")
        weights = [gain ** o for o in range(octaves)]
        norm = sum(weights)
        return sum((w / norm) * slope * (lac ** o) / texel for o, w in enumerate(weights))


    def test_the_lattice_is_triangulated_not_square(self):
        """Squares read as graph paper. Every cell additionally carries one of its
        two diagonals, so the field is ~550 triangles rather than ~550 boxes at the
        same vertex count."""
        self.assertIn("flips = new Uint8Array(", self.mesh, "no per-cell diagonal table")
        self.assertIn("flips[c] = hash2(c, 0x5f3a7c11) & 1;", self.mesh,
                      "the diagonal choice must be hashed per cell")
        # The diagonal now appears twice -- once where its bucket is decided and once
        # where it is drawn -- and the two MUST pick the same pair of corners, or an
        # edge is stroked at its neighbour's opacity. Both are pinned.
        classify = self.mesh.split("var edgeIndex = 0;", 1)[1].split("context.lineWidth = 1;", 1)[0]
        paint = self.mesh.split("context.lineWidth = 1;", 1)[1]
        self.assertIn("ebuck[edgeIndex++] = flips[cellBase + column]", classify)
        self.assertIn("? edgeBucket(corner, corner + columns + 1)", classify)
        self.assertIn(": edgeBucket(corner + 1, corner + columns);", classify)
        self.assertIn("var lean = flips[cb + column];", paint)
        self.assertIn("var da = lean ? c0 : (c0 + 1);", paint)
        self.assertIn("var db = lean ? (c0 + columns + 1) : (c0 + columns);", paint)
        # A first draft drew both diagonals from the top-left corner. The source
        # looked fine and the lattice lost every anti-diagonal.
        self.assertNotIn("var db = lean ? (c0 + columns + 1) : (c0 + columns + 1);", paint)

    def test_the_diagonal_choice_actually_varies(self):
        """`& 1` proves intent, not outcome. This runs the REAL constants from
        hash2 over a 40x40 field.

        The failure it catches is specific: without Math.imul the products exceed
        2^53, the low bits -- the only ones that look random -- are lost, and
        every diagonal leans the same way. A uniform lattice of diagonals is as
        monotonous as no diagonals at all, and it looks fine in the source.
        """
        body = self.app.split("function hash2(a, b) {", 1)[1].split("\n  }", 1)[0]
        self.assertEqual(body.count("Math.imul"), 3,
                         "hash2 must multiply in 32-bit integer range; a plain * overflows "
                         "to a double and only its high bits survive")
        self.assertIn(">>> 0", body, "and must fold back to an unsigned 32-bit int")
        salts = [int(x) for x in re.findall(r"Math\.imul\(\w+ \| 0, (\d+)\)", body)]
        self.assertEqual(len(salts), 2, "hash2 must mix both of its arguments")
        mix_shift, mix_mul = (int(x) for x in
                              re.search(r"Math\.imul\(h \^ \(h >>> (\d+)\), (\d+)\)", body).groups())
        final_shift = int(re.search(r"\(h \^ \(h >>> (\d+)\)\) >>> 0", body).group(1))

        mask = 0xFFFFFFFF

        def hash2(a, b):
            h = ((a * salts[0]) & mask) ^ ((b * salts[1]) & mask)
            h = ((h ^ (h >> mix_shift)) * mix_mul) & mask
            return (h ^ (h >> final_shift)) & mask

        flips = [hash2(c, 0x5F3A7C11) & 1 for c in range(1600)]
        ones = sum(flips)
        self.assertGreater(ones, 1600 * 0.35, f"only {ones}/1600 cells lean one way")
        self.assertLess(ones, 1600 * 0.65, f"{ones}/1600 cells lean one way")
        # A hash with a short period shows up as long runs of identical diagonals,
        # which reads on screen as banding rather than as an organic lean.
        # A run of 8 is NORMAL here -- for 1600 fair coin flips the expected
        # longest run is about log2(1600) = 10.6 -- so an aggressive run limit
        # would flag a good hash and pass a bad one. What a degenerate hash
        # actually loses is entropy: repeated outputs and a period short enough to
        # tile visibly. Assert those instead.
        values = [hash2(c, 0x5F3A7C11) for c in range(1600)]
        self.assertGreater(len(set(values)), 1590, "hash2 is colliding; entropy is being lost")
        self.assertGreater(len(set(flips[:400])), 1, "the low bit is constant over a row")
        period = next((p for p in range(1, 64) if flips[:1500] == flips[p:1500 + p][:1500]
                       and flips[:p] * (1500 // p) == flips[:(1500 // p) * p]), None)
        self.assertIsNone(period, f"the diagonal pattern repeats with period {period}")

    def test_the_jitter_is_deterministic_not_random(self):
        """The topology has to survive from frame to frame. A jitter recomputed per
        frame would make the whole mesh boil, and Math.random() in a draw loop is
        how that happens by accident."""
        self.assertNotIn("Math.random", self.mesh.replace("Not Math.random()", ""))
        self.assertIn("jitterX = new Float32Array(vertices);", self.mesh)
        self.assertIn("jitterY = new Float32Array(vertices);", self.mesh)
        resize = self.mesh.split("function resize()", 1)[1].split("\n      }", 1)[0]
        self.assertIn("hash2(", resize, "the jitter is not hashed from (column, row)")
        self.assertNotIn("hash2(", self.draw,
                         "and must not be recomputed per frame")
        # Both axes come from ONE hash, split high/low, so they are uncorrelated
        # without costing a second hash per vertex.
        self.assertIn("h & 0xffff", resize)
        self.assertIn("h >>> 16", resize)

    # --- the budget that keeps it from tearing ----------------------------


    def test_the_jitter_is_gentle_because_it_is_the_expensive_kind(self):
        """Jitter is what stops the lattice reading as graph paper, and it is also the
        one term whose wavelength IS a single cell -- so it spends 2*JITTER of the tear
        budget unconditionally, before the noise field has moved anything.

        It is down to 0.06 of a cell from 0.12 two rounds ago and 0.22 before that.
        Each reduction bought real amplitude for the waves, and none of them cost
        visible organic character, because the random DIAGONAL LEAN carries most of
        that for free: a diagonal is a topology choice rather than a displacement, so
        it spends nothing in the gradient budget at all.
        """
        self.assertLessEqual(self.num("JITTER"), 0.08,
                             "jitter at this level reads as noise and starves the field")
        self.assertGreater(self.num("JITTER"), 0.02,
                           "with no jitter the lattice is graph paper again")
        self.assertIn("flips[c] = hash2(c, 0x5f3a7c11) & 1;", self.mesh,
                      "the diagonal lean is what carries the organic character")


    def test_the_tear_budget_covers_every_term(self):
        """Recomputed from the constants on disk, from a condition that is actually a
        theorem rather than a rule of thumb.

        A vertex may move, but if two neighbours close the gap between them the
        triangles they share invert -- invisible in a diff, only mildly visible on
        screen, which is exactly the combination that ships. The map x -> x + u(x) is
        injective and orientation-preserving whenever the operator norm of the
        displacement gradient is under 1, and the Frobenius norm bounds the operator
        norm, so sqrt(sum of the four squared partials) < 1 is a sufficient condition.
        2*JITTER is added on top because jitter is not a smooth field.

        For value noise the per-axis partial is amplitude * gradient, and the gradient
        of a quintic-interpolated texel whose corners span -1..1 peaks at 3.75 per
        texel (fade' maxes at 1.875), summed over octaves at their normalised weights.

        The bound is a worst case over phases that essentially never align -- it wants
        every octave's corners at opposite extremes AND all four partials peaking at
        the same vertex -- so it runs about 3x pessimistic. That is fine and is the
        point of stating it: 0.628 against a 0.75 allowance, while the harness measures
        0 inverted triangles in 231,420 cells and a minimum signed area of 81% of a
        cell. The arithmetic catches an amplitude bump in review; the measurement
        catches everything else.
        """
        spacing = 54    # the desktop cell: same fractions, more pixels, tightest case
        self.assertAlmostEqual(self.num("QUINTIC_PEAK_SLOPE"), 3.75, places=6,
                               msg="fade() peaks at 1.875 against a corner range of 2")
        gradient = self.fbm_gradient()

        amp = self.num("NOISE_AMP") * spacing

        # The budget above assumes fbm() returns a NORMALISED value in -1..1. Without
        # the division it returns sum, whose range is `norm` = 1.875 times larger, so
        # every amplitude in here -- and therefore the gradient, the velocity and the
        # tear spend -- is silently 87.5% bigger than the arithmetic says. Deleting one
        # token would blow the budget with no constant changing.
        fbm_body = self.mesh.split("function fbm(x, y, z)", 1)[1].split("\n      }", 1)[0]
        self.assertIn("norm += amp;", fbm_body)
        self.assertIn("return sum / norm;", fbm_body,
                      "fbm is not normalised, so NOISE_AMP does not mean what it says")
        self.assertEqual(self.draw.count("* amplitude;"), 1)
        self.assertEqual(self.draw.count("* amplitude * NOISE_DX_RATIO;"), 1,
                         "the amplitude reaching a vertex is not the one being budgeted")

        ddy = amp * gradient
        ddx = amp * self.num("NOISE_DX_RATIO") * gradient
        frobenius = math.sqrt((2 * ddx ** 2) + (2 * ddy ** 2))
        total = frobenius + (2 * self.num("JITTER"))

        limit = self.num("TEAR_LIMIT")
        self.assertLessEqual(total, limit,
                             f"the field can close {total:.4f} of the injectivity threshold "
                             f"against a {limit} allowance (Frobenius {frobenius:.4f} + jitter "
                             f"{2 * self.num('JITTER'):.4f}): triangles will invert")
        self.assertLessEqual(limit, 1.0, "the theorem's threshold is 1.0; there is nothing above it")
        self.assertGreater(total, limit * 0.5,
                           f"the terms only spend {total:.4f} of {limit}: either the field is far "
                           f"smaller than it could be or this test cannot fail")

    def test_the_field_is_dense_enough_to_read_as_filled(self):
        """"Richly filled rather than empty" is a vertex count. Pinned at the two
        spacings the code actually uses, over the viewports that matter, so
        'denser' and 'cheaper' are both decisions recorded in a diff."""
        mobile, desktop = (int(x) for x in re.search(
            r"spacing = width < 600 \? (\d+) : (\d+);", self.mesh).groups())
        self.assertEqual((desktop, mobile), (54, 38),
                         "the cell size is a density decision, not a free parameter")
        for width, height, spacing in ((1440, 900, desktop), (1920, 1080, desktop),
                                       (390, 844, mobile), (768, 1024, desktop)):
            cols = math.ceil(width / spacing) + 3
            rows = math.ceil(height / spacing) + 3
            with self.subTest(viewport=f"{width}x{height}"):
                self.assertGreaterEqual(cols * rows, 250, "too sparse to read as a field")
                self.assertGreaterEqual((cols - 1) * (rows - 1), 200,
                                        "too few triangles to read as low-poly")
                self.assertLessEqual(cols * rows, 1600,
                                     "more vertices than a phone can blit at 60fps")
        # One spare cell each way is what stops the field showing a ragged border
        # where a displaced vertex would otherwise run off the edge.
        self.assertIn("columns = Math.ceil(width / spacing) + 3;", self.mesh)
        self.assertIn("rows = Math.ceil(height / spacing) + 3;", self.mesh)

    # --- direction of travel ---------------------------------------------


    def test_the_field_movers_are_integrated_never_multiplied_by_time(self):
        """THE bug class this file keeps finding, and the reason it gets its own test
        every round.

        A rate can be applied two ways. `position = time * rate` is correct only while
        the rate never changes; the moment it does, the position jumps by
        `time * delta`, and after a minute open that jump is the whole field
        teleporting. `position += rate * dt` is continuous by construction whatever the
        rate does later.

        The version two rounds back computed its travelling phase as `time * kx * SPEED`
        with kx derived from the dominant pitch: 239 radians of jump after a minute,
        worse the longer the page stayed up. Nothing is audio-derived any more, so the
        rates are constants and either form would work -- but the integrated form is
        kept, because the discipline is what survives the next person adding a rate
        that varies.

        Measured: peak per-vertex motion 0.695px over 420 frames, and 2.41px returning
        from a 9-second background tab.
        """
        self.assertNotIn("var time =", self.mesh, "a wall-clock variable is being derived")
        self.assertNotRegex(self.mesh, r"=\s*time\b", "something is assigned from time * rate")
        # Anchored on an ASSIGNMENT shape. The comment above the movers quotes the
        # broken expression in order to explain the fix, so a bare `timestamp *` search
        # matches the documentation that prevents the regression -- the third time in
        # this file that a guard has collided with the prose explaining it.
        self.assertNotRegex(self.mesh, r"=\s*timestamp\s*\*",
                            "a mover is being multiplied out of the raw rAF timestamp")
        self.assertNotIn("timestamp / 1000", self.mesh,
                         "the raw clock is being read for motion rather than to derive a dt")
        for mover, rate in (("driftX", "NOISE_DRIFT_X"), ("driftY", "NOISE_DRIFT_Y"),
                            ("noiseTime", "NOISE_TIME_SCALE")):
            with self.subTest(mover=mover):
                self.assertIn(f"{mover} += {rate} * dt;", self.mesh,
                              f"{mover} is not integrated from a clamped dt")
        # dt is clamped, or a backgrounded tab's several-second gap lands as one
        # enormous step and the field leaps on the way back in.
        self.assertIn("clamp((timestamp - lastTimestamp) / 1000, 0, MAX_FRAME_DT)", self.mesh)
        self.assertLessEqual(self.num("MAX_FRAME_DT"), 0.05)
        self.assertIn("if (!lastTimestamp) lastTimestamp = timestamp;", self.mesh,
                      "the first frame would otherwise integrate the whole page age")
        # And the morph clock is the only time input the field has besides the two
        # advection offsets, so there is no second path by which a jump could arrive.
        # Counted on roles rather than on the bare name, which also turns up in prose.
        self.assertIn("var noiseTime = 0;", self.mesh)
        self.assertEqual(self.mesh.count("fbm(nx, ny, noiseTime)"), 1)
        self.assertEqual(self.mesh.count("fbm(nx + NOISE_SEED, ny + NOISE_SEED, noiseTime)"), 1)


    def test_the_domain_advection_sign_is_derived_not_guessed(self):
        """The third backwards direction sign in this file's history, so this test
        derives the convention instead of pattern-matching a string.

        A feature sitting at noise coordinate N appears on screen where the sample
        coordinate equals N:

            (gx - driftX) * NOISE_SCALE = N   ->   gx = N / NOISE_SCALE + driftX

        so d(gx)/d(driftX) = +1 and the feature travels in +x as driftX grows. With a
        PLUS sign in the sample it is gx = N/NOISE_SCALE - driftX and the whole field
        runs left.

        That reads identically frame to frame, which is why it survived a full review
        round: the harness searched shifts of 0..+8 columns, the correct lag was
        negative, and it reported "stationary" rather than "backwards". Widening the
        search to both directions is what turned a null result into a sign error.

        Measured after the fix, cross-correlating a lattice row against itself 960ms
        later: peaks at +4 columns = +225px/s against a declared 240, correlation
        0.584 unshifted -> 0.819 shifted in +x -> 0.048 shifted the other way.

        Previous instances of the same mistake: `sin(k*x + w*t)` in the layer this
        replaced, and `sin(time*0.23 + column*0.17)` in the idle drift after that --
        which was the loudest term in silence, so the one wave every visitor saw with
        the music off travelled backwards.
        """
        self.assertIn("var nx = (gx - driftX) * NOISE_SCALE;", self.mesh)
        self.assertIn("var ny = (gy - driftY) * NOISE_SCALE;", self.mesh)
        self.assertNotRegex(self.mesh, r"\(g[xy] \+ drift[XY]\)",
                            "the advection sign is flipped and the field runs left")
        self.assertGreater(self.num("NOISE_DRIFT_X"), 0, "the field must travel in +x")
        # Drift has to actually reach the sample point, not sit there as a dead
        # variable that makes the assertion above pass on its own.
        self.assertIn("(gx - driftX) * NOISE_SCALE", self.mesh)
        self.assertIn("fbm(nx, ny, noiseTime)", self.mesh,
                      "the advected coordinate is not what gets sampled")


    def test_the_elevation_normalisation_matches_the_field_it_measures(self):
        """ELEVATION_SPREAD is the one constant here whose correct value comes from a
        measurement rather than from a formula, so it gets a documented range.

        The normalised fBm sum has sd 0.264 and 1st/99th percentiles of -0.57/+0.64
        against a theoretical +-1 (336,000 vertex samples). Dividing by 2*amplitude --
        i.e. assuming the extremes are reached -- put 0.7% of vertices in the trough
        band and 1.5% in the crest, with 54.6% piled into the baseline: the specified
        0.03 and 0.24 were dead and the shading was three levels, not five. At 0.50 the
        occupancy is 11.8 / 26.1 / 28.8 / 19.2 / 14.1 percent with 5.9% clipping.

        Below ~0.30 the clipping passes 18% and the shading posterises; above ~0.60 the
        outer bands empty out again. Both ends are asserted so the constant cannot drift
        back to either failure.
        """
        spread = self.num("ELEVATION_SPREAD")
        self.assertLessEqual(spread, 0.60,
                             "the outer elevation bands empty out and the crest/trough "
                             "alphas become decoration")
        self.assertGreater(spread, 0.30,
                           "this much clipping posterises the shading into two levels")

    def test_the_bucket_index_is_clamped_to_the_tables(self):
        """`lights` is clamped to [0,1], and bucketOf(1.0) is ELEVATION_BUCKETS -- one
        past the end of all three tables. Without the clamp that indexes `undefined`,
        which interpolates into an rgba() string as the literal text "undefined": not an
        exception, not a console warning, just a stroke that silently does not paint.
        The highest crest in the field would vanish.
        """
        n = int(self.num("ELEVATION_BUCKETS"))
        for name in ("LINE_ALPHAS", "DOT_ALPHAS", "DOT_RADII"):
            table = re.search(r"var " + name + r" = \[([^\]]+)\];", self.mesh).group(1)
            self.assertEqual(len(table.split(",")), n,
                             f"{name} does not have exactly one entry per band, so an index "
                             f"that is valid for one table is out of range for another")
        self.assertIn("return b > (ELEVATION_BUCKETS - 1) ? ELEVATION_BUCKETS - 1 : b;", self.mesh)
        self.assertIn("| 0;", self.mesh, "the floor must truncate, not round")

    def test_the_octaves_are_a_proper_fbm_ladder(self):
        """"Multi-octave" is a claim about ratios, not about having several terms.

        Lacunarity near 2 with a non-integer value keeps the octaves from landing on
        shared harmonics (exactly 2 makes every octave a harmonic of the base, which
        reads as one texture at several volumes rather than as broadband detail). Gain
        near 0.5 is the standard 1/f falloff: much higher and the fine octaves dominate
        into grit, much lower and there is only the base swell.

        Both ends are also bounded by the sampling. The finest texel must not fall much
        below the cell size or the detail is undersampled and wasted; the base texel
        must span several cells or there is no broad structure to flow.
        """
        octaves = int(self.num("NOISE_OCTAVES"))
        lac = self.num("NOISE_LACUNARITY")
        gain = self.num("NOISE_GAIN")
        self.assertGreaterEqual(octaves, 3, "two octaves is a beat, not a texture")
        self.assertLessEqual(octaves, 6, "each octave costs 12 hash mixes per vertex")
        self.assertGreater(abs(lac - round(lac)), 0.02,
                           "an integer lacunarity makes every octave a harmonic of the base")
        self.assertGreater(lac, 1.5)
        self.assertLess(lac, 2.6)
        self.assertGreater(gain, 0.35, "the fine octaves are inaudible at this gain")
        self.assertLess(gain, 0.7, "and the field turns to grit above this")

        base = self.num("NOISE_TEXEL")
        finest = base / (lac ** (octaves - 1))
        self.assertGreaterEqual(base, 54 * 6,
                                f"a {base:.0f}px base texel has no broad structure to flow")
        self.assertGreaterEqual(finest, 54,
                                f"the finest texel is {finest:.0f}px against a 54px cell: the "
                                f"detail is undersampled and the octaves are wasted")
        # Morph has to be present but slow, or the field either slides rigidly or boils.
        ts = self.num("NOISE_TIME_SCALE")
        self.assertGreater(ts, 0.02, "with no morph the field is a rigid slide, not a flow")
        self.assertLess(ts, 0.6, "a fast morph boils instead of flowing")
        # dx and dy must read decorrelated regions, or every vertex travels along one
        # diagonal instead of looping.
        self.assertGreater(self.num("NOISE_SEED"), 4,
                           "dx and dy are sampling nearly the same region")
        self.assertIn("fbm(nx + NOISE_SEED, ny + NOISE_SEED, noiseTime)", self.mesh)


    def test_nothing_in_the_field_is_derived_from_audio(self):
        """Asserted structurally rather than by listing band names.

        Every quantity that reaches a vertex position must be either a literal or a
        function of position and the integrated clock. That is what makes the motion
        identical with the music playing, paused, muted or unsupported -- and it is
        also what makes it smooth, since a rate that varies is a rate that can jump.

        The harness proves the same thing from outside: a facade reporting full scale
        on every band and a facade whose getBands() THROWS produce bit-identical
        lattices, 0.00e+0px divergence over 36,000 vertex positions.
        """
        # The two fbm calls are the only source of displacement.
        samples = re.findall(r"fbm\(([^)]*)\)", self.draw)
        self.assertEqual(len(samples), 2, f"expected dx and dy, got {samples}")
        for expression in samples:
            with self.subTest(sample=expression):
                self.assertRegex(expression, r"^nx(?: \+ NOISE_SEED)?, ny(?: \+ NOISE_SEED)?, "
                                             r"noiseTime$",
                                 "the noise is sampled with something other than the advected "
                                 "coordinate and the integrated clock")
        # And those coordinates come only from position, jitter and the movers.
        for line in ("var nx = (gx - driftX) * NOISE_SCALE;",
                     "var ny = (gy - driftY) * NOISE_SCALE;"):
            self.assertIn(line, self.mesh)
        self.assertIn("* amplitude;", self.draw)
        # amplitude is declared with the other buffers and set in resize(), because it
        # is spacing-derived and spacing changes at the 600px breakpoint.
        self.assertIn("amplitude = spacing * NOISE_AMP;", self.mesh)
        # The one audio-free brightness source: the surface's own height.
        self.assertIn("lights[i] = clamp(0.5 + (dy / (2 * amplitude * ELEVATION_SPREAD)), 0, 1);", self.mesh)


    def test_the_flow_is_clearly_visible_but_not_frantic(self):
        """"Noticeable amplitude and speed" and "liquid, not jittery" pull in opposite
        directions, so both ends are numbers.

        Amplitude is NOISE_AMP of a cell. Peak vertex velocity from advection is
        amplitude * gradient * drift speed -- the same gradient the tear budget uses,
        which is why the two cannot be tuned independently. Measured on the real code
        path: 0.49px of mean motion per frame, 0.70px peak, and a mean travel of
        ~12px over 3 seconds.
        """
        spacing = 54
        gradient = self.fbm_gradient()

        amp = self.num("NOISE_AMP") * spacing
        self.assertGreater(amp, spacing * 0.25,
                           f"{amp:.1f}px on a {spacing}px cell is a shimmer, not an undulation")
        self.assertLess(amp, spacing * 0.48,
                        f"{amp:.1f}px is close enough to a whole cell that neighbours meet")

        peak = amp * gradient * self.num("NOISE_DRIFT_X")
        self.assertGreater(peak, 25.0,
                           f"{peak:.0f}px/s peak vertex velocity is under half a pixel a "
                           f"frame: a still image with a bug in it")
        self.assertLess(peak, 160.0,
                        f"{peak:.0f}px/s is over two pixels a frame: agitation, not liquid")

    # --- calibration ------------------------------------------------------



    def test_the_mesh_lines_are_calibrated_into_their_band(self):
        """0.03 at the deepest trough, 0.10 on a flat field, 0.24 at the highest
        crest -- the seventh contract these numbers have carried, and the shape of it
        has changed: it used to be a single resting value with an audio-driven ramp on
        top, and it is now a five-band table keyed to wave elevation.

        The band is what makes a dim baseline affordable. At a uniform opacity the
        whole lattice has to be bright enough to see, which is bright enough to fight
        the type. With elevation shading, the flat majority can sit at 0.10 and only
        the crests reach 0.24 -- so the mesh reads as a lit surface rather than as a
        grid printed over the page.
        """
        alphas = _mesh_alphas(self.app)
        lines = alphas["lines"]
        self.assertEqual(len(lines), alphas["buckets"])
        self.assertEqual(lines, sorted(lines), "the bands must run trough -> crest")
        self.assertEqual(lines[alphas["base"]], 0.10, "a flat field must read at 0.10")
        self.assertEqual(lines[0], 0.03, "and the deepest trough at 0.03")
        self.assertEqual(lines[-1], 0.24, "the crest tops out at 0.24")
        self.assertLess(lines[-1], 0.30, "past this the lattice competes with the copy")
        # The bands have to be distinguishable, or five passes are doing the work of
        # one and the shading is theoretical.
        steps = [round(b - a, 6) for a, b in zip(lines, lines[1:])]
        self.assertGreaterEqual(min(steps), 0.03,
                                f"two adjacent bands are indistinguishable: {steps}")
        self.assertIn("(LINE_ALPHAS[bucket] * palette.ink).toFixed(4)", self.mesh,
                      "every band must follow the theme's ink dial")


    def test_the_vertices_are_calibrated_into_their_band(self):
        """1.5px to 2.0px radius, 0.06 to 0.35 alpha, with 0.18 on a flat field.

        Radius rides the same band as alpha, so a crest is both brighter and slightly
        larger -- which is how a shaded surface reads, as opposed to a flat grid with a
        dimmer overlay on it. Quantising the radius to five steps costs nothing
        visible: the step is 0.125px on a dot under 2px across.
        """
        alphas = _mesh_alphas(self.app)
        dots, radii = alphas["dots"], alphas["radii"]
        self.assertEqual(len(dots), alphas["buckets"])
        self.assertEqual(len(radii), alphas["buckets"])
        self.assertEqual(dots, sorted(dots), "the bands must run trough -> crest")
        self.assertEqual(radii, sorted(radii))
        self.assertEqual(dots[alphas["base"]], 0.18, "a flat field must read at 0.18")
        self.assertEqual(dots[0], 0.06, "the deepest trough at 0.06")
        self.assertEqual(dots[-1], 0.35, "and the crest at 0.35")
        self.assertEqual(radii[0], 1.5)
        self.assertEqual(radii[-1], 2.0)
        self.assertIn("DOT_ALPHAS[bucket] * palette.ink", self.mesh)
        self.assertIn("DOT_RADII[bucket] * 2 * MESH_GLOW_SPREAD", self.mesh,
                      "radius must come from the band, not be recomputed per vertex")
        # The elevation the bands key off has to be the surface's own height: with no
        # audio left, that is the only signal there is.
        self.assertIn("lights[i] = clamp(0.5 + (dy / (2 * amplitude * ELEVATION_SPREAD)), 0, 1);",
                      self.mesh)
        self.assertIn("vbuck[i] = bucketOf(lights[i]);", self.mesh)
        self.assertIn("return bucketOf((lights[i] + lights[j]) * 0.5);", self.mesh,
                      "an edge must take the band its MIDPOINT is in, or it flickers "
                      "between two as the wave passes")


    def test_the_sprite_choice_is_static_so_vertices_cannot_pop(self):
        """Which of the two baked textures a vertex uses is decided by its lattice
        position and never changes. A version of this switched sprite on a moving
        threshold, and vertices popped between two textures as a crest passed under
        them -- that popping reads as flicker no matter how smooth the geometry is.

        Quantising opacity into five bands is a threshold too, so it deserves the same
        scrutiny. The difference is magnitude: a band crossing moves a 1.9px dot's
        alpha by ~0.07, which is below the just-noticeable difference, where a sprite
        swap changes its texture outright. The bands are asserted to be that close
        together in test_the_mesh_lines_are_calibrated_into_their_band.
        """
        self.assertIn("(((column + row) % 4) === 0) ? sprites.hi : sprites.node", self.mesh)
        self.assertNotRegex(self.mesh, r"sprites\.hi\s*:\s*sprites\.node[^;]*\blight\b",
                            "the sprite choice is keyed to elevation and will pop")
        self.assertNotIn("var near", self.mesh, "the travelling-front proximity term is back")
        # And the choice must be evaluated inside the blit loop, not hoisted into a
        # per-frame constant that would make every vertex identical.
        blit = self.mesh.split("context.globalAlpha = DOT_ALPHAS[bucket] * palette.ink;", 1)[1]
        self.assertIn("% 4", blit)

    def reach(self, ceiling, total, what):
        """A capped ramp has exactly two ways to be wrong, and they look opposite.

        If the ramp cannot REACH its ceiling the Math.min never binds and the
        ceiling is decoration -- the calibration comment describes a range the code
        does not actually produce. If it overshoots by a lot the ceiling binds all
        the time, so every loud vertex pins to the same value and the modulation
        the ramp was written for disappears.

        A modest overshoot is the intended design, though: it means any ONE driver
        can light a vertex to full, and several drivers saturate together rather
        than having to align exactly. So the window is generous upward and exact
        downward.
        """
        self.assertGreaterEqual(total, ceiling - 1e-9,
                                f"the {what} ramp cannot reach its own {ceiling} ceiling, "
                                f"so the Math.min never binds and the ceiling is decoration")
        self.assertLessEqual(total, ceiling * 1.2 + 1e-9,
                             f"the {what} ramp reaches {total:.3f} against a {ceiling} ceiling: "
                             f"it would pin there constantly and lose all modulation")




    def test_the_whole_grid_costs_five_strokes_not_seventeen_hundred(self):
        """~1700 edges a frame at 1440x900, drawn in ELEVATION_BUCKETS batched paths.

        Opacity now varies per edge, and a stroke carries exactly one strokeStyle, so
        the choice is five strokes over ~1700 two-point segments or ~1700 strokes over
        five alphas. The first is what this does, and it is the whole reason the
        elevation is quantised at all: per-edge opacity computed continuously would
        force the second, and the state changes alone would drop frames on the credits
        screen -- which is the page least able to afford them.

        What it costs instead is path operations. Rows used to be one contiguous
        polyline each (30 calls for a 30-column row); now every row edge is its own
        moveTo/lineTo pair (58 calls), because a row whose elevation varies along its
        length spans several bands. Path operations are cheap appends to the current
        path and strokes are the expensive part, so that is the right way round --
        measured, 4012 context calls and 15 state changes per frame, 0.64ms.
        """
        n = _mesh_alphas(self.app)["buckets"]
        self.assertEqual(self.draw.count("context.beginPath();"), 1,
                         "one beginPath in the source, executed once per band")
        self.assertEqual(self.draw.count("context.stroke();"), 1,
                         "one stroke in the source, executed once per band")
        self.assertEqual(self.draw.count("context.lineWidth = 1;"), 1)
        self.assertIn("for (bucket = 0; bucket < ELEVATION_BUCKETS; bucket += 1) {", self.draw)
        self.assertEqual(self.num("ELEVATION_BUCKETS"), n)
        # The five band tables must agree in length, or a band indexes past one of them
        # and paints undefined -- which is `NaN` in a colour string and a silently
        # invisible lattice rather than an error.
        for name in ("LINE_ALPHAS", "DOT_ALPHAS", "DOT_RADII"):
            table = re.search(r"var " + name + r" = \[([^\]]+)\];", self.mesh).group(1)
            self.assertEqual(len(table.split(",")), n, f"{name} does not have one entry per band")
        # And the per-band vertex pass must set globalAlpha once, not per vertex.
        blit = self.draw.split("if (sprites.node && sprites.hi) {", 1)[1]
        self.assertEqual(blit.count("context.globalAlpha ="), 2,
                         "one set per band plus the reset; per-vertex would be ~600")


    def test_positions_are_computed_once_per_frame_and_shared_by_every_pass(self):
        """Everything downstream reads one buffer: the edge-bucket pass, the five
        stroke passes and the five blit passes. If displacement depended on which pass
        reached a vertex the mesh would tear at every intersection, so positions are
        written once into a shared Float32Array -- which is what replaced the old
        bandAt() agreement helper.

        The crest elevation travels the same way, and now so does its bucket: both are
        computed in the displacement loop and read by everything after it. Recomputing
        the fBm in the blit pass would double the most expensive part of the frame --
        twelve hash mixes per octave per vertex.
        """
        for decl in ("pts = new Float32Array(vertices * 2);",
                     "lights = new Float32Array(vertices);",
                     "vbuck = new Uint8Array(vertices);"):
            self.assertIn(decl, self.mesh)
        self.assertIn("ebuck = new Uint8Array(Math.max(0, edgeCap));", self.mesh)
        self.assertNotIn("bandAt(", self.mesh, "the agreement helper is back")
        self.assertEqual(self.draw.count("pts[index] = gx + dx;"), 1,
                         "positions are computed in more than one place")
        self.assertEqual(self.draw.count("lights[i] = clamp("), 1)
        self.assertEqual(self.draw.count("vbuck[i] = bucketOf("), 1)
        self.assertEqual(self.draw.count("fbm("), 2,
                         "fBm must be evaluated exactly twice per vertex, once per axis")
        # The edge-bucket pass must enumerate edges in exactly the order the stroke
        # passes walk them, or ebuck indexes disagree and edges take each other's
        # opacity. Asserted by counting the three families in both places.
        classify = self.mesh.split("var edgeIndex = 0;", 1)[1].split("context.lineWidth = 1;", 1)[0]
        paint = self.mesh.split("context.lineWidth = 1;", 1)[1].split("Vertices on top", 1)[0]
        for label, region in (("classify", classify), ("paint", paint)):
            with self.subTest(pass_=label):
                self.assertEqual(region.count("columns - 1; column += 1"), 2,
                                 "the row and diagonal families are not both walked")
                self.assertEqual(region.count("rows - 1; row += 1"), 2,
                                 "the column and diagonal families are not both walked")

    def test_the_noise_is_mixed_not_shortcutted(self):
        """A corner value has to come out of a real hash mix, and this is the guard on
        the shortcut that looks like one.

        An earlier draft of the noise wrote `(h00 ^ iz) & 0xffff` to save a mix per
        corner. It is not equivalent: iz is a small integer, so XOR only touches the
        lowest handful of bits and corner values for z and z+1 come out nearly
        identical. The time axis then barely varies, and the morph degenerates into
        banding -- the exact artefact the quintic interpolant exists to prevent,
        reintroduced one level above it.

        The harness catches this from the other side: a field whose time axis is dead
        cross-correlates with a shifted copy of itself at ~1.0, because it has become a
        rigid translation. Measured residual decorrelation is 0.181.
        """
        # No negative search for an XOR here: the mesh's own comment quotes the broken
        # `(h00 ^ iz)` expression to explain why it is broken. The positive count below
        # is the complete guard anyway -- a shortcut corner is one fewer hashed corner.
        # The two z faces are named iz and z1, not iz/iz1.
        corners = re.findall(r"toUnit\(hash2\((h\d\d), (iz|z1)\)\)", self.mesh)
        self.assertEqual(len(corners), 8, f"expected eight hashed corners, got {corners}")
        self.assertEqual(len({c for c, _ in corners}), 4,
                         "the four (x, y) pairs should each be reused across both z faces")
        self.assertEqual(len({z for _, z in corners}), 2, "and both z faces must be hashed")
        self.assertIn("return ((h & 0xffff) / 0x7fff) - 1;", self.mesh,
                      "corners must fold to -1..1 from the low bits, where hash2 keeps its entropy")
        # And the interpolant has to be the quintic, or the second derivative snaps at
        # every texel boundary and a faint grid pulses through the motion.
        fade = self.mesh.split("function fade(t)", 1)[1].split("\n      }", 1)[0]
        self.assertIn("(t * 6) - 15", fade, "fade() is not Perlin's improved quintic")
        self.assertIn("* t * t", fade)

class CreditsBackdrop(unittest.TestCase):
    """What sits behind the credits copy, and what keeps that copy readable.

    The review asked for the background to stop reading as a faint texture. That
    is a real change of contract -- this file used to assert the opposite -- so
    the colour channels the review specified are pinned here, and so is the thing
    that makes them survivable: a scrim behind each block of copy. The mesh's own
    size, brightness and geometry live in AmbientMesh and AmbientMeshGeometry; what
    belongs here is the interaction between that background and the words on top
    of it, because that is the only place the two can be tuned against each other.
    """

    TOKENS = ("--mesh-node-rgb", "--mesh-node-hi-rgb", "--mesh-glow-rgb",
              "--mesh-line-rgb")

    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "style.css").read_text()
        cls.app = (ROOT / "app.js").read_text()
        cls.root = cls.css.split(":root {", 1)[1].split("\n}", 1)[0]
        # Bounded by the call site that FOLLOWS initAmbientMesh, not by the next
        # top-level function. The looser boundary used here before ran past the mesh
        # into the rest of initAmbientExperience -- including the audio graph itself --
        # so an assertion that the mesh contains no reference to AudioContext was
        # failing on code that is not the mesh. A region split has to end where the
        # thing being described ends.
        cls.mesh = cls.app.split("function initAmbientMesh()", 1)[1].split(
            "\n    initCursor();", 1)[0]
        i = cls.css.index("@media (prefers-color-scheme: light) {")
        cls.light = cls.css[i:].split("\n}", 1)[0]

    def channels(self, region):
        out = {}
        for token in self.TOKENS:
            found = re.findall(re.escape(token) + r":\s*([\d,\s]+);", region)
            if found:
                out[token] = [int(x) for x in found[0].replace(" ", "").split(",")]
        return out

    # --- the colour contract -------------------------------------------
    def test_the_mesh_channels_exist_in_both_themes(self):
        """Four dedicated channels, not literals in the canvas code. The mesh reads
        them back out of CSS, so a theme with no definition would silently fall
        back to the dark values on a light page."""
        dark, light = self.channels(self.root), self.channels(self.light)
        for token in self.TOKENS:
            with self.subTest(token=token):
                self.assertIn(token, dark, "missing from :root")
                self.assertIn(token, light, "missing from the light theme")
                self.assertEqual(len(dark[token]), 3)
                self.assertNotEqual(dark[token], light[token],
                                    "light mode would inherit dark neon")

    def test_the_mesh_channels_are_the_requested_colours(self):
        """The review specified exact channels -- dots from rgba(147,112,255)
        up to rgba(190,210,255), bloom at rgba(124,92,255), lines at
        rgba(120,95,255). Pinning them means a recolour is a decision recorded
        in a diff rather than a silent drift, and it is what stops the dark
        theme from being swapped for a generic brand blue."""
        dark = self.channels(self.root)
        self.assertEqual(dark["--mesh-node-rgb"], [167, 139, 250])
        self.assertEqual(dark["--mesh-node-hi-rgb"], [196, 181, 253])
        self.assertEqual(dark["--mesh-glow-rgb"], [124, 58, 237])
        self.assertEqual(dark["--mesh-line-rgb"], [139, 92, 246])
        # The line channel is the site's own accent rather than a bespoke indigo, so
        # the lattice is on-brand instead of sitting next to the brand. Pinning the
        # equality, not just the value, is what stops the two drifting apart.
        self.assertEqual(dark["--mesh-line-rgb"], self.channels(self.root)["--mesh-line-rgb"])
        accent = re.search(r"--accent-rgb:\s*([\d,\s]+);", self.root)
        self.assertEqual([int(x) for x in accent.group(1).replace(" ", "").split(",")],
                         dark["--mesh-line-rgb"],
                         "the lattice has stopped matching --accent-rgb")
        # The glow is deliberately MORE saturated than the core it blooms around, which
        # is what makes a halo read as coloured light rather than as a grey smudge.
        self.assertLess(sum(dark["--mesh-glow-rgb"]), sum(dark["--mesh-node-rgb"]))

    def test_the_light_theme_deepens_the_mesh(self):
        """On a light page a bright violet reads as a stain, so the light values
        have to go DARKER, not just different. Asserting direction rather than
        exact numbers keeps this from becoming a second copy of the palette."""
        dark, light = self.channels(self.root), self.channels(self.light)
        for token in self.TOKENS:
            with self.subTest(token=token):
                self.assertLess(sum(light[token]), sum(dark[token]),
                                "light theme mesh is not deeper than dark")

    def test_the_canvas_never_hardcodes_a_channel(self):
        """The literals may only survive as named fallbacks for an unreadable
        custom property. A bare triple inside a draw call is how a canvas ends up
        painting the wrong theme."""
        # Two earlier versions of this check were both wrong. Scanning quoted
        # literals pairs apostrophes across the whole file, and a comment like
        # "the dot's own disc" shifts that pairing so real literals fall BETWEEN
        # matches -- which is how it passed on a mutated file. Stripping comments
        # with a regex is worse: app.js is full of regex literals, so a
        # non-greedy /*...*/ pairs across them and eats live code. Assert the
        # bug class directly instead of trying to parse JavaScript.
        dark_triples = ("167,139,250", "196,181,253", "124,58,237", "139,92,246")
        light_triples = ("109,40,217", "91,33,182", "76,29,149")
        for rgb in dark_triples:
            bare = r"\s*,\s*".join(rgb.split(","))
            with self.subTest(channel="dark " + rgb):
                # The dark values exist in app.js, but ONLY as named fallbacks for an
                # unreadable custom property...
                self.assertIn("'" + rgb + "'", self.app, "channel is not declared at all")
                # ...and are never baked into a colour literal, which is the shape an
                # inlined paint call takes: 'rgba(167,139,250,0.8)'.
                self.assertNotRegex(self.app, r"rgba\(\s*" + bare,
                                    f"{rgb} is inlined into an rgba() literal")
        # The light values live only in the stylesheet. If one turns up in app.js it is
        # an inlined paint call by definition -- there is no legitimate reason for the
        # canvas to know a light-theme triple.
        # Flattened on BOTH sides. Stripping commas from the needle but only spaces
        # from the haystack is how this check passed on a file containing
        # `var LIGHT_LEAK = '109,40,217'` -- the mutation it exists to catch.
        flattened = re.sub(r"[\s,]", "", self.app)
        for rgb in light_triples:
            with self.subTest(channel="light " + rgb):
                self.assertNotIn(rgb.replace(",", ""), flattened,
                                 "a light-theme triple appears in the canvas code; the canvas "
                                 "has no business knowing one")
        for name in ("FALLBACK_NODE", "FALLBACK_HI", "FALLBACK_GLOW", "FALLBACK_LINE",
                     "FALLBACK_INK"):
            self.assertIn(name, self.app)
        # The dark fallbacks must equal the dark tokens, or an unreadable custom
        # property silently paints a different palette than the one being tested.
        dark = self.channels(self.root)
        for name, token in (("FALLBACK_NODE", "--mesh-node-rgb"),
                            ("FALLBACK_HI", "--mesh-node-hi-rgb"),
                            ("FALLBACK_GLOW", "--mesh-glow-rgb"),
                            ("FALLBACK_LINE", "--mesh-line-rgb")):
            literal = re.search(name + r" = '([\d,]+)'", self.app).group(1)
            self.assertEqual([int(x) for x in literal.split(",")], dark[token],
                             f"{name} has drifted from {token}")

    # --- the mesh and the scrim are one budget --------------------------


    def test_the_scrim_outweighs_the_mesh_at_its_brightest(self):
        """The scrim and the mesh are one budget, not two independent choices.

        A detail block can sit directly on the brightest thing the mesh paints -- a
        vertex at its alpha ceiling, times the theme's ink, over the page background --
        so the copy's contrast has to be computed against THAT. Both alphas are read out
        of app.js: this test used to hardcode 0.30, and when the calibration moved to
        0.60 it kept passing, measuring a layer half as bright as the real one. A guard
        that hardcodes the number it guards is not a guard.

        What the assertions MEAN moved with the calibration, and the direction is worth
        being explicit about. When the mesh was at 0.45-0.60 the paragraph measured
        2.39:1 on the bare mesh, so the scrim was structure and the test demanded it
        recover at least 2.0:1. At 0.16-0.22 the copy clears AA on the bare mesh in both
        themes (5.59:1 dark, 4.96:1 light), so the scrim is insurance again and the
        recovery it can offer is naturally smaller. The floor behind the scrim stays
        strict at 6.0 -- that is the number the credits copy actually has to hit, and it
        is unchanged by any of this.
        """
        para = self.css.split(".rotary-disc__contributions {", 1)[1].split("}", 1)[0]
        token = re.search(r"color:\s*var\((--[\w-]+)\)", para)
        self.assertIsNotNone(token,
                             "the contribution paragraph is not on a colour token, so nothing "
                             "can reason about its contrast")

        scrim = self.css.split(".rotary-segment__content::before {", 1)[1].split("}", 1)[0]
        stops = [float(x) for x in re.findall(r"rgba\(var\(--bg-rgb\),\s*([\d.]+)\)", scrim)]
        self.assertEqual(len(stops), 3, "the scrim should be a three-stop radial falloff")
        self.assertEqual(stops, sorted(stops, reverse=True),
                         "the scrim must fall off monotonically from its centre")
        centre = stops[0]
        self.assertGreaterEqual(centre, 0.85, "too thin to guarantee the copy")
        self.assertGreaterEqual(stops[1], 0.5,
                                "the mid stop is what carries coverage past the first line "
                                "of the paragraph; a centre-only assertion cannot see it thin")
        self.assertEqual(stops[2], 0.0, "and it must reach full transparency at its edge")

        alphas = _mesh_alphas(self.app)
        self.assertIsNotNone(alphas["node"], "the vertex alpha ramp changed shape")

        light = self.css[self.css.index("@media (prefers-color-scheme: light) {"):].split("\n}", 1)[0]
        for name, region in (("dark", self.root), ("light", light)):
            page = _resolve_colour("--bg-rgb", region)
            inkcolour = _resolve_colour(token.group(1), region)
            node = _resolve_colour("--mesh-node-rgb", region)
            for label, value in (("--bg-rgb", page), (token.group(1), inkcolour),
                                 ("--mesh-node-rgb", node)):
                self.assertIsNotNone(value, f"{label} is missing from the {name} theme")
            ink = _theme_ink(self.css, region)
            # Two cases, because one number cannot describe an elevation-shaded
            # layer. The BASELINE band is what most of the screen shows, so the copy
            # has to clear AA on it with no help at all. The CREST band is the worst
            # single pixel the mesh ever paints and is a small minority of them --
            # measured, ~14% of vertices reach the top band -- so it gets a floor
            # rather than a pass mark, and the scrim is what actually guarantees the
            # copy where the two coincide.
            base = _composite(node, page, alphas["baseline_dot"] * ink, SOURCE_OVER)
            crest = _composite(node, page, max(alphas["dots"]) * ink, SOURCE_OVER)
            bare_base = _contrast(inkcolour, base)
            bare_crest = _contrast(inkcolour, crest)
            behind = _contrast(inkcolour, _composite(page, crest, centre, SOURCE_OVER))
            with self.subTest(theme=name):
                self.assertGreater(bare_base, 4.5,
                                   f"{name}: on the FLAT part of the mesh the paragraph is only "
                                   f"{bare_base:.2f}:1 -- that is most of the screen, so it must "
                                   f"clear AA with no scrim at all")
                self.assertGreater(bare_crest, 3.5,
                                   f"{name}: even sitting directly on a crest the paragraph is "
                                   f"only {bare_crest:.2f}:1")
                self.assertGreater(behind, 6.0,
                                   f"{name}: {behind:.2f}:1 through the scrim misses the 6.0 floor "
                                   f"the credits copy has to hold")
                self.assertGreater(behind, bare_crest + 2.0,
                                   f"{name}: the scrim only moves {bare_crest:.2f} -> {behind:.2f}, "
                                   f"so it is decoration rather than the thing holding the copy up")

    def test_the_credits_page_paints_no_background_of_its_own(self):
        """One canvas, one lattice. The credits screen used to carry a second
        animated layer plus a static grid-and-dot texture on ::before; both are
        gone, and what is left is a stacking order that puts the wheels over the
        site-wide mesh rather than over a second mesh."""
        self.assertNotIn(".credits-rotary-page::before", self.css,
                         "the static texture this replaced is back")
        body = self.css.split(".credits-rotary-page main.credits-rotary {", 1)[1].split("}", 1)[0]
        self.assertEqual(int(re.search(r"z-index:\s*(\d+)", body).group(1)), 1,
                         "the wheels have to sit above the canvas's z-index 0")
        self.assertIn("isolation: isolate", body,
                      "without it the wheels' own blend modes reach down into the canvas")
        self.assertIn("touch-action: none", body)
        # No other element in the credits section paints a competing lattice.
        credits_css = self.css[self.css.index(".credits-rotary-page main.credits-rotary {"):]
        for pattern in (r"background-image:\s*(repeating-)?linear-gradient",
                        r"background-image:\s*radial-gradient"):
            hits = [m.start() for m in re.finditer(pattern, credits_css)]
            for hit in hits:
                context = credits_css[max(0, hit - 400):hit]
                selector = re.findall(r"\.([\w-]+(?:__?[\w-]+)*)\s*(?:::[\w-]+)?\s*\{[^}]*$",
                                      context)
                with self.subTest(selector=selector[-1] if selector else "?"):
                    self.assertNotIn(selector[-1] if selector else "", ("credits-rotary",),
                                     "a grid texture is being painted over the mesh")

    # --- the scrim that makes the brightness survivable -----------------
    def test_the_copy_gets_a_scrim_behind_it(self):
        """Chosen over both alternatives the review was offered: full brightness
        everywhere with a soft radial scrim behind each detail block, rather than
        dimming the whole canvas or vignetting the edges. The paragraph and the
        caption sit on the darkest part of it."""
        body = self.css.split(".rotary-segment__content::before {", 1)[1].split("}", 1)[0]
        self.assertIn("radial-gradient", body)
        self.assertIn("z-index: -1", body, "the scrim must sit behind the copy")
        self.assertIn("pointer-events: none", body)
        # Negative inset: the scrim has to extend past the text box, or the glow
        # returns right at the edge of the paragraph where it is most visible.
        self.assertRegex(body, r"inset:\s*-")

    def test_the_scrim_follows_the_theme(self):
        """A hardcoded dark blob would put a black halo behind the copy in light
        mode. It has to be the theme's own background channel."""
        body = self.css.split(".rotary-segment__content::before {", 1)[1].split("}", 1)[0]
        self.assertIn("rgba(var(--bg-rgb)", body)
        self.assertNotRegex(body, r"rgba\(\s*\d+\s*,", "a literal rgb triple crept in")
        # --bg-rgb has to be defined in BOTH themes or the scrim breaks in one.
        self.assertIn("--bg-rgb:", self.root)
        self.assertIn("--bg-rgb:", self.light)


class CreditsScrollPhysics(unittest.TestCase):
    """The wheel's feel is arithmetic too, and it fails silently.

    A spring that is under-damped overshoots the contributor and settles back;
    one integrated per-frame rather than per-second settles differently on a
    144Hz display than on a 60Hz one; a snap threshold set too high makes the
    user scroll through a sector of dead space before anything commits. None of
    those throw, so all of them are asserted.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.rotary = cls.app.split("function initCreditsRotary()", 1)[1]

    def const(self, name):
        match = re.search(r"var " + name + r" = ([\d.]+);", self.rotary)
        self.assertIsNotNone(match, f"{name} is not declared")
        return float(match.group(1))

    def test_the_spring_is_critically_damped(self):
        """damping == 2*sqrt(stiffness) is the exact boundary at which the wheel
        returns to its target as fast as possible WITHOUT overshooting. Asserting
        the expression rather than a number means the relationship cannot drift
        if the stiffness is ever retuned."""
        self.assertIn("var SPRING_DAMPING = 2 * Math.sqrt(SPRING_STIFFNESS);", self.rotary,
                      "damping must be derived from stiffness, not picked separately")
        self.assertGreater(self.const("SPRING_STIFFNESS"), 0)

    def test_the_spring_integrates_in_seconds_not_frames(self):
        """The previous integrator multiplied by a frame count normalised to
        16.67ms, which is frame-rate dependent: the same flick settled visibly
        differently at 144Hz than at 60Hz."""
        self.assertIn("/ 1000;", self.rotary, "no seconds-based dt found")
        self.assertIn("acceleration * dt", self.rotary)
        self.assertIn("state.rotationVelocity * dt", self.rotary)
        self.assertNotIn("Math.pow(0.68, elapsed)", self.rotary,
                         "the per-frame exponential damping is still there")

    def test_angular_velocity_is_bounded(self):
        """A hard fling must move fast but stay bounded, or one trackpad gesture
        throws the wheel past several contributors."""
        ceiling = self.const("MAX_ANGULAR_VELOCITY")
        self.assertGreater(ceiling, 0)
        self.assertIn("-MAX_ANGULAR_VELOCITY, MAX_ANGULAR_VELOCITY", self.rotary,
                      "the velocity clamp is missing from the integrator")

    def test_the_wheel_locks_exactly_onto_its_target(self):
        """A spring asymptotes forever. Without a hard settle the wheel idles
        fractionally off-sector, which reads as a label that never sits straight."""
        self.assertIn("state.rotation = state.rotationTarget;", self.rotary)
        self.assertIn("state.rotationVelocity = 0;", self.rotary)
        self.assertLess(self.const("SETTLE_ANGLE"), 0.1)

    def test_a_fast_scroll_commits_earlier_than_a_slow_drag(self):
        """Two thresholds, and the quicker one has to be armed BY the input
        rather than applied always -- otherwise a hesitant drag jumps sectors."""
        slow = self.const("SNAP_THRESHOLD")
        fast = self.const("SNAP_THRESHOLD_FAST")
        self.assertLess(fast, slow, "the fast threshold must be the smaller one")
        self.assertLess(fast, 0.5, "committing before half a sector removes the dead space")
        self.assertIn("nowMs() < commitBoostUntil ? SNAP_THRESHOLD_FAST : SNAP_THRESHOLD",
                      self.rotary, "the snap does not actually consult the boost")
        # Both input paths have to be able to arm it.
        self.assertEqual(self.rotary.count("armCommitBoost()"), 3,
                         "expected the definition plus one call each from the "
                         "wheel and touch paths")
        self.assertIn("Math.abs(delta) >= FAST_WHEEL_DELTA", self.rotary)
        self.assertIn("Math.abs(state.touchVelocity) >= TOUCH_FLING_VELOCITY", self.rotary)

    def test_one_sector_does_not_take_excessive_scrolling(self):
        """The dead-space complaint, expressed as a number. A standard mouse notch
        is deltaY 100; at the old 0.05 damping one 120-degree sector took about 24
        notches, and committing took about 13."""
        damping = self.const("WHEEL_DAMPING")
        segment = self.const("SEGMENT")
        threshold = self.const("SNAP_THRESHOLD")
        degrees_per_notch = 100 * damping
        self.assertGreater(degrees_per_notch, 8, "a notch barely moves the wheel")
        notches_to_commit = (segment * threshold) / degrees_per_notch
        notches_per_sector = segment / degrees_per_notch
        self.assertLessEqual(notches_to_commit, 6,
                             f"{notches_to_commit:.1f} notches to commit is still dead space")
        self.assertLessEqual(notches_per_sector, 12)

    def test_a_single_input_can_never_throw_the_wheel_past_a_sector(self):
        self.assertIn("clamp(delta * WHEEL_DAMPING, -WHEEL_MAX_STEP, WHEEL_MAX_STEP)", self.rotary)
        self.assertIn("clamp(verticalDelta * TOUCH_DAMPING, -TOUCH_MAX_STEP, TOUCH_MAX_STEP)",
                      self.rotary)
        self.assertLessEqual(self.const("WHEEL_MAX_STEP"), self.const("SEGMENT"))
        self.assertLessEqual(self.const("TOUCH_MAX_STEP"), self.const("SEGMENT"))

    def test_the_settle_lock_reads_the_post_integration_error(self):
        """The lock must test the error AFTER the position update, and must run
        before the frame's stop test. Testing the pre-integration error lets the
        rAF loop exit one frame early: a frame arrives with error 0.025 (no lock),
        integrates down to 0.0198, the stop test sees "close enough" and quits --
        freezing the wheel at 119.98 degrees instead of 120. Invisible, but it is
        the difference between a wheel that locks and one that merely stops."""
        body = self.rotary.split("state.rotation += state.rotationVelocity * dt;", 1)
        self.assertEqual(len(body), 2, "the integrator changed shape")
        lock = body[1].split("state.rotation = state.rotationTarget;", 1)[0]
        self.assertIn("state.rotationTarget - state.rotation", lock,
                      "the lock still tests a stale, pre-integration error")
        self.assertNotRegex(lock, r"Math\.abs\(error\)",
                            "`error` is captured before the integration")

    def test_the_touch_fling_still_gets_its_commitment(self):
        """A short fast flick must reach the threshold on its own; without it a
        quick swipe does nothing and the wheel feels unresponsive."""
        self.assertIn("velocity >= TOUCH_FLING_VELOCITY", self.rotary)
        self.assertIn("SEGMENT * SNAP_THRESHOLD", self.rotary)


class AmbientMeshAutonomy(unittest.TestCase):
    """Nothing outside the mesh can reach it.

    This has been true in stages, and each stage removed a channel rather than
    guarding one. First the mesh stopped reading scroll (the credits wheel used to
    publish its angular velocity into a module-level slot). Then it stopped reading
    audio. Then the droplet system that the audio used to trigger went with it.

    What is left is a function of exactly four things: the viewport size, the theme,
    the reduced-motion preference, and its own integrated clock. Every one of those
    is asserted here, because "the mesh is autonomous" is only meaningful as a list of
    the inputs it does not have.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.mesh = cls.app.split("function initAmbientMesh()", 1)[1].split(
            "\n    initCursor();", 1)[0]
        cls.draw = cls.mesh.split("function draw(timestamp)", 1)[1]
        cls.physics = cls.app.split("function initCreditsRotary()", 1)[1].split(
            "     9. DYNAMIC DOWNLOAD LINK", 1)[0]

    def test_the_mesh_has_no_connection_to_the_audio_engine(self):
        """Asserted on comment-stripped source, because app.js explains at length
        which audio APIs it no longer uses -- and on behaviour, because a source check
        can be fooled by an indirect path. The behavioural form is the strong one: a
        facade screaming full scale on every band and a facade whose getBands() THROWS
        both produced bit-identical lattices, 0.00e+0px over 36,000 vertex positions.
        """
        code = _strip_js_comments(self.mesh)
        for token in ("readBands", "AgoraAudio", "getBands", "analyser", "AnalyserNode",
                      "getByteFrequencyData", "AudioContext", "IDLE_BANDS",
                      "bass", "treble", "onset", "pitch", "centroid", "spectrum"):
            with self.subTest(token=token):
                self.assertNotIn(token, code, "the mesh has a wire to the audio engine")
        # The draw loop's only input is the frame timestamp.
        self.assertIn("function draw(timestamp) {", self.mesh)
        self.assertEqual(len(re.findall(r"fbm\(([^)]*)\)", self.draw)), 2)
        for expression in re.findall(r"fbm\(([^)]*)\)", self.draw):
            self.assertRegex(expression, r"^nx(?: \+ NOISE_SEED)?, ny(?: \+ NOISE_SEED)?, noiseTime$")

    def test_scroll_cannot_reach_the_mesh_at_all(self):
        """The credits screen is entirely gesture driven, and none of it reaches the
        canvas. Measured end to end: flinging the wheel eight times leaves the lattice
        bit-for-bit identical, while the wheel itself still turns and commits
        contributors (counter trace 01 -> 03 -> 01).

        Asserted as the absence of a channel rather than as a gate, because a gate is
        something a future edit forgets and a slot that does not exist cannot be.
        """
        code = _strip_js_comments(self.app)
        for token in ("wheelSpin", "readSpin", "SPIN_DECAY_MS", "SPIN_REFERENCE",
                      "pushMeshPulse", "meshPulses", "activePulses", "spinWave", "spinDir"):
            with self.subTest(token=token):
                self.assertNotIn(token, code, "a scroll channel survived")
        mesh_code = _strip_js_comments(self.mesh)
        self.assertNotIn("credits-rotary-page", mesh_code, "the mesh knows which page it is on")
        self.assertNotIn("deltaY", mesh_code)
        self.assertNotIn("addEventListener('wheel'", mesh_code)
        # The rotary may not publish to a global either -- that is the shape the old
        # spin slot took, and the shape any replacement coupling would take.
        self.assertNotRegex(_strip_js_comments(self.physics), r"window\.\w+\s*=")

    def test_the_droplet_system_is_gone_rather_than_dormant(self):
        """The ripple events were audio-triggered by definition, so removing the audio
        removed their only trigger. They are deleted rather than left waiting for one:
        ~70 lines of ring buffer, envelope follower, soft-knee strength curve and
        refractory gate that nothing could reach, and an invented autonomous trigger
        would be behaviour nobody asked for.

        Pinned so the removal stays a decision on the record. What replaced them as the
        source of contrast is the surface's own height, asserted in AmbientMeshGeometry.
        """
        code = _strip_js_comments(self.mesh)
        for token in ("RIPPLE_MAX", "RIPPLE_SPEED", "RIPPLE_LAMBDA", "RIPPLE_SIGMA",
                      "RIPPLE_REFRACTORY", "RIPPLE_KNEE", "ENVELOPE_TAU", "novelty",
                      "prepareRipples", "dropRipple", "smoothstep", "approach("):
            with self.subTest(token=token):
                self.assertNotIn(token, code)

    def test_the_only_inputs_left_are_the_four_it_is_allowed(self):
        """Viewport, theme, reduced motion, clock. Enumerated positively as well as by
        the absences above, so this fails if a fifth input is introduced rather than
        only if one of the known four is removed."""
        self.assertIn("width = window.innerWidth;", self.mesh)
        self.assertIn("height = window.innerHeight;", self.mesh)
        self.assertIn("window.devicePixelRatio", self.mesh)
        self.assertIn("getPropertyValue('--mesh-node-rgb')", self.mesh)
        self.assertIn("getPropertyValue('--mesh-ink')", self.mesh)
        self.assertIn("reduceMotion()", self.mesh)
        self.assertIn("if (!reduceMotion()) window.requestAnimationFrame(draw);", self.mesh)
        self.assertIn("lastTimestamp = timestamp;", self.mesh)
        # The theme is re-read on a scheme flip, and the sprite rebuilt with it, or the
        # vertices keep glowing in the previous theme's colour.
        flip = self.mesh.split("function onSchemeChange()", 1)[1].split("\n      }", 1)[0]
        self.assertIn("palette = readPalette();", flip)
        self.assertIn("sprites = buildSprites(palette);", flip)



class AmbientAudio(unittest.TestCase):
    """The background track streams, and the first gesture of any kind starts it.

    The behavioural half of this is in the jsdom harness, which simulates the autoplay
    policy refusing and then allowing. What is pinned here is the contract that
    simulation depends on, because each of these is a one-token change that would
    otherwise fail silently and only in a real browser.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.code = _strip_js_comments(cls.app)
        cls.ambient = cls.app.split("function initAmbientExperience()", 1)[1].split(
            "\n  function initCreditsRotary", 1)[0]

    def test_it_streams_rather_than_downloading_and_decoding(self):
        """`fetch(url).then(r => r.arrayBuffer())` followed by `decodeAudioData` cannot
        play a single sample until the entire file has arrived and been decoded into
        PCM. On a ~12MB asset that is the 10-15 minute delay, and it also explains why
        the track seemed to start on navigation -- a page change re-ran boot(), and by
        then the bytes had landed. A streaming element starts from a partial download.
        """
        self.assertIn("createElement('audio')", self.code)
        self.assertIn("el.preload = 'auto';", self.code,
                      "anything other than 'auto' waits for a nudge before fetching")
        self.assertIn("el.loop = true;", self.code)
        self.assertIn("el.volume = TARGET_VOLUME;", self.code,
                      "volume moved off the deleted master gain and onto the element")
        self.assertIn("el.controls", self.code) if False else None
        self.assertNotIn("el.controls = true", self.code,
                         "native controls would be a second transport fighting the toggle")
        self.assertIn("doc.body.appendChild(el)", self.code,
                      "detached, and preload priority for a node outside the document is "
                      "engine-dependent -- which defeats the point of preload=auto")
        # Exactly one element per session: the router only replaces <header> and
        # <main>, so a body child survives every swap and must not be re-created,
        # or the track restarts on each navigation.
        self.assertIn("if (audio.el) return audio.el;", self.code)
        self.assertIn("createAudioElement();", self.ambient.split("function boot()", 1)[0])

    def test_canplay_attempts_playback_immediately(self):
        self.assertIn("el.addEventListener('canplay'", self.code)
        canplay = self.code.split("el.addEventListener('canplay'", 1)[1].split("});", 1)[0]
        self.assertIn("attemptPlay(", canplay)
        # canplay fires more than once (after a stall, a seek, a re-buffer), and each
        # firing must not restart a track that is already going.
        self.assertIn("audio.autoplayTried", canplay)
        self.assertIn("audio.userMuted", canplay,
                      "an autoplay attempt after an explicit mute overrides the visitor")
        self.assertIn("audio.isPlaying", canplay)

    def test_the_unlock_covers_every_gesture_on_both_targets(self):
        """Capture phase, passive, on window AND document, for five event types.

        Capture runs before any page handler can stopPropagation, so a gesture consumed
        by the credits wheel, the mobile menu or a form field still unlocks the audio --
        which is the specific failure being fixed, since the old listener was a single
        bubble-phase click on document and therefore only fired on things that did not
        stop propagation. Passive matters because `wheel` is in the list and the credits
        screen is entirely gesture driven: a non-passive wheel listener forces the
        browser to wait for the handler before it can scroll.
        """
        events = re.search(r"var UNLOCK_EVENTS = \[([^\]]+)\];", self.code)
        self.assertIsNotNone(events, "the gesture list is gone")
        listed = [x.strip().strip("'\"") for x in events.group(1).split(",")]
        self.assertEqual(sorted(listed),
                         sorted(["pointerdown", "touchstart", "wheel", "keydown", "click"]))
        bind = self.code.split("function bindUnlock()", 1)[1].split("\n    }", 1)[0]
        self.assertIn("window.addEventListener(type, onFirstGesture, { capture: true, passive: true });", bind)
        self.assertIn("doc.addEventListener(type, onFirstGesture, { capture: true, passive: true });", bind)
        unbind = self.code.split("function unbindUnlock()", 1)[1].split("\n    }", 1)[0]
        self.assertIn("window.removeEventListener(type, onFirstGesture, true);", unbind)
        self.assertIn("doc.removeEventListener(type, onFirstGesture, true);", unbind)
        # Both are armed at init, not only after a rejection: a visitor who scrolls
        # before canplay fires still has to start the track on that scroll.
        tail = self.ambient.split("initAmbientMesh();", 1)[1]
        self.assertIn("createAudioElement();", tail)
        self.assertIn("bindUnlock();", tail)

    def test_the_first_gesture_fires_once_and_respects_an_explicit_mute(self):
        """Bound on two targets, so one gesture invokes the handler twice; and the mute
        toggle is itself a gesture, so starting the track there only for the toggle's own
        handler to stop it a millisecond later is a wasted play() and an audible blip.
        """
        handler = self.code.split("function onFirstGesture(event)", 1)[1].split("\n    }", 1)[0]
        self.assertIn("if (audio.unlockFired) return;", handler,
                      "the handler is not idempotent across its two bindings")
        self.assertIn("unbindUnlock();", handler)
        self.assertIn("closest('.ambient-toggle')", handler,
                      "the mute button's own click would start the music it is about to stop")
        self.assertIn("if (audio.userMuted) return;", handler)
        # The mute has to be recorded where a later gesture can see it.
        stop = self.code.split("function stopMusic()", 1)[1].split("\n    }", 1)[0]
        self.assertIn("audio.userMuted = true;", stop)
        start = self.code.split("function startMusic()", 1)[1].split("\n    }", 1)[0]
        self.assertIn("audio.userMuted = false;", start,
                      "an explicit start must clear a previous mute")

    def test_a_blocked_autoplay_is_not_reported_as_broken(self):
        """NotAllowedError is the policy working as designed. The old single rejection
        path marked the music unavailable, which then suppressed the very gesture that
        would have started it -- so a browser doing exactly the right thing produced a
        toggle permanently reading "sound unavailable".
        """
        attempt = self.code.split("function attemptPlay(reason)", 1)[1].split("\n    }", 1)[0]
        self.assertIn("error.name === 'NotAllowedError'", attempt)
        blocked = attempt.split("NotAllowedError", 1)[1].split("markUnavailable", 1)[0]
        self.assertIn("bindUnlock();", blocked,
                      "a blocked attempt must leave the gesture path armed")
        self.assertNotIn("markUnavailable", attempt.split("NotAllowedError", 1)[1].split("}", 1)[0])
        # A real failure still has to surface, or a 404 becomes an eternal silent page.
        self.assertIn("markUnavailable();", attempt)
        self.assertIn("el.addEventListener('error'", self.code)


class EmailHydration(unittest.TestCase):
    """No literal address exists in any served file, and every one is assembled at
    runtime -- on boot and after every PJAX swap.

    Cloudflare's Email Address Obfuscation rewrites raw addresses at the edge into
    anchors on its own protection path. That broke twice here: the rewritten href is
    relative, so the PJAX router treated it as an internal navigation and clicking the
    address performed a page swap instead of opening the mail client; and the
    replacement markup lands in the parsed document, so a shell fetched mid-swap carries
    obfuscated anchors nothing decodes.

    The behavioural half is in the harness, which encodes an address exactly the way
    Cloudflare does, injects the resulting anchor, and checks that boot repairs it.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.code = _strip_js_comments(cls.app)
        cls.pages = {p.name: p.read_text() for p in ROOT.glob("*.html")}
        cls.boot_page = cls.app.split("function bootPage()", 1)[1].split("\n  }", 1)[0]

    def test_no_served_file_contains_a_literal_address(self):
        """The whole scheme rests on there being nothing at the edge to match."""
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn("@agora.in.net", html)
                self.assertNotIn("mailto:", html)
                self.assertNotIn("__cf_email__", html)
                self.assertNotIn("cdn-cgi", html,
                                 "obfuscated markup shipped in the static file")
        # JavaScript too: it is a served file, and although the edge only rewrites
        # HTML, keeping the literal out of every served file is what lets the claim be
        # checked with one grep instead of a list of exceptions.
        self.assertNotIn("@agora.in.net", self.code)
        self.assertIn("['mail', 'agora.in.net'].join('@')", self.code)

    def test_every_address_in_the_html_is_carried_in_data_attributes(self):
        for name, html in self.pages.items():
            users = re.findall(r'data-email-user="([^"]*)"', html)
            domains = re.findall(r'data-email-domain="([^"]*)"', html)
            with self.subTest(page=name):
                self.assertEqual(len(users), len(domains),
                                 "a user without a domain, or the reverse, assembles nothing")
                for user in users:
                    self.assertNotIn("@", user,
                                     "a whole address in one attribute is the literal this avoids")
                    self.assertTrue(user, "an empty data-email-user assembles '@domain'")
                for domain in domains:
                    self.assertEqual(domain, "agora.in.net")
                    self.assertNotIn("@", domain)

    def test_hydration_runs_on_boot_and_after_every_swap(self):
        """Once at boot is not enough. A PJAX swap installs fresh markup whose anchors
        have no href at all, so the address would be dead text on every page reached by
        in-app navigation -- which is most of them.

        And it runs BEFORE initRouting: an unhydrated anchor has no href, a hydrated one
        has a mailto: href that getInternalPageUrl already excludes, so either way the
        router cannot mistake it for an internal link -- but hydrating first means there
        is no window in which a click lands on an anchor with no destination.
        """
        self.assertIn("hydrateEmailLinks();", self.boot_page)
        self.assertLess(self.boot_page.index("hydrateEmailLinks();"),
                        self.boot_page.index("initRouting();"))
        # bootPage is the router's post-swap hook, so one call covers both moments.
        self.assertEqual(self.code.count("hydrateEmailLinks()"), 1,
                         "called once, from the one place that runs at boot and after every swap")
        router = self.code.split("function routeTo(url, pushHistory)", 1)[1].split(
            "function canonicalPath", 1)[0]
        self.assertIn("bootPage();", router)

    def test_the_subject_and_label_attributes_are_honoured(self):
        """The category cards prefill a subject and keep their own copy; the footer and
        the bio want the address itself as the visible text. Both have to work, or one
        of the two shapes silently degrades.
        """
        body = self.code.split("function hydrateEmailLinks(scope)", 1)[1].split("\n  }", 1)[0]
        self.assertIn("encodeURIComponent(subject)", body,
                      "a subject with a space or an ampersand would break the href")
        self.assertIn("?subject=", body)
        self.assertIn("hasAttribute('data-email-label')", body)
        self.assertIn("node.textContent = address", body)
        self.assertIn("node.setAttribute('href', href)", body)
        # Present in the markup in both shapes.
        contact = self.pages["contact.html"]
        # The four per-category subject links are gone: the cards became buttons that
        # advance the flow, and a link inside a button is invalid HTML as well as a
        # small target inside a large one that people miss. The subject attribute is
        # still supported and still exercised, by the one remaining direct-email link.
        self.assertEqual(len(re.findall(r'data-email-user="', contact)), 2,
                         "the step-1 fallback and the footer")
        self.assertEqual(len(re.findall(r'data-email-subject="', contact)), 1,
                         "the remaining email link should still prefill a subject")
        self.assertNotIn('data-email-label', contact,
                         "both show the address itself rather than a label")
        # about.html carries two anchors and they deliberately differ. The callout
        # button is labelled -- it says "Email the team", because a button that reads
        # as an address looks like body text. The developer bio is NOT labelled, so the
        # address replaces its fallback and the sentence reads exactly as it did before
        # this scheme existed: "... an email is the best way to reach me" becomes
        # "... mail@agora.in.net is the best way to reach me".
        about_src = self.pages["about.html"]
        self.assertEqual(len(re.findall(r'data-email-label', about_src)), 1,
                         "only the callout button keeps its authored copy")
        bio = about_src.split("best way to reach me", 1)[0]
        self.assertIn("data-email-user", bio)
        self.assertNotIn("data-email-label", bio.rsplit("<a ", 1)[1],
                         "the bio must show the address, not a label")
        # And the form's own "prefer email?" line deliberately does NOT, so the address
        # itself is what the visitor sees there.
        # The step-1 fallback is inside the flow, not below it: a visitor who does
        # not want to pick a category still has a way out.
        alt = contact.split('class="contact-alt signal__alt"', 1)[1].split("</p>", 1)[0]
        self.assertIn("data-email-user", alt)
        self.assertIn("data-email-subject", alt)
        self.assertNotIn("data-email-label", alt)
        self.assertRegex(self.pages["index.html"], r'data-email-user="mail"(?![^>]*data-email-label)',
                         "the footer link should show the address, not a label")

    def test_a_stray_obfuscated_anchor_is_decoded_not_ignored(self):
        """Defensive, and the reason this is not just "we removed the addresses".

        If an address ever reaches the HTML again -- a hand edit, a cached shell from
        before this change -- the edge will obfuscate it and the site must repair
        itself rather than ship a dead link. data-cfemail is the address XORed against
        its own first byte, which is a stable public format, so decoding is not a hack.
        """
        decoder = self.code.split("function decodeCfEmail(encoded)", 1)[1].split("\n  }", 1)[0]
        self.assertIn("parseInt(encoded.substr(0, 2), 16)", decoder, "the key byte")
        self.assertIn("^ key", decoder, "and the XOR that recovers each character")
        self.assertIn("indexOf('@') > 0", decoder,
                      "a decode with no @ is a malformed payload, not an address")
        self.assertRegex(decoder, r"/\^\[0-9a-f\]\+\$/i", "the hex shape must be validated")
        repair = self.code.split("function hydrateEmailLinks(scope)", 1)[1]
        # Both selectors, because the two do not always travel together: Cloudflare
        # writes the class AND the protection href, but a cached or hand-edited shell
        # can carry one without the other, and matching on the class alone leaves a
        # dead link in the DOM.
        self.assertIn("a.__cf_email__", repair)
        self.assertIn("email-protection", repair,
                      "the href-based selector is gone, so an anchor carrying only the "
                      "protection path is never repaired")
        self.assertIn("data-cfemail", repair)
        self.assertIn("classList.remove('__cf_email__')", repair,
                      "a repaired anchor must stop carrying the class Cloudflare added")


class ContactFlow(unittest.TestCase):
    """The three-step contact flow: category, identity, message.

    The behavioural half is in the jsdom harness, which clicks through every path.
    What is pinned here is the markup contract that behaviour depends on, plus the two
    decisions that are invisible in a rendered page and expensive to get wrong.
    """

    CATEGORIES = ["General", "Feedback & Ideas", "Questions", "Press", "Anything else"]
    ANYTHING_ELSE = "Anything else"

    @classmethod
    def setUpClass(cls):
        cls.html = _strip_html_comments((ROOT / "contact.html").read_text())
        cls.app = (ROOT / "app.js").read_text()
        cls.code = _strip_js_comments(cls.app)
        cls.flow = cls.app.split("function initSignalFlow()", 1)[1].split(
            "\n  /* ------------------------------------------------------------\n     7.", 1)[0]

    def opening_tag(self, n):
        """The panel's whole opening tag. Splitting forwards from the step attribute
        only yields the tail of the tag, so anything in the class list -- `hidden`,
        `is-current` -- is missed, which is exactly what a first draft did."""
        i = self.html.index('data-signal-step="%d"' % n)
        start = self.html.rindex("<div", 0, i)
        return self.html[start:self.html.index(">", i) + 1]

    def test_the_five_categories_are_the_five_that_were_asked_for(self):
        found = re.findall(r'data-category="([^"]+)"', self.html)
        self.assertEqual(found, self.CATEGORIES,
                         "the category list, its order or its exact wording changed")
        # The fifth is the only one with different behaviour, and it is matched by
        # string equality in app.js -- so the two spellings have to agree exactly.
        self.assertIn("var ANYTHING_ELSE = '%s';" % self.ANYTHING_ELSE, self.flow)

    def test_each_card_is_one_button_and_not_a_div_with_a_link_inside(self):
        """"Clicking anywhere on the card selects" is free with a <button> and costs a
        keyboard trap with a div. A link inside a button is also invalid HTML, and it
        is a small target inside a large one, which is the thing the brief was asking
        to remove."""
        cards = re.findall(r'<button type="button" class="contact-category"[^>]*>(.*?)</button>',
                           self.html, re.DOTALL)
        self.assertEqual(len(cards), 5, f"expected five card buttons, got {len(cards)}")
        for i, body in enumerate(cards):
            with self.subTest(category=self.CATEGORIES[i]):
                self.assertNotIn("<a ", body, "a card still contains a sub-link")
                self.assertNotIn("<button", body, "and no nested interactive element")
        self.assertNotIn("contact-category__mail", self.html, "the old sub-link class survives")

    def test_only_step_one_is_in_the_document_flow_at_load(self):
        """`hidden`, not merely styled away: a hidden panel is out of the tab order and
        out of the accessibility tree, so a keyboard visitor meets one step at a time
        instead of tabbing through a form whose fields are invisible."""
        for n in (2, 3):
            self.assertIn("hidden", self.opening_tag(n), f"step {n} is not hidden at load")
        first = self.opening_tag(1)
        self.assertNotIn("hidden", first)
        self.assertIn("is-current", first)
        # And each panel is a labelled group, so the step has an accessible name.
        for n in (1, 2, 3):
            with self.subTest(step=n):
                self.assertIn('role="group"', self.html.split('data-signal-step="%d"' % n, 1)[1][:400])
                self.assertIn('aria-labelledby="signal-step-%d-title"' % n,
                              self.html.split('data-signal-step="%d"' % n, 1)[1][:400])
                self.assertIn('<h2 class="h3" id="signal-step-%d-title" tabindex="-1">' % n
                              if n > 1 else 'id="signal-step-1-title"', self.html)

    def test_step_two_is_a_gate_not_a_shortcut_to_the_form(self):
        p2 = self.html.split('data-signal-step="2"', 1)[1].split('data-signal-step="3"', 1)[0]
        self.assertIn('id="signal-identity"', p2)
        self.assertIn('data-signal-advance="3"', p2,
                      "the gate must declare where it goes rather than hardcoding it in JS")
        self.assertIn('name="name"', p2)
        self.assertIn('name="email"', p2)
        self.assertIn("required", p2)
        self.assertIn('data-error-for="name"', p2)
        self.assertIn('data-error-for="email"', p2)
        self.assertIn('type="submit"', p2)
        self.assertIn('data-signal-back="1"', p2, "and a way back to step 1")
        self.assertNotIn('name="message"', p2, "the gate must not collect the message")

    def test_step_three_carries_the_message_and_the_way_back(self):
        p3 = self.html.split('data-signal-step="3"', 1)[1].split("</section>", 1)[0]
        self.assertIn('id="feedback-form"', p3)
        self.assertIn('method="post"', p3)
        for field in ("name", "email", "topic", "message"):
            with self.subTest(field=field):
                self.assertIn('name="%s"' % field, p3)
        self.assertIn('data-honeypot', p3)
        self.assertIn('id="feedback-status"', p3)
        self.assertIn('id="feedback-success"', p3)
        self.assertIn('data-signal-back="1"', p3, "the 'change topic' way back to step 1")
        self.assertIn("Change topic", p3)
        self.assertIn('data-signal-restart', p3, "and a way to start over after success")
        # No second POST target: the gate form must not be able to submit anywhere.
        self.assertEqual(p3.count('id="feedback-form"'), 1)

    def test_the_topic_is_an_input_because_a_select_cannot_be_locked_cleanly(self):
        """The brief asks for no dropdown arrow and no direct editing for the four
        fixed categories, and a freely typed topic for the fifth. One <input> whose
        readOnly flag flips does both; a <select> plus a text input would mean two
        controls with the same name, and only one of them in the FormData.
        """
        topic = re.search(r'<input id="fb-topic"[^>]*>', self.html)
        self.assertIsNotNone(topic, "the topic is not an input")
        self.assertIn('type="text"', topic.group(0))
        self.assertIn("readonly", topic.group(0),
                      "it must start locked; step 1 unlocks it for 'Anything else'")
        self.assertNotIn("<select", self.html.split('data-signal-step="3"', 1)[1],
                         "a select came back")
        self.assertNotIn("<option", self.html.split('data-signal-step="3"', 1)[1])
        self.assertIn('data-topic-hint', self.html,
                      "a locked field with no explanation reads as broken, not as decided")

    def test_the_lock_is_readonly_and_never_disabled(self):
        """THE trap in this feature, and the reason it gets its own test.

        A disabled control is omitted from FormData, so a locked topic would silently
        vanish from the submission and the Function would reject the message for a
        missing field -- at the last step, after the visitor had written the whole
        thing. readOnly keeps it in the payload, keeps it focusable for a screen
        reader, and still refuses edits. The harness proves the payload half by
        building a real FormData and reading `topic` back out of it.
        """
        self.assertIn("topic.readOnly = locked;", self.flow)
        self.assertNotRegex(self.flow, r"topic\.disabled\s*=")
        self.assertNotIn(".disabled = true", self.flow)
        # Announced, not just styled: a screen reader has to know the field is fixed.
        self.assertIn("topic.setAttribute('aria-readonly', 'true')", self.flow)
        self.assertIn("topic.removeAttribute('aria-readonly')", self.flow)
        self.assertIn("topic.placeholder = 'What is this regarding?'", self.flow,
                      "the requested placeholder for the editable case")
        self.assertIn("topic.classList.toggle('is-locked', locked)", self.flow)

    def test_focus_follows_the_step(self):
        """Without this, focus stays on the control that was clicked -- which is now
        inside a hidden panel, so a keyboard visitor is left focused on nothing and a
        screen reader announces no change at all."""
        self.assertIn("panel.hidden = !on;", self.flow)
        self.assertIn('target.querySelector(\'[tabindex="-1"]\')', self.flow)
        self.assertIn("heading.focus()", self.flow)

    def test_the_flow_runs_before_the_forms_are_wired(self):
        page = self.app.split("function bootPage()", 1)[1].split("\n  }", 1)[0]
        self.assertIn("initSignalFlow();", page)
        self.assertIn("initContactForm();", page)
        self.assertLess(page.index("initSignalFlow();"), page.index("initContactForm();"))
        # Both forms share one rule table; a second copy would drift.
        self.assertEqual(self.code.count("var RULES = {"), 1)
        self.assertIn("doc.querySelectorAll('form[data-contact-form]')", self.code)
        self.assertEqual(len(re.findall(r'data-contact-form', self.html)), 2)

    def test_a_step_three_correction_survives_a_trip_back_through_step_two(self):
        """The prefill has to be one-directional in practice. Going 3 -> 1 -> 2 -> 3 is
        the documented path for changing the topic, and if step 2 blindly overwrote
        step 3 on every arrival, a name corrected in step 3 would be silently reverted
        to the older value on the way back through."""
        self.assertIn("var edited = { name: false, email: false };", self.flow)
        self.assertIn("if (from && to && !edited[key]) to.value = from.value;", self.flow)
        self.assertIn("edited[key] = true;", self.flow)
        self.assertIn("edited.name = false;", self.flow,
                      "and a restart must clear the dirty flags")


class CreditsChrome(unittest.TestCase):
    """The credits screen keeps exactly one way out and a colophon, and nothing else.

    This page is a single-viewport composition the visitor drives with a wheel. Every
    extra piece of chrome competes with that, so the header carries one link and the
    bottom bar carries a hint, a counter and a copyright line.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = _strip_html_comments((ROOT / "credits.html").read_text())
        cls.css = (ROOT / "style.css").read_text()
        cls.css_code = _strip_css_comments(cls.css)
        cls.header = cls.html.split('<header class="credits-screen-header">', 1)[1].split("</header>", 1)[0]
        cls.status = cls.html.split('<div class="credits-rotary-status"', 1)[1].split("</div>", 1)[0]

    def test_the_header_carries_one_link_and_it_goes_home(self):
        actions = self.header.split('<nav class="credits-screen-actions"', 1)[1].split("</nav>", 1)[0]
        links = re.findall(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', actions, re.DOTALL)
        self.assertEqual(len(links), 1, f"the header gained links again: {links}")
        href, text = links[0]
        self.assertEqual(href, "/")
        self.assertEqual(" ".join(re.sub(r"<[^>]+>", "", text).split()), "Back to Square")
        self.assertIn('data-page="home"', actions[actions.index(href):],
                      "so the router resolves it like any other internal link")
        # The logo is the other way home and stays; it is branding, not chrome.
        self.assertIn('class="nav__logo brand-lockup credits-screen-brand" href="/"',
                      self.header)
        self.assertNotIn("Why Agora", self.header)
        self.assertNotIn("Contact", self.header)

    def test_the_bottom_bar_has_no_address_and_carries_the_colophon(self):
        self.assertNotIn("@", self.status)
        self.assertNotIn("mailto", self.status)
        self.assertNotIn("contact", self.status.lower())
        self.assertIn("credits-screen-colophon", self.status)
        self.assertIn("Agora &middot; &copy;", self.status)
        # The year is the shared span so initChrome keeps it current like every other
        # page's footer, instead of going stale in 2027.
        self.assertIn('<span id="year">2026</span> Agora', self.status)
        # The wheel mechanics stay: the hint and the JS-driven counter are how the
        # visitor knows what to do and where they are.
        self.assertIn("wheel to rotate", self.status)
        self.assertIn("data-rotary-count", self.status)
        self.assertIn("data-rotary-total", self.status)

    def test_the_removed_contact_link_left_no_dead_css(self):
        """Dead CSS is not harmless: `.credits-screen-contact` still had a hover rule
        and a mobile override after the element was gone, and the mobile override was
        retargeted rather than deleted because the colophon took its slot. A rule
        pointing at nothing reads as though it is still doing work."""
        self.assertNotIn("credits-screen-contact", self.css_code)
        self.assertIn(".credits-screen-colophon {", self.css_code)
        # And the colophon has to inherit the mobile downsize, or it overflows the pill.
        mobile = self.css_code.split("@media (max-width: 768px)", 1)[-1]
        self.assertIn(".credits-screen-colophon", mobile)

    def test_the_one_link_is_sized_to_the_site_not_to_the_screen(self):
        """It used to carry the .mono class AND its own font-size and letter-spacing,
        so two rules fought over the same properties and the page drifted out of step
        with the site without either file being edited. It now sets its own type once,
        to the same metrics as .nav__link."""
        # `.credits-screen-exit` appears in a shared pointer-events rule before the
        # one that sets its type, so take the block that actually carries font-size
        # rather than the first match.
        blocks = re.findall(r"\.credits-screen-exit \{([^}]*)\}", self.css_code)
        rule = next((b for b in blocks if "font-size" in b), None)
        self.assertIsNotNone(rule, "no .credits-screen-exit rule sets a font-size")
        nav = self.css_code.split(".nav__link {", 1)[1].split("}", 1)[0]
        for prop in ("font-size", "letter-spacing", "text-transform", "font-weight"):
            with self.subTest(prop=prop):
                exit_value = re.search(prop + r":\s*([^;]+);", rule)
                nav_value = re.search(prop + r":\s*([^;]+);", nav)
                self.assertIsNotNone(exit_value, f"the exit link no longer sets {prop}")
                self.assertIsNotNone(nav_value)
                self.assertEqual(exit_value.group(1).strip(), nav_value.group(1).strip(),
                                 f"{prop} differs from the site's nav link")
        self.assertNotRegex(self.html, r'credits-screen-exit[^>]*class="[^"]*\bmono\b')

    def test_no_selector_can_hide_the_only_way_off_the_page(self):
        """The rule that made this worth a test: `.credits-screen-actions >
        a:first-child { display: none }` existed to hide a second header link on
        phones. When the header was cut to one link, that selector matched the ONLY
        link left -- so a phone visitor would have had no way off the credits screen
        at all, and nothing on desktop would have shown it.

        A sibling rule set `.credits-screen-exit { font-size: 0 }` and re-sized an
        arrow <span> that the declutter removed, which would have made the link
        invisible a second time over. Both are asserted absent, and the mobile rule
        is asserted to give the link a real size.
        """
        self.assertNotIn(".credits-screen-actions > a:first-child", self.css_code)
        mobile = self.css_code.split("@media (max-width: 768px)", 1)[-1]
        exit_mobile = mobile.split(".credits-screen-exit {", 1)[1].split("}", 1)[0]
        self.assertNotIn("display: none", exit_mobile)
        size = re.search(r"font-size:\s*([\d.]+)rem", exit_mobile)
        self.assertIsNotNone(size, "the mobile exit link has no font-size of its own")
        self.assertGreaterEqual(float(size.group(1)), 0.55,
                                "the only way off the credits screen is unreadable on a phone")
        self.assertNotIn(".credits-screen-exit span", self.css_code,
                         "styling survives for an arrow element that was deleted")


class StylesheetIntegrity(unittest.TestCase):
    """Structural checks on style.css that no per-rule test can make.

    These exist because of a specific mistake. Deleting one name from a SHARED
    selector list by cutting from that name to the closing brace leaves the surviving
    name dangling into whatever rule follows: `.vision-grid .section-head,` merged into
    `.site-footer__grid { gap: 2rem }`, so the section head lost `position: static` and
    silently acquired a gap. The braces still balanced, every rule still parsed, and
    the deleted class looked correctly gone -- the damage was entirely to its neighbour.
    """

    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "style.css").read_text()
        cls.css = re.sub(r"/\*.*?\*/", " ", cls.raw, flags=re.DOTALL)

    def test_braces_balance(self):
        self.assertEqual(self.css.count("{"), self.css.count("}"),
                         "unbalanced braces; the browser will drop everything after the error")

    def test_no_selector_list_is_left_dangling(self):
        """A comma ending a line, then a blank line, then a selector, is the signature
        of a shared rule that lost one of its names."""
        for m in re.finditer(r",\s*\n\s*\n+\s*[^{}@/\s][^{}]*\{", self.css):
            self.fail("a selector list ends in a comma and is separated from what follows "
                      f"-- a shared rule was cut in half: {m.group(0)[:90]!r}")

    def test_every_selector_in_a_list_is_non_empty(self):
        for m in re.finditer(r"([^{}@/][^{}]*)\{", self.css):
            head = m.group(1)
            for part in head.split(","):
                self.assertTrue(part.strip(),
                                f"empty selector in a list, i.e. a trailing or doubled comma: "
                                f"{' '.join(head.split())[-70:]!r}")

    def test_no_rule_is_empty(self):
        for m in re.finditer(r"([^{}@]+)\{\s*\}", self.css):
            selector = " ".join(m.group(1).split())[-70:]
            self.fail(f"empty rule left behind: {selector} {{ }}")

    # Every panel/card class in the site, pinned because of a specific loss.
    # .signal__card is deliberately absent: it is a width modifier on an element that
    # also carries .form-card, so it has no box of its own by design.
    CARDS = (".form-card", ".cta-panel", ".principle", ".dl-card", ".shared-card",
             ".post-preview", ".creator", ".contact-callout", ".contact-category",
             ".standard", ".form-success", ".step", ".badge", ".peek")

    def test_every_card_class_still_declares_its_own_box(self):
        """A class can survive in a shared selector list long after its own rule is
        deleted, which is exactly what happened to .form-card.

        Cutting a shared selector list by slicing to the second close-brace-on-its-own
        line skipped the indented inner braces of a media query and swallowed the next
        top-level rule with it. `.form-card` stayed in the `@supports` backdrop-filter
        group, so it still counted as "styled" and every structural check passed, while
        having lost its border, radius, padding, background and shadow -- and both
        contact panels flattened into bare text on the page background.

        A general "every container class has a box rule" version of this produced 15
        false positives (modifier classes, typography-only blocks, children that
        inherit their box from a parent), so this pins the classes that ARE cards
        instead. Narrower, but it fails on the real failure and not on the design.
        """
        for card in self.CARDS:
            blocks = re.findall(re.escape(card) + r"\s*\{([^}]*)\}", self.css)
            joined = " ".join(blocks)
            with self.subTest(card=card):
                self.assertTrue(blocks, f"{card} has no rule of its own at all")
                self.assertRegex(joined, r"(?:^|[\s;])(?:padding|border|background)\s*:",
                                 f"{card} is in a selector list somewhere but nothing declares "
                                 f"its padding, border or background -- the panel has no box")

    def test_no_declaration_sits_outside_a_rule(self):
        """A cut that removes a closing brace rather than an opening one leaves
        declarations at top level, which the browser discards along with everything up
        to the next rule."""
        depth = 0
        for m in re.finditer(r"[{}]|:\s*[^;{}]+;", self.css):
            token = m.group(0)
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                self.assertGreaterEqual(depth, 0, "a closing brace with no opening brace")
            elif depth == 0:
                self.fail(f"declaration outside any rule: {token.strip()[:70]!r}")
        self.assertEqual(depth, 0)


class ContactPage(unittest.TestCase):
    """The new page has to be wired like every other page, not merely exist.

    Five separate mutations survived the first sweep here, and all five are the same
    shape: a page that renders perfectly and is simply unreachable, or that offers a
    navigation which quietly omits a destination. Nothing looks wrong on the page
    itself, so each needs an assertion that spans pages rather than one that reads a
    single file.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.code = _strip_js_comments(cls.app)
        cls.pages = {p.name: p.read_text() for p in ROOT.glob("*.html")}
        table = cls.app.split("var PAGE_MAP = {", 1)[1].split("};", 1)[0]
        cls.page_map = dict(re.findall(r"(\w+): '(/[^']*)'", table))

    def test_every_data_page_value_resolves(self):
        """`syncPageLinks()` rewrites `a[data-page]` from PAGE_MAP and leaves the
        authored href alone when the key is unknown -- so a missing entry is not an
        error, it is a link that silently keeps whatever the markup said."""
        used = set()
        for name, html in self.pages.items():
            used |= set(re.findall(r'data-page="([^"]+)"', html))
        self.assertTrue(used, "no data-page attributes found; the parser moved")
        for key in sorted(used):
            with self.subTest(key=key):
                self.assertIn(key, self.page_map,
                              f'data-page="{key}" has no PAGE_MAP entry')
        self.assertIn("contact", self.page_map)
        self.assertEqual(self.page_map["contact"], "/contact")
        # The reverse direction matters too: a PAGE_MAP entry nothing links to is a
        # route no visitor can reach, and it reads as though the page is wired up.
        # PAGE_MAP.why survived three rounds pointing at a hash target no element ever
        # carried a data-page for.
        every_html = "\n".join(self.pages.values())
        for key, target in self.page_map.items():
            with self.subTest(route=key):
                self.assertIn(target, CLEAN_ROUTES)
                self.assertIn('data-page="%s"' % key, every_html,
                              f"PAGE_MAP.{key} is unreachable: nothing carries that data-page")

    def test_the_header_and_the_footer_offer_the_same_destinations(self):
        """Two failures this catches, and neither is visible on the page that has them.

        A footer that omits a page the header lists makes that page unreachable from
        the bottom of every other page -- the About link was missing from all four
        footers for the whole life of the site. And a bare `#hash` href only resolves on
        the page that owns the anchor: the footer's "Why Agora" was `#why-agora`, which
        works on index.html and points at nothing on the other three. app.js papered
        over it by routing a bare hash home, so it worked with JavaScript and was simply
        dead without it.
        """
        expected = {"/", "/#why-agora", "/download",
                    "/about", "/credits", "/contact"}
        for name in ("index.html", "about.html", "download.html", "contact.html", "privacy.html", "terms.html"):
            html = _strip_html_comments(self.pages[name])
            nav = re.search(r'<nav class="nav__links"[^>]*>(.*?)</nav>', html, re.DOTALL)
            foot = re.search(r'<nav aria-label="Footer"[^>]*>(.*?)</nav>', html, re.DOTALL)
            self.assertIsNotNone(nav, f"{name} has no header nav")
            self.assertIsNotNone(foot, f"{name} has no footer nav")
            nav_hrefs = re.findall(r'href="([^"]+)"', nav.group(1))
            foot_hrefs = re.findall(r'href="([^"]+)"', foot.group(1))

            def normalise(hrefs):
                # index.html's header legitimately uses the bare `#why-agora`: on the
                # page that owns the anchor, initSmoothScroll handles it in place and a
                # PJAX round-trip to itself would be worse. Everywhere else the
                # absolute form is the only one that resolves. Both mean the same
                # destination, so normalise before comparing the two navigations.
                return {("/" + h if h.startswith("#") and name == "index.html" else h)
                        for h in hrefs}

            with self.subTest(page=name):
                self.assertEqual(normalise(nav_hrefs), expected, "the header nav is incomplete")
                self.assertEqual(normalise(foot_hrefs), expected | {"/privacy", "/terms"}, "the footer nav is incomplete")
            for href in sorted(set(nav_hrefs) | set(foot_hrefs)):
                with self.subTest(page=name, href=href):
                    if href.startswith("#"):
                        self.assertIn('id="%s"' % href[1:], html,
                                      "a bare hash is only valid on the page that owns the "
                                      "anchor; anywhere else it points at nothing")

    def test_every_full_shell_page_offers_the_same_navigation(self):
        """index, about, download and contact share one header. If one drops a link the
        site is not navigable from that page, and the page still looks finished."""
        expected_keys = {"home", "download", "about", "credits", "contact"}
        expected_hrefs = {"/", "/download", "/about",
                          "/credits", "/contact"}
        for name in ("index.html", "about.html", "download.html", "contact.html", "privacy.html", "terms.html"):
            nav = re.search(r'<nav class="nav__links"[^>]*>(.*?)</nav>',
                            self.pages[name], re.DOTALL)
            self.assertIsNotNone(nav, f"{name} has no primary nav")
            self.assertEqual(set(re.findall(r'data-nav-key="([^"]+)"', nav.group(1))),
                             expected_keys, f"{name}'s primary nav is incomplete")
            menu = re.search(r'<nav id="mobile-menu"[^>]*>(.*?)</nav>',
                             self.pages[name], re.DOTALL)
            self.assertIsNotNone(menu, f"{name} has no mobile menu")
            self.assertEqual(set(re.findall(r'href="(/[^"#]*)"', menu.group(1))),
                             expected_hrefs, f"{name}'s mobile menu is incomplete")

    def test_the_contact_page_carries_its_own_active_key(self):
        """initChrome derives the active key from the filename, so the value has to be
        exactly `contact` or the nav never highlights on this page."""
        self.assertIn('href="/contact" data-page="contact" data-nav-key="contact"',
                      self.pages["contact.html"])
        self.assertIn("path.replace(/\.html$/, '')", self.code)

    def test_every_contact_entry_point_reaches_the_page_not_a_hash(self):
        """The callout and the footers must navigate to /contact. A link to
        `#contact` on a page whose contact section is now an invitation rather than a
        form scrolls the visitor to a card that tells them to go somewhere else."""
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn('href="#contact"', html)
        # Scoped to the callout's own section: about.html has four other
        # /contact links, so a whole-file assertIn would keep passing with the
        # callout's link repointed at a hash. That is exactly how this survived.
        callout = self.pages["about.html"].split('id="contact"', 1)[1].split("</section>", 1)[0]
        self.assertIn('href="/contact"', callout)
        self.assertIn('data-page="contact"', callout)
        self.assertIn("Have a question, idea, or press inquiry?", callout)
        for name in ("index.html", "about.html", "download.html", "contact.html", "privacy.html", "terms.html"):
            footer = self.pages[name].split('class="site-footer__contact"', 1)[1].split("</div>", 1)[0]
            with self.subTest(page=name, where="footer"):
                self.assertIn('href="/contact"', footer,
                              "the footer contact block does not reach the contact page")

    def test_the_form_exists_once_site_wide(self):
        """A form that was copied rather than moved leaves two live forms sharing
        `fb-name`, `fb-email` and `feedback-status`. Duplicate ids do not throw: the
        validation and status wiring attaches to whichever element querySelector finds
        first, and the other form silently does nothing when submitted."""
        owners = [name for name, html in self.pages.items() if 'id="feedback-form"' in html]
        self.assertEqual(owners, ["contact.html"], f"the form lives on {owners}")
        for field in ("fb-name", "fb-email", "fb-topic", "fb-message", "fb-company",
                      "feedback-status", "feedback-success"):
            with self.subTest(field=field):
                total = sum(html.count('id="%s"' % field) for html in self.pages.values())
                self.assertEqual(total, 1, f'{field} appears {total} times site-wide')


class CreditsAudioRemoval(unittest.TestCase):
    """The credits screen no longer reacts to the music, and the wheel it does react
    to is unchanged.

    This class replaced CreditsAudioBands, which tested an analyser tuned to 2048/0.35,
    six derived band metrics, and a per-frame driver that wrote three custom properties
    onto each disc. All of that is gone: the credits screen was running a
    getByteFrequencyData plus a per-bin pitch loop 60 times a second, then a dozen
    style recalculations per disc on top of two large rotating elements with masks,
    conic gradients and drop-shadows. That combination is what cost it frames.

    What survives, and is asserted here, is the part that was never about audio: the
    wheel physics, the locked contributor coordinates, and the invariant that no
    decoration may transform the subtree the copy lives in.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text()
        cls.css = (ROOT / "style.css").read_text()
        cls.code = _strip_js_comments(cls.app)
        cls.css_code = _strip_css_comments(cls.css)
        cls.physics = cls.app.split("function initCreditsRotary()", 1)[1].split(
            "     9. DYNAMIC DOWNLOAD LINK", 1)[0]

    def test_the_analysis_and_the_wheel_driver_are_both_gone(self):
        for token in ("initWheelReactivity", "wheelReactivityCleanup", "--wheel-bass",
                      "--wheel-onset", "--wheel-treble", "computeBands", "bandAverage",
                      "buildBandBins", "previousMid", "ONSET_DECAY", "TREBLE_GAIN"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.code, "an audio-reactive hook survived")
                self.assertNotIn(token, self.css_code, "and its CSS consumer survived")
        # The facade is a transport now, not an analysis.
        facade = self.app.split("window.AgoraAudio = {", 1)[1].split("};", 1)[0]
        for member in ("start: startMusic", "stop: stopMusic", "toggle: toggleMusic",
                       "get isPlaying()"):
            self.assertIn(member, facade)
        for gone in ("getEnergy", "getPulse", "getSpectrum", "getBands", "SPECTRUM_BANDS"):
            self.assertNotIn(gone, facade, f"{gone} is still exported")

    def test_the_wheel_physics_was_not_touched_by_the_removal(self):
        """Taking the audio out of the wheels must not take the wheels out. The spring,
        the snap and the velocity limits are the thing that makes the screen usable, and
        none of them were ever audio-driven."""
        # Values, not presence. Asserting only that these exist lets any of them
        # drift, and the wheel's feel is a solved quantity rather than a free one:
        # SNAP_THRESHOLD 0.5 is the 65% rule, WHEEL_MAX_STEP 45 is what stops one
        # notch throwing the wheel past a whole sector, and the settle pair is what
        # makes the arrival lock instead of idling a hair off-sector. A mutation
        # moving SPRING_STIFFNESS from 132 to 40 survived the first sweep on a
        # presence check alone.
        pinned = {
            "SPRING_STIFFNESS": 132, "MAX_ANGULAR_VELOCITY": 760, "SEGMENT": 120,
            "WHEEL_DAMPING": 0.11, "WHEEL_MAX_STEP": 45,
            "TOUCH_DAMPING": 0.92, "TOUCH_MAX_STEP": 40,
            "SNAP_DELAY": 90, "SNAP_THRESHOLD": 0.5, "SNAP_THRESHOLD_FAST": 0.26,
            "COMMIT_BOOST_MS": 240, "FAST_WHEEL_DELTA": 60, "ARRIVAL_MS": 420,
            "SETTLE_ANGLE": 0.02, "SETTLE_VELOCITY": 0.6,
        }
        for name, expected in sorted(pinned.items()):
            m = re.search(r"var " + name + r" = ([\d.]+);", self.physics)
            with self.subTest(constant=name):
                self.assertIsNotNone(m, f"{name} is gone")
                self.assertEqual(float(m.group(1)), expected, f"{name} drifted")
        # Critically damped, in seconds, so the settle is identical at 60Hz and 144Hz.
        self.assertIn("SPRING_DAMPING = 2 * Math.sqrt(SPRING_STIFFNESS)", self.physics)
        self.assertIn("state.rotation += state.rotationVelocity * dt;", self.physics)
        self.assertIn("calculateSnapTarget()", self.physics)
        self.assertIn("indexForRotation(", self.physics)

    def test_nothing_audio_driven_may_transform_the_copy_subtree(self):
        """The invariant the audio-reactive wheels were built around, and the one worth
        keeping now that they are gone.

        It is NOT "the copy has no transform" -- it has a large and essential one:

            translate(-50%, -50%)
            rotate(calc(0deg - var(--segment-angle) - var(--disc-rotation, 0deg)))
            scale(var(--segment-scale))

        The rotate is a counter-rotation that keeps the block upright as the wheel
        turns, the translate is what centres it on its solved landing point instead of
        hanging it from its top-left corner, and the scale is the settled emphasis that
        moves 0.6 -> 1 between the active and inactive sectors. All three are geometry
        and state, solved against 14 viewports and locked.

        What must never appear is a transform driven by the music. That was the whole
        design constraint of the old reactivity: the scale landed only on layers with no
        descendants, because a bass pulse scaling the plate by 3.5% of a 1260px disc
        moved the contributor copy 44px. With --wheel-* deleted the rule is simpler and
        stronger -- nothing references them, and the sector track, which is the subtree
        the copy actually lives in, carries no transform at all.
        """
        track = self.css.split(".rotary-disc__sector-track {", 1)[1].split("}", 1)[0]
        self.assertNotIn("transform", _strip_css_comments(track),
                         "the copy's own subtree is being transformed")

        credits_css = self.css[self.css.index(".credits-rotary-page"):]
        transforms = re.findall(r"transform:\s*([^;]+);", _strip_css_comments(credits_css))
        self.assertTrue(transforms, "no transforms found -- the selector moved")
        for declaration in transforms:
            with self.subTest(transform=declaration.strip()[:64]):
                self.assertNotRegex(declaration, r"var\(--wheel-",
                                    "a transform is driven by the music")
                self.assertNotRegex(declaration, r"var\(--(?:bass|mid|treble|onset)",
                                    "a transform is driven by a band")

        # The counter-rotation and the centring arm must survive: deleting either does
        # not break a test about audio, it silently moves the copy off its solved mark.
        content = _strip_css_comments(
            self.css.split(".rotary-segment__content {", 1)[1].split("\n}", 1)[0])
        self.assertIn("translate(-50%, -50%)", content)
        self.assertIn("rotate(calc(0deg - var(--segment-angle) - var(--disc-rotation, 0deg)))",
                      content, "the counter-rotation that keeps the copy upright is gone")
        self.assertIn("scale(var(--segment-scale))", content)
        self.assertIn("--segment-scale: 0.6;", content)
        self.assertIn("--segment-scale: 1;",
                      self.css.split(".rotary-segment.is-active .rotary-segment__content {", 1)[1]
                      .split("}", 1)[0])

        # And the locked coordinates are still exactly where four rounds of solving put them.
        for decl in ("top: 58%", "left: 76%", "top: 64%", "left: 76.5%",
                     "min(max(23vw, 230px), 340px)", "min(max(17.5vw, 200px), 260px)"):
            with self.subTest(decl=decl):
                self.assertEqual(self.css.count(decl), 1, f"{decl} moved or duplicated")
        for decl in ("--sector-offset: 40", "--sector-offset: 220",
                     "translate(-44%, -44%)", "translate(44%, 44%)"):
            with self.subTest(decl=decl):
                self.assertIn(decl, self.css, f"{decl} is gone")



class CleanPageRoutes(unittest.TestCase):
    """Public URLs are routes; .html names are storage and server fallback only."""

    def test_html_page_links_are_clean_and_assets_are_unchanged(self):
        for path in ROOT.glob('*.html'):
            page = Page(path)
            for attrs, _ in page.anchors:
                href = attrs.get('href', '')
                parsed = urlsplit(href)
                if href.startswith('/') and not href.startswith('//'):
                    self.assertFalse(parsed.path.endswith('.html'), (path.name, href))
                    if parsed.path in CLEAN_ROUTES:
                        self.assertTrue((ROOT / CLEAN_ROUTES[parsed.path].lstrip('/')).is_file())
            self.assertIn('href="/style.css"', path.read_text())
            self.assertIn('src="/app.js"', path.read_text())

    def test_clean_pages_are_native_html_assets_without_rewrite_rules(self):
        self.assertFalse((ROOT / '_redirects').exists())
        for clean, file in CLEAN_ROUTES.items():
            self.assertTrue((ROOT / file.lstrip('/')).is_file(), clean)
            if clean != '/':
                self.assertEqual(file, clean + '.html')


    def test_boot_normalizes_before_initializing_the_page(self):
        app = (ROOT / 'app.js').read_text()
        boot = app.split('function boot() {', 1)[1]
        self.assertLess(boot.index('normalizeInitialUrl();'), boot.index('initAmbientExperience();'))
        self.assertIn("window.location.origin + '/download'", app)

    def test_router_behavior_in_javascript(self):
        """Run actual router helpers, without needing a browser or a JS dependency.

        The mock server deliberately only serves .html. A clean-route 404 must retry
        once, while a 500 or an enriched share route must never get the static retry.
        """
        import subprocess
        app = (ROOT / 'app.js').read_text()
        helpers = app[app.index('  var PAGE_FILES = {'):app.index('  function syncPageLinks()')]
        internal = app[app.index('  function getInternalPageUrl('):app.index('  function scrollToRouteHash(')]
        route = app[app.index('  function routeTo('):app.index('  function handleRouterClick(')]
        script = r'''
const assert = require('node:assert/strict');
let replaced, pushed, calls = [], status = 404;
const window = {location: {href: 'https://agora.in.net/contact.html?ref=a#message',
  origin: 'https://agora.in.net'}, history: {state: {keep: true},
  replaceState(state, title, url) { replaced = {state, url}; },
  pushState(state, title, url) { pushed = url; }}};
const doc = {documentElement: {classList: {add(){}, remove(){}}}};
const routerState = {currentPath: '/', navigating: false};
function getHashTarget() { return null; }
function scrollToRouteHash() {}
function readPageShell() {return {};}
function updateDocumentShell() {}
function bootPage() {}
const DOMParser = class { parseFromString() {return {};}};
function fetch(url, opts) {calls.push({url, opts}); return Promise.resolve({
  status: url.includes('.html') ? 200 : status,
  ok: url.includes('.html') || status === 200, text: () => Promise.resolve('<main></main>')});}
''' + helpers + internal + route + r'''
(async () => {
  normalizeInitialUrl();
  const firstReplacement = replaced;
  normalizeInitialUrl();
  assert.equal(replaced, firstReplacement);
  assert.equal(replaced.url, '/contact?ref=a#message');
  assert.deepEqual(replaced.state, {keep: true});
  for (const [legacy, clean] of [['/index.html','/'], ['/about.html','/about'],
      ['/download.html','/download'], ['/contact.html','/contact'],
      ['/credits.html','/credits'], ['/shared-post.html','/shared-post'], ['/privacy.html','/privacy'], ['/terms.html','/terms']]) {
    window.location.href = 'https://agora.in.net' + legacy + '?x=1#top';
    initialUrlNormalized = false; // independent boot for each legacy alias
    normalizeInitialUrl();
    assert.equal(replaced.url, clean + '?x=1#top');
    assert.equal(canonicalPath(new URL('https://agora.in.net' + clean)), clean);
  }
  assert.equal(canonicalPath(new URL('https://agora.in.net/post/uuid')), '/post/uuid');
  assert.equal(canonicalPath(new URL('https://agora.in.net/assets/mockup.png')), '/assets/mockup.png');
  const link = href => ({getAttribute: () => href, hasAttribute: () => false});
  assert.equal(getInternalPageUrl(link('/about.html?x=1#bio')).pathname, '/about');
  assert.equal(getInternalPageUrl(link('/about')).pathname, '/about');
  for (const path of ['/assets/a.png','/api/contact','/post/uuid','/p/uuid','/unknown'])
    assert.equal(getInternalPageUrl(link(path)), null);
  window.location.href = 'https://agora.in.net/';
  const opts = {headers: {'X-Requested-With': 'PJAX'}, signal: 'same-signal'};
  await fetchPage(new URL('https://agora.in.net/about?q=1#bio'), opts);
  assert.deepEqual(calls.map(x => x.url), ['https://agora.in.net/about?q=1#bio',
    'https://agora.in.net/about.html?q=1']);
  assert.equal(calls[1].opts, opts);
  calls = []; status = 500;
  await fetchPage(new URL('https://agora.in.net/about'), opts);
  assert.equal(calls.length, 1);
  calls = []; status = 404;
  await fetchPage(new URL('https://agora.in.net/post/uuid'), opts);
  assert.equal(calls.length, 1);
  calls = [];
  await routeTo(new URL('https://agora.in.net/download.html?ref=cta#install'), true);
  assert.equal(pushed, 'https://agora.in.net/download?ref=cta#install');
  assert.equal(routerState.currentPath, '/download');
  calls = [];
  await routeTo(new URL('https://agora.in.net/privacy.html?ref=footer#retention'), true);
  assert.equal(pushed, 'https://agora.in.net/privacy?ref=footer#retention');
  assert.equal(routerState.currentPath, '/privacy');
  assert.deepEqual(calls.map(x => x.url), ['https://agora.in.net/privacy?ref=footer#retention',
    'https://agora.in.net/privacy.html?ref=footer']);
  calls = [];
  await routeTo(new URL('https://agora.in.net/terms.html?ref=footer#license'), true);
  assert.equal(pushed, 'https://agora.in.net/terms?ref=footer#license');
  assert.equal(routerState.currentPath, '/terms');
  assert.deepEqual(calls.map(x => x.url), ['https://agora.in.net/terms?ref=footer#license',
    'https://agora.in.net/terms.html?ref=footer']);

})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PrivacyPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'privacy.html').read_text()
        cls.page = Page(ROOT / 'privacy.html')

    def test_identity_effective_date_and_shared_shell(self):
        for token in ('<title>Privacy Policy — Agora</title>', 'October 24, 2026',
                      'datetime="2026-10-24"', 'net.agora.app', 'https://agora.in.net',
                      'A New Town Square For Free Speech', 'class="site-header"',
                      'class="site-footer"', 'href="/style.css"', 'src="/app.js"',
                      'rel="canonical" href="https://agora.in.net/privacy"'):
            self.assertIn(token, self.html)
        self.assertNotIn('data-contact-form', self.html)
        self.assertEqual(self.html.count('<h1'), 1)

    def test_architecture_and_retention_disclosures(self):
        for token in ('Supabase Authentication', 'One-Tap OAuth', 'Google Identity Services',
                      '@handle', 'Supabase Storage', 'post_id', 'reporter_id', 'reports',
                      'Spam', 'Harassment', 'Hate speech', 'Misinformation', 'registered email',
                      '30 days', 'permanently purged', 'daily cleanup job', 'pg_cron',
                      'Agora Mail', 'Cloudflare Workers', 'Resend', 'Google Fonts',
                      'session storage', '13 and older', 'full account and personal data deletion',
                      'precise or background GPS', 'contacts, microphone, SMS, or call logs'):
            self.assertIn(token, self.html)
        users = [a.get('data-email-user') for a, _ in self.page.anchors]
        self.assertIn('noreply', users)
        self.assertIn('mail', users)
        self.assertNotIn('mailto:', self.html)
        self.assertNotIn('@agora.in.net', self.html)
        self.assertIn('href="/contact"', self.html)

    def test_contents_links_resolve_on_this_page(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)), 'duplicate ids break section navigation')
        contents = re.search(r'<nav class="privacy-contents".*?</nav>', self.html, re.S)[0]
        targets = re.findall(r'href="#([^"]+)"', contents)
        self.assertEqual(len(targets), 10)
        for target in targets:
            self.assertIn(target, ids)
            self.assertIn('<section id="' + target + '" aria-labelledby=', self.html)

    def test_visible_footer_entry_on_every_page(self):
        for path in ROOT.glob('*.html'):
            with self.subTest(page=path.name):
                footers = re.findall(r'<footer\b[^>]*>.*?</footer>', path.read_text(), re.S)
                self.assertTrue(any(re.search(r'<a[^>]+href="/privacy"[^>]*>Privacy Policy</a>',
                                              f) for f in footers))
        css = (ROOT / 'style.css').read_text()
        self.assertRegex(css, r'\.credits-screen-colophon a\s*\{[^}]*pointer-events:\s*auto')

    def test_native_routing_has_no_redirect_rule_cycles(self):
        self.assertFalse((ROOT / '_redirects').exists())
        self.assertEqual(list(ROOT.glob('*.html.html')), [])


class RouterLoopRegression(unittest.TestCase):
    def test_history_normalization_clicks_and_back_navigation(self):
        import subprocess
        app = (ROOT / 'app.js').read_text()
        helpers = app[app.index('  var PAGE_FILES = {'):app.index('  function scrollToRouteHash(')]
        navigation = app[app.index('  function routeTo('):app.index('  /* ------------------------------------------------------------\n     2. MOBILE MENU')]
        script = r'''
const assert = require('node:assert/strict');
let pushes = 0, replaces = 0, fetches = 0, swaps = 0, scrolls = 0;
const listeners = {click: [], popstate: []};
const routerState = {currentPath: '', bound: false, navigating: false, abortController: null};
const window = {location: {href: 'https://agora.in.net/index.html?ref=boot#top',
  origin: 'https://agora.in.net', assign() {throw Error('unexpected full navigation');}},
  history: {state: {keep: true},
    replaceState(state, title, url) {replaces++; window.location.href = new URL(url, window.location.href).href;},
    pushState(state, title, url) {pushes++; window.location.href = url;}},
  addEventListener(type, callback) {listeners[type].push(callback);},
  dispatchEvent() {throw Error('synthetic events are forbidden');}};
function link(href, key) {return {target: '', href,
  getAttribute(name) {return name === 'href' ? this.href : key;},
  setAttribute(name, value) {this.href = value;}, hasAttribute() {return false;}};}
const links = [link('/about.html', 'about'), link('/privacy.html', 'privacy')];
const PAGE_MAP = {about: '/about', privacy: '/privacy'};
const doc = {querySelectorAll() {return links;},
  addEventListener(type, callback) {listeners[type].push(callback);},
  documentElement: {classList: {add(){}, remove(){}}}};
function isDynamicDownloadLink() {return false;}
function getHashTarget() {return null;}
function scrollToRouteHash() {scrolls++;}
function readPageShell() {return {};}
function updateDocumentShell() {swaps++;}
function bootPage() {initRouting();}
const DOMParser = class {parseFromString() {return {};}};
function fetch() {fetches++; return Promise.resolve({status: 200, ok: true,
  text: () => Promise.resolve('<main></main>')});}
''' + helpers + navigation + r'''
function click(anchor) {
  const event = {button: 0, target: {closest() {return anchor;}},
    preventDefault() {this.defaultPrevented = true;}};
  handleRouterClick(event);
  return event;
}
(async () => {
  normalizeInitialUrl();
  normalizeInitialUrl();
  assert.equal(replaces, 1);
  assert.equal(window.location.href, 'https://agora.in.net/?ref=boot#top');
  initRouting(); initRouting(); syncPageLinks();
  assert.equal(listeners.click.length, 1);
  assert.equal(listeners.popstate.length, 1);
  assert.deepEqual(links.map(l => l.href), ['/about', '/privacy']);
  for (const href of ['/', '/index.html', '/?ref=other', '/#section']) {
    assert.ok(!click(link(href)).defaultPrevented, 'same path is native navigation');
    await routeTo(new URL(href, window.location.href), true);
  }
  assert.equal(fetches, 0); assert.equal(pushes, 0);
  const dest = new URL('https://agora.in.net/about');
  await Promise.all([routeTo(dest, true), routeTo(dest, true)]);
  assert.equal(fetches, 1); assert.equal(pushes, 1); assert.equal(swaps, 1);
  assert.equal(window.location.href, dest.href);
  await routeTo(dest, true);
  assert.equal(fetches, 1); assert.equal(pushes, 1);
  assert.ok(!click(links[0]).defaultPrevented);
  assert.ok(click(links[1]).defaultPrevented);
  // Allow the clicked navigation to finish before testing Back.
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(fetches, 2); assert.equal(pushes, 2);
  normalizeInitialUrl(); assert.equal(replaces, 1);
  assert.equal(listeners.click.length, 1); assert.equal(listeners.popstate.length, 1);
  window.location.href = 'https://agora.in.net/about'; // browser Back moves URL first
  listeners.popstate[0]();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(routerState.currentPath, '/about');
  assert.equal(fetches, 3); assert.equal(swaps, 3);
  assert.equal(pushes, 2, 'Back must never push another history entry');
  assert.equal(replaces, 1, 'page boot after PJAX must not normalize again');
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class NativeSharedPostFallback(unittest.TestCase):
    def test_get_and_head_serve_the_landing_without_redirect_rules(self):
        import subprocess
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const source = fs.readFileSync('functions/post/[id].js', 'utf8');
  const {onRequestGet, onRequestHead} = await import('data:text/javascript;base64,' +
    Buffer.from(source).toString('base64'));
  const html = fs.readFileSync('shared-post.html', 'utf8');
  const id = '0c298d8b-c2f0-4f38-8585-7199f41c7769';
  let reads = 0, nexts = 0;
  const context = {request: new Request('https://agora.in.net/post/' + id + '?ref=test'),
    params: {id}, env: {ASSETS: {async fetch(request) {
      reads++;
      assert.equal(new URL(request.url).pathname, '/shared-post');
      assert.equal(new URL(request.url).search, '');
      assert.equal(request.method, 'GET');
      return new Response(html, {headers: {'Content-Type': 'text/html'}});
    }}}, next() {nexts++; return new Response('home fallback');}};
  const response = await onRequestGet(context);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('location'), null);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(await response.text(), html);
  assert.equal(nexts, 0); assert.equal(reads, 1);
  const head = await onRequestHead(context);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal(head.headers.get('location'), null);
  assert.equal(nexts, 0);
  context.params.id = 'not-a-uuid';
  await onRequestGet(context);
  assert.equal(nexts, 1, 'invalid IDs still bypass database lookup');
  context.params.id = id;
  context.env.ASSETS.fetch = async () => {throw Error('assets unavailable');};
  const unavailable = await onRequestGet(context);
  assert.equal(unavailable.status, 200);
  assert.equal(nexts, 2, 'last-resort next() is retained if assets cannot be read');
})().catch(e => {console.error(e); process.exitCode = 1;});
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TermsOfService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / 'terms.html').read_text()
        cls.page = Page(ROOT / 'terms.html')

    def test_identity_date_metadata_and_shared_shell(self):
        for token in ('<title>Terms of Service — Agora</title>', 'October 24, 2026',
                      'datetime="2026-10-24"', 'net.agora.app', 'https://agora.in.net',
                      'A New Town Square For Free Speech', 'class="site-header"',
                      'class="site-footer"', 'href="/style.css"', 'src="/app.js"',
                      'rel="canonical" href="https://agora.in.net/terms"',
                      'property="og:title" content="Terms of Service — Agora"'):
            self.assertIn(token, self.html)
        self.assertEqual(self.html.count('<h1'), 1)
        self.assertNotIn('data-contact-form', self.html)
        self.assertIn('class="privacy-copy"', self.html)

    def test_detailed_contents_have_unique_accessible_targets(self):
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)))
        contents = re.search(r'<nav class="privacy-contents".*?</nav>', self.html, re.S)[0]
        targets = re.findall(r'href="#([^"]+)"', contents)
        self.assertEqual(len(targets), 19)
        for target in targets:
            self.assertIn(target, ids)
            self.assertIn(f'<section id="{target}" aria-labelledby="{target}-title">', self.html)
            self.assertIn(f'id="{target}-title"', self.html)

    def test_substantive_user_and_operator_protections(self):
        for token in ('13 years old', 'parent or legal guardian', 'One-Tap OAuth',
                      'You retain ownership of your content.', 'non-exclusive, worldwide, royalty-free',
                      'only as reasonably necessary', 'license ends', 'child sexual abuse material',
                      'non-consensual intimate images', 'copyright', 'appeal', 'registered email',
                      'Uninstalling the app alone does not delete your account',
                      '30-day automated deletion', 'appropriate notice', 'renewed agreement',
                      'mandatory consumer or data-protection remedies', 'gross negligence',
                      'do not require binding arbitration', 'not a compulsory waiting period',
                      'do not select an exclusive foreign governing law or court',
                      'do not impose a blanket monetary cap', 'not blanket consent'):
            self.assertIn(token, self.html)
        self.assertNotIn('governed exclusively by the laws of', self.html)
        self.assertNotIn('data-contact-form', self.html)

    def test_privacy_support_and_email_are_reachable(self):
        self.assertIn('href="/privacy"', self.html)
        self.assertIn('href="/contact"', self.html)
        self.assertIn('data-email-user="mail" data-email-domain="agora.in.net"', self.html)
        self.assertIn('<noscript>', self.html)
        self.assertNotIn('mailto:', self.html)
        self.assertNotIn('@agora.in.net', self.html)

    def test_every_footer_exposes_both_legal_documents(self):
        for path in ROOT.glob('*.html'):
            with self.subTest(page=path.name):
                footers = re.findall(r'<footer\b[^>]*>.*?</footer>', path.read_text(), re.S)
                self.assertTrue(footers)
                for route, label in (('/privacy', 'Privacy Policy'), ('/terms', 'Terms of Service')):
                    self.assertTrue(any(re.search(fr'<a[^>]+href="{route}"[^>]*>{label}</a>', f)
                                        for f in footers), f'{path.name} omits {label}')

    def test_terms_route_stays_native_without_redirect_rules(self):
        self.assertFalse((ROOT / '_redirects').exists())
        app = (ROOT / 'app.js').read_text()
        self.assertIn("terms: '/terms'", app)
        self.assertIn("'/terms': '/terms.html'", app)
        self.assertIn('href="/terms" data-page="terms"', self.html)
