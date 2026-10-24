# Aurora Launchpad RPM

Aurora Launchpad is an experimental, graphical per-user installer. The RPM itself installs only the GTK/libadwaita wizard and a read-only copy of the Aurora payload under `/usr/share/aurora-launchpad`; the wizard then prepares the current user's application under `~/.local/share/aurora`.

## Supported environment

Only Fedora Workstation with GNOME on Wayland is accepted by this initial build. It checks available RAM, disk space, session type and desktop, lists the installation actions before downloads, and requires explicit acknowledgement of the model download and administrator prompt.

The installer creates a Python virtual environment, installs Aurora's Python requirements, downloads its Portuguese Vosk model, installs Ollama if needed, pulls the configured Gemma models, migrates the local memory file from the currently configured user service if one exists, then enables and starts `aurora.service`. The privileged Ollama script is accepted only when its SHA-256 matches the version reviewed and pinned in the Launchpad. Its possible system-wide effects (Ollama service/account, group membership, GPU packages, and in some cases NVIDIA repository/driver changes) are disclosed before the user confirms. Ollama/model downloads require network access.

## Removal behavior

The Launchpad can remove the managed application and service. Preference/memory/log removal and deletion of only Gemma models newly downloaded by Launchpad are separate opt-in checkboxes. Pre-existing Ollama models are never removed. The system-wide Ollama installation is preserved because other software may use it. The optional RPM removal uses Fedora's DNF with an administrator prompt.

## Build

On Fedora 44, install the Fedora package `rpm-build`, then run:

```sh
SOURCE_REF=master packaging/rpm/build-rpm.sh
```

The resulting RPM and `SHA256SUMS` appear under `dist/`. The script resolves `SOURCE_REF` to a Git commit first and assembles both the wizard and Aurora payload from that same commit; uncommitted working-tree changes are not included. The repository currently has no automated RPM publishing workflow.

## Limits

- This is a first experimental installer; it is not an OS-level transaction manager. A failed step leaves downloaded caches and the current per-user app files so the wizard can be run again.
- A changed upstream Ollama installer intentionally blocks installation until its privileged effects are reviewed and the new digest is committed. The installer still downloads Ollama's runtime and optional hardware components from upstream over HTTPS.
- Python dependency versions are currently specified as minimums rather than a fully hash-locked environment; this remains a supply-chain hardening item.
- The wizard reports stage-level progress; individual pip/Vosk stages do not expose byte-accurate progress.
- A reboot is not required by design. The user service is started when setup succeeds.
- The RPM does not bundle Ollama, Gemma weights, Python wheels, or Vosk model data.
