"""Prueba real de carga → selección → arrastre → exportación en Qt."""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import Window, STYLE


def wait_until(app, condition, timeout=20):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("La interfaz no terminó el proceso a tiempo")
        app.processEvents()
        QTest.qWait(20)
    app.processEvents()


app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = Window()
window.show()
assert window.ratio == 950 / 1250
assert window.output_format.currentData() == "PNG"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    paths = []
    for index, size in enumerate(((1200, 800), (800, 1200), (1600, 900))):
        picture = Image.new("RGB", size, "#7db6c8")
        draw = ImageDraw.Draw(picture)
        draw.rectangle((0, size[1] // 2, size[0], size[1]), fill="#42665b")
        draw.ellipse((size[0] - 290, 70, size[0] - 150, 210), fill="#f6d78d")
        draw.polygon([(0, size[1] // 2 + 100), (size[0] // 3, 160), (size[0] * 2 // 3, size[1] // 2 + 100)], fill="#456479")
        path = root / f"Paisaje {index + 1}.png"
        picture.save(path)
        paths.append(str(path))
    window.add_paths(paths)
    wait_until(app, lambda: not window.busy)
    assert window.files.count() == 3
    window.add_paths(paths)
    assert window.files.count() == 3, "No debe duplicar imágenes"
    window.set_ratio(4, 5)
    assert window.ratio == 4 / 5
    assert window.preview.entry is not None
    origin = window.preview.image_rect().center().toPoint()
    QTest.mousePress(window.preview, Qt.MouseButton.LeftButton, pos=origin)
    QTest.mouseMove(window.preview, origin + QPoint(110, 0), delay=20)
    QTest.mouseRelease(window.preview, Qt.MouseButton.LeftButton, pos=origin + QPoint(110, 0))
    assert window.preview.entry.center[0] > 0.5, "El arrastre debe cambiar el encuadre"
    adjusted = window.preview.entry.center
    window.files.setCurrentRow(1)
    window.files.setCurrentRow(0)
    assert window.preview.entry.center == adjusted
    # Introducir medidas mediante teclado debe actualizar tanto el encuadre como la exportación.
    window.ratio_width.setFocus()
    window.ratio_width.selectAll()
    QTest.keyClicks(window.ratio_width, "950")
    QTest.keyClick(window.ratio_width, Qt.Key.Key_Tab)
    window.ratio_height.setFocus()
    window.ratio_height.selectAll()
    QTest.keyClicks(window.ratio_height, "1250")
    QTest.keyClick(window.ratio_height, Qt.Key.Key_Tab)
    assert window.ratio == 950 / 1250
    assert window.preview.ratio == 950 / 1250
    assert "950 × 1250" in window.strip_summary.text()
    window.destination = root / "salida"
    window.output_format.setCurrentIndex(1)
    window.export_all()
    wait_until(app, lambda: not window.busy)
    results = sorted(window.destination.glob("*.png"))
    assert len(results) == 3
    for result in results:
        with Image.open(result) as image:
            assert abs(image.width / image.height - 950 / 1250) < 0.002
    window.folder_label.setText("Carpeta de salida seleccionada · los originales se conservan")
    window.status.setText("Exportación terminada · 3 guardadas · 0 errores.")
    app.processEvents()
    artifact = Path(__file__).resolve().parent.parent / "build" / "preview.png"
    artifact.parent.mkdir(exist_ok=True)
    window.grab().save(str(artifact))
    window.set_ratio(7, 5)
    assert window.ratio == 1.4
    window.swap_ratio()
    assert abs(window.ratio - 5 / 7) < 0.00001
    window.reset_center()
    assert window.preview.entry.center == (0.5, 0.5)
    window.remove_images()
    assert window.files.count() == 2
window.close()
print("GUI OK: carga, duplicados, encuadre, exportación de lote, medidas de tira y eliminación.")
