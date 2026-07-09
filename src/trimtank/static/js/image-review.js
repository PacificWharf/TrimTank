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
const MIN_CROP_SIZE = 16;
const DEFAULT_ASPECT_KEY = "1:1";
const ASPECT_RATIOS = new Map([
  ["1:1", 1],
  ["4:5", 4 / 5],
  ["3:4", 3 / 4],
  ["4:3", 4 / 3],
  ["3:2", 3 / 2],
  ["free", null],
]);

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
    crop: null,
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
    cropDialog: document.getElementById("crop-dialog"),
    cropFilename: document.getElementById("crop-dialog-filename"),
    cropImage: document.getElementById("crop-image"),
    cropBox: document.getElementById("crop-box"),
    closeCropDialog: document.getElementById("close-crop-dialog"),
    saveCrop: document.getElementById("save-crop"),
    useFullCrop: document.getElementById("use-full-crop"),
    clearCrop: document.getElementById("clear-crop"),
    cropCoordinates: document.getElementById("crop-coordinates"),
    cropMessage: document.getElementById("crop-message"),
    cropAspectButtons: document.querySelectorAll("[data-crop-aspect]"),
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
    if (button) {
      const card = button.closest("[data-filename]");
      if (!card || !state.projectPath) {
        return;
      }

      void saveImageStatus(elements, state, card.dataset.filename, button.dataset.reviewStatus);
      return;
    }

    const cropButton = event.target.closest("button[data-crop-action]");
    if (!cropButton) {
      return;
    }

    const card = cropButton.closest("[data-filename]");
    if (!card || !state.projectPath) {
      return;
    }

    openCropDialog(elements, state, card.dataset.filename);
  });

  elements.closeCropDialog.addEventListener("click", () => {
    closeCropDialog(elements, state);
  });

  elements.cropDialog.addEventListener("click", (event) => {
    if (event.target === elements.cropDialog) {
      closeCropDialog(elements, state);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.cropDialog.hidden) {
      closeCropDialog(elements, state);
    }
  });

  window.addEventListener("resize", () => {
    renderCropBox(elements, state);
  });

  elements.cropImage.addEventListener("load", () => {
    prepareCropImage(elements, state);
  });

  elements.cropImage.addEventListener("error", () => {
    elements.cropBox.hidden = true;
    setCropMessage(elements, "Image preview failed to load.", "error");
  });

  elements.cropBox.addEventListener("pointerdown", (event) => {
    startCropDrag(elements, state, event);
  });

  elements.cropBox.addEventListener("pointermove", (event) => {
    updateCropDrag(elements, state, event);
  });

  elements.cropBox.addEventListener("pointerup", (event) => {
    finishCropDrag(elements, state, event);
  });

  elements.cropBox.addEventListener("pointercancel", (event) => {
    finishCropDrag(elements, state, event);
  });

  elements.saveCrop.addEventListener("click", () => {
    void saveImageCrop(elements, state);
  });

  elements.useFullCrop.addEventListener("click", () => {
    useFullCrop(elements, state);
  });

  elements.clearCrop.addEventListener("click", () => {
    void clearImageCrop(elements, state);
  });

  for (const button of elements.cropAspectButtons) {
    button.addEventListener("click", () => {
      setCropAspect(elements, state, button.dataset.cropAspect, true);
    });
  }

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

  if (image.has_crop) {
    const cropBadge = document.createElement("span");
    cropBadge.className = "crop-badge";
    cropBadge.textContent = "Crop saved";
    meta.append(cropBadge);
  }

  const dimensions = document.createElement("dl");
  dimensions.className = "image-dimensions";

  const sourceDimensions = document.createElement("dd");
  sourceDimensions.textContent = image.raw_width && image.raw_height
    ? formatPixelSize(image.raw_width, image.raw_height)
    : "Loading...";
  dimensions.append(createDimensionRow("Source", sourceDimensions));

  const cropDimensions = document.createElement("dd");
  cropDimensions.textContent = image.has_crop && image.crop
    ? formatPixelSize(image.crop.width, image.crop.height)
    : "None";
  dimensions.append(createDimensionRow("Crop", cropDimensions));

  img.addEventListener("load", () => {
    image.raw_width = img.naturalWidth;
    image.raw_height = img.naturalHeight;
    sourceDimensions.textContent = formatPixelSize(img.naturalWidth, img.naturalHeight);
  });

  details.append(title, meta, dimensions);

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

  const cropButton = document.createElement("button");
  cropButton.type = "button";
  cropButton.dataset.cropAction = "open";
  cropButton.className = "crop-control-button";
  cropButton.textContent = image.has_crop ? "Edit Crop" : "Crop";
  controls.append(cropButton);

  card.append(frame, details, controls);
  return card;
}

function openCropDialog(elements, state, filename) {
  const image = state.images.find((item) => item.filename === filename);
  if (!image) {
    return;
  }

  state.crop = {
    filename,
    image,
    naturalWidth: 0,
    naturalHeight: 0,
    rect: normalizeClientCrop(image.crop),
    aspectKey: image.has_crop ? inferCropAspect(image.crop) : DEFAULT_ASPECT_KEY,
    drag: null,
  };

  elements.cropFilename.textContent = filename;
  elements.cropMessage.textContent = "";
  elements.cropMessage.dataset.tone = "";
  elements.cropCoordinates.textContent = "";
  elements.cropBox.hidden = true;
  elements.cropDialog.hidden = false;
  elements.cropImage.src = imageSourceUrl(state.projectPath, filename);
  elements.cropImage.alt = filename;
  setCropMessage(elements, "Loading image...", "");
  renderAspectControls(elements, state);

  if (elements.cropImage.complete && elements.cropImage.naturalWidth) {
    prepareCropImage(elements, state);
  }
}

function closeCropDialog(elements, state) {
  elements.cropDialog.hidden = true;
  elements.cropImage.removeAttribute("src");
  elements.cropBox.hidden = true;
  state.crop = null;
}

function prepareCropImage(elements, state) {
  if (!state.crop) {
    return;
  }

  state.crop.naturalWidth = elements.cropImage.naturalWidth;
  state.crop.naturalHeight = elements.cropImage.naturalHeight;
  state.crop.image.raw_width = state.crop.naturalWidth;
  state.crop.image.raw_height = state.crop.naturalHeight;

  if (state.crop.rect) {
    state.crop.rect = constrainCropRect(
      state.crop.rect,
      state.crop.naturalWidth,
      state.crop.naturalHeight,
    );
  } else {
    state.crop.rect = defaultCropRect(
      state.crop.naturalWidth,
      state.crop.naturalHeight,
      aspectRatioForKey(state.crop.aspectKey),
    );
  }

  renderCropBox(elements, state);
  setCropMessage(elements, "Adjust the rectangle, then save.", "");
}

function startCropDrag(elements, state, event) {
  if (!state.crop?.rect || event.button !== 0) {
    return;
  }

  event.preventDefault();
  elements.cropBox.setPointerCapture(event.pointerId);
  state.crop.drag = {
    pointerId: event.pointerId,
    mode: event.target.dataset.cropHandle || "move",
    startX: event.clientX,
    startY: event.clientY,
    rect: { ...state.crop.rect },
  };
}

function updateCropDrag(elements, state, event) {
  const cropState = state.crop;
  if (!cropState?.drag || cropState.drag.pointerId !== event.pointerId) {
    return;
  }

  event.preventDefault();

  const scale = displayedImageScale(elements, cropState);
  const deltaX = (event.clientX - cropState.drag.startX) / scale.x;
  const deltaY = (event.clientY - cropState.drag.startY) / scale.y;
  cropState.rect = resizeCropRect(
    cropState.drag.rect,
    cropState.drag.mode,
    deltaX,
    deltaY,
    cropState.naturalWidth,
    cropState.naturalHeight,
    aspectRatioForKey(cropState.aspectKey),
  );
  renderCropBox(elements, state);
}

function finishCropDrag(elements, state, event) {
  if (!state.crop?.drag || state.crop.drag.pointerId !== event.pointerId) {
    return;
  }

  state.crop.drag = null;
  if (elements.cropBox.hasPointerCapture(event.pointerId)) {
    elements.cropBox.releasePointerCapture(event.pointerId);
  }
}

async function saveImageCrop(elements, state) {
  const cropState = state.crop;
  if (!cropState?.rect) {
    return;
  }

  setCropBusy(elements, true);
  setCropMessage(elements, "Saving crop...", "");

  try {
    const data = await apiPost("/api/projects/images/crop", {
      path: state.projectPath,
      filename: cropState.filename,
      crop: cropState.rect,
    });
    updateImageCropState(state, data.filename, data.crop, data.has_crop);
    cropState.rect = normalizeClientCrop(data.crop) || cropState.rect;
    renderCropBox(elements, state);
    renderImages(elements, state);
    setCropMessage(elements, "Crop saved.", "ok");
  } catch (error) {
    setCropMessage(elements, getErrorMessage(error), "error");
  } finally {
    setCropBusy(elements, false);
  }
}

async function clearImageCrop(elements, state) {
  const cropState = state.crop;
  if (!cropState) {
    return;
  }

  setCropBusy(elements, true);
  setCropMessage(elements, "Clearing crop...", "");

  try {
    const data = await apiPost("/api/projects/images/crop", {
      path: state.projectPath,
      filename: cropState.filename,
      crop: null,
    });
    updateImageCropState(state, data.filename, data.crop, data.has_crop);
    setCropAspect(elements, state, DEFAULT_ASPECT_KEY, false);
    cropState.rect = defaultCropRect(
      cropState.naturalWidth,
      cropState.naturalHeight,
      aspectRatioForKey(cropState.aspectKey),
    );
    renderCropBox(elements, state);
    renderImages(elements, state);
    setCropMessage(elements, "Crop cleared. A new draft rectangle is ready.", "ok");
  } catch (error) {
    setCropMessage(elements, getErrorMessage(error), "error");
  } finally {
    setCropBusy(elements, false);
  }
}

function useFullCrop(elements, state) {
  if (!state.crop) {
    return;
  }

  setCropAspect(elements, state, "free", false);
  state.crop.rect = {
    x: 0,
    y: 0,
    width: state.crop.naturalWidth,
    height: state.crop.naturalHeight,
  };
  renderCropBox(elements, state);
  setCropMessage(elements, "Full image selected. Save to keep it.", "");
}

function setCropAspect(elements, state, aspectKey, adjustRect) {
  if (!ASPECT_RATIOS.has(aspectKey) || !state.crop) {
    return;
  }

  state.crop.aspectKey = aspectKey;
  const aspectRatio = aspectRatioForKey(aspectKey);
  if (adjustRect && aspectRatio && state.crop.rect) {
    state.crop.rect = fitCropRectToAspect(
      state.crop.rect,
      state.crop.naturalWidth,
      state.crop.naturalHeight,
      aspectRatio,
    );
  }

  renderAspectControls(elements, state);
  renderCropBox(elements, state);
}

function renderAspectControls(elements, state) {
  const activeAspect = state.crop?.aspectKey || DEFAULT_ASPECT_KEY;
  for (const button of elements.cropAspectButtons) {
    const active = button.dataset.cropAspect === activeAspect;
    button.dataset.active = String(active);
    button.setAttribute("aria-pressed", String(active));
  }
}

function renderCropBox(elements, state) {
  const cropState = state.crop;
  if (!cropState?.rect || !cropState.naturalWidth || !cropState.naturalHeight) {
    elements.cropBox.hidden = true;
    elements.cropCoordinates.textContent = "";
    return;
  }

  const scale = displayedImageScale(elements, cropState);
  elements.cropBox.hidden = false;
  elements.cropBox.style.left = `${cropState.rect.x * scale.x}px`;
  elements.cropBox.style.top = `${cropState.rect.y * scale.y}px`;
  elements.cropBox.style.width = `${cropState.rect.width * scale.x}px`;
  elements.cropBox.style.height = `${cropState.rect.height * scale.y}px`;
  elements.cropCoordinates.textContent = formatCropCoordinates(cropState);
}

function displayedImageScale(elements, cropState) {
  return {
    x: elements.cropImage.clientWidth / cropState.naturalWidth,
    y: elements.cropImage.clientHeight / cropState.naturalHeight,
  };
}

function resizeCropRect(startRect, mode, deltaX, deltaY, imageWidth, imageHeight, aspectRatio) {
  const minSize = Math.max(1, Math.min(MIN_CROP_SIZE, imageWidth, imageHeight));
  const rect = { ...startRect };

  if (mode === "move") {
    rect.x = clamp(Math.round(startRect.x + deltaX), 0, imageWidth - startRect.width);
    rect.y = clamp(Math.round(startRect.y + deltaY), 0, imageHeight - startRect.height);
    return rect;
  }

  if (aspectRatio) {
    return resizeAspectCropRect(
      startRect,
      mode,
      deltaX,
      deltaY,
      imageWidth,
      imageHeight,
      aspectRatio,
      minSize,
    );
  }

  if (mode.includes("w")) {
    const right = startRect.x + startRect.width;
    rect.x = clamp(Math.round(startRect.x + deltaX), 0, right - minSize);
    rect.width = right - rect.x;
  }

  if (mode.includes("e")) {
    rect.width = clamp(Math.round(startRect.width + deltaX), minSize, imageWidth - startRect.x);
  }

  if (mode.includes("n")) {
    const bottom = startRect.y + startRect.height;
    rect.y = clamp(Math.round(startRect.y + deltaY), 0, bottom - minSize);
    rect.height = bottom - rect.y;
  }

  if (mode.includes("s")) {
    rect.height = clamp(Math.round(startRect.height + deltaY), minSize, imageHeight - startRect.y);
  }

  return rect;
}

function resizeAspectCropRect(
  startRect,
  mode,
  deltaX,
  deltaY,
  imageWidth,
  imageHeight,
  aspectRatio,
  minSize,
) {
  const east = mode.includes("e");
  const south = mode.includes("s");
  const anchorX = east ? startRect.x : startRect.x + startRect.width;
  const anchorY = south ? startRect.y : startRect.y + startRect.height;
  const movingX = (east ? startRect.x + startRect.width : startRect.x) + deltaX;
  const movingY = (south ? startRect.y + startRect.height : startRect.y) + deltaY;
  const maxWidth = east ? imageWidth - anchorX : anchorX;
  const maxHeight = south ? imageHeight - anchorY : anchorY;
  const maxRatioWidth = Math.max(minSize, Math.min(maxWidth, maxHeight * aspectRatio));
  const rawWidth = Math.max(minSize, Math.abs(movingX - anchorX));
  const rawHeight = Math.max(minSize, Math.abs(movingY - anchorY));
  const widthFromPointer = Math.abs(deltaX) >= Math.abs(deltaY)
    ? rawWidth
    : rawHeight * aspectRatio;
  const width = clamp(Math.round(widthFromPointer), minSize, maxRatioWidth);
  const height = Math.round(width / aspectRatio);

  return {
    x: east ? anchorX : anchorX - width,
    y: south ? anchorY : anchorY - height,
    width,
    height,
  };
}

function constrainCropRect(rect, imageWidth, imageHeight) {
  const minSize = Math.max(1, Math.min(MIN_CROP_SIZE, imageWidth, imageHeight));
  const width = clamp(rect.width, minSize, imageWidth);
  const height = clamp(rect.height, minSize, imageHeight);

  return {
    x: clamp(rect.x, 0, imageWidth - width),
    y: clamp(rect.y, 0, imageHeight - height),
    width,
    height,
  };
}

function fitCropRectToAspect(rect, imageWidth, imageHeight, aspectRatio) {
  const minSize = Math.max(1, Math.min(MIN_CROP_SIZE, imageWidth, imageHeight));
  const centerX = rect.x + rect.width / 2;
  const centerY = rect.y + rect.height / 2;
  let width = rect.width;
  let height = rect.height;

  if (width / height > aspectRatio) {
    width = height * aspectRatio;
  } else {
    height = width / aspectRatio;
  }

  width = clamp(Math.round(width), minSize, imageWidth);
  height = clamp(Math.round(height), minSize, imageHeight);

  if (width / height > aspectRatio) {
    width = Math.round(height * aspectRatio);
  } else {
    height = Math.round(width / aspectRatio);
  }

  return {
    x: clamp(Math.round(centerX - width / 2), 0, imageWidth - width),
    y: clamp(Math.round(centerY - height / 2), 0, imageHeight - height),
    width,
    height,
  };
}

function defaultCropRect(width, height, aspectRatio = 1) {
  const minSize = Math.max(1, Math.min(MIN_CROP_SIZE, width, height));
  const maxWidth = Math.max(minSize, Math.round(width * 0.8));
  const maxHeight = Math.max(minSize, Math.round(height * 0.8));
  let cropWidth = Math.min(width, maxWidth);
  let cropHeight = Math.min(height, maxHeight);

  if (aspectRatio) {
    if (cropWidth / cropHeight > aspectRatio) {
      cropWidth = Math.round(cropHeight * aspectRatio);
    } else {
      cropHeight = Math.round(cropWidth / aspectRatio);
    }
  }

  return {
    x: Math.round((width - cropWidth) / 2),
    y: Math.round((height - cropHeight) / 2),
    width: cropWidth,
    height: cropHeight,
  };
}

function aspectRatioForKey(aspectKey) {
  return ASPECT_RATIOS.has(aspectKey) ? ASPECT_RATIOS.get(aspectKey) : 1;
}

function inferCropAspect(crop) {
  const rect = normalizeClientCrop(crop);
  if (!rect) {
    return DEFAULT_ASPECT_KEY;
  }

  const ratio = rect.width / rect.height;
  for (const [key, aspectRatio] of ASPECT_RATIOS) {
    if (aspectRatio && Math.abs(ratio - aspectRatio) < 0.01) {
      return key;
    }
  }

  return "free";
}

function normalizeClientCrop(crop) {
  if (!crop || typeof crop !== "object") {
    return null;
  }

  const rect = {};
  for (const key of ["x", "y", "width", "height"]) {
    const value = crop[key];
    if (!Number.isFinite(value)) {
      return null;
    }
    rect[key] = Math.round(value);
  }

  if (rect.width <= 0 || rect.height <= 0 || rect.x < 0 || rect.y < 0) {
    return null;
  }

  return rect;
}

function updateImageCropState(state, filename, crop, hasCrop) {
  const image = state.images.find((item) => item.filename === filename);
  if (!image) {
    return;
  }

  image.crop = crop || null;
  image.has_crop = Boolean(hasCrop);
}

function setCropBusy(elements, busy) {
  elements.saveCrop.disabled = busy;
  elements.useFullCrop.disabled = busy;
  elements.clearCrop.disabled = busy;
  for (const button of elements.cropAspectButtons) {
    button.disabled = busy;
  }
}

function setCropMessage(elements, text, tone) {
  elements.cropMessage.textContent = text;
  elements.cropMessage.dataset.tone = tone;
}

function formatCropCoordinates(cropState) {
  const source = formatPixelSize(cropState.naturalWidth, cropState.naturalHeight);
  const crop = formatPixelSize(cropState.rect.width, cropState.rect.height);
  return `Source ${source} / Crop x ${cropState.rect.x}, y ${cropState.rect.y}, ${crop}`;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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

function formatPixelSize(width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return "";
  }

  return `${Math.round(width)} x ${Math.round(height)} px`;
}

function createDimensionRow(label, valueElement) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = label;
  row.append(term, valueElement);
  return row;
}

function setMessage(elements, text, tone) {
  elements.message.textContent = text;
  elements.message.dataset.tone = tone;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
