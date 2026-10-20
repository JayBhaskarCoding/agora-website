/* ============================================================
   AGORA — /p/:id   (short alias for /post/:id)

   The long route is the one the Android app shares; this is the
   short alias for people typing or truncating a link. Both get
   the same server-rendered author card and the same og:* tags,
   so the alias delegates instead of duplicating four hundred
   lines that would then drift apart.

   Two deliberate details:

   1. This is a real route file importing a sibling route file,
      rather than both importing a helper from functions/_shared/.
      Pages excludes some underscore-prefixed paths from routing,
      but a shared link is a poor thing to bet on that detail:
      importing a file that is itself a live route cannot be
      affected by it either way.

   2. og:url still points at /post/<id>. That is the canonical
      route, and chat apps deduplicate previews by og:url, so a
      link shared both ways should produce one card, not two.
   ============================================================ */

export { onRequestGet, onRequestHead } from '../post/[id].js';
