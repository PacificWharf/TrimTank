import { initImageReview } from "./image-review.js";
import { initProjectPicker } from "./project-picker.js";
import { initTrainingHandoff } from "./training-handoff.js";
import { initTrainingPrep } from "./training-prep.js";
import { initTrainingReview } from "./training-review.js";

function markJavaScriptReady() {
  document.documentElement.dataset.js = "ready";
}

function init() {
  markJavaScriptReady();
  initProjectPicker();
  initImageReview();
  initTrainingPrep();
  initTrainingReview();
  initTrainingHandoff();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}
