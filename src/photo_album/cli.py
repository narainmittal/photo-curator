"""Inventory, human review, conservative rendering and verified album export."""
import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageCms, ImageFilter, ImageOps
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.bmp', '.heic', '.heif'}
WEIGHTS = {'clarity': 35, 'exposure': 15, 'framing': 25, 'expression': 15, 'artifacts': 10}
PROFILES = {'nixplay': {'width': 1280, 'height': 800, 'max_bytes': 500000000, 'file_max_bytes': 3000000}, 'generic': {'width': 1920, 'height': 1080, 'max_bytes': 500000000, 'file_max_bytes': 10000000}}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')

def period_bounds(period):
    if re.fullmatch('\\d{4}', period):
        return (date(int(period), 1, 1), date(int(period) + 1, 1, 1))
    if re.fullmatch('\\d{4}-Q[1-4]', period):
        y, q = (int(period[:4]), int(period[-1]))
        month = 3 * q - 2
        start = date(y, month, 1)
        return (start, date(y + 1, 1, 1) if q == 4 else date(y, month + 3, 1))
    if re.fullmatch('\\d{4}-\\d{2}', period):
        y, m = map(int, period.split('-'))
        start = date(y, m, 1)
        return (start, date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1))
    if ':' in period:
        left, right = period.split(':', 1)
        start, last = (date.fromisoformat(left), date.fromisoformat(right))
        if last < start:
            raise ValueError('End date precedes start date')
        return (start, last + timedelta(days=1))
    raise ValueError('Use YYYY, YYYY-Q1, YYYY-MM, or inclusive YYYY-MM-DD:YYYY-MM-DD')

def open_photo(path):
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    with Image.open(path) as source:
        source.load()
        exif = source.getexif()
        try:
            exif = dict(exif) | dict(exif.get_ifd(34665))
        except (KeyError, TypeError, ValueError):
            exif = dict(exif)
        image = ImageOps.exif_transpose(source)
        if image.info.get('icc_profile'):
            image = ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile'])), ImageCms.createProfile('sRGB'), outputMode='RGB')
        if 'A' in image.getbands() or 'transparency' in image.info:
            rgba = image.convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'white')
            background.alpha_composite(rgba)
            image = background
        return (image.convert('RGB'), exif)

def capture_date(path, exif, tz):
    candidates = [Path(str(path) + '.json'), Path(str(path) + '.supplemental-metadata.json')]
    candidates += sorted(path.parent.glob(path.name[:40] + '*.json'))
    for side in dict.fromkeys(candidates):
        try:
            data = read(side)
            if data.get('title') != path.name and side not in candidates[:2]:
                continue
            stamp = data.get('photoTakenTime', {}).get('timestamp')
            if stamp:
                return (datetime.fromtimestamp(int(stamp), tz).isoformat(), 'takeout')
        except (OSError, ValueError, TypeError):
            pass
    for key in [36867, 36868, 306]:
        try:
            return (datetime.strptime(str(exif.get(key, ''))[:19], '%Y:%m:%d %H:%M:%S').isoformat(), 'exif-local')
        except ValueError:
            pass
    match = re.search('(20\\d{2})[-_]?(\\d{2})[-_]?(\\d{2})', path.name)
    if match:
        try:
            return (date(*map(int, match.groups())).isoformat(), 'filename')
        except ValueError:
            pass
    return ('', 'unknown')

def scan(args):
    from zoneinfo import ZoneInfo
    batch = Path(args.batch).resolve()
    roots = [Path(x).resolve() for x in args.inputs]
    if any((not root.is_dir() for root in roots)):
        raise ValueError('Inputs must be extracted folders; extract all Takeout ZIP parts first')
    if any((batch == root or root in batch.parents or batch in root.parents for root in roots)):
        raise ValueError('Keep batch outputs separate from input folders')
    bounds = period_bounds(args.period)
    tz = ZoneInfo(args.timezone)
    batch.mkdir(parents=True, exist_ok=False)
    inventory, errors, seen, duplicates, outside = ([], [], {}, [], [])
    for path in sorted({p for root in roots for p in root.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS}):
        try:
            digest = sha(path)
            if digest in seen:
                duplicates.append({'source': str(path), 'same_as': seen[digest], 'sha256': digest})
                continue
            image, exif = open_photo(path)
            taken, origin = capture_date(path, exif, tz)
            if not taken or not bounds[0] <= date.fromisoformat(taken[:10]) < bounds[1]:
                outside.append({'source': str(path), 'taken': taken, 'reason': 'unknown date' if not taken else 'outside period'})
                continue
            seen[digest] = str(path)
            inventory.append({'id': digest[:16], 'source': str(path), 'sha256': digest, 'taken': taken, 'date_source': origin, 'size': list(image.size)})
        except Exception as error:
            errors.append({'source': str(path), 'error': str(error)})
    prior = {}
    if args.reuse:
        for row in read(Path(args.reuse) / 'rendered.json'):
            prior[row['source_sha256']] = row
    plans = []
    for row in inventory:
        old = prior.get(row['sha256'])
        plans.append({'id': row['id'], 'category': 'B', 'title': Path(row['source']).stem, 'reason': 'Needs visual review', 'ratings': None, 'tags': [], 'rotation': 0, 'crop': None, 'protected': None, 'prior_category': old['category'] if old else None})
    settings = dict(PROFILES[args.profile])
    settings.update({k: getattr(args, k) or settings[k] for k in ['width', 'height', 'max_bytes', 'file_max_bytes']})
    write(batch / 'batch.json', {'schema_version': 1, 'label': args.label or args.period, 'period': args.period, 'timezone': args.timezone, 'profile': args.profile, **settings})
    write(batch / 'inventory.json', inventory)
    write(batch / 'plan.json', plans)
    write(batch / 'intake-report.json', {'photos': len(inventory), 'exact_duplicates': duplicates, 'outside_period_or_unknown_date': outside, 'errors': errors})
    print(f'{len(inventory)} unique photos; {len(duplicates)} exact duplicates; {len(outside)} outside period/undated; {len(errors)} errors. Review intake-report.json before proceeding.')

def render(args):
    batch = Path(args.batch).resolve()
    config = read(batch / 'batch.json')
    inventory = {r['id']: r for r in read(batch / 'inventory.json')}
    plans = read(batch / 'plan.json')
    if len(plans) != len(inventory) or {r['id'] for r in plans} != set(inventory):
        raise ValueError('Plan must cover every input exactly once')
    (batch / 'previews').mkdir(exist_ok=True)
    records = []
    for plan in plans:
        r = dict(plan)
        source = inventory[r['id']]
        path = Path(source['source'])
        if sha(path) != source['sha256']:
            raise ValueError('Original changed: ' + str(path))
        category = r['category']
        ratings = r.get('ratings')
        if category not in ['A', 'B', 'C', 'D']:
            raise ValueError('Category must be A, B, C or D')
        if not r.get('reason') or not r.get('title'):
            raise ValueError('A title and reason are required')
        if ratings is not None and (set(ratings) != set(WEIGHTS) or any((type(v) not in (int, float) or not 0 <= v <= 4 for v in ratings.values()))):
            raise ValueError('Rate all five dimensions from 0 to 4')
        score = 5 * round(sum((ratings[k] * w / 4 for k, w in WEIGHTS.items())) / 5) if ratings else None
        if category == 'A' and (score is None or score < 75 or any((ratings[k] < 3 for k in ['clarity', 'exposure', 'framing', 'artifacts']))):
            raise ValueError('A quality gate failed: ' + r['id'])
        r.update(source_sha256=source['sha256'], taken=source['taken'], score=score, after=None, output_sha256=None)
        if category == 'D':
            records.append(r)
            continue
        image, _ = open_photo(path)
        rotation = r.get('rotation', 0)
        if rotation not in [0, 90, 180, 270]:
            raise ValueError('Rotation must be 0, 90, 180 or 270 degrees counterclockwise')
        image = image.rotate(rotation, expand=True)
        crop = r.get('crop')
        protected = r.get('protected')
        if crop:
            if len(crop) != 4 or any((type(x) is not int for x in crop)):
                raise ValueError('Crop uses four integer pixels after EXIF orientation and rotation')
            l, t, rr, b = crop
            if not 0 <= l < rr <= image.width or not 0 <= t < b <= image.height:
                raise ValueError('Crop outside source')
            if protected and (not (l <= protected[0] < protected[2] <= rr and t <= protected[1] < protected[3] <= b)):
                raise ValueError('Crop cuts protected people or context')
            image = image.crop(crop)
        width, height = (config['width'], config['height'])
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        coverage = image.width * image.height / (width * height)
        if category == 'A' and coverage < 0.995:
            raise ValueError('A must safely fill the display without enlargement; use C for portrait/padded exceptions')
        image = image.filter(ImageFilter.UnsharpMask(radius=0.5, percent=40, threshold=3))
        canvas = Image.new('RGB', (width, height), (20, 20, 20))
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        output = batch / 'previews' / (r['id'] + '.jpg')
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        for quality in [93, 90, 87, 84, 81]:
            canvas.save(output, quality=quality, subsampling=0, optimize=True, icc_profile=profile)
            if output.stat().st_size < config['file_max_bytes']:
                break
        else:
            raise ValueError('Per-photo budget too small; choose a different profile')
        r.update(after='previews/' + output.name, output_sha256=sha(output), bytes=output.stat().st_size, frame_coverage=coverage, jpeg_quality=quality)
        records.append(r)
    write(batch / 'rendered.json', records)
    build_review(batch)
    print(f"Rendered {len(records)} records. Open {batch / 'review.html'}")

def build_review(batch):
    config = read(batch / 'batch.json')
    records = read(batch / 'rendered.json')
    payload = json.dumps({'label': config['label'], 'width': config['width'], 'height': config['height'], 'batch_key': sha(batch / 'rendered.json'), 'photos': records}).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (Path(__file__).parent / 'templates/review.html').read_text()
    (batch / 'review.html').write_text(template.replace('__PAYLOAD__', payload))

def finalize(args):
    batch = Path(args.batch).resolve()
    config = read(batch / 'batch.json')
    records = read(batch / 'rendered.json')
    inv = read(batch / 'inventory.json')
    for source in inv:
        if sha(source['source']) != source['sha256']:
            raise ValueError('Original changed since intake')
    with Path(args.choices).open(newline='', encoding='utf-8-sig') as f:
        choices = list(csv.DictReader(f))
    by = {r['source_id']: r for r in choices}
    if len(by) != len(choices) or set(by) != {r['id'] for r in records}:
        raise ValueError('Choices must cover this exact batch once each')
    selected = []
    for row in records:
        choice = by[row['id']]
        if choice['chosen'] not in ['yes', 'no']:
            raise ValueError('Choices must be yes/no')
        if choice['chosen'] == 'no':
            continue
        if row['category'] not in ['A', 'C']:
            raise ValueError('Only reviewed A or explicitly selected C can be finalized')
        if choice.get('reviewed_sha256') != row['output_sha256']:
            raise ValueError('Stale review; inspect changed previews again')
        output = batch / row['after']
        if sha(output) != row['output_sha256']:
            raise ValueError('Preview changed since rendering')
        selected.append(row)
    if not selected:
        raise ValueError('No photos chosen')
    total = sum(((batch / r['after']).stat().st_size for r in selected))
    if total > config['max_bytes']:
        raise ValueError('Album exceeds budget; adjust selection/profile and re-review changed images')
    target = Path(args.output).resolve()
    if any((target == Path(r['source']).parent or target in Path(r['source']).parents or Path(r['source']).parent in target.parents for r in inv)):
        raise ValueError('Export cannot contain original sources')
    target.mkdir(parents=True, exist_ok=False)
    (target / 'photos').mkdir()
    manifest = []
    for row in sorted(selected, key=lambda r: (r['taken'], r['id'])):
        name = row['taken'][:10] + '_' + row['id'] + '.jpg'
        dest = target / 'photos' / name
        shutil.copy2(batch / row['after'], dest)
        manifest.append({'file': name, 'sha256': row['output_sha256'], 'bytes': dest.stat().st_size, 'source_sha256': row['source_sha256'], 'category': row['category']})
    write(target / 'manifest.json', {'settings': config, 'photos': manifest, 'bytes': total, 'uploaded': False})
    with zipfile.ZipFile(target / 'album.zip', 'w', zipfile.ZIP_STORED) as z:
        for row in manifest:
            z.write(target / 'photos' / row['file'], row['file'])
    verify_export(target)
    print(f'{len(selected)} photos, {total / 1000000.0:.2f} MB. Verified export: {target}')

def verify_export(target):
    manifest = read(target / 'manifest.json')
    config = manifest['settings']
    expected = {r['file'] for r in manifest['photos']}
    if {p.name for p in (target / 'photos').iterdir()} != expected:
        raise ValueError('Unexpected/missing export files')
    for row in manifest['photos']:
        path = target / 'photos' / row['file']
        if sha(path) != row['sha256'] or path.stat().st_size != row['bytes']:
            raise ValueError('Export hash/size mismatch')
        with Image.open(path) as image:
            image.load()
            if image.size != (config['width'], config['height']) or image.mode != 'RGB' or image.getexif() or (not image.info.get('icc_profile')):
                raise ValueError('Invalid dimensions, color or metadata')
        if path.stat().st_size >= config['file_max_bytes']:
            raise ValueError('Photo exceeds limit')
    if sum((r['bytes'] for r in manifest['photos'])) > config['max_bytes']:
        raise ValueError('Album exceeds limit')
    with zipfile.ZipFile(target / 'album.zip') as z:
        if z.testzip() or len(z.namelist()) != len(expected) or set(z.namelist()) != expected:
            raise ValueError('Invalid archive')
        for row in manifest['photos']:
            if hashlib.sha256(z.read(row['file'])).hexdigest() != row['sha256']:
                raise ValueError('Archive content changed')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('scan')
    p.add_argument('inputs', nargs='+')
    p.add_argument('--batch', required=True)
    p.add_argument('--period', required=True)
    p.add_argument('--label')
    p.add_argument('--timezone', default='UTC')
    p.add_argument('--reuse', help='Earlier batch: retain category hints, never image approval')
    p.add_argument('--profile', choices=PROFILES, default='nixplay')
    for key in ['width', 'height', 'max_bytes', 'file_max_bytes']:
        p.add_argument('--' + key.replace('_', '-'), type=int)
    p.set_defaults(func=scan)
    for name, func in [('render', render), ('review', lambda a: build_review(Path(a.batch))), ('finalize', finalize)]:
        p = commands.add_parser(name)
        p.add_argument('--batch', required=True)
        p.set_defaults(func=func)
        if name == 'finalize':
            p.add_argument('--choices', required=True)
            p.add_argument('--output', required=True)
    p = commands.add_parser('verify')
    p.add_argument('output')
    p.set_defaults(func=lambda a: verify_export(Path(a.output)))
    args = parser.parse_args(argv)
    try:
        if args.command == 'scan' and any((getattr(args, k) is not None and getattr(args, k) <= 0 for k in ['width', 'height', 'max_bytes', 'file_max_bytes'])):
            raise ValueError('Display and storage limits must be positive')
        args.func(args)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')
if __name__ == '__main__':
    main()
