import { apiGet, apiPost } from "./api.js";

const RECENT_PROJECTS_KEY = "trimtank.recentProjects";
const MAX_RECENT_PROJECTS = 8;

export function initProjectPicker() {
  const elements = getElements();
  if (!elements.panel) {
    return;
  }

  const state = {
    browsePath: "",
    currentBrowseParent: null,
    roots: [],
    lastInspection: null,
  };

  bindProjectControls(elements, state);
  renderRecentProjects(elements);
  void loadFilesystemRoots(elements, state);
}

function getElements() {
  return {
    panel: document.getElementById("project-panel"),
    projectPath: document.getElementById("project-path"),
    browseProject: document.getElementById("browse-project"),
    openProject: document.getElementById("open-project"),
    createProject: document.getElementById("create-project"),
    recentProjects: document.getElementById("recent-projects"),
    projectMessage: document.getElementById("project-message"),
    projectState: document.getElementById("project-state"),
    workspace: document.getElementById("project-workspace"),
    workspaceName: document.getElementById("workspace-project-name"),
    workspacePath: document.getElementById("workspace-project-path"),
    workspaceManifest: document.getElementById("workspace-manifest-status"),
    folderDialog: document.getElementById("folder-dialog"),
    closeFolderDialog: document.getElementById("close-folder-dialog"),
    filesystemRoots: document.getElementById("filesystem-roots"),
    browseParent: document.getElementById("browse-parent"),
    useCurrentFolder: document.getElementById("use-current-folder"),
    folderCurrentPath: document.getElementById("folder-current-path"),
    folderList: document.getElementById("folder-list"),
    folderMessage: document.getElementById("folder-message"),
    newFolderName: document.getElementById("new-folder-name"),
    createFolder: document.getElementById("create-folder"),
  };
}

function bindProjectControls(elements, state) {
  elements.projectPath.addEventListener("change", () => {
    void inspectCurrentPath(elements, state);
  });

  elements.projectPath.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void inspectCurrentPath(elements, state);
    }
  });

  elements.browseProject.addEventListener("click", () => {
    void openFolderDialog(elements, state);
  });

  elements.openProject.addEventListener("click", () => {
    void openCurrentProject(elements, state);
  });

  elements.createProject.addEventListener("click", () => {
    void createCurrentProject(elements, state);
  });

  elements.recentProjects.addEventListener("change", () => {
    if (!elements.recentProjects.value) {
      return;
    }
    elements.projectPath.value = elements.recentProjects.value;
    void inspectCurrentPath(elements, state);
  });

  elements.closeFolderDialog.addEventListener("click", () => {
    closeFolderDialog(elements);
  });

  elements.folderDialog.addEventListener("click", (event) => {
    if (event.target === elements.folderDialog) {
      closeFolderDialog(elements);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.folderDialog.hidden) {
      closeFolderDialog(elements);
    }
  });

  elements.filesystemRoots.addEventListener("change", () => {
    if (elements.filesystemRoots.value) {
      void browsePath(elements, state, elements.filesystemRoots.value);
    }
  });

  elements.browseParent.addEventListener("click", () => {
    if (state.currentBrowseParent) {
      void browsePath(elements, state, state.currentBrowseParent);
    }
  });

  elements.useCurrentFolder.addEventListener("click", () => {
    if (!state.browsePath) {
      return;
    }
    elements.projectPath.value = state.browsePath;
    closeFolderDialog(elements);
    void inspectCurrentPath(elements, state);
  });

  elements.folderList.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-browse-path]");
    if (!button) {
      return;
    }
    void browsePath(elements, state, button.dataset.browsePath);
  });

  elements.createFolder.addEventListener("click", () => {
    void createFolder(elements, state);
  });

  elements.newFolderName.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void createFolder(elements, state);
    }
  });
}

async function loadFilesystemRoots(elements, state) {
  try {
    const data = await apiGet("/api/filesystem/roots");
    state.roots = data.roots || [];
    renderFilesystemRoots(elements, state.roots);
  } catch (error) {
    setFolderMessage(elements, getErrorMessage(error), "error");
  }
}

function renderFilesystemRoots(elements, roots) {
  elements.filesystemRoots.replaceChildren();

  for (const root of roots) {
    const option = document.createElement("option");
    option.value = root.path;
    option.textContent = root.name;
    elements.filesystemRoots.append(option);
  }
}

async function openFolderDialog(elements, state) {
  elements.folderDialog.hidden = false;

  if (!state.roots.length) {
    await loadFilesystemRoots(elements, state);
  }

  const startPath = elements.projectPath.value.trim() || state.roots[0]?.path || "";
  if (startPath) {
    await browsePath(elements, state, startPath);
  }
}

function closeFolderDialog(elements) {
  elements.folderDialog.hidden = true;
}

async function browsePath(elements, state, path) {
  if (!path) {
    return;
  }

  setFolderMessage(elements, "Loading folders...", "");
  elements.folderList.replaceChildren();

  try {
    const data = await apiGet("/api/filesystem/browse", { path });
    state.browsePath = data.path;
    state.currentBrowseParent = data.parent;
    renderBrowseResult(elements, data);
    setFolderMessage(elements, `${data.directories.length} folders`, "");
  } catch (error) {
    setFolderMessage(elements, getErrorMessage(error), "error");
  }
}

function renderBrowseResult(elements, data) {
  elements.folderCurrentPath.textContent = data.path;
  elements.browseParent.disabled = !data.parent;
  elements.useCurrentFolder.disabled = !data.path;
  elements.folderList.replaceChildren();

  if (!data.directories.length) {
    const emptyItem = document.createElement("li");
    emptyItem.className = "folder-list-empty";
    emptyItem.textContent = "No folders";
    elements.folderList.append(emptyItem);
    return;
  }

  for (const directory of data.directories) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.browsePath = directory.path;
    button.textContent = directory.name;
    item.append(button);
    elements.folderList.append(item);
  }
}

async function createFolder(elements, state) {
  const parentPath = state.browsePath;
  const name = elements.newFolderName.value.trim();

  if (!parentPath || !name) {
    setFolderMessage(elements, "Folder name is required.", "warn");
    return;
  }

  try {
    const data = await apiPost("/api/filesystem/create-folder", {
      parent_path: parentPath,
      name,
    });
    elements.newFolderName.value = "";
    state.browsePath = data.directory.path;
    state.currentBrowseParent = data.browse.parent;
    renderBrowseResult(elements, data.browse);
    elements.projectPath.value = data.directory.path;
    setFolderMessage(elements, "Folder created.", "ok");
    await inspectCurrentPath(elements, state);
  } catch (error) {
    setFolderMessage(elements, getErrorMessage(error), "error");
  }
}

async function inspectCurrentPath(elements, state) {
  const path = elements.projectPath.value.trim();
  if (!path) {
    state.lastInspection = null;
    updateProjectControls(elements, null);
    return;
  }

  setProjectMessage(elements, "Checking project folder...", "");

  try {
    const data = await apiPost("/api/projects/inspect", { path });
    state.lastInspection = data;
    updateProjectControls(elements, data);
  } catch (error) {
    state.lastInspection = null;
    updateProjectControls(elements, null);
    setProjectMessage(elements, getErrorMessage(error), "error");
  }
}

function updateProjectControls(elements, inspection) {
  elements.openProject.disabled = !inspection?.can_open;
  elements.createProject.disabled = !inspection?.can_create;

  if (!inspection) {
    setProjectState(elements, "No project open", "");
    setProjectMessage(elements, "Choose or create a project folder.", "");
    return;
  }

  const manifest = inspection.manifest;

  if (inspection.can_open) {
    const name = inspection.project?.name || "TrimTank project";
    setProjectState(elements, "Project found", "ok");
    setProjectMessage(elements, `${name} is ready to open.`, "ok");
    return;
  }

  if (inspection.can_create) {
    setProjectState(elements, "Project not initialized", "warn");
    setProjectMessage(elements, manifest.detail, "warn");
    return;
  }

  setProjectState(elements, "Cannot open", "error");
  setProjectMessage(elements, manifest.detail, "error");
}

async function openCurrentProject(elements, state) {
  const path = elements.projectPath.value.trim();
  if (!path) {
    return;
  }

  try {
    const data = await apiPost("/api/projects/open", { path });
    activateProject(elements, data);
    addRecentProject(data.path);
    renderRecentProjects(elements);
  } catch (error) {
    setProjectMessage(elements, getErrorMessage(error), "error");
  }
}

async function createCurrentProject(elements, state) {
  const path = elements.projectPath.value.trim();
  if (!path) {
    return;
  }

  try {
    const data = await apiPost("/api/projects/create", { path });
    state.lastInspection = data;
    activateProject(elements, data);
    addRecentProject(data.path);
    renderRecentProjects(elements);
  } catch (error) {
    setProjectMessage(elements, getErrorMessage(error), "error");
  }
}

function activateProject(elements, data) {
  const projectName = data.project?.name || "TrimTank Project";

  elements.projectPath.value = data.path;
  elements.workspace.hidden = false;
  elements.workspaceName.textContent = projectName;
  elements.workspacePath.textContent = data.path;
  elements.workspaceManifest.textContent = `${data.manifest.status} / schema ${data.manifest.schema_version}`;
  setProjectState(elements, "Project open", "ok");
  setProjectMessage(elements, `${projectName} is open.`, "ok");
  announceProjectOpened(data);
}

function announceProjectOpened(data) {
  window.dispatchEvent(new CustomEvent("trimtank:project-opened", { detail: data }));
}

function renderRecentProjects(elements) {
  const recentProjects = getRecentProjects();
  elements.recentProjects.replaceChildren();

  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = recentProjects.length ? "Recent projects" : "No recent projects";
  elements.recentProjects.append(emptyOption);

  for (const path of recentProjects) {
    const option = document.createElement("option");
    option.value = path;
    option.textContent = path;
    elements.recentProjects.append(option);
  }
}

function getRecentProjects() {
  try {
    const value = JSON.parse(window.localStorage.getItem(RECENT_PROJECTS_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function addRecentProject(path) {
  const recentProjects = getRecentProjects().filter((item) => item !== path);
  recentProjects.unshift(path);
  window.localStorage.setItem(
    RECENT_PROJECTS_KEY,
    JSON.stringify(recentProjects.slice(0, MAX_RECENT_PROJECTS)),
  );
}

function setProjectState(elements, text, tone) {
  elements.projectState.textContent = text;
  elements.projectState.dataset.tone = tone;
}

function setProjectMessage(elements, text, tone) {
  elements.projectMessage.textContent = text;
  elements.projectMessage.dataset.tone = tone;
}

function setFolderMessage(elements, text, tone) {
  elements.folderMessage.textContent = text;
  elements.folderMessage.dataset.tone = tone;
}

function getErrorMessage(error) {
  return error?.message || "Unexpected error.";
}
