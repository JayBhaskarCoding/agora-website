# Agora launch assets

## Brand asset

`/assets/agora-logo.svg` is the single logo source for every navbar, footer,
favicon, and the download card. It contains the existing repository logo artwork
(previously `favicon.svg`), not the generic circle used by the old navbar.
Replace this file with the final approved SVG export without changing any HTML.
Keep the artwork's native colors; the surrounding UI uses violet `#8B5CF6` / `#7C3AED`.
If delivering PNG instead, update all logo sources and favicon MIME types together.

## Credits portraits

The Credits page displays Jayvardhan Bhaskar's portrait from
`/assets/developer.png` and reserves `/assets/yashvardhan-bhaskar.jpg` for
Yashvardhan Bhaskar's supplied portrait. If Yashvardhan's image is not present,
the rotary card shows a designed initials placeholder rather than inventing a
photo. When adding the portrait, use a square image (at least 320×320 pixels)
with enough room for a circular crop.

The third Credits profile uses `/assets/agora-public.jpg`: a purpose-made
community illustration for the people who use Agora. It is intentionally not
the Agora logo or app mark; replace it only if the public/community artwork is
updated deliberately.

## Background music

`/assets/bgMusic.mpeg` is the looping ambient track used by every page. The
single-page app decodes it into one persistent Web Audio buffer source and routes
it through a gentle low-pass filter, compressor, and very low master gain so the
track stays soft rather than sharp. Browsers may wait for the visitor's first
gesture before allowing sound; that first click starts the persistent source.

The About page displays Jayvardhan Bhaskar's portrait from `/assets/developer.png`
at 160×160 with `object-fit: cover`, a subtle ring, and a restrained violet glow.
If the image cannot load, the container shows a labeled fallback rather than
an invented photo. When replacing the portrait, use a square image (at least
320×320 pixels) with enough room for a circular crop.

## Screenshot checklist — exactly 3 unique captures

The preserved layout has **6 placements**, filled by **3 files**:

| File | Content to capture | Placements |
| --- | --- | --- |
| `home-feed.png` | Populated Home Feed in the latest dark theme: readable text and image posts, avatars, timestamps, reaction/comment controls, and bottom navigation. Include purple primary actions where visible. | Homepage hero, gallery slot 1, download page (3) |
| `profile-screen.png` | Complete member profile: avatar, display name, handle, short bio, the current purple profile action, and several populated posts below. Use a demo account with consented content. | Gallery slot 2 (1) |
| `shared-post-preview.png` | A single post opened from a shared link: author, timestamp, full readable text, attached photo, reactions, and visible replies/thread context. Dismiss the share sheet so the post is visible. | Gallery slot 3, shared-post page (2) |

### Capture and upload requirements

- **No external device frame.** Upload raw screen captures, not Samsung marketing
  mockups or images already wrapped in a bezel. CSS supplies a clean, unbranded
  Android frame; no synthetic camera notch is overlaid on the app UI.
- Prefer portrait **1080×1920 (9:16) PNG**. Native **1080×2400 (9:20)** is also
  accepted: `object-fit: contain` preserves the entire capture, with space above
  and below inside the fixed 9:16 slot. Do not stretch or crop away app controls.
- Use the same device, dark theme, status-bar treatment, and UI scale throughout.
  Hide personal notifications and sensitive data. Use realistic, consented demo
  content, not loading skeletons or empty feeds.
- Compress losslessly where practical; target under 500 KB per image without
  sacrificing readable UI. Keep these exact case-sensitive filenames.
- The old generated screenshots (including fake branding) have been removed.
  Until the files arrive, the existing frames show a neutral pending message.
  Real files at these paths appear automatically on the next page load.
- The Custom Cropper and Post Editor are **not separate slots in this retained
  layout**. They are not additional required captures; replacing a gallery slot
  with either would also require changing its filename, caption, and alt text.

## Before the official APK launch

- Replace/approve the SVG logo and upload all three captures above.
- Once captures are approved, replace the homepage's screenshot-preparation copy.
- **Download links need no manual update — but the APK must be named `app.apk`.**
  Every download CTA on `download.html`, `shared-post.html`, `index.html`, and
  `about.html` uses GitHub's permanent latest-release redirect
  (`…/agora-android/releases/latest/download/app.apk`), which GitHub resolves
  server-side to the `app.apk` of whichever release is newest at click time.
  Upload the release asset under any other name and that URL 404s, so keep the
  `app.apk` convention (it is `PREFERRED_APK_NAME` in `app.js` and
  `functions/api/latest-release.js` if it ever needs to move).
  Publish a release and the buttons, version tag, filename, and file-size copy all
  follow on the next load — `initDynamicDownload()` in `app.js` resolves the exact
  asset (covering releases that used a different filename) and rewrites the
  `[data-download-tag|file|size]` hooks.
  The download works with JavaScript disabled and with the GitHub API
  rate-limited; the version/size text in the markup is only a no-JS fallback, so
  refresh it when you want the static copy to match a new build. See **Dynamic
  download links** in the root README for the full contract.
- The feedback form and shared-post backend remain demos; see the root README.
