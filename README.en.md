# CardVault

**Memory card backup · SHA-256 verification · Native Windows desktop app**

[简体中文](README.md) | **English**

Windows 10/11 x64 · Python + PySide6

> **AI disclosure: This software was made with AI.** A human user supplied the requirements and guided iterations; AI generated and helped refine the application code, interface, and documentation. Third-party components, including Python, Qt, PySide6, and Source Han Sans, were developed by their respective authors and retain their own copyrights and licenses.

CardVault backs up files from SD cards, microSD cards, USB drives, and camera memory cards to a computer or another storage device. Concurrent copying, SHA-256 verification, task recovery, and result reports help you check the outcome of each backup.

## Features

| Feature | Description |
| --- | --- |
| Device and destination checks | Detect storage devices; check write access and available space |
| Concurrent copying | 1–8 threads per task, 3 by default; up to 3 active tasks |
| Two backup destinations | Copy the same files to two destinations and verify each copy |
| Two verification modes | Verify each copy immediately, or verify after all copying finishes |
| File organization | File type filters, date-based folders, naming, and duplicate handling |
| Recovery | Retries, task pause and resume, and task history |
| Live status | Overall progress, current file, copy speed, and estimated time remaining |
| Clear reports | Highlight successful, failed, skipped, and pending counts; export results |
| Four UI languages | Simplified Chinese, Traditional Chinese, English, and Japanese; timezone-based first-run selection and manual override |
| Appearance | Bundled open-licensed Source Han Sans; selectable font and theme color |
| Local updates | Drop a newer Setup installer into the update page, then update and restart |

Throughput depends on the source card, reader, connection, and destination drive. More threads do not necessarily produce a proportional speed increase.

## Installation

### Packaged releases

Once the maintainer publishes binaries, look for these files on this repository's **Releases** page:

- `CardVault-x.x.x-Setup-x64.exe`: run the installer, then launch the installed shortcut.
- `CardVault-x.x.x-Windows-x64.zip`: extract the entire archive and run `CardVault.exe`.

**Packaged releases do not require Python or additional libraries to be installed.** Keep the portable application folder intact, including its DLLs, fonts, and resources. Copying only the EXE will not work. Installers are not included in the source repository.

### Run from source

Development environment: Windows 10/11 x64 and Python 3.13 x64; verified with Python 3.13.7. Open PowerShell in the source directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe start.py
```

Use the Python entry point directly; no BAT launcher or virtual environment activation is needed. Downloading dependencies requires internet access. Copying, verification, and task management run locally.

## Basic workflow

1. Insert a memory card and select the source device and backup destination.
2. Configure filters, organization, naming, and a second destination if needed.
3. Choose the thread count and verification mode in Settings.
4. Start the backup and monitor copying and verification.
5. Review the final report, including failed and pending items, before managing the source files further.

Language changes take effect after restarting. Font and theme changes apply when saved.

## Default font and licensing

The default font is **Source Han Sans SC**. The application bundles Adobe's unmodified version 2.005 Regular and Bold fonts and registers them for the application at startup. No system-wide font installation is required.

Source Han Sans **is copyrighted**, but is distributed under the **SIL Open Font License 1.1**, which permits use, embedding, and redistribution subject to its terms. This project retains the original font files, copyright notice, and full license. It does not bundle Microsoft YaHei, Segoe UI, or Consolas font files. Other system fonts selected by the user remain subject to their own licenses.

- [Font provenance and SHA-256 hashes](assets/fonts/README.md)
- [Full font license](assets/fonts/LICENSE.txt)
- [Adobe upstream project](https://github.com/adobe-fonts/source-han-sans)

Previously saved custom font choices remain in effect. To switch, select `Source Han Sans SC` in Settings.

## Local installer updates

Drop a newer CardVault Setup installer into **Settings → Updates**. The app checks and stages the installer in the `update` folder. When the update starts, it saves task state and exits. An independent helper waits for the application to close, runs the installer against the existing installation directory, and relaunches the app.

This workflow uses a local installer; it does not download updates online. Use a newer Setup built for this project, not an arbitrary EXE or ZIP file.

## Tests and builds

Run the automated tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To build Windows releases, install Inno Setup and set `ISCC` to the actual compiler path:

```powershell
.\.venv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
$env:ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
.\.venv\Scripts\python.exe packaging/build_release.py
```

The `release/` directory receives the application folder, Setup installer, portable ZIP, source ZIP, and SHA-256 checksums. The build needs internet access to retrieve third-party license texts.

Additional documentation: [Build and source guide](docs/构建与源码说明.md) and [GitHub and Git tutorial](docs/GitHub与Git教程.md) (both in Chinese).

## Project layout

```text
start.py                 Application entry point
cardvault/               UI, copy engine, languages, devices, and updates
assets/                  SVG resources and update helper
  fonts/                 Source Han Sans, provenance, and license
tests/                   Automated tests and UI rendering tools
packaging/               Build scripts, installer definition, release checks
docs/                    Development and Git guides
requirements.txt         Runtime dependencies
README.md                Chinese documentation
README.en.md             English documentation
```

## Data and limitations

- Source cards are read-only by default; the app does not delete source files. Verification checks copy integrity, but cannot guarantee the future reliability of storage hardware.
- Two destinations on one physical drive do not protect against losing both copies if that drive fails.
- Source runs store records in `data/`; installed builds default to `%LOCALAPPDATA%\CardVault`. Records, reports, and build outputs are excluded by Git ignore rules.
- Date-based organization uses file modification times. Complete preservation of empty directories, NTFS ACLs, and alternate data streams is outside the current scope.
- Copy speed and time estimates do not include all verification overhead. Safe ejection depends on Windows and whether the device is in use.

## Feedback and contributions

Use Issues to report the application version, Windows version, reproduction steps, and relevant errors. Remove personal paths and other private data before posting logs. Include validation steps or test results with code changes.

## Project license and third-party components

No open-source license has currently been assigned to the CardVault application code in this repository. Publishing the source alone does not grant unrestricted rights to use, modify, or redistribute it. Third-party components retain their own licenses; see [Third-party notices](packaging/THIRD_PARTY_NOTICES.txt). The font's OFL license applies to the font and does not license the application code.
