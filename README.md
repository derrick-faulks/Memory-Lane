# Memory Lane

Memory Lane is a private, portable Windows viewer for large photo and video
collections. It indexes media in place, arranges it chronologically, and creates
a local thumbnail cache. It never uploads, moves, renames, or edits the original
files.

## Download and run

1. Open this repository's **Releases** page.
2. Download `MemoryLane-Windows-Portable.zip`.
3. Extract the ZIP to a writable folder or USB drive.
4. Double-click `MemoryLane.exe`.
5. Choose the folder containing your photos and videos.

The first scan can take a while for a large collection. You can browse while the
scan continues. Later scans only process files that are new or changed.

> Windows may show a SmartScreen warning because community-built executables are
> not code-signed. Choose **More info**, then **Run anyway** only if you downloaded
> the file from a release you trust.

## How dates are chosen

Memory Lane uses the first available date:

1. Embedded camera date for JPEG or TIFF photos
2. A recognizable date in the filename
3. The file's last-modified date

Use **Change folder** to select another library and **Refresh library** to scan
for new or changed media.

## Portable data

The app creates a `data` folder beside `MemoryLane.exe`. It contains:

- `catalog.db` — the SQLite media index
- `thumbnails/` — generated previews

Keep the app in a writable folder. Delete `data` to reset the app or create a
fresh index. Deleting it does not affect your originals.

## Supported files

Common JPEG, PNG, GIF, BMP, WebP, TIFF, HEIC/HEIF, AVIF, MP4, MOV, M4V, AVI,
MKV, WMV, WebM, MTS, M2TS, 3GP, MPG, and MPEG filenames are recognized.
Thumbnail decoding and browser playback depend on the file codec. Some uncommon
or proprietary formats may display without a thumbnail or may not play.

## Run from source

Requirements:

- Windows 10 or 11
- Python 3.11 or newer

Clone the repository, then run:

```powershell
.\run-source.ps1
```

The script creates a virtual environment and installs the dependencies on its
first run.

## Build the portable executable

From PowerShell:

```powershell
.\build.ps1
```

The finished package is written to:

```text
dist\MemoryLane-Windows-Portable.zip
```

## Publish a GitHub release

1. Create a new GitHub repository and upload all files from this folder,
   including the `.github` directory.
2. Commit and push the project.
3. Create and push a version tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions builds the Windows package and attaches it to the release. You
can also open the repository's **Actions** tab and run **Build Windows portable
app** manually; that produces a downloadable workflow artifact.

## Privacy and security

- The server listens only on `127.0.0.1`, so it is accessible only from the
  computer running the app.
- Media is served locally to the user's browser.
- Nothing is uploaded or shared.
- The selected library is read only; only the adjacent `data` folder is changed.

## Contributing

Bug reports and pull requests are welcome. Please include the Windows version,
media extension, and any visible error details. Do not attach private media.

## License

PolyForm Noncommercial License 1.0.0
