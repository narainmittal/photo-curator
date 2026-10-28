# Curation and review contract

Review each image at useful size. Compare bursts together. Record distinct places, experiences, children’s activities and family groups as coverage tags; do not add quality points for emotional importance. Never infer people’s identities without user context.

| Category | Meaning | Final export |
| --- | --- | --- |
| A | Display-ready, clear primary subject, safe full-frame composition | Only after explicit review choice |
| B | Needs review/edit; unresolved crop, light or quality | Blocked |
| C | Meaningful portrait or imperfect but worthwhile memory | Explicit choice required |
| D | Medical/detail documentation, screenshots, paperwork, accidents, severe blur or weaker repeat | Blocked; no preview |

Rate clarity, exposure, framing, expression/scenic impact, and clean detail from 0 to 4. Weights are 35/15/25/15/10, rounded to five points. A requires score 75+ and clarity, exposure, framing and artifacts each at least 3. These ratings are anchored human judgments, not calibrated scientific scores. Category overrides score.

A plan record looks like:

```json
{
  "id": "ID_FROM_INVENTORY",
  "category": "A",
  "title": "Family at the park",
  "reason": "Readable faces and complete activity context",
  "ratings": {"clarity": 4, "exposure": 3, "framing": 4, "expression": 4, "artifacts": 4},
  "tags": ["family group", "park"],
  "rotation": 0,
  "crop": [0, 100, 3200, 2100],
  "protected": [150, 200, 3050, 2000]
}
```

Crop and protected bounds are integer pixels **after EXIF orientation and the requested counterclockwise rotation**. Set crop to null to retain the complete composition. Protected bounds must remain inside the crop; use them for heads, hands, props and location context. Do not use a harmful crop merely to fill a landscape screen. A low-resolution source is not enlarged to pass A.

The reviewer shows the actual output. Keep commits a decision against its SHA-256. Re-rendering changes the review key; previous approvals cannot silently apply to changed output. Review B files after correcting their plan/category; D records never expose their source images in the gallery. An independent reviewer can inspect the same HTML and export their own choices; compare disagreements before finalizing. Human choice is required; the tool does not certify an independent review occurred.

If photo edits are needed, edit a copy, keep the source untouched, and use a new batch. The portable renderer intentionally limits edits to orientation, explicit crop, downsampling and mild resizing sharpening. It does not reconstruct faces or repair blur.
