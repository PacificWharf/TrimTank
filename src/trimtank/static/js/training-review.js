import { apiGet, apiPost } from "./api.js";

const REVIEW_PROJECT_KEY = "trimtank.reviewProjectPath";

export function initTrainingReview() {
  const elements = getElements();
  if (!elements.page) {
    return;
  }

  const projectPath = projectPathFromUrl() || window.localStorage.getItem(REVIEW_PROJECT_KEY) || "";
  if (!projectPath) {
    setMessage(elements, "Open a project and run Prepare for Training first.", "warn");
    return;
  }

  const state = {
    projectPath,
    cacheToken: "",
  };

  bindTrainingReview(elements, state);
  elements.path.textContent = projectPath;
  window.localStorage.setItem(REVIEW_PROJECT_KEY, projectPath);
  void loadTrainingOutputs(elements, state);
}

function getElements() {
  return {
    page: document.querySelector('[data-page="training-review"]'),
    path: document.getElementById("training-review-path"),
    summary: document.getElementById("training-review-summary"),
    count: document.getElementById("training-review-count"),
    message: document.getElementById("training-review-message"),
    grid: document.getElementById("training-output-grid"),
    upscale: document.getElementById("upscale-training"),
    upscaleDialog: document.getElementById("upscale-confirm-dialog"),
    upscalePath: document.getElementById("upscale-confirm-path"),
    cancelUpscale: document.getElementById("cancel-upscale-training"),
    confirmUpscale: document.getElementById("confirm-upscale-training"),
  };
}

function bindTrainingReview(elements, state) {
  elements.upscale.addEventListener("click", () => {
    openUpscaleDialog(elements, state);
  });

  elements.cancelUpscale.addEventListener("click", () => {
    closeUpscaleDialog(elements);
  });

  elements.upscaleDialog.addEventListener("click", (event) => {
    if (event.target === elements.upscaleDialog) {
      closeUpscaleDialog(elements);
    }
  });

  elements.confirmUpscale.addEventListener("click", () => {
    void upscaleTrainingOutputs(elements, state);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.upscaleDialog.hidden) {
      closeUpscaleDialog(elements);
    }
  });
}

async function loadTrainingOutputs(elements, state) {
  setMessage(elements, "Loading prepared images...", "");
  elements.upscale.disabled = true;

  try {
    const data = await apiGet("/api/projects/training", { path: state.projectPath });
    renderTrainingOutputs(elements, state, data);
  } catch (error) {
    elements.grid.replaceChildren();
    setMessage(elements, getErrorMessage(error), "error");
  }
}

function renderTrainingOutputs(elements, state, data) {
  const outputs = Array.isArray(data.outputs) ? data.outputs : [];
  elements.grid.replaceChildren();
  elements.count.textContent = `${outputs.length} images`;
  elements.summary.textContent = data.training_path || "training/";
  elements.upscale.disabled = !outputs.length;

  if (!outputs.length) {
    setMessage(elements, "No prepared training images found.", "warn");
    return;
  }

  setMessage(elements, `Showing ${outputs.length} prepared images.`, "");
  for (const output of outputs) {
    elements.grid.append(createTrainingCard(state.projectPath, output, state.cacheToken));
  }
}

function openUpscaleDialog(elements, state) {
  elements.upscalePath.textContent = state.projectPath;
  elements.upscaleDialog.hidden = false;
}

function closeUpscaleDialog(elements) {
  elements.upscaleDialog.hidden = true;
}

async function upscaleTrainingOutputs(elements, state) {
  setBusy(elements, true);
  setMessage(elements, "Resizing prepared images to exact bucket sizes...", "");

  try {
    const data = await apiPost("/api/projects/training/upscale", {
      path: state.projectPath,
      confirm_overwrite: true,
    });
    closeUpscaleDialog(elements);
    state.cacheToken = String(Date.now());
    await loadTrainingOutputs(elements, state);
    setMessage(elements, upscaleMessage(data), data.warnings?.length ? "warn" : "ok");
  } catch (error) {
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    setBusy(elements, false);
  }
}

function createTrainingCard(projectPath, output, cacheToken) {
  const card = document.createElement("article");
  card.className = "image-card";

  const frame = document.createElement("div");
  frame.className = "image-frame";

  const image = document.createElement("img");
  image.src = trainingImageUrl(projectPath, output.filename, cacheToken);
  image.alt = output.filename;
  image.loading = "lazy";
  image.decoding = "async";
  image.addEventListener("error", () => {
    frame.dataset.error = "true";
  });

  const fallback = document.createElement("span");
  fallback.textContent = "Preview unavailable";
  frame.append(image, fallback);

  const details = document.createElement("div");
  details.className = "image-details";

  const title = document.createElement("h3");
  title.textContent = output.filename;

  const dimensions = document.createElement("dl");
  dimensions.className = "image-dimensions";
  const size = document.createElement("dd");
  size.textContent = "Loading...";
  dimensions.append(createDimensionRow("Size", size));
  image.addEventListener("load", () => {
    size.textContent = `${image.naturalWidth} x ${image.naturalHeight} px`;
  });

  const caption = document.createElement("p");
  caption.className = "caption-preview";
  caption.textContent = output.caption || "";

  details.append(title, dimensions, caption);
  card.append(frame, details);
  return card;
}

function createDimensionRow(label, valueElement) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = label;
  row.append(term, valueElement);
  return row;
}

function trainingImageUrl(projectPath, filename, cacheToken = "") {
  const url = new URL("/api/projects/training/image", window.location.origin);
  url.searchParams.set("path", projectPath);
  url.searchParams.set("filename", filename);
  if (cacheToken) {
    url.searchParams.set("v", cacheToken);
  }
  return url.toString();
}

function projectPathFromUrl() {
  return new URLSearchParams(window.location.search).get("path") || "";
}

function setMessage(elements, text, tone) {
  elements.message.textContent = text;
  elements.message.dataset.tone = tone;
}

function setBusy(elements, busy) {
  elements.upscale.disabled = busy;
  elements.confirmUpscale.disabled = busy;
}

function upscaleMessage(data) {
  const changed = data.changed_count || 0;
  const skipped = data.skipped_count || 0;
  const warnings = data.warnings?.length ? ` ${data.warnings.length} warnings.` : "";
  return `Resized ${changed} images. Skipped ${skipped}.${warnings}`;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
