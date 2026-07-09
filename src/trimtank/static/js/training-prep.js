import { apiGet, apiPost } from "./api.js";

const REVIEW_PROJECT_KEY = "trimtank.reviewProjectPath";
const DEFAULT_SETTINGS = {
  trigger_token: "",
  num_repeats: 10,
  enable_bucket: true,
  resolution: 1024,
  min_bucket_reso: 256,
  max_bucket_reso: 2048,
  bucket_reso_steps: 64,
};

export function initTrainingPrep() {
  const elements = getElements();
  if (!elements.panel) {
    return;
  }

  const state = {
    projectPath: "",
    settings: { ...DEFAULT_SETTINGS },
  };

  bindTrainingPrep(elements, state);
}

function getElements() {
  return {
    panel: document.getElementById("training-prep"),
    triggerToken: document.getElementById("training-trigger-token"),
    numRepeats: document.getElementById("training-num-repeats"),
    enableBucket: document.getElementById("training-enable-bucket"),
    resolution: document.getElementById("training-resolution"),
    minBucket: document.getElementById("training-min-bucket"),
    maxBucket: document.getElementById("training-max-bucket"),
    bucketStep: document.getElementById("training-bucket-step"),
    saveSettings: document.getElementById("save-training-settings"),
    refreshBuckets: document.getElementById("refresh-bucket-stats"),
    prepare: document.getElementById("prepare-training"),
    bucketSummary: document.getElementById("bucket-summary"),
    message: document.getElementById("training-message"),
    reviewLink: document.getElementById("review-training-link"),
    confirmDialog: document.getElementById("prepare-confirm-dialog"),
    confirmPath: document.getElementById("prepare-confirm-path"),
    cancelPrepare: document.getElementById("cancel-prepare-training"),
    confirmPrepare: document.getElementById("confirm-prepare-training"),
  };
}

function bindTrainingPrep(elements, state) {
  elements.saveSettings.addEventListener("click", () => {
    void saveSettings(elements, state);
  });

  elements.refreshBuckets.addEventListener("click", () => {
    void refreshBuckets(elements, state);
  });

  elements.prepare.addEventListener("click", () => {
    void openPrepareConfirmation(elements, state);
  });

  elements.cancelPrepare.addEventListener("click", () => {
    closePrepareConfirmation(elements);
  });

  elements.confirmDialog.addEventListener("click", (event) => {
    if (event.target === elements.confirmDialog) {
      closePrepareConfirmation(elements);
    }
  });

  elements.confirmPrepare.addEventListener("click", () => {
    void prepareTraining(elements, state);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.confirmDialog.hidden) {
      closePrepareConfirmation(elements);
    }
  });

  window.addEventListener("trimtank:project-opened", (event) => {
    const project = event.detail;
    if (!project?.path) {
      return;
    }

    state.projectPath = project.path;
    state.settings = normalizeSettings(project.settings);
    window.localStorage.setItem(REVIEW_PROJECT_KEY, state.projectPath);
    elements.panel.hidden = false;
    renderSettings(elements, state.settings);
    renderReviewLink(elements, state.projectPath);
    void refreshBuckets(elements, state);
  });
}

async function saveSettings(elements, state) {
  if (!state.projectPath) {
    return null;
  }

  setBusy(elements, true);
  setMessage(elements, "Saving training settings...", "");

  try {
    const settings = collectSettings(elements);
    const data = await apiPost("/api/projects/settings", {
      path: state.projectPath,
      settings,
    });
    state.settings = normalizeSettings(data.settings);
    renderSettings(elements, state.settings);
    renderBuckets(elements, data.buckets);
    setMessage(elements, "Training settings saved.", "ok");
    return data;
  } catch (error) {
    setMessage(elements, getErrorMessage(error), "error");
    return null;
  } finally {
    setBusy(elements, false);
  }
}

async function refreshBuckets(elements, state) {
  if (!state.projectPath) {
    return;
  }

  setBusy(elements, true);
  setMessage(elements, "Loading bucket statistics...", "");

  try {
    const data = await apiGet("/api/projects/buckets", { path: state.projectPath });
    renderBuckets(elements, data);
    setMessage(elements, "Bucket statistics loaded.", "");
  } catch (error) {
    elements.bucketSummary.replaceChildren();
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    setBusy(elements, false);
  }
}

async function openPrepareConfirmation(elements, state) {
  if (!state.projectPath) {
    return;
  }

  const settings = collectSettings(elements);
  if (!settings.trigger_token) {
    setMessage(elements, "Trigger token is required before preparing training files.", "warn");
    elements.triggerToken.focus();
    return;
  }

  const saved = await saveSettings(elements, state);
  if (!saved) {
    return;
  }

  elements.confirmPath.textContent = state.projectPath;
  elements.confirmDialog.hidden = false;
}

function closePrepareConfirmation(elements) {
  elements.confirmDialog.hidden = true;
}

async function prepareTraining(elements, state) {
  if (!state.projectPath) {
    return;
  }

  setBusy(elements, true);
  elements.confirmPrepare.disabled = true;
  setMessage(elements, "Preparing training files...", "");

  try {
    const data = await apiPost("/api/projects/prepare", {
      path: state.projectPath,
      confirm_clear_training: true,
    });
    closePrepareConfirmation(elements);
    renderBuckets(elements, data.buckets);
    renderReviewLink(elements, state.projectPath);
    setMessage(elements, preparedMessage(data), data.warnings?.length ? "warn" : "ok");
    window.location.assign(reviewUrl(state.projectPath));
  } catch (error) {
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    elements.confirmPrepare.disabled = false;
    setBusy(elements, false);
  }
}

function renderSettings(elements, settings) {
  elements.triggerToken.value = settings.trigger_token;
  elements.numRepeats.value = settings.num_repeats;
  elements.enableBucket.checked = settings.enable_bucket;
  elements.resolution.value = settings.resolution;
  elements.minBucket.value = settings.min_bucket_reso;
  elements.maxBucket.value = settings.max_bucket_reso;
  elements.bucketStep.value = settings.bucket_reso_steps;
}

function collectSettings(elements) {
  return {
    trigger_token: elements.triggerToken.value.trim(),
    num_repeats: numberValue(elements.numRepeats),
    enable_bucket: elements.enableBucket.checked,
    resolution: numberValue(elements.resolution),
    min_bucket_reso: numberValue(elements.minBucket),
    max_bucket_reso: numberValue(elements.maxBucket),
    bucket_reso_steps: numberValue(elements.bucketStep),
  };
}

function renderBuckets(elements, data) {
  elements.bucketSummary.replaceChildren();
  if (!data) {
    return;
  }

  const heading = document.createElement("div");
  heading.className = "bucket-summary-heading";
  heading.textContent = `${data.total_images || 0} kept images / ${data.bucket_count || 0} buckets`;
  elements.bucketSummary.append(heading);

  if (!data.buckets?.length) {
    const empty = document.createElement("p");
    empty.textContent = "No kept images are ready for bucket statistics.";
    elements.bucketSummary.append(empty);
    return;
  }

  const list = document.createElement("div");
  list.className = "bucket-list";
  for (const bucket of data.buckets) {
    const item = document.createElement("span");
    item.className = "bucket-chip";
    item.textContent = `${bucket.width} x ${bucket.height}: ${bucket.count}`;
    list.append(item);
  }
  elements.bucketSummary.append(list);

  if (data.warnings?.length) {
    const warnings = document.createElement("p");
    warnings.className = "bucket-warnings";
    warnings.textContent = `${data.warnings.length} images could not be inspected.`;
    elements.bucketSummary.append(warnings);
  }
}

function renderReviewLink(elements, projectPath) {
  elements.reviewLink.href = reviewUrl(projectPath);
  elements.reviewLink.hidden = false;
}

function reviewUrl(projectPath) {
  const url = new URL("/review", window.location.origin);
  url.searchParams.set("path", projectPath);
  return url.toString();
}

function normalizeSettings(settings) {
  return {
    ...DEFAULT_SETTINGS,
    ...(settings || {}),
  };
}

function numberValue(input) {
  return Number.parseInt(input.value, 10);
}

function setBusy(elements, busy) {
  elements.saveSettings.disabled = busy;
  elements.refreshBuckets.disabled = busy;
  elements.prepare.disabled = busy;
}

function setMessage(elements, text, tone) {
  elements.message.textContent = text;
  elements.message.dataset.tone = tone;
}

function preparedMessage(data) {
  const count = data.count || 0;
  const warningText = data.warnings?.length ? ` ${data.warnings.length} warnings.` : "";
  return `Prepared ${count} training images.${warningText}`;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
