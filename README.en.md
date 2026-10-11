# CardVault

## 2.3.3 smaller distributions

Removed unused Qt QML, virtual keyboard, PDF and OpenGL components while retaining complete Source Han Sans fonts and all four interface languages. Packages are written to the workspace release/ directory, including when built from push; no installers, ZIPs, source ZIPs or .upd files are generated inside push. CARDVAULT_OUTPUT_DIR can select an external output directory. Setup removes explicitly listed obsolete components. Older .upd updaters retain extra libraries: use Setup or a fresh portable extraction to reduce installed size.

Measured against 2.3.2: application directory 142.4 → 102.4 MiB, Setup 53.3 → 41.9 MiB, portable ZIP 70.9 → 54.8 MiB. Validated retained DLL dependencies, real window startup and packaged multi-destination verification.

A ~2.6 MiB `CardVault-2.3.3-from-2.3.2-Windows-x64.upd` delta is now available **only for complete 2.3.2 installations upgrading to 2.3.3**. Drop it into Settings → Update. Existing 2.3.3 installations need no update. Legacy updaters do not enforce delta base versions: do not use this package with another version or an incomplete installation. It reuses identical libraries and fonts and replaces only three changed files. It retains obsolete libraries; use Setup to reduce installed size.

To reproduce, keep complete base and target folders in the workspace release/ directory, run `python packaging/build_delta_update.py --base-version 2.3.2`, then validate with `python packaging/test_update.py`.

## 2.3.2 fixes

Fixed hidden main windows after updates, including launches from older updaters. Hashing now runs in isolated read-only processes: pause and inactivity timeout cover opening, reading, and closing files. A digest is accepted only after file closure and successful worker exit; failed or timed-out verification never publishes a copy. Preserves the 16:9 startup window. Passed 78 automated tests, including timeout and pause with a simulated permanently blocked file close. Hardware or driver failures may still require attention; staged files and task checkpoints remain available for recovery.

**Memory card backup · SHA-256 / MD5 verification · Native Windows desktop app**

[简体中文](README.md) | **English**

Windows 10/11 x64 · Python + PySide6

> **AI disclosure: This software was made with AI.** A human user supplied the requirements and guided iterations; AI generated and helped refine the application code, interface, and documentation. Third-party components, including Python, Qt, PySide6, and Source Han Sans, were developed by their respective authors and retain their own copyrights and licenses.

CardVault backs up files from SD cards, microSD cards, USB drives, and camera memory cards to a computer or another storage device. Concurrent copying, SHA-256 / MD5 verification, task recovery, and result reports help you check the outcome of each backup.

## Recent changes

**2.3.1** prevents slow state writes from blocking the interface and pause requests. Batch verification uses sequential reads, with Windows read cancellation and timeout handling; complete staged copies are reused on resume. The startup window uses a screen-adaptive 16:9 aspect ratio.

**2.3.0** adds multiple destinations with remembered paths, SHA-256 / MD5 selection on the preparation page, separate batch verification progress bars, and `.upd` packages with rollback on failure.

See the [changelog](CHANGELOG.md) for release notes.

## Features

| Feature | Description |
| --- | --- |
| Device and destination checks | Detect storage devices; check write access and available space |
| Concurrent copying | 1–8 threads per task, 3 by default; up to 3 active tasks |
| Multiple destinations | Add or remove destinations on the preparation page and remember them for next time |
| Checksum selection | Select SHA-256 (Hash) or MD5 before starting; the choice is stored per task |
| Separate progress | Batch verification shows green copy progress above blue verification progress |
| Two verification modes | Verify each copy immediately, or verify after all copying finishes |
| File organization | File type filters, date-based folders, naming, and duplicate handling |
| Recovery | Retries, task pause and resume, and task history |
| Live status | Overall progress, current file, copy speed, and estimated time remaining |
| Clear reports | Highlight successful, failed, skipped, and pending counts; export results |
| Four UI languages | Simplified Chinese, Traditional Chinese, English, and Japanese; timezone-based first-run selection and manual override |
| Appearance | Bundled open-licensed Source Han Sans; selectable font and theme color |
| Local updates | Drop a dedicated .upd package to validate, extract, replace, roll back on failure, and restart |

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
2. Configure filters, organization, naming, and additional destinations if needed.
3. Choose the thread count in Settings, and the checksum algorithm and verification mode on the preparation page.
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

## Local .upd updates

Drop a newer `CardVault-version-Windows-x64.upd` file into **Settings → Updates**. The dedicated ZIP-based format includes a manifest with file sizes and SHA-256 hashes. Renaming an arbitrary ZIP is not sufficient.

The application validates and stages the package in `update/`, saves task state, and exits. A helper waits for exit, rechecks and extracts the full payload, then replaces application files. On replacement errors it attempts to restore originals and restart the old version. Results and rollback copies remain in `update/`; task records and unrelated files are preserved.

**Users on 2.2.x or earlier must first install 2.3 through Setup or switch to the new portable folder.** Older update pages cannot read `.upd`. Starting with 2.3, the update page accepts only newer `.upd` packages; Setup remains available for installation.

Checksums detect corruption; they are not digital signatures. Obtain updates from a trusted source. The MD5 setting affects backup verification only; update packages always use SHA-256.

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

The `release/` directory receives the application folder, Setup installer, portable ZIP, source ZIP, dedicated `.upd`, and SHA-256 checksums. The build needs internet access to retrieve third-party license texts.


## Project layout

```text
start.py                 Application entry point
cardvault/               UI, copy engine, languages, devices, and updates
assets/                  SVG resources and update helper
  fonts/                 Source Han Sans, provenance, and license
tests/                   Automated tests and UI rendering tools
packaging/               Build scripts, installer definition, release checks
requirements.txt         Runtime dependencies
README.md                Chinese documentation
README.en.md             English documentation
```

## Data and limitations

Batch verification uses one sequential worker; copying still uses the configured concurrency. Long-running reads show a storage-wait indicator and request cancellation after 30 seconds before following the retry policy. Pausing also requests cancellation of pending reads. Windows drivers must acknowledge cancellation, so an unresponsive device may not stop immediately. State-file writes no longer hold the interface's global lock; the paused status is published after the checkpoint is written.

- Source cards are read-only by default; the app does not delete source files. Verification checks copy integrity, but cannot guarantee the future reliability of storage hardware.
- Two destinations on one physical drive do not protect against losing both copies if that drive fails.
- Source runs store records in `data/`; installed builds default to `%LOCALAPPDATA%\CardVault`. Records, reports, and build outputs are excluded by Git ignore rules.
- Date-based organization uses file modification times. Complete preservation of empty directories, NTFS ACLs, and alternate data streams is outside the current scope.
- Copy speed and time estimates do not include all verification overhead. Safe ejection depends on Windows and whether the device is in use.

## Feedback and contributions

Use Issues to report the application version, Windows version, reproduction steps, and relevant errors. Remove personal paths and other private data before posting logs. Include validation steps or test results with code changes.

## Project license and third-party components

No open-source license has currently been assigned to the CardVault application code in this repository. Publishing the source alone does not grant unrestricted rights to use, modify, or redistribute it. Third-party components retain their own licenses; see [Third-party notices](packaging/THIRD_PARTY_NOTICES.txt). The font's OFL license applies to the font and does not license the application code.
