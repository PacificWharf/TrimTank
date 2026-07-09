import { apiGet } from "./api.js";

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

  elements.path.textContent = projectPath;
  window.localStorage.setItem(REVIEW_PROJECT_KEY, projectPath);
  void loadTrainingOutputs(elements, projectPath);
}

function getElements() {
  return {
    page: document.querySelector('[data-page="training-review"]'),
    path: document.getElementById("training-review-path"),
    summary: document.getElementById("training-review-summary"),
    count: document.getElementById("training-review-count"),
    message: document.getElementById("training-review-message"),
    grid: document.getElementById("training-output-grid"),
  };
}

async function loadTrainingOutputs(elements, projectPath) {
  setMessage(elements, "Loading prepared images...", "");

  try {
    const data = await apiGet("/api/projects/training", { path: projectPath });
    renderTrainingOutputs(elements, projectPath, data);
  } catch (error) {
    elements.grid.replaceChildren();
    setMessage(elements, getErrorMessage(error), "error");
  }
}

function renderTrainingOutputs(elements, projectPath, data) {
  const outputs = Array.isArray(data.outputs) ? data.outputs : [];
  elements.grid.replaceChildren();
  elements.count.textContent = `${outputs.length} images`;
  elements.summary.textContent = data.training_path || "training/";

  if (!outputs.length) {
    setMessage(elements, "No prepared training images found.", "warn");
    return;
  }

  setMessage(elements, `Showing ${outputs.length} prepared images.`, "");
  for (const output of outputs) {
    elements.grid.append(createTrainingCard(projectPath, output));
  }
}

function createTrainingCard(projectPath, output) {
  const card = document.createElement("article");
  card.className = "image-card";

  const frame = document.createElement("div");
  frame.className = "image-frame";

  const image = document.createElement("img");
  image.src = trainingImageUrl(projectPath, output.filename);
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

function trainingImageUrl(projectPath, filename) {
  const url = new URL("/api/projects/training/image", window.location.origin);
  url.searchParams.set("path", projectPath);
  url.searchParams.set("filename", filename);
  return url.toString();
}

function projectPathFromUrl() {
  return new URLSearchParams(window.location.search).get("path") || "";
}

function setMessage(elements, text, tone) {
  elements.message.textContent = text;
  elements.message.dataset.tone = tone;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
