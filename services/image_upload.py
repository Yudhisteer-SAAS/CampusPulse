import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from config import EVENT_UPLOAD_DIR


ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
FORMAT_EXTENSIONS = {'JPEG': {'.jpg', '.jpeg'}, 'PNG': {'.png'}, 'WEBP': {'.webp'}}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000
MAX_IMAGE_DIMENSION = 6000


def has_upload(file: FileStorage | None) -> bool:
    return bool(file and file.filename)


def validate_image_upload(file: FileStorage):
    extension = Path(file.filename or '').suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError('Images must be JPEG, PNG, or WebP files.')

    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size <= 0 or size > MAX_IMAGE_BYTES:
        raise ValueError('Each image must be smaller than 5 MB.')

    try:
        with Image.open(file.stream) as image:
            image_format = image.format
            image.verify()
        if extension not in FORMAT_EXTENSIONS.get(image_format, set()):
            raise ValueError('The selected file extension does not match its image content.')

        file.stream.seek(0)
        with Image.open(file.stream) as image:
            if (
                image.width <= 0
                or image.height <= 0
                or image.width > MAX_IMAGE_DIMENSION
                or image.height > MAX_IMAGE_DIMENSION
                or image.width * image.height > MAX_IMAGE_PIXELS
            ):
                raise ValueError('Images must be no larger than 6000 by 6000 pixels.')
            image.seek(0)
            image.load()
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode in ('RGBA', 'LA') or (
                normalized.mode == 'P' and 'transparency' in normalized.info
            ):
                normalized = normalized.convert('RGBA')
            else:
                normalized = normalized.convert('RGB')
            file.stream.seek(0)
            return normalized.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('The uploaded file is not a valid image.') from exc


def save_uploaded_image(file: FileStorage):
    image = validate_image_upload(file)
    EVENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.webp'
    destination = EVENT_UPLOAD_DIR / filename
    try:
        image.save(destination, format='WEBP', quality=88, method=5)
    finally:
        image.close()
    return filename


def delete_image_file(filename):
    if not filename or Path(filename).name != filename:
        return False
    destination = EVENT_UPLOAD_DIR / filename
    if destination.resolve().parent != EVENT_UPLOAD_DIR.resolve():
        return False
    try:
        destination.unlink(missing_ok=True)
    except OSError:
        return False
    return True
