# Agora launch assets

## Brand asset

`/assets/agora-logo.svg` is the single logo source for every navbar, footer,
favicon, and the download card. It contains the existing repository logo artwork
(previously `favicon.svg`), not the generic circle used by the old navbar.
Replace this file with the final approved SVG export without changing any HTML.
Keep the artwork's native colors; the surrounding UI uses purple `#A855F7`.
If delivering PNG instead, update all logo sources and favicon MIME types together.

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
- Current downloads serve `/app-beta-v2.0.apk` (37,917,762 bytes, about 38 MB).
  This is the existing beta, not a newly signed or verified official release.
  Upload the final release and update both direct links in `download.html` and
  `shared-post.html`, plus version, minimum Android version, and file-size copy
  after checking the release manifest. No APK was modified by the theme update.
- The feedback form and shared-post backend remain demos; see the root README.
