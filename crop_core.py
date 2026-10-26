"""Recorte sin reescalado; no depende de la interfaz gráfica."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}


def crop_box(size, ratio, center=(0.5, 0.5)):
    """Devuelve el mayor rectángulo de la proporción, ajustado al píxel."""
    width, height = size
    if width < 1 or height < 1 or not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Las dimensiones y la proporción deben ser positivas.")
    if not all(math.isfinite(c) for c in center):
        raise ValueError("El encuadre no es válido.")
    if width / height > ratio:
        cw, ch = max(1, min(width, round(height * ratio))), height
    else:
        cw, ch = width, max(1, min(height, round(width / ratio)))
    left = max(0, min(width - cw, round(center[0] * width - cw / 2)))
    top = max(0, min(height - ch, round(center[1] * height - ch / 2)))
    return left, top, left + cw, top + ch


def open_image(path):
    with Image.open(path) as source:
        if getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) > 1:
            raise ValueError("Usa una imagen fija de un solo fotograma o página.")
        # La orientación de cámara se aplica antes de calcular el recorte.
        result = ImageOps.exif_transpose(source)
        result.load()
        return result


def inspect_image(path):
    """Lee tamaño orientado y una miniatura; no retiene la imagen completa."""
    with Image.open(path) as source:
        if getattr(source, "is_animated", False) or getattr(source, "n_frames", 1) > 1:
            raise ValueError("Usa una imagen fija de un solo fotograma o página.")
        size = source.size
        if source.getexif().get(274, 1) in (5, 6, 7, 8):
            size = size[::-1]
        source.thumbnail((160, 120))
        thumb = ImageOps.exif_transpose(source).convert("RGBA")
        return size, thumb


def export_image(source, destination, ratio, center, output_format, *, expected_size=None):
    extensions = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
    if output_format not in extensions:
        raise ValueError("Formato de salida no compatible.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with open_image(source) as original:
        if expected_size and original.size != expected_size:
            raise ValueError("La imagen cambió de tamaño. Elimínala de la lista y vuelve a añadirla.")
        box = crop_box(original.size, ratio, center)
        cropped = original.crop(box)
        # Solo conservamos el perfil de color, no GPS ni otros metadatos EXIF.
        profile = original.info.get("icc_profile")
        original_mode = cropped.mode
        if output_format == "JPEG":
            rgba = cropped.convert("RGBA")
            converted = Image.new("RGB", rgba.size, "white")
            converted.paste(rgba, mask=rgba.getchannel("A"))
            cropped = converted
        elif output_format == "PNG" and cropped.mode in ("L", "LA", "I;16", "I;16B", "I;16L"):
            if cropped.mode in ("I;16B", "I;16L"):
                cropped = cropped.convert("I;16")
        elif cropped.mode not in ("RGB", "RGBA"):
            cropped = cropped.convert("RGBA" if "A" in cropped.getbands() or "transparency" in cropped.info else "RGB")
        cropped.info.clear()
        options = {}
        if profile and original_mode in ("RGB", "RGBA", "P"):
            options["icc_profile"] = profile
        if output_format == "JPEG":
            options.update(quality=100, optimize=True, subsampling=0)
        elif output_format == "WEBP":
            options.update(lossless=True, exact=True)
        stem = Path(source).stem[:150] + "_recortada"
        suffix = extensions[output_format]
        counter = 1
        while True:
            name = stem + ("" if counter == 1 else f"_{counter}") + suffix
            target = destination / name
            try:
                handle = target.open("xb")
                break
            except FileExistsError:
                counter += 1
        try:
            with handle:
                cropped.save(handle, format=output_format, **options)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target, cropped.size

