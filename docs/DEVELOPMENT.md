# Development Notes

This file records developer-facing guidance for TrimTank. It is meant to help
future coding sessions preserve project direction without turning early design
ideas into overly rigid implementation requirements.

README.md is the forward-facing user document. This file is for development
context, design intent, and implementation guidance.

## Purpose

TrimTank is a local-first image dataset preparation tool for LoRA training
workflows.

It should help a single local operator review candidate source images, choose
usable images, create training crops, write captions, and export a clean
training-ready image/caption set.

TrimTank is not tied to any specific character, person, subject, or dataset.

## Design Principles

TrimTank should be:

- local-first
- source-safe
- boring and maintainable
- understandable by inspection
- useful before it is clever
- simple to run from a local machine
- usable through a browser served by the local app

TrimTank should not require a database for v1.

Project state should be stored in normal files on disk.

The frontend should not require a build step for v1.

Avoid premature abstraction. Prefer clear code that solves the current workflow
over architecture that anticipates every possible future feature.

## Runtime Targets

TrimTank must support Windows and Linux as required runtime environments.

macOS support is nice to have. Include macOS compatibility when it is simple, but
do not add meaningful v1 complexity only to support macOS.

Target Python version: Python 3.10+

Do not use Python features newer than 3.10 unless the minimum supported version
is intentionally changed.

The frontend should target modern browsers. Internet Explorer does not need to
be supported.

## Development Workflow

TrimTank should run as a local/private-network web app.

The normal local command should be:

    trimtank start

A typical private-network development command should be:

    trimtank start --host 0.0.0.0 --port 8145 --dev

Development mode should make browser review less painful by disabling frontend
asset caching and enabling useful debug/status information.

Do not require HTTPS for v1. HTTP is acceptable when TrimTank is accessed over
localhost, LAN, or a secured private network.

## Packaging and CLI

Use pyproject.toml as the Python project configuration file.

Do not use requirements.txt as the dependency source of truth for v1.

TrimTank should install a console command:

    trimtank

The primary command should be:

    trimtank start

Also support the module form:

    python -m trimtank start

Use argparse for CLI parsing.

Do not require a .env file for v1.

TrimTank should also support a top-level version flag:

    trimtank --version

This should print the installed TrimTank version and exit without starting the
server.

The reported version should come from the package metadata or a single shared
version source. Do not hardcode separate conflicting version strings in multiple
places.

Expected trimtank start arguments:

    --host HOST
        Host/interface to bind.
        Default: 127.0.0.1

    --port PORT
        Port to serve on.
        Default: 8145

    --dev
        Enable development mode.
        Default: false

    --verbose
        Enable verbose logging explicitly.
        Default:
          false in normal/prod mode
          true when --dev is present

Normal mode should be production-like local mode.

Development mode should enable no-cache static assets, helpful debug/status
information, and verbose logging by default.

## Project Model

TrimTank works on a user-selected project folder.

A project folder contains a `manifest.json` file plus standard project folders:

    inputs/
    training/
    checkpoints/

The `inputs/` folder is the flat source image folder. Raw images should live
there and should not be modified in place.

The `training/` folder is the generated training-ready output folder. Future
export/generate behavior may rebuild this folder from manifest records and write
padded image/caption pairs such as `001.png` and `001.txt`.

The `checkpoints/` folder is reserved for future LoRA checkpoint output or
references. TrimTank does not train models in v1.

Critical project data belongs on disk, not only in the browser.

Browser localStorage may be used for UI preferences and convenience state, such
as:

- last opened project path
- display preferences
- thumbnail size
- sort order
- last viewed image index
- last used caption template

Do not store critical dataset state only in browser localStorage.

## Data Safety

TrimTank works with user image datasets. Treat filesystem writes as important
user data operations.

Never modify original/source image files in place.

Never delete files automatically.

All destructive actions require confirmation.

Handle duplicate filenames safely.

Handle unsupported or corrupt images gracefully.

Do not overwrite existing cropped or captioned outputs silently.

Prefer explicit save actions over automatic destructive behavior.

Keep file operations conservative, inspectable, and reversible where practical.

## Core Workflows

The core v1 workflows are:

1. Open or create a project.
2. Discover source images.
3. Review source images.
4. Mark source images with a decision.
5. Create crops from selected images.
6. Write or revise captions for cropped outputs.
7. Review cropped/captioned outputs.
8. Export a clean training-ready image/caption set.

Formal persisted review statuses are:

- keep
- reject
- duplicate
- unsure

Images with no persisted status are treated as `unreviewed` in the UI and API.
`unreviewed` is a workflow state for filtering and reset behavior, not a final
decision. This keeps new source images visible without forcing a manifest record
for every file before review starts.

Decision labels may be refined later, but v1 should preserve the ability to
distinguish usable images, rejected images, duplicates, unresolved images, and
images that have not been reviewed yet.

## Manifest

Use a JSON manifest for persistent project state.

The manifest should be human-readable and reasonably stable.

The manifest should include a top-level `training` object keyed by unique source
filenames from the flat `inputs/` folder. Each key can track the image selection
status, crop rectangle when applicable, and caption text.

The manifest should track enough information to answer:

- which `inputs/` filename a record describes
- what decision status the source image currently has
- what crop rectangle should be used when generating training output
- what caption text should be written beside the generated output image

The generated `training/` filenames do not need to match source filenames.
Future generate/export behavior should assign stable padded names such as
`001.png` and `001.txt`.

The exact schema can evolve during v1.

Do not add a database for v1.

## Frontend

Use raw HTML, raw CSS, and raw JavaScript for v1.

Do not use Webpack, Vite, React, Vue, Svelte, or a similar frontend build system
for v1.

Cropper.js is acceptable for the browser crop UI.

The UI should be mobile-friendly.

Prefer a simple dark interface with large touch-friendly controls.

The UI should prioritize:

- image review
- fast navigation
- clear decisions
- crop creation
- caption editing
- visible save/export status
- understandable errors

Avoid overdesigning the UI before the core workflow works.

## Server

Use FastAPI for the local web app.

Use Uvicorn to serve the app.

Serve the frontend and API from one local server.

Development mode should prevent browser caching of frontend assets. Prefer simple
no-cache headers for static files over query-string cache busting. Only add
query-string cache busting if no-cache headers are not sufficient.

Production-like local mode may use normal static asset behavior.

## Testing Direction

Prefer tests around:

- CLI argument parsing
- project path handling
- project creation/opening
- manifest creation and updates
- image discovery
- supported extension filtering
- corrupt or unsupported image handling
- crop output naming
- caption filename pairing
- source-to-output mapping
- export validation
- dev/prod mode behavior

Use small generated test images when image files are needed.

Do not require real user datasets for automated tests.

Avoid committing large binary fixtures.

## Documentation Direction

README.md should stay user-facing.

README.md should explain:

- what TrimTank is
- what problem it solves
- how to install it
- how to run it
- current project maturity/status

README.md should not include private development-session details.

This file may include developer-facing decisions and open questions, but should
still avoid machine-specific or private session details unless explicitly needed
for local agent continuity.

## Open Questions

These are intentionally not locked down yet:

- Final manifest schema.
- Whether selected source images should be copied into a separate folder.
- Whether export profiles should exist for different training tools.
- Whether thumbnails should be generated and cached.
- Whether project files should use relative paths only, absolute paths, or a
  mixture.
- How much caption editing should happen inline during crop creation versus in a
  later review pass.
- Whether v1 should support multiple crops from one source image.

## Initial v1 Direction

The first useful version should prove the workflow end-to-end:

    open project -> review images -> crop -> caption -> export

Do not delay the first working version for advanced features.

Prefer a narrow working tool over a broad unfinished tool.
