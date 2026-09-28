# /assets — app screenshots

Drop the **real Android screenshots** here, keeping these exact filenames
(the HTML references them with root-absolute paths, e.g. `/assets/home-feed.png`):

| File                        | Used on                                  | Shows                              |
| --------------------------- | ---------------------------------------- | ---------------------------------- |
| `home-feed.png`             | `index.html` hero + gallery, `download.html` | The chronological home timeline |
| `profile-screen.png`        | `index.html` gallery                     | A member profile                   |
| `shared-post-preview.png`   | `index.html` gallery, `shared-post.html` | A single post opened from a link   |

Guidelines
- **Portrait 9:16** (e.g. 1080×1920). Taller captures (1080×2400, 9:20) also work —
  the frame uses `object-fit: cover` anchored to the top, so the bottom is cropped.
- PNG is expected; if you switch to `.webp`/`.jpg`, update the `src` attributes.
- Keep each file under ~500 KB for fast loads (compress with e.g. `pngquant` or Squoosh).
- The current files are generated placeholders — delete/overwrite them freely.
