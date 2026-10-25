# SPDX-License-Identifier: GPL-3.0-only
Name:           aurora-launchpad
Version:        0.4.0
Release:        2%{?dist}
Summary:        GTK setup assistant and installer for Aurora Desktop
License:        GPL-3.0-only
URL:            https://github.com/Nylofofin/Aurora
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       polkit
Requires:       systemd
Requires:       curl
Requires:       unzip
Requires:       python3-pip

%description
Aurora Launchpad is a graphical setup wizard for Aurora Desktop,
initially targeted only at Fedora Workstation running GNOME on Wayland. It
checks compatibility, explains each operation and installs Aurora into the
current user's home directory. Ollama models and local user data are preserved
by default during removal.

%prep
%setup -q -n %{name}-%{version}

%build

%install
install -Dpm0755 launchpad/aurora-launchpad %{buildroot}%{_bindir}/aurora-launchpad
install -Dpm0644 launchpad/aurora_launchpad.py %{buildroot}%{_libexecdir}/aurora-launchpad/aurora_launchpad.py
install -Dpm0644 launchpad/aurora_launchpad_core.py %{buildroot}%{_libexecdir}/aurora-launchpad/aurora_launchpad_core.py
install -Dpm0644 launchpad/icons/com.nylofofin.AuroraLaunchpad.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/com.nylofofin.AuroraLaunchpad.svg
install -Dpm0644 launchpad/aurora-launchpad.desktop %{buildroot}%{_datadir}/applications/aurora-launchpad.desktop

%files
%license LICENSE
%doc packaging/rpm/README.md
%{_bindir}/aurora-launchpad
%{_libexecdir}/aurora-launchpad/
%{_datadir}/applications/aurora-launchpad.desktop
%{_datadir}/icons/hicolor/scalable/apps/com.nylofofin.AuroraLaunchpad.svg

%changelog
* Sun Oct 25 2026 Aurora Project <nylofofin@localhost> - 0.4.0-2
- Refresh the compact dark Launchpad interface and align the installer identity with Aurora 2.0.0a.

* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.8-1
- Repair release refresh and correct installed build identity
- Add post-install personalization panel and session-safe onboarding restart.

* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.5-1
- Accept GitHub's official release-assets redirect host during verified self-update.

* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.4-1
- Show a maintenance dashboard for installed Aurora builds and preserve update choices.
- Show at most three newer Aurora builds and report installed model health.
* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.3-1
- Preserve the Python virtual environment during Aurora upgrades.
* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.2-1
- Detect and install newer Launchpad RPMs from verified GitHub release assets.
* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.1-1
- Integrate first-run personalization into a newly installed Aurora desktop.
* Sat Oct 24 2026 Aurora Project <nylofofin@localhost> - 0.3.0-1
- Redesign the setup wizard and allow the user to choose among recommended releases.
* Fri Oct 23 2026 Aurora Project <nylofofin@localhost> - 0.2.1-1
- Download the newest published Aurora release instead of bundling the application.
- Create the Ollama service data directory with the service account before startup.
* Fri Oct 23 2026 Aurora Project <nylofofin@localhost> - 0.1.0-1
- First experimental Fedora Workstation installer.
