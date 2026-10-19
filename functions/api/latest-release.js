/* ============================================================
   AGORA — /api/latest-release
   Cloudflare Pages Function that proxies GitHub's "latest
   release" endpoint so the browser never burns a visitor's
   unauthenticated api.github.com quota (60 requests/hour/IP).

   Response shape (mirrors the fields app.js needs):
     {
       ok: true,
       release: {
         url, fileName, size, tag, name, publishedAt, htmlUrl
       },
       cached: boolean,
       fetchedAt: string
     }

   Failure responses keep `ok: false` plus `fallback` (the human
   browsable releases page) so the client can degrade quietly and
   leave the buttons pointing somewhere useful.
   ============================================================ */

const OWNER = 'JayBhaskarCoding';
const REPO = 'agora-android';
const GITHUB_RELEASE_URL = `https://api.github.com/repos/${OWNER}/${REPO}/releases/latest`;
const RELEASES_PAGE_URL = `https://github.com/${OWNER}/${REPO}/releases/latest`;

// Edge cache lifetime. A new build ships far less often than this, and the
// browser adds its own sessionStorage cache on top.
const EDGE_TTL_SECONDS = 300;
const UPSTREAM_TTL_SECONDS = 300;
const REQUEST_TIMEOUT_MS = 8000;

function json(body, status = 200, cacheable = false) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': cacheable
        ? `public, max-age=60, s-maxage=${EDGE_TTL_SECONDS}, stale-while-revalidate=86400`
        : 'no-store',
      // Same-origin in production; the header only matters for local previews
      // served from a different origin than the Pages deployment.
      'Access-Control-Allow-Origin': '*',
      'X-Content-Type-Options': 'nosniff'
    }
  });
}

function failure(message, status = 502) {
  return json({ ok: false, error: message, fallback: RELEASES_PAGE_URL }, status);
}

/** First asset whose name (or download URL) ends in .apk wins. */
function pickApkAsset(release) {
  const assets = release && Array.isArray(release.assets) ? release.assets : [];
  return assets.find((asset) => {
    if (!asset || typeof asset !== 'object') return false;
    const name = typeof asset.name === 'string' ? asset.name : '';
    const url = typeof asset.browser_download_url === 'string' ? asset.browser_download_url : '';
    return /\.apk$/i.test(name) || /\.apk$/i.test(url);
  }) || null;
}

function normalizeRelease(release) {
  const asset = pickApkAsset(release);
  const url = asset && typeof asset.browser_download_url === 'string' ? asset.browser_download_url.trim() : '';
  if (!/^https:\/\//i.test(url)) return null;

  return {
    url,
    fileName: typeof asset.name === 'string' && asset.name ? asset.name : url.split('/').pop() || 'agora.apk',
    size: Number(asset.size) || 0,
    tag: typeof release.tag_name === 'string' ? release.tag_name : '',
    name: typeof release.name === 'string' ? release.name : '',
    publishedAt: typeof release.published_at === 'string' ? release.published_at : '',
    htmlUrl: typeof release.html_url === 'string' && release.html_url ? release.html_url : RELEASES_PAGE_URL
  };
}

function edgeCache() {
  // `caches.default` exists on Cloudflare Workers/Pages; local dev servers
  // (wrangler pages dev aside) may not provide it, so treat it as optional.
  try {
    return typeof caches !== 'undefined' && caches.default ? caches.default : null;
  } catch (error) {
    return null;
  }
}

async function fetchLatestRelease(env) {
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;

  const headers = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'agora-website-release-proxy',
    'X-GitHub-Api-Version': '2022-11-28'
  };
  // Optional: add GITHUB_TOKEN as a Pages secret to raise the upstream quota
  // from 60 to 5,000 requests/hour. Without it the edge cache carries the load.
  const token = env && env.GITHUB_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const response = await fetch(GITHUB_RELEASE_URL, {
      headers,
      signal: controller ? controller.signal : undefined,
      cf: { cacheTtl: UPSTREAM_TTL_SECONDS, cacheEverything: true }
    });

    if (response.status === 404) {
      // A repo with no published releases answers 404 here.
      return { error: 'no-release', status: 404 };
    }
    if (response.status === 403 || response.status === 429) {
      return { error: 'rate-limited', status: 503 };
    }
    if (!response.ok) {
      return { error: 'upstream', status: 502 };
    }

    const release = await response.json();
    const normalized = normalizeRelease(release);
    if (!normalized) return { error: 'no-apk', status: 502 };
    return { release: normalized };
  } catch (error) {
    console.error('Agora latest-release proxy failed.', error);
    return { error: 'network', status: 502 };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function onRequestGet(context) {
  const cache = edgeCache();
  const cacheKey = new Request(context.request.url, { method: 'GET' });

  if (cache) {
    try {
      const hit = await cache.match(cacheKey);
      if (hit) {
        const body = await hit.clone().json().catch(() => null);
        if (body && body.ok) {
          return json({ ...body, cached: true }, 200, true);
        }
      }
    } catch (error) {
      // A broken cache read must never break the endpoint.
      console.error('Agora latest-release cache read failed.', error);
    }
  }

  const result = await fetchLatestRelease(context.env);
  if (!result.release) {
    const message = result.error === 'no-release'
      ? 'The repository has no published release yet.'
      : result.error === 'no-apk'
        ? 'The latest release has no .apk asset.'
        : result.error === 'rate-limited'
          ? 'GitHub rate limited the release lookup.'
          : 'The release lookup is temporarily unavailable.';
    return failure(message, result.status || 502);
  }

  const payload = {
    ok: true,
    release: result.release,
    cached: false,
    fetchedAt: new Date().toISOString()
  };
  const response = json(payload, 200, true);

  if (cache && context.waitUntil) {
    try {
      context.waitUntil(cache.put(cacheKey, response.clone()));
    } catch (error) {
      console.error('Agora latest-release cache write failed.', error);
    }
  }

  return response;
}

// OPTIONS preflight — harmless for same-origin callers, useful in previews.
export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Accept, Content-Type',
      'Access-Control-Max-Age': '86400'
    }
  });
}
