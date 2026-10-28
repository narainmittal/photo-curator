# Photo Curator

Turn a personal photo export into a reviewed, compact album for a digital frame. Nixplay is the default profile; any landscape or portrait display can use custom dimensions and storage limits.

Everything runs locally. No cloud API, subscription, telemetry, face identification or automated upload. Originals are read only. A person reviews quality and composition; the tool inventories, removes exact duplicates, renders the planned edits, records choices and verifies the final package.

## What you need

- An extracted Google Photos Takeout export or local photo folder.
- The display’s width, height and storage limit (Nixplay defaults are included).
- Python 3.10+ and a desktop browser.
- A human or local assistant to visually curate the images. This release does not automatically grade faces or blur.

## Step 1 · Install

Requires Python 3.10+ and Pillow. Install from this source checkout:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Step 2 · Create a batch

Extract all Google Takeout ZIP parts first. Other local photo folders also work. Keep your private photos and batch folders **outside this repository**.

```sh
photo-curator scan /path/to/photos --period 2027-Q1 \
  --timezone Asia/Kolkata --profile nixplay \
  --batch /path/to/private/batches/2027-Q1-first
```

Periods: `2027`, `2027-Q1`, `2027-03`, or inclusive `2027-03-10:2027-04-15`. Use a new batch folder for each run. Date priority: Takeout sidecar, EXIF local time, filename. UTC is the default for Takeout timestamps; set your timezone to avoid boundary mistakes. Undated, out-of-period and unreadable files are listed in the intake report, never silently included. Videos are outside scope. HEIC needs an optional local `pillow-heif` installation; unsupported files appear as errors.

## Step 3 · Review the intake and plan

1. Inspect `intake-report.json`. Resolve missing dates or unreadable inputs before calling the album complete.
2. Visually inspect sources, compare similar bursts and edit `plan.json` using the [curation guide](docs/curation.md). You can ask a local photo-capable assistant to do this using the [review brief](docs/review-brief.md); grant it access only to your local intake. The assistant must inspect real images and record decisions, rather than guess from filenames. New records start B (needs review). No automatic blur metric decides whether a family memory is good enough.

## Step 4 · Render display previews

Render the reviewed plan and open the generated `review.html` in your browser:

```sh
photo-curator render --batch /path/to/private/batches/2027-Q1-first
```

## Step 5 · Choose your photos

Review actual display JPEGs. Filter quality/month, search activities, Keep or Skip, and **Save choices**. `K`, `S` and arrow keys speed review. Import a saved CSV to resume on another browser. Nothing is selected automatically. Browser storage is a convenience; downloaded choices are the durable record.

## Step 6 · Export and verify

Create a new export from those choices:

```sh
photo-curator finalize --batch /path/to/private/batches/2027-Q1-first \
  --choices /path/to/photo-album-choices.csv \
  --output /path/to/private/exports/2027-Q1-final
photo-curator verify /path/to/private/exports/2027-Q1-final
```

## Step 7 · Upload manually

The export contains `photos/`, `album.zip` (JPEGs only), and a hash manifest. Upload the JPEGs using your frame account. Prepared and uploaded are separate states: this tool never claims a cloud upload happened. Back up and verify existing cloud media before any account cleanup, and confirm permanent deletions separately.

## Profiles and repeating a run

Nixplay defaults: 1280×800, 500 MB total, each JPEG below 3 MB. Confirm dimensions for your exact model. Generic defaults: 1920×1080, 500 MB total, each below 10 MB. Override with `--width`, `--height`, `--max-bytes` and `--file-max-bytes`. Budgets use decimal bytes and count JPEGs, not the ZIP container. A profile is saved in each batch.

Use `--reuse /path/to/earlier/batch` at intake for exact-source category hints. Hints never count as review or approval of a new crop. For a replacement album, provide the complete desired date range; for an incremental album, provide only the new period. Avoid enabling overlapping complete albums on a frame. Keep each batch, review CSV and export as a dated snapshot.

Rendering normalizes EXIF orientation and color, honors explicit crops/rotations, avoids enlargement and stretching, and strips source EXIF/GPS from JPEGs. A images must fill at least 99.5% of the canvas. Portraits that need padding remain C and require explicit selection. JPEG quality is reduced conservatively only to meet the per-file cap; all resulting files must be visually reviewed. There is no AI-generated detail or blur repair.

## Development and privacy

```sh
python -m unittest discover -s tests -v
node tests/reviewer.test.cjs  # Optional Node.js 22+ for reviewer checks
```

Publish this source folder only. Do not initialize Git at a parent containing personal photos. `.gitignore` is a secondary guard, not permission to stage private data. No real photos, account details, private manifests or personal paths belong in issues, screenshots or fixtures. Tests generate synthetic images in temporary folders.

The original personal project, reviewed albums and backups are maintained separately from this portable source package. This release deliberately does not import private manifests.

For common errors, see [Troubleshooting](docs/troubleshooting.md).
