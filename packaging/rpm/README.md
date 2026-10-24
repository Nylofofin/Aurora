# Aurora Launchpad RPM

Aurora Launchpad is an experimental graphical installer for Fedora Workstation with GNOME on Wayland. The RPM contains only the GTK/libadwaita wizard and its license. It no longer bundles Aurora's application payload.

After the user reviews and confirms the installation plan, Launchpad selects the most recently published GitHub release, whether stable or pre-release. It resolves the release tag to a commit SHA, downloads the archive for that immutable commit over HTTPS, checks the final host, enforces download and extraction limits, rejects links and unsafe archive paths, and verifies that the expected desktop files exist before copying them to the user's application directory.

Because the newest published release is selected across both channels, this installer may install experimental pre-releases. The selected tag and channel are shown during installation. GitHub access is required.

## Installation

The wizard checks Fedora Workstation, GNOME/Wayland, available RAM and disk space before enabling the install flow. It explains the planned downloads and requires acknowledgement before model downloads or privileged Ollama installation.

The installer prepares a private Python environment, downloads the Portuguese Vosk model, installs Ollama if needed, downloads the configured Gemma models, migrates existing local memory without deleting its source, then configures and starts aurora.service. The privileged Ollama script is accepted only when its SHA-256 matches the reviewed version pinned in the wizard.

## Removal

Launchpad can remove its managed Aurora files and service. Removing preferences, memory, logs, newly downloaded models, or the RPM itself are separate options. Existing Ollama models and the system-wide Ollama installation are preserved.

## Building the RPM

On Fedora, install rpm-build and run:

    SOURCE_REF=master packaging/rpm/build-rpm.sh

The output RPM and SHA256SUMS are written to dist/. The build script resolves SOURCE_REF to a commit and packages only the Launchpad sources. Aurora code changes no longer require rebuilding the installer; Launchpad changes do. RPM publishing is not automated yet.

## Limits

- This is an experimental installer, not an OS transaction manager. A failed step can leave downloaded caches and application files so installation can be retried.
- An upstream Ollama installer change blocks installation until its privileged effects are reviewed and its pinned digest is updated.
- Python dependencies are minimum-version constraints, not a hash-locked environment.
- Stage-level progress is shown, but individual downloads do not expose byte-accurate progress.
- A reboot is not required by design. The user service starts when setup succeeds.
- The RPM does not bundle Aurora, Ollama, Gemma weights, Python wheels, or Vosk model data.
