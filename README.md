# TrimTank

TrimTank is a local-first image dataset preparation tool for LoRA training
workflows.

It is designed to help you review source images, choose the best candidates,
create training crops, write captions, and export a clean image/caption dataset
for training.

TrimTank runs on your local machine and provides a browser-based interface. It
is not a hosted service and does not require a database.

## Project Status

TrimTank is in early development.

The initial goal is to prove the core workflow end-to-end:

    open project -> review images -> crop -> caption -> export

Expect the project structure, manifest format, and UI workflow to evolve during
early versions.

## Goals

TrimTank should help with:

- Reviewing candidate training images
- Marking images as keep, reject, duplicate, or unsure
- Cropping images for training
- Writing and revising captions
- Preserving source-to-output mappings
- Exporting training-ready image/caption pairs

## Non-Goals

TrimTank is not intended to be:

- A LoRA trainer
- A hosted web service
- A cloud sync tool
- A multi-user annotation platform
- A database-backed asset management system
- A replacement for ComfyUI, Kohya, or other training tools

## Runtime Model

TrimTank runs as a local web app.

By default, it binds to localhost:

    trimtank start

For private-network use, such as accessing the UI from another device on your
LAN or private network:

    trimtank start --host 0.0.0.0 --port 8145

For development mode:

    trimtank start --host 0.0.0.0 --port 8145 --dev

Development mode enables behavior such as reduced frontend caching and more
verbose diagnostic information.

## Installation

TrimTank is not yet published to PyPI.

During development, install it from the repository:

    git clone https://github.com/PacificWharf/TrimTank.git
    cd TrimTank
    python -m venv .venv

On Windows PowerShell:

    .\.venv\Scripts\Activate.ps1

On Linux/macOS:

    source .venv/bin/activate

Then install TrimTank in editable mode:

    pip install -e .

Run it:

    trimtank start

## CLI

Primary command:

    trimtank start

Useful options:

    --host HOST
        Host/interface to bind.
        Default: 127.0.0.1

    --port PORT
        Port to serve on.
        Default: 8145

    --dev
        Enable development mode.

    --verbose
        Enable verbose logging.

Version:

    trimtank --version

## Data Safety

TrimTank is designed to preserve source images.

The app should not modify original/source images in place. Generated crops,
captions, manifests, and exports should be written separately from the original
source files.

Destructive actions should be explicit and confirmed.

## Development

Developer-facing notes are kept in:

    docs/DEVELOPMENT.md

Coding-agent guidance is kept in:

    AGENTS.md

Commit message guidance is kept in:

    .gitmessage

## License

TrimTank is licensed under the [MIT License](LICENSE).
