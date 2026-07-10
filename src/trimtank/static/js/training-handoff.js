import { apiGet } from "./api.js";

const REVIEW_PROJECT_KEY = "trimtank.reviewProjectPath";

export function initTrainingHandoff() {
  const elements = getElements();
  if (!elements.page) {
    return;
  }

  const projectPath = projectPathFromUrl() || window.localStorage.getItem(REVIEW_PROJECT_KEY) || "";
  if (!projectPath) {
    setMessage(elements, "Open a project and prepare training files first.", "warn");
    return;
  }

  elements.path.textContent = projectPath;
  setReviewLink(elements, projectPath);
  window.localStorage.setItem(REVIEW_PROJECT_KEY, projectPath);

  elements.refresh.addEventListener("click", () => {
    void loadValidation(elements, projectPath);
  });

  void loadValidation(elements, projectPath);
}

function getElements() {
  return {
    page: document.querySelector('[data-page="training-handoff"]'),
    path: document.getElementById("train-handoff-path"),
    reviewLink: document.getElementById("train-review-link"),
    refresh: document.getElementById("refresh-validation"),
    status: document.getElementById("validation-status"),
    summary: document.getElementById("validation-summary"),
    message: document.getElementById("train-handoff-message"),
    checks: document.getElementById("validation-checks"),
    issues: document.getElementById("validation-issues"),
    trainingPath: document.getElementById("handoff-training-path"),
    configPath: document.getElementById("handoff-config-path"),
    configArg: document.getElementById("handoff-config-arg"),
  };
}

async function loadValidation(elements, projectPath) {
  setMessage(elements, "Checking training handoff...", "");
  elements.refresh.disabled = true;
  elements.status.textContent = "Checking";
  elements.status.dataset.tone = "";

  try {
    const data = await apiGet("/api/projects/training/validation", { path: projectPath });
    renderValidation(elements, data);
  } catch (error) {
    elements.checks.replaceChildren();
    elements.issues.replaceChildren();
    elements.status.textContent = "Error";
    elements.status.dataset.tone = "error";
    setMessage(elements, getErrorMessage(error), "error");
  } finally {
    elements.refresh.disabled = false;
  }
}

function renderValidation(elements, data) {
  const errorCount = data.issue_counts?.error || 0;
  const warningCount = data.issue_counts?.warn || 0;
  const ready = data.status === "ready";

  elements.status.textContent = ready ? "Ready" : "Blocked";
  elements.status.dataset.tone = ready ? "ok" : "error";
  elements.summary.textContent = ready
    ? `${data.image_count || 0} prepared images are ready for Kohya.`
    : `${errorCount} errors and ${warningCount} warnings need review.`;

  elements.trainingPath.textContent = data.training_path || "-";
  elements.configPath.textContent = data.config_path || "-";
  elements.configArg.textContent = data.kohya?.dataset_config_arg || "-";

  renderChecks(elements.checks, data.checks || []);
  renderIssues(elements.issues, data.issues || []);
  setMessage(elements, ready ? "Validation passed." : "Validation found issues.", ready ? "ok" : "warn");
}

function renderChecks(container, checks) {
  container.replaceChildren();
  for (const check of checks) {
    const item = document.createElement("article");
    item.className = "validation-check-item";
    item.dataset.status = check.status || "";

    const text = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = check.label || "Check";
    const detail = document.createElement("p");
    detail.textContent = check.detail || "";
    text.append(title, detail);

    const status = document.createElement("span");
    status.className = "status-pill";
    status.dataset.tone = statusTone(check.status);
    status.textContent = check.status || "unknown";

    item.append(text, status);
    container.append(item);
  }
}

function renderIssues(container, issues) {
  container.replaceChildren();
  if (!issues.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No validation issues found.";
    container.append(empty);
    return;
  }

  for (const issue of issues) {
    const item = document.createElement("article");
    item.className = "validation-issue";
    item.dataset.level = issue.level || "";

    const title = document.createElement("h3");
    title.textContent = issue.message || "Validation issue";

    const metaParts = [issue.filename, issue.source].filter(Boolean);
    const meta = document.createElement("p");
    meta.textContent = metaParts.length ? metaParts.join(" / ") : issue.check || "";

    item.append(title, meta);
    container.append(item);
  }
}

function statusTone(status) {
  if (status === "ok") {
    return "ok";
  }
  if (status === "warn") {
    return "warn";
  }
  return "error";
}

function setReviewLink(elements, projectPath) {
  const url = new URL("/review", window.location.origin);
  url.searchParams.set("path", projectPath);
  elements.reviewLink.href = url.toString();
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
