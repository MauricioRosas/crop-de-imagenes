"""Verifica la revisión manual y la copia numerada desde la interfaz Qt."""
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import Window, STYLE


app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(STYLE)
window = Window()
window.show()
window.tabs.setCurrentIndex(1)
organizer = window.organizer
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory).resolve()
    strip_names = ["20261025_101004_994_1x.jpg", "20261025_101141_899_1x.jpg"]
    photo_names = [f"IMG_{number}_20261025_{stamp}_recortada.png" for number, stamp in
                   ((8614, "100948"), (8615, "101001"), (8616, "101125"), (8617, "101138"))]
    for name in strip_names + photo_names:
        Image.new("RGB", (120, 360) if name in strip_names else (152, 200), "#42665b").save(root / name)
    strips, photos = [root / n for n in strip_names], [root / n for n in photo_names]
    organizer.add_paths(strips[::-1], "strip")
    organizer.add_paths(photos[::-1], "photo")
    assert organizer.tree.topLevelItemCount() == 2
    assert organizer.tree.topLevelItem(0).childCount() == 2
    assert organizer.groups[1].photos == photos[2:]

    # Mover un grupo debe llevar consigo sus fotos y cambiar la numeración.
    organizer.tree.setCurrentItem(organizer.tree.topLevelItem(0))
    QTest.mouseClick(organizer.move_down, Qt.MouseButton.LeftButton)
    assert organizer.groups[0].strip == strips[1]
    assert organizer.plan[0].source == strips[1]
    organizer.regroup()

    # Corregir una asociación y devolverla sin duplicar archivos.
    organizer.tree.setCurrentItem(organizer.tree.topLevelItem(0).child(0))
    organizer.assignment.setCurrentIndex(1)
    QTest.mouseClick(organizer.assign_button, Qt.MouseButton.LeftButton)
    assert len(organizer.groups[0].photos) == 1
    assert organizer.groups[1].photos[-1] == photos[0]
    assert len(organizer.plan) == 6
    organizer.regroup()
    organizer.tree.setCurrentItem(organizer.tree.topLevelItem(0).child(0))
    QTest.mouseClick(organizer.unassign_button, Qt.MouseButton.LeftButton)
    assert organizer.unassigned == [photos[0]]
    assert organizer.plan[-1].kind == "Sin_asignar"
    organizer.regroup()
    organizer.prefix.setText("Festival")
    organizer.start.setValue(10)
    assert organizer.plan[0].filename.startswith("Festival_000010_Tira_")
    organizer.save_to(root / "resultados")
    deadline = time.monotonic() + 20
    while organizer.busy:
        assert time.monotonic() < deadline
        app.processEvents()
        QTest.qWait(20)
    assert organizer.output is not None
    assert len(list(organizer.output.glob("*.jpg"))) == 2
    assert len(list(organizer.output.glob("*.png"))) == 4
    for item in organizer.plan:
        assert (organizer.output / item.filename).read_bytes() == item.source.read_bytes()
    assert (organizer.output / "orden.csv").exists()
    window.close()
print("Organizador OK: agrupación, correcciones, orden manual, numeración y copias idénticas.")
