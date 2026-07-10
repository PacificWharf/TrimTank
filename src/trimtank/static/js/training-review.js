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
  setTrainHandoffLink(elements, projectPath);
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
    trainLink: document.getElementById("train-handoff-link"),
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
    elements.grid.append(createTrainingCard(elements, state, output));
  }
}

function openUpscaleDialog(elements, state) {
  elements.upscalePath.textContent = state.projectPath;
  elements.upscaleDialog.hidden = false;
}

function closeUpscaleDialog(elements) {
  elements.upscaleDialog.hidden = true;
}

function setTrainHandoffLink(elements, projectPath) {
  if (!elements.trainLink) {
    return;
  }

  const url = new URL("/train", window.location.origin);
  url.searchParams.set("path", projectPath);
  elements.trainLink.href = url.toString();
  elements.trainLink.hidden = false;
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

function createTrainingCard(elements, state, output) {
  const card = document.createElement("article");
  card.className = "image-card";

  const frame = document.createElement("div");
  frame.className = "image-frame";

  const image = document.createElement("img");
  image.src = trainingImageUrl(state.projectPath, output.filename, state.cacheToken);
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
  if (output.source) {
    const source = document.createElement("dd");
    source.textContent = output.source;
    dimensions.append(createDimensionRow("Source", source));
  }
  const size = document.createElement("dd");
  size.textContent = "Loading...";
  dimensions.append(createDimensionRow("Size", size));
  image.addEventListener("load", () => {
    size.textContent = `${image.naturalWidth} x ${image.naturalHeight} px`;
  });

  const captionEditor = createCaptionEditor(elements, state, output);

  details.append(title, dimensions, captionEditor);
  card.append(frame, details);
  return card;
}

function createCaptionEditor(elements, state, output) {
  const form = document.createElement("form");
  form.className = "caption-editor";

  const textarea = document.createElement("textarea");
  textarea.value = output.caption || "";
  textarea.rows = 3;
  textarea.spellcheck = true;
  textarea.autocomplete = "off";
  textarea.setAttribute("aria-label", `Caption for ${output.filename}`);

  const actions = document.createElement("div");
  actions.className = "caption-editor-actions";

  const status = document.createElement("span");
  status.className = "caption-save-status";
  status.textContent = "Saved";
  status.dataset.tone = "ok";

  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save";
  save.disabled = true;

  let savedCaption = textarea.value;
  textarea.addEventListener("input", () => {
    const changed = textarea.value !== savedCaption;
    save.disabled = !changed;
    status.textContent = changed ? "Unsaved" : "Saved";
    status.dataset.tone = changed ? "warn" : "ok";
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveTrainingCaption({
      elements,
      state,
      output,
      textarea,
      save,
      status,
      onSaved: (caption) => {
        savedCaption = caption;
      },
    });
  });

  actions.append(status, save);
  form.append(textarea, actions);
  return form;
}

async function saveTrainingCaption({ elements, state, output, textarea, save, status, onSaved }) {
  save.disabled = true;
  textarea.disabled = true;
  status.textContent = "Saving";
  status.dataset.tone = "";

  try {
    const data = await apiPost("/api/projects/training/caption", {
      path: state.projectPath,
      filename: output.filename,
      caption: textarea.value,
    });
    const caption = data.caption || "";
    textarea.value = caption;
    onSaved(caption);
    status.textContent = "Saved";
    status.dataset.tone = "ok";
    setMessage(elements, `Saved caption for ${output.filename}.`, "ok");
  } catch (error) {
    save.disabled = false;
    status.textContent = "Error";
    status.dataset.tone = "error";
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    textarea.disabled = false;
  }
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
