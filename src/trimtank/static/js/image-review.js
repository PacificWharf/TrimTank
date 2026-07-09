import { apiGet, apiPost } from "./api.js";

const FILTER_STATUSES = ["all", "unreviewed", "keep", "reject", "duplicate", "unsure"];
const REVIEW_CONTROLS = ["unreviewed", "keep", "reject", "duplicate", "unsure"];
const STATUS_LABELS = {
  all: "All statuses",
  unreviewed: "Unreviewed",
  keep: "Keep",
  reject: "Reject",
  duplicate: "Duplicate",
  unsure: "Unsure",
};

export function initImageReview() {
  const elements = getElements();
  if (!elements.panel) {
    return;
  }

  const state = {
    projectPath: "",
    images: [],
    counts: emptyCounts(),
    filter: elements.statusFilter.value || "all",
  };

  bindReviewControls(elements, state);
}

function getElements() {
  return {
    panel: document.getElementById("image-review"),
    sourcePath: document.getElementById("review-source-path"),
    count: document.getElementById("review-count"),
    statusFilter: document.getElementById("review-status-filter"),
    refresh: document.getElementById("refresh-images"),
    statusCounts: document.getElementById("review-status-counts"),
    message: document.getElementById("image-review-message"),
    grid: document.getElementById("image-grid"),
  };
}

function bindReviewControls(elements, state) {
  elements.statusFilter.addEventListener("change", () => {
    state.filter = elements.statusFilter.value;
    renderImages(elements, state);
  });

  elements.refresh.addEventListener("click", () => {
    void loadProjectImages(elements, state);
  });

  elements.grid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-review-status]");
    if (!button) {
      return;
    }

    const card = button.closest("[data-filename]");
    if (!card || !state.projectPath) {
      return;
    }

    void saveImageStatus(elements, state, card.dataset.filename, button.dataset.reviewStatus);
  });

  window.addEventListener("trimtank:project-opened", (event) => {
    const project = event.detail;
    if (!project?.path) {
      return;
    }

    state.projectPath = project.path;
    elements.panel.hidden = false;
    void loadProjectImages(elements, state);
  });
}

async function loadProjectImages(elements, state) {
  if (!state.projectPath) {
    return;
  }

  setMessage(elements, "Loading images...", "");
  elements.refresh.disabled = true;

  try {
    const data = await apiGet("/api/projects/images", { path: state.projectPath });
    state.images = Array.isArray(data.images) ? data.images : [];
    state.counts = data.counts || countStatuses(state.images);
    elements.sourcePath.textContent = data.inputs_path || "inputs/";
    renderStatusCounts(elements, state);
    renderImages(elements, state);
  } catch (error) {
    state.images = [];
    state.counts = emptyCounts();
    renderStatusCounts(elements, state);
    elements.grid.replaceChildren();
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    elements.refresh.disabled = false;
  }
}

async function saveImageStatus(elements, state, filename, status) {
  if (!filename || !status) {
    return;
  }

  setImageBusy(elements, filename, true);
  setMessage(elements, `Saving ${filename}...`, "");

  try {
    const data = await apiPost("/api/projects/images/status", {
      path: state.projectPath,
      filename,
      status,
    });
    const image = state.images.find((item) => item.filename === filename);
    if (image) {
      image.status = data.status;
    }
    state.counts = data.counts || countStatuses(state.images);
    renderStatusCounts(elements, state);
    renderImages(elements, state);
  } catch (error) {
    setImageBusy(elements, filename, false);
    setMessage(elements, getErrorMessage(error), "error");
  }
}

function renderStatusCounts(elements, state) {
  const counts = state.counts || emptyCounts();
  elements.count.textContent = `${counts.total || 0} images`;
  elements.statusCounts.replaceChildren();

  for (const status of REVIEW_CONTROLS) {
    const chip = document.createElement("span");
    chip.className = "status-count";
    chip.dataset.status = status;
    chip.textContent = `${STATUS_LABELS[status]}: ${counts[status] || 0}`;
    elements.statusCounts.append(chip);
  }
}

function renderImages(elements, state) {
  const filter = FILTER_STATUSES.includes(state.filter) ? state.filter : "all";
  const visibleImages = filter === "all"
    ? state.images
    : state.images.filter((image) => image.status === filter);

  elements.grid.replaceChildren();

  if (!state.images.length) {
    setMessage(elements, "No supported images found in inputs/.", "warn");
    return;
  }

  if (!visibleImages.length) {
    setMessage(elements, `No ${STATUS_LABELS[filter].toLowerCase()} images.`, "warn");
    return;
  }

  setMessage(elements, `Showing ${visibleImages.length} of ${state.images.length} images.`, "");
  for (const image of visibleImages) {
    elements.grid.append(createImageCard(image, state.projectPath));
  }
}

function createImageCard(image, projectPath) {
  const card = document.createElement("article");
  card.className = "image-card";
  card.dataset.filename = image.filename;
  card.dataset.status = image.status;

  const frame = document.createElement("div");
  frame.className = "image-frame";

  const img = document.createElement("img");
  img.src = imageSourceUrl(projectPath, image.filename);
  img.alt = image.filename;
  img.loading = "lazy";
  img.decoding = "async";
  img.addEventListener("error", () => {
    frame.dataset.error = "true";
  });

  const fallback = document.createElement("span");
  fallback.textContent = "Preview unavailable";

  frame.append(img, fallback);

  const details = document.createElement("div");
  details.className = "image-details";

  const title = document.createElement("h3");
  title.textContent = image.filename;

  const meta = document.createElement("div");
  meta.className = "image-meta";

  const badge = document.createElement("span");
  badge.className = "status-badge";
  badge.dataset.status = image.status;
  badge.textContent = STATUS_LABELS[image.status] || image.status;

  const size = document.createElement("span");
  size.textContent = formatFileSize(image.size);

  meta.append(badge, size);
  details.append(title, meta);

  const controls = document.createElement("div");
  controls.className = "status-controls";
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", `Review status for ${image.filename}`);

  for (const status of REVIEW_CONTROLS) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.reviewStatus = status;
    button.dataset.active = String(image.status === status);
    button.setAttribute("aria-pressed", String(image.status === status));
    button.textContent = STATUS_LABELS[status];
    controls.append(button);
  }

  card.append(frame, details, controls);
  return card;
}

function imageSourceUrl(projectPath, filename) {
  const url = new URL("/api/projects/images/source", window.location.origin);
  url.searchParams.set("path", projectPath);
  url.searchParams.set("filename", filename);
  return url.toString();
}

function setImageBusy(elements, filename, busy) {
  const selector = `[data-filename="${CSS.escape(filename)}"] button[data-review-status]`;
  for (const button of elements.grid.querySelectorAll(selector)) {
    button.disabled = busy;
  }
}

function countStatuses(images) {
  const counts = emptyCounts();
  counts.total = images.length;
  for (const image of images) {
    if (Object.prototype.hasOwnProperty.call(counts, image.status)) {
      counts[image.status] += 1;
    }
  }
  return counts;
}

function emptyCounts() {
  return {
    total: 0,
    unreviewed: 0,
    keep: 0,
    reject: 0,
    duplicate: 0,
    unsure: 0,
  };
}

function formatFileSize(value) {
  if (!Number.isFinite(value) || value < 0) {
    return "";
  }

  if (value < 1024) {
    return `${value} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function setMessage(elements, text, tone) {
  elements.message.textContent = text;
  elements.message.dataset.tone = tone;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
