"""Dependency-free launch structure checks. Run with npm test."""
from collections import Counter
from html.parser import HTMLParser
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
APK_URL = (
    "https://github.com/JayBhaskarCoding/agora-android/releases/download/"
    "v2.0-beta/app-beta-v2.0.apk"
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
        downloads = []
        for name, page in self.pages.items():
            for attrs, text in page.anchors:
                label = " ".join(text.split())
                if "btn--primary" in attrs.get("class", ""):
                    expected = "Download APK" if name == "download.html" and attrs.get("href") == APK_URL else "Get the app"
                    self.assertEqual(label, expected)
                    self.assertEqual("btn--get-app" in attrs.get("class", "").split(), label == "Get the app")
                    self.assertIn(attrs.get("href"), ["/download.html", APK_URL])
                if attrs.get("href", "").endswith(".apk"):
                    downloads.append(name)
                    self.assertEqual(attrs["href"], APK_URL)
                    self.assertNotIn("data-page", attrs, "Routing must not override the release URL")
                    self.assertNotIn("download", attrs, "GitHub handles the cross-origin attachment")
            if name != "download.html":
                self.assertNotIn("download apk", (ROOT / name).read_text().lower())
        self.assertCountEqual(downloads, ["download.html", "shared-post.html"])

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
        primary = re.search(r"\.btn--primary \{([^}]+)\}", self.css)[1]
        self.assertIn("color: #110819", primary)
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


if __name__ == "__main__":
    unittest.main()
