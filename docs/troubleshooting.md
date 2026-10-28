# Troubleshooting

**No photos found:** Confirm the period and timezone, then inspect `intake-report.json`. Inputs must be extracted folders, not ZIP paths. Files without a reliable capture date are reported instead of assigned the filesystem modification date.

**HEIC cannot open:** Install the optional `pillow-heif` package in the same virtual environment, then create a fresh batch. JPEG, PNG, TIFF, BMP and WebP use Pillow directly. Resolve errors before treating a batch as complete.

**A cannot fill the display:** Choose a safe crop matching the display ratio. If the crop loses people/context or needs enlargement, keep the full composition as C. Do not stretch the photo.

**B cannot be finalized:** Review/edit it and change its plan category to A or C, then render again and inspect the new JPEG.

**Stale review:** The reviewed JPEG changed or you supplied choices from another batch. Reopen the new reviewer, inspect the image and save fresh choices. Never replace hashes in a CSV just to bypass this check.

**An image does not show:** Keep `review.html` beside its `previews` folder. Move the complete batch together. D images intentionally have no preview. Use a current desktop browser and ensure local file access is allowed.

**Choices disappeared:** Browser storage may be cleared, blocked, or scoped differently after moving a file. Import the CSV saved with “Save choices.” Save a CSV before leaving any review session.

**Export exceeds the total budget:** Reduce selected duplicates or use a smaller display profile in a new batch and review the new output. Photo Curator never silently removes unique experiences or lowers already-reviewed JPEG quality during finalization.

**Batch or export already exists:** Use a new dated name. Completed folders are snapshots and are never overwritten by these commands.
