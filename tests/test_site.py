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
LOGO = "/assets/agora-logo.svg"


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
                self.assertEqual(len(marks), 2, "Navbar and footer both need the logo")
                self.assertTrue(all(a.get("src") == LOGO and a.get("alt") == "Agora" for a in marks))
                icons = [a for tag, a in page.tags if tag == "link" and a.get("rel") == "icon"]
                self.assertEqual(icons[0]["href"], LOGO)
                self.assertEqual(icons[0]["type"], "image/svg+xml")

    def test_download_ctas(self):
        downloads = 0
        for page in self.pages.values():
            for attrs, text in page.anchors:
                if "btn--primary" in attrs.get("class", ""):
                    self.assertEqual(" ".join(text.split()), "Download APK")
                    self.assertIn(attrs.get("href"), ["/download.html", "/app-beta-v2.0.apk"])
                if "download" in attrs:
                    downloads += 1
                    self.assertTrue((ROOT / attrs["href"].lstrip("/")).is_file())
        self.assertEqual(downloads, 2)

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
        # Only the three explicitly documented, pending captures may be absent.
        for name, page in self.pages.items():
            for tag, attrs in page.tags:
                for attr in ("src", "href"):
                    url = attrs.get(attr, "")
                    if url.startswith("/"):
                        path = urlsplit(url).path
                        with self.subTest(page=name, url=url):
                            self.assertTrue(path in CAPTURES or (ROOT / path.lstrip("/")).is_file())

    def test_theme_contract(self):
        self.assertIn("--accent-deep: #A855F7;", self.css)
        primary = re.search(r"\.btn--primary \{([^}]+)\}", self.css)[1]
        self.assertIn("background: var(--accent-deep)", primary)
        self.assertIn("border-radius: 9999px", primary)
        self.assertIn("backdrop-filter: blur(18px)", self.css)
        self.assertEqual(self.css.count("{"), self.css.count("}"))
        for old_accent in ["#a5f3fc", "#22d3ee", "--emerald", "#fda4af"]:
            self.assertNotIn(old_accent, self.css)


if __name__ == "__main__":
    unittest.main()
