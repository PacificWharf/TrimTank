import { initImageReview } from "./image-review.js";
import { initProjectPicker } from "./project-picker.js";

function markJavaScriptReady() {
  document.documentElement.dataset.js = "ready";
}

function init() {
  markJavaScriptReady();
  initProjectPicker();
  initImageReview();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}
