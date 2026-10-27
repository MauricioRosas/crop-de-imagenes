"""Agrupación por fechas del nombre y copias numeradas sin recodificar imágenes."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable


STAMP = re.compile(r"(?<!\d)(20\d{6})_(\d{6})(?:_(\d{3})(?=_|$))?(?!\d)")


def filename_time(path: Path):
    match = STAMP.search(Path(path).stem)
    if not match:
        return None
    try:
        value = datetime.strptime(match[1] + match[2], "%Y%m%d%H%M%S")
        return value.replace(microsecond=int(match[3] or 0) * 1000)
    except ValueError:
        return None


def time_key(path: Path):
    return filename_time(path) or datetime.max, path.name.casefold(), str(path)


@dataclass
class StripGroup:
    strip: Path
    photos: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def suggest_groups(strips, photos, photos_per_strip=2, max_seconds=180):
    """Cada tira toma las N fotos anteriores más cercanas, sin reutilizarlas.

    Solo se proponen fotos del mismo día dentro del margen elegido. Las que
    no encajan quedan aparte, disponibles para una asignación manual.
    """
    if photos_per_strip < 1 or max_seconds < 1:
        raise ValueError("La cantidad de fotos y el margen deben ser positivos.")
    strips = sorted(set(map(Path, strips)), key=time_key)
    photos = sorted(set(map(Path, photos)), key=time_key)
    if set(strips) & set(photos):
        raise ValueError("Un mismo archivo no puede ser tira y foto.")
    available = set(photos)
    groups = []
    for strip in strips:
        stamp = filename_time(strip)
        group = StripGroup(strip)
        if stamp is None:
            group.notes.append("Sin fecha reconocible; asigna las fotos manualmente")
        else:
            candidates = [p for p in photos if p in available and
                          (photo_time := filename_time(p)) is not None and
                          photo_time.date() == stamp.date() and
                          0 <= (stamp - photo_time).total_seconds() <= max_seconds]
            chosen = candidates[-photos_per_strip:]
            group.photos = chosen
            available.difference_update(chosen)
            if len(candidates) > photos_per_strip:
                group.notes.append("Hay más fotos cercanas; se eligieron las últimas")
            chosen_times = [filename_time(p) for p in chosen]
            if len(chosen_times) != len(set(chosen_times)):
                group.notes.append("Fotos con la misma hora; revisa la selección")
            if sum(filename_time(s) == stamp for s in strips) > 1:
                group.notes.append("Hay otra tira con la misma hora; revisa la asignación")
        groups.append(group)
    return groups, sorted(available, key=time_key)


@dataclass(frozen=True)
class CopyItem:
    source: Path
    filename: str
    kind: str
    strip: Path | None


def safe_prefix(text):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", text.strip())
    return cleaned.strip(" ._")[:50]


def make_plan(groups, unassigned=(), prefix="", start=1):
    if start < 1:
        raise ValueError("La numeración debe empezar en un número positivo.")
    rows = []
    seen = set()
    for group in groups:
        rows.append((group.strip, "Tira", group.strip))
        rows.extend((photo, "Foto", group.strip) for photo in group.photos)
    rows.extend((photo, "Sin_asignar", None) for photo in unassigned)
    digits = max(6, len(str(start + len(rows) - 1)))
    prefix = safe_prefix(prefix)
    result = []
    for number, (path, kind, strip) in enumerate(rows, start):
        path = Path(path)
        if path in seen:
            raise ValueError(f"Un archivo aparece más de una vez: {path.name}")
        seen.add(path)
        name = f"{number:0{digits}d}_{kind}_{path.stem[:140]}{path.suffix.lower()}"
        if prefix:
            name = f"{prefix}_{name}"
        result.append(CopyItem(path, name, kind, strip))
    return result


def copy_plan(plan, destination, progress: Callable | None = None,
              cancelled: Callable | None = None):
    """Crea una carpeta nueva con copias idénticas y un CSV de correspondencias."""
    if not plan:
        raise ValueError("No hay archivos para guardar.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    # Una carpeta nueva en cada ejecución permite repetir sin pisar resultados.
    output = Path(tempfile.mkdtemp(prefix="Ordenadas_", dir=destination))
    outputs, errors = [], []
    stopped = False
    with (output / "orden.csv").open("x", encoding="utf-8-sig", newline="") as log:
        writer = csv.writer(log)
        writer.writerow(["orden", "tipo", "original", "nombre_nuevo", "tira", "ruta_original", "estado"])
        for index, item in enumerate(plan, 1):
            if cancelled and cancelled():
                stopped = True
                break
            target = output / item.filename
            # El plan también puede venir de código: solo aceptamos nombres simples.
            if Path(item.filename).name != item.filename or item.filename in ("", ".", ".."):
                raise ValueError("El nombre de salida debe ser un nombre de archivo simple.")
            created = False
            try:
                with item.source.open("rb") as source, target.open("xb") as copied:
                    created = True
                    while block := source.read(1024 * 1024):
                        if cancelled and cancelled():
                            raise InterruptedError("Copia cancelada")
                        copied.write(block)
                shutil.copystat(item.source, target)
                outputs.append(target)
                state = "OK"
            except InterruptedError:
                if created:
                    target.unlink(missing_ok=True)
                stopped = True
                break
            except Exception as error:
                if created:
                    target.unlink(missing_ok=True)
                state = str(error)
                errors.append(f"{item.source.name}: {error}")
            writer.writerow([index, item.kind, item.source.name, item.filename,
                             item.strip.name if item.strip else "", str(item.source), state])
            log.flush()
            if progress:
                progress(index, item.source.name)
    return output, outputs, errors, stopped
