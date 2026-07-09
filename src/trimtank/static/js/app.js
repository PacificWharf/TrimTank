(() => {
  function markJavaScriptReady() {
    document.documentElement.dataset.js = "ready";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", markJavaScriptReady, { once: true });
    return;
  }

  markJavaScriptReady();
})();
