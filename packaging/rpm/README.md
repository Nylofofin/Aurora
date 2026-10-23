# Aurora Launchpad RPM

Aurora Launchpad is an experimental, graphical per-user installer. The RPM itself installs only the GTK/libadwaita wizard and a read-only copy of the Aurora payload under `/usr/share/aurora-launchpad`; the wizard then prepares the current user's application under `~/.local/share/aurora`.

## Supported environment

Only Fedora Workstation with GNOME on Wayland is accepted by this initial build. It checks available RAM, disk space, session type and desktop, lists the installation actions before downloads, and requires explicit acknowledgement of the model download and administrator prompt.

The installer creates a Python virtual environment, installs Aurora's Python requirements, downloads its Portuguese Vosk model, installs Ollama from the upstream `https://ollama.com/install.sh` endpoint if needed, pulls the configured Gemma models, migrates the local memory file from the currently configured user service if one exists, then enables and starts `aurora.service`. Ollama/model downloads require network access; Ollama's system installer needs polkit authentication.

## Removal behavior

The Launchpad can remove the managed application and service. Preference/memory/log removal and deletion of only Gemma models newly downloaded by Launchpad are separate opt-in checkboxes. Pre-existing Ollama models are never removed. The system-wide Ollama installation is preserved because other software may use it. The optional RPM removal uses Fedora's DNF with an administrator prompt.

## Build

On Fedora 44, install the Fedora package `rpm-build`, then run:

```sh
SOURCE_REF=master packaging/rpm/build-rpm.sh
```

The resulting RPM and `SHA256SUMS` appear under `dist/`. The GitHub Actions workflow builds the package in Fedora 44 and uploads it to an existing pre-release; it refuses stable releases.

## Limits

- This is a first experimental installer; it is not an OS-level transaction manager. A failed step leaves downloaded caches and the current per-user app files so the wizard can be run again.
- The official Ollama installer and pip/model downloads are network dependencies and may change upstream.
- The wizard reports stage-level progress; individual pip/Vosk stages do not expose byte-accurate progress.
- A reboot is not required by design. The user service is started when setup succeeds.
- The RPM does not bundle Ollama, Gemma weights, Python wheels, or Vosk model data.
