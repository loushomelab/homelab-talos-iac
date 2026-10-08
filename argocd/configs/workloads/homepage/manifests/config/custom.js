// Homepage preloads /api/config/custom.css from src/pages/_document.jsx
// (<link rel="preload" as="style">). Safari reuses that preload cache entry for
// the stylesheet and keeps serving the old bytes after the file changes, so a
// custom.css edit stays invisible even after a reload. The server is not at
// fault: it sends cache-control: no-store with a fresh ETag, and a link created
// from script does fetch the new file. Re-apply the sheet through such a link,
// and drop the stale node once the fresh one has loaded so there is no flash.
(() => {
  const href = "/api/config/custom.css";

  const refresh = () => {
    const stale = document.querySelector(`link[rel="stylesheet"][href="${href}"]`);
    if (!stale) return;

    const fresh = document.createElement("link");
    fresh.rel = "stylesheet";
    fresh.href = href;
    fresh.addEventListener("load", () => stale.remove());
    document.head.appendChild(fresh);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", refresh);
  } else {
    refresh();
  }
})();
