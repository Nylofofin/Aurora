# Aurora Launchpad RPM

Aurora Launchpad is an experimental graphical installer for Fedora Workstation with GNOME on Wayland. The RPM contains only the GTK/libadwaita wizard and its license. It no longer bundles Aurora's application payload.

Launchpad recommends up to three published GitHub releases: the newest pre-release, the preceding pre-release, and the newest stable release. It labels experimental channels and dates separately. The user selects a card, reviews the exact tag and installation effects, and confirms before any release payload is downloaded. The chosen tag is resolved to a commit SHA; Launchpad downloads that immutable commit archive over HTTPS, checks the final host, enforces download and extraction limits, rejects links and unsafe archive paths, and verifies the expected desktop files before copying them to the user's application directory.

When an older Aurora Studio starts, it checks published stable releases and pre-releases for a newer `aurora-launchpad-*.noarch.rpm`. This lets a beta carry its matching Studio update while still allowing the older stable Studio to discover it through the stable release asset. If an update exists, installation choices remain locked until the user presses **Atualizar Aurora Studio**. The downloaded RPM is accepted only from an official GitHub release URL, within the size limit, and with the SHA-256 digest published by GitHub; after `dnf` replaces the package, the new executable is reopened.

The preceding pre-release is only an earlier build and is not guaranteed stable. A release channel is omitted if GitHub has no valid published candidate for it. GitHub access is required to load the recommendations and download the selected version.

## Installation

The wizard checks Fedora Workstation, GNOME/Wayland, available RAM and disk space before enabling the install flow. It explains the planned downloads and requires acknowledgement before model downloads or privileged Ollama installation.

The installer prepares a private Python environment, downloads the Portuguese Vosk model, installs Ollama if needed, creates /usr/share/ollama for the ollama service account when missing, downloads the configured Gemma models, migrates existing local memory without deleting its source, then configures and starts aurora.service. The privileged Ollama script is accepted only when its SHA-256 matches the reviewed version pinned in the wizard.

An existing installation opens a maintenance dashboard. **Atualizar Aurora** selects the newest published desktop release, including pre-releases, and explains the channel before switching files. It never offers builds at or below the installed version. The Launchpad stages a clean payload, stops `aurora.service` before switching files, and retains the old application tree until the updated service is confirmed active. If activation fails, it restores the previous application and attempts to restart it. User settings, legacy in-tree settings and memory, the Python environment, Vosk data, voice models, and Ollama models are kept. Dependency checks run after the switch; already-installed speech and Ollama models are not downloaded again. If the GitHub check fails, the update action stays disabled and the dashboard exposes a retry button.

## Removal

Launchpad can remove its managed Aurora files and service. Removing preferences, memory, logs, newly downloaded models, or the RPM itself are separate options. Existing Ollama models and the system-wide Ollama installation are preserved.

## Building the RPM

On Fedora, install rpm-build and run:

    SOURCE_REF=master packaging/rpm/build-rpm.sh

The output RPM and SHA256SUMS are written to dist/. The build script resolves SOURCE_REF to a commit and packages only the Launchpad sources. Aurora code changes no longer require rebuilding the installer; Launchpad changes do.

## Limits

- This is an experimental installer, not an OS transaction manager. A failed step can leave downloaded caches and application files so installation can be retried.
- An upstream Ollama installer change blocks installation until its privileged effects are reviewed and its pinned digest is updated.
- Python dependencies are minimum-version constraints, not a hash-locked environment.
- Stage-level progress is shown, but individual downloads do not expose byte-accurate progress.
- A reboot is not required by design. The user service starts when setup succeeds.
- The RPM does not bundle Aurora, Ollama, Gemma weights, Python wheels, or Vosk model data.
