"""Recorta: interfaz de escritorio para recortar imágenes por lotes."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QSize, QRectF, Signal, QThread, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QPixmap, QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QAbstractItemView, QFileDialog,
    QMessageBox, QComboBox, QDoubleSpinBox, QProgressBar, QFrame, QTabWidget,
)

from crop_core import EXTENSIONS, crop_box, open_image, inspect_image, export_image
from organizer_ui import Organizer


def qt_image(image):
    rgba = image.convert("RGBA")
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


@dataclass
class Entry:
    path: Path
    size: tuple[int, int]
    center: tuple[float, float] = (0.5, 0.5)


class ImportWorker(QThread):
    loaded = Signal(object, object)
    completed = Signal(object)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        errors = []
        for path in self.paths:
            if self.isInterruptionRequested():
                break
            try:
                size, thumbnail = inspect_image(path)
                self.loaded.emit(Entry(path, size), qt_image(thumbnail))
            except Exception as error:
                errors.append(f"{path.name}: {error}")
        self.completed.emit(errors)


class ExportWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object, object, bool)

    def __init__(self, jobs, destination, ratio, fmt, parent=None):
        super().__init__(parent)
        self.jobs, self.destination, self.ratio = jobs, destination, ratio
        self.fmt = fmt

    def run(self):
        outputs, errors = [], []
        for index, entry in enumerate(self.jobs):
            if self.isInterruptionRequested():
                break
            try:
                path, _ = export_image(entry.path, self.destination, self.ratio,
                                       entry.center, self.fmt, expected_size=entry.size)
                outputs.append(path)
            except Exception as error:
                errors.append(f"{entry.path.name}: {error}")
            self.progress.emit(index + 1, entry.path.name)
        self.completed.emit(outputs, errors, self.isInterruptionRequested())


class ImageList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setIconSize(QSize(70, 60))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(4)
        self.setMinimumWidth(245)
        self.setMaximumWidth(340)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.files_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()


class Preview(QWidget):
    center_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(340, 300)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.picture = None
        self.entry = None
        self.ratio = 1.0
        self.drag = None
        self.error = ""

    def display(self, entry):
        self.entry, self.picture, self.error = entry, None, ""
        if entry:
            try:
                with open_image(entry.path) as image:
                    image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
                    self.picture = qt_image(image)
            except Exception as error:
                self.error = f"No se pudo abrir la vista previa.\n{error}"
        self.update()

    def image_rect(self):
        if not self.entry:
            return QRectF()
        w, h = self.entry.size
        scale = min((self.width() - 48) / w, (self.height() - 48) / h)
        return QRectF((self.width() - w * scale) / 2, (self.height() - h * scale) / 2,
                      w * scale, h * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111923"))
        if not self.picture or not self.entry:
            painter.setPen(QColor("#a7b5c5"))
            painter.drawText(self.rect().adjusted(24, 24, -24, -24),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self.error or "Tu encuadre empieza aquí\n\nAñade imágenes o arrástralas a la lista de la izquierda.")
            return
        target = self.image_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self.picture)
        left, top, right, bottom = crop_box(self.entry.size, self.ratio, self.entry.center)
        sx, sy = target.width() / self.entry.size[0], target.height() / self.entry.size[1]
        crop = QRectF(target.x() + left * sx, target.y() + top * sy,
                      (right - left) * sx, (bottom - top) * sy)
        shade = QColor(0, 0, 0, 155)
        painter.fillRect(QRectF(target.left(), target.top(), target.width(), crop.top() - target.top()), shade)
        painter.fillRect(QRectF(target.left(), crop.bottom(), target.width(), target.bottom() - crop.bottom()), shade)
        painter.fillRect(QRectF(target.left(), crop.top(), crop.left() - target.left(), crop.height()), shade)
        painter.fillRect(QRectF(crop.right(), crop.top(), target.right() - crop.right(), crop.height()), shade)
        painter.setPen(QPen(QColor("#73e0b9"), 2))
        painter.drawRect(crop)
        painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
        for fraction in (1 / 3, 2 / 3):
            x, y = crop.x() + crop.width() * fraction, crop.y() + crop.height() * fraction
            painter.drawLine(x, crop.top(), x, crop.bottom())
            painter.drawLine(crop.left(), y, crop.right(), y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.entry and self.picture:
            rect = self.image_rect()
            if rect.contains(event.position()):
                box = crop_box(self.entry.size, self.ratio, self.entry.center)
                center = ((box[0] + box[2]) / (2 * self.entry.size[0]),
                          (box[1] + box[3]) / (2 * self.entry.size[1]))
                self.drag = (event.position(), center)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag and self.entry:
            start, center = self.drag
            delta = event.position() - start
            rect = self.image_rect()
            proposed = (center[0] + delta.x() / rect.width(), center[1] + delta.y() / rect.height())
            box = crop_box(self.entry.size, self.ratio, proposed)
            self.entry.center = ((box[0] + box[2]) / (2 * self.entry.size[0]),
                                 (box[1] + box[3]) / (2 * self.entry.size[1]))
            self.center_changed.emit(self.entry.center)
            self.update()

    def mouseReleaseEvent(self, event):
        self.drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)


STYLE = """
QWidget { background: #18222f; color: #ebf0f6; font-size: 13px; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#subtle { color: #a7b5c5; }
QLabel#section { font-size: 11px; font-weight: 700; color: #8ea3ba; }
QPushButton { background: #2b3a4d; border: 1px solid #405269; border-radius: 7px; padding: 9px 13px; }
QPushButton:hover { background: #374b63; }
QPushButton:disabled { color: #6d7c8e; border-color: #2b3a4d; }
QPushButton#primary { background: #73e0b9; color: #12251e; border: 0; font-weight: 700; }
QPushButton#primary:disabled { background: #32594e; color: #85a396; }
QListWidget { background: #111923; border: 1px solid #304055; border-radius: 9px; padding: 5px; }
QListWidget::item { padding: 6px; border-radius: 5px; }
QListWidget::item:selected { background: #304a59; color: white; }
QComboBox, QDoubleSpinBox { background: #111923; border: 1px solid #405269; border-radius: 5px; padding: 7px; min-height: 20px; }
QComboBox QAbstractItemView { background: #26364a; selection-background-color: #40556c; }
QFrame#panel { background: #1d2a3a; border-radius: 10px; }
QFrame#panel QLabel { background: transparent; }
QProgressBar { border: 0; border-radius: 3px; background: #111923; height: 7px; text-align: center; }
QProgressBar::chunk { background: #73e0b9; border-radius: 3px; }
"""


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Recorta — imágenes por lotes")
        self.resize(1160, 860)
        self.setMinimumSize(990, 760)
        self.entries = {}
        self.worker = None
        self.busy = False
        self.destination = None
        root = QWidget()
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.tabs.addTab(root, "Recortar imágenes")
        self.organizer = Organizer()
        self.tabs.addTab(self.organizer, "Ordenar y renombrar")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Recorta")
        title.setObjectName("title")
        subtitle = QLabel("Un mismo formato. El mejor encuadre para cada imagen.")
        subtitle.setObjectName("subtle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.add_button = QPushButton("＋ Añadir imágenes")
        self.add_button.clicked.connect(self.choose_images)
        header.addWidget(self.add_button)
        layout.addLayout(header)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.count = QLabel("IMÁGENES · 0")
        self.count.setObjectName("section")
        left.addWidget(self.count)
        self.files = ImageList()
        self.files.files_dropped.connect(self.add_paths)
        self.files.currentItemChanged.connect(self.select_image)
        left.addWidget(self.files, 1)
        self.remove_button = QPushButton("Quitar seleccionadas")
        self.remove_button.clicked.connect(self.remove_images)
        left.addWidget(self.remove_button)
        body.addLayout(left, 1)
        right = QVBoxLayout()
        measurements_panel = QFrame()
        measurements_panel.setObjectName("panel")
        measurements_layout = QVBoxLayout(measurements_panel)
        measurements_layout.setContentsMargins(16, 12, 16, 12)
        measurements_title = QLabel("MEDIDAS DE LA FOTO EN LA TIRA")
        measurements_title.setObjectName("section")
        measurements_layout.addWidget(measurements_title)
        measurements_hint = QLabel("Introduce el ancho y el alto del espacio de una foto, ambos en la misma unidad.")
        measurements_hint.setObjectName("subtle")
        measurements_hint.setWordWrap(True)
        measurements_layout.addWidget(measurements_hint)
        controls = QHBoxLayout()
        width_label = QLabel("Ancho en la tira")
        controls.addWidget(width_label)
        self.ratio_width = QDoubleSpinBox()
        self.ratio_height = QDoubleSpinBox()
        self.ratio_width.setObjectName("strip_width")
        self.ratio_width.setAccessibleName("Ancho de la foto en la tira")
        self.ratio_height.setObjectName("strip_height")
        self.ratio_height.setAccessibleName("Alto de la foto en la tira")
        width_label.setBuddy(self.ratio_width)
        for spin in (self.ratio_width, self.ratio_height):
            spin.setRange(0.01, 100000)
            spin.setDecimals(2)
            spin.setValue(1)
            spin.setMinimumWidth(115)
            spin.setMaximumWidth(150)
            spin.setKeyboardTracking(False)
            spin.setToolTip("Medida del espacio de una foto en la tira. Se usa para calcular el recorte.")
            spin.valueChanged.connect(self.ratio_changed)
        controls.addWidget(self.ratio_width)
        controls.addWidget(QLabel("×"))
        height_label = QLabel("Alto en la tira")
        height_label.setBuddy(self.ratio_height)
        controls.addWidget(height_label)
        controls.addWidget(self.ratio_height)
        self.swap_button = QPushButton("⇄")
        self.swap_button.setToolTip("Intercambiar ancho y alto")
        self.swap_button.clicked.connect(self.swap_ratio)
        controls.addWidget(self.swap_button)
        controls.addStretch()
        measurements_layout.addLayout(controls)
        self.strip_summary = QLabel()
        self.strip_summary.setObjectName("subtle")
        self.strip_summary.setWordWrap(True)
        measurements_layout.addWidget(self.strip_summary)
        right.addWidget(measurements_panel)
        self.preview = Preview()
        right.addWidget(self.preview, 1)
        info_row = QHBoxLayout()
        self.dimensions = QLabel("Sin imágenes · recorte sin deformar ni ampliar")
        self.dimensions.setObjectName("subtle")
        info_row.addWidget(self.dimensions, 1)
        self.reset_button = QPushButton("Centrar encuadre")
        self.reset_button.clicked.connect(self.reset_center)
        info_row.addWidget(self.reset_button)
        right.addLayout(info_row)
        hint = QLabel("Arrastra el recuadro para mover el encuadre. La proporción se aplica a toda la lista.")
        hint.setWordWrap(True)
        hint.setObjectName("subtle")
        right.addWidget(hint)
        body.addLayout(right, 3)
        layout.addLayout(body, 1)

        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("Guardar como"))
        self.output_format = QComboBox()
        self.output_format.addItem("JPEG · calidad máxima", "JPEG")
        self.output_format.addItem("PNG · sin pérdida", "PNG")
        self.output_format.addItem("WebP · sin pérdida", "WEBP")
        self.output_format.setCurrentIndex(1)
        export_row.addWidget(self.output_format)
        self.folder_button = QPushButton("Carpeta de salida…")
        self.folder_button.clicked.connect(self.choose_folder)
        export_row.addWidget(self.folder_button)
        export_row.addStretch()
        self.export_button = QPushButton("Exportar todas")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_all)
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)
        self.folder_label = QLabel("Elige dónde guardar. Los archivos originales se conservan siempre.")
        self.folder_label.setObjectName("subtle")
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)
        footer = QHBoxLayout()
        self.status = QLabel("JPEG, PNG, WebP, HEIC, TIFF y BMP · imágenes fijas")
        self.status.setObjectName("subtle")
        footer.addWidget(self.status, 1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel_work)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        self.open_button = QPushButton("Abrir carpeta")
        self.open_button.clicked.connect(self.open_folder)
        self.open_button.hide()
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.refresh()
        self.set_ratio(950, 1250)

    @property
    def ratio(self):
        return self.ratio_width.value() / self.ratio_height.value()

    def refresh(self):
        count = self.files.count()
        self.count.setText(f"IMÁGENES · {count}")
        self.export_button.setText(f"Exportar {count} {'imagen' if count == 1 else 'imágenes'}")
        self.export_button.setEnabled(bool(count) and not self.busy)
        self.remove_button.setEnabled(bool(count) and not self.busy)
        self.reset_button.setEnabled(bool(count) and not self.busy)

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.add_button, self.files, self.preview, self.ratio_width,
                       self.ratio_height, self.swap_button, self.output_format, self.folder_button):
            widget.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        self.refresh()

    def choose_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Añadir imágenes", "",
            "Imágenes (*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff *.bmp)")
        self.add_paths(paths)

    def add_paths(self, paths):
        if self.busy:
            return
        candidates = []
        skipped = 0
        for value in paths:
            path = Path(value).resolve()
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                if path not in self.entries and path not in candidates:
                    candidates.append(path)
            else:
                skipped += 1
        if not candidates:
            self.status.setText("No hay imágenes nuevas compatibles para añadir.")
            return
        self.import_skipped = skipped
        self.import_total = len(candidates)
        self.import_added = 0
        self.set_busy(True)
        self.status.setText(f"Leyendo {len(candidates)} imágenes…")
        self.progress.setRange(0, 0)
        self.worker = ImportWorker(candidates, self)
        self.worker.loaded.connect(self.import_loaded)
        self.worker.completed.connect(self.import_complete)
        self.worker.start()

    def import_loaded(self, entry, thumbnail):
        self.entries[entry.path] = entry
        self.import_added += 1
        item = QListWidgetItem(QIcon(QPixmap.fromImage(thumbnail)),
                               f"{entry.path.name}\n{entry.size[0]} × {entry.size[1]} px")
        item.setData(Qt.ItemDataRole.UserRole, entry.path)
        item.setToolTip(str(entry.path))
        self.files.addItem(item)
        self.status.setText(f"Cargadas {self.import_added} de {self.import_total} imágenes…")

    def import_complete(self, errors):
        self.worker.wait()
        canceled = self.worker.isInterruptionRequested()
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        if self.files.currentItem() is None and self.files.count():
            self.files.setCurrentRow(0)
        suffix = " · carga cancelada" if canceled else ""
        if self.import_skipped:
            suffix += f" · {self.import_skipped} archivos no compatibles omitidos"
        self.status.setText(f"{self.files.count()} imágenes listas{suffix}.")
        self.show_errors("Algunas imágenes no se pudieron cargar", errors)

    def select_image(self, current, previous=None):
        entry = self.entries.get(current.data(Qt.ItemDataRole.UserRole)) if current else None
        self.preview.display(entry)
        self.update_dimensions()

    def remove_images(self):
        for item in self.files.selectedItems():
            self.entries.pop(item.data(Qt.ItemDataRole.UserRole), None)
            self.files.takeItem(self.files.row(item))
        self.select_image(self.files.currentItem())
        self.refresh()

    def set_ratio(self, width, height):
        for spin, value in ((self.ratio_width, width), (self.ratio_height, height)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self.ratio_changed()

    def ratio_changed(self):
        value = (self.ratio_width.value(), self.ratio_height.value())
        self.strip_summary.setText(
            f"Recorte {value[0]:g} × {value[1]:g} para todas las imágenes · conserva la resolución del recorte."
        )
        self.preview.ratio = self.ratio
        self.preview.update()
        self.update_dimensions()

    def swap_ratio(self):
        self.set_ratio(self.ratio_height.value(), self.ratio_width.value())

    def update_dimensions(self):
        entry = self.preview.entry
        if entry:
            box = crop_box(entry.size, self.ratio, entry.center)
            self.dimensions.setText(f"{entry.size[0]} × {entry.size[1]} → {box[2] - box[0]} × {box[3] - box[1]} px")
        else:
            self.dimensions.setText("Sin imágenes · recorte sin deformar ni ampliar")

    def reset_center(self):
        if self.preview.entry:
            self.preview.entry.center = (0.5, 0.5)
            self.preview.update()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para las imágenes recortadas",
                                                   str(self.destination or Path.home() / "Pictures"))
        if folder:
            self.destination = Path(folder)
            self.folder_label.setText(str(self.destination))

    def export_all(self):
        if self.busy or not self.entries:
            return
        if not self.destination:
            self.choose_folder()
        if not self.destination:
            return
        jobs = [Entry(e.path, e.size, e.center) for e in self.entries.values()]
        self.set_busy(True)
        self.open_button.hide()
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.status.setText("Exportando imágenes…")
        self.worker = ExportWorker(jobs, self.destination, self.ratio,
                                   self.output_format.currentData(), self)
        self.worker.progress.connect(self.export_progress)
        self.worker.completed.connect(self.export_complete)
        self.worker.start()

    def export_progress(self, count, name):
        self.progress.setValue(count)
        self.status.setText(f"Procesadas {count} de {self.progress.maximum()} · {name}")

    def export_complete(self, outputs, errors, canceled):
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.set_busy(False)
        prefix = "Exportación cancelada" if canceled else "Exportación terminada"
        self.status.setText(f"{prefix} · {len(outputs)} guardadas · {len(errors)} errores.")
        self.open_button.setVisible(bool(outputs))
        self.show_errors("Algunas imágenes no se pudieron exportar", errors)

    def cancel_work(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelando al terminar la imagen actual…")

    def open_folder(self):
        if self.destination:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.destination)))

    def show_errors(self, title, errors):
        if errors:
            dialog = QMessageBox(QMessageBox.Icon.Warning, title,
                                 f"{len(errors)} archivo(s) con problemas. Los demás se procesaron.", parent=self)
            dialog.setDetailedText("\n".join(errors))
            dialog.exec()

    def closeEvent(self, event):
        if self.busy or self.organizer.busy:
            QMessageBox.information(self, "Proceso en curso",
                                    "Cancela el proceso o espera a que termine antes de cerrar.")
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Recorta")
    app.setOrganizationName("Recorta")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
