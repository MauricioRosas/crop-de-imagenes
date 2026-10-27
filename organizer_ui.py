"""Apartado para revisar grupos y guardar tiras y fotos con nombres ordenados."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QImage, QPixmap, QDesktopServices, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QLineEdit,
    QComboBox, QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox, QProgressBar, QMenu, QSplitter,
)

from crop_core import EXTENSIONS, open_image
from organize_core import StripGroup, filename_time, time_key, suggest_groups, make_plan, copy_plan


class CopyWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, plan, destination, parent=None):
        super().__init__(parent)
        self.plan, self.destination = plan, destination

    def run(self):
        try:
            result = copy_plan(self.plan, self.destination, self.progress.emit,
                               self.isInterruptionRequested)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class PhotoPreview(QLabel):
    def __init__(self):
        super().__init__("Selecciona una tira o foto para revisarla.")
        self.picture = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(210, 250)
        self.setWordWrap(True)
        self.setStyleSheet("background: #111923; border-radius: 8px; color: #a7b5c5;")

    def display(self, path):
        self.picture = None
        self.clear()
        if path:
            try:
                with open_image(path) as image:
                    image.thumbnail((1000, 1200))
                    rgba = image.convert("RGBA")
                    qimage = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                                    QImage.Format.Format_RGBA8888).copy()
                    self.picture = QPixmap.fromImage(qimage)
            except Exception as error:
                self.setText(f"No se pudo abrir la vista previa.\n{error}")
        else:
            self.setText("Selecciona una tira o foto para revisarla.")
        self.rescale()

    def rescale(self):
        if self.picture:
            self.setPixmap(self.picture.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rescale()


class Organizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.strips, self.photos = [], []
        self.groups, self.unassigned = [], []
        self.plan = []
        self.busy = False
        self.worker = None
        self.manual_edits = False
        self.output = None
        self.controls = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("Ordenar y renombrar")
        title.setObjectName("title")
        layout.addWidget(title)
        hint = QLabel("Cada grupo saldrá así: tira → sus fotos → siguiente tira → sus fotos. "
                      "La fecha y hora del nombre permiten proponer las asociaciones.")
        hint.setObjectName("subtle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        load_row = QHBoxLayout()
        for text, kind in (("＋ Añadir tiras", "strip"), ("＋ Añadir fotos", "photo")):
            button = QPushButton(text)
            menu = QMenu(button)
            menu.addAction("Seleccionar archivos…", lambda k=kind: self.choose_files(k))
            menu.addAction("Seleccionar carpeta…", lambda k=kind: self.choose_directory(k))
            button.setMenu(menu)
            self.controls.append(button)
            load_row.addWidget(button)
        load_row.addStretch()
        self.counts = QLabel("0 tiras · 0 fotos")
        load_row.addWidget(self.counts)
        layout.addLayout(load_row)

        rules = QHBoxLayout()
        rules.addWidget(QLabel("Fotos por tira"))
        self.photos_count = QSpinBox()
        self.photos_count.setRange(1, 20)
        self.photos_count.setValue(2)
        rules.addWidget(self.photos_count)
        rules.addWidget(QLabel("Buscar en los últimos"))
        self.time_margin = QSpinBox()
        self.time_margin.setRange(1, 3600)
        self.time_margin.setValue(180)
        self.time_margin.setSuffix(" s")
        rules.addWidget(self.time_margin)
        self.group_button = QPushButton("Agrupar por fecha")
        self.group_button.setToolTip("Vuelve a proponer todos los grupos con estas reglas; reemplaza los ajustes manuales.")
        self.group_button.clicked.connect(self.regroup)
        rules.addWidget(self.group_button)
        rules.addStretch()
        layout.addLayout(rules)
        rules_hint = QLabel("Se proponen las últimas fotos anteriores a cada tira, del mismo día. "
                            "Revisa las asociaciones; puedes corregirlas debajo de la lista.")
        rules_hint.setObjectName("subtle")
        rules_hint.setWordWrap(True)
        layout.addWidget(rules_hint)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tira y sus fotos", "Fecha y hora", "Nombre de salida", "Revisión"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSortingEnabled(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setColumnWidth(0, 255)
        self.tree.setColumnWidth(1, 135)
        self.tree.setColumnWidth(2, 270)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.setMinimumWidth(510)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        split.addWidget(self.tree)
        preview_area = QWidget()
        preview_layout = QVBoxLayout(preview_area)
        preview_layout.setContentsMargins(8, 0, 0, 0)
        self.preview = PhotoPreview()
        preview_layout.addWidget(self.preview, 1)
        self.preview_name = QLabel()
        self.preview_name.setObjectName("subtle")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)
        split.addWidget(preview_area)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)

        corrections = QHBoxLayout()
        self.move_up = QPushButton("↑ Subir")
        self.move_down = QPushButton("↓ Bajar")
        self.move_up.clicked.connect(lambda: self.move_selected(-1))
        self.move_down.clicked.connect(lambda: self.move_selected(1))
        corrections.addWidget(self.move_up)
        corrections.addWidget(self.move_down)
        corrections.addWidget(QLabel("Tira de la foto:"))
        self.assignment = QComboBox()
        self.assignment.setMinimumWidth(175)
        corrections.addWidget(self.assignment, 1)
        self.assign_button = QPushButton("Asignar")
        self.assign_button.clicked.connect(self.assign_selected)
        corrections.addWidget(self.assign_button)
        self.unassign_button = QPushButton("Separar")
        self.unassign_button.clicked.connect(self.unassign_selected)
        corrections.addWidget(self.unassign_button)
        self.remove_button = QPushButton("Quitar de lista")
        self.remove_button.clicked.connect(self.remove_selected)
        corrections.addWidget(self.remove_button)
        layout.addLayout(corrections)
        names = QHBoxLayout()
        names.addWidget(QLabel("Prefijo opcional"))
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("Ej. Festival")
        self.prefix.setMaxLength(50)
        self.prefix.textChanged.connect(self.refresh_tree)
        names.addWidget(self.prefix)
        names.addWidget(QLabel("Empezar en"))
        self.start = QSpinBox()
        self.start.setRange(1, 999999)
        self.start.valueChanged.connect(self.refresh_tree)
        names.addWidget(self.start)
        names.addStretch()
        self.save_button = QPushButton("Guardar copias ordenadas…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.choose_output)
        names.addWidget(self.save_button)
        layout.addLayout(names)
        output_hint = QLabel("Se crea una carpeta con copias idénticas y nombres numerados. "
                             "Para ver este orden en Finder, ordena por Nombre.")
        output_hint.setObjectName("subtle")
        output_hint.setWordWrap(True)
        layout.addWidget(output_hint)
        footer = QHBoxLayout()
        self.status = QLabel("Carga las tiras y las fotos para preparar el orden.")
        self.status.setWordWrap(True)
        self.status.setObjectName("subtle")
        footer.addWidget(self.status, 1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        self.open_button = QPushButton("Abrir resultado")
        self.open_button.clicked.connect(self.open_output)
        self.open_button.hide()
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.controls.extend([self.photos_count, self.time_margin, self.group_button, self.tree,
                              self.move_up, self.move_down, self.assignment, self.assign_button,
                              self.unassign_button, self.remove_button, self.prefix, self.start])
        self.refresh_tree()

    def choose_files(self, kind):
        paths, _ = QFileDialog.getOpenFileNames(self, "Añadir tiras" if kind == "strip" else "Añadir fotos", "",
            "Imágenes (*.jpg *.jpeg *.png *.webp *.heic *.heif *.tif *.tiff *.bmp)")
        self.add_paths(paths, kind)

    def choose_directory(self, kind):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de tiras" if kind == "strip" else "Carpeta de fotos")
        if folder:
            self.add_paths([p for p in Path(folder).iterdir() if p.is_file()], kind)

    def add_paths(self, paths, kind):
        if self.busy:
            return
        added, skipped = [], 0
        for value in paths:
            path = Path(value).resolve()
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                skipped += 1
            elif path not in self.strips and path not in self.photos:
                added.append(path)
                (self.strips if kind == "strip" else self.photos).append(path)
        if self.manual_edits:
            if kind == "strip":
                self.groups.extend(StripGroup(p) for p in sorted(added, key=time_key))
            else:
                self.unassigned.extend(sorted(added, key=time_key))
            self.refresh_tree()
            self.status.setText("Archivos añadidos. Se conservaron tus ajustes; puedes asignar los nuevos manualmente o volver a agrupar.")
        else:
            self.regroup()
        if skipped:
            self.status.setText(self.status.text() + f" · {skipped} archivos no compatibles omitidos")

    def regroup(self):
        self.groups, self.unassigned = suggest_groups(self.strips, self.photos,
                                                      self.photos_count.value(), self.time_margin.value())
        self.manual_edits = False
        self.refresh_tree()
        self.status.setText(f"Propuesta por fecha lista · {len(self.unassigned)} fotos sin asignar. Revisa los grupos antes de guardar.")

    def refresh_tree(self):
        selected = self.tree.currentItem()
        selected_data = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        self.plan = make_plan(self.groups, self.unassigned, self.prefix.text(), self.start.value())
        names = {row.source: row.filename for row in self.plan}
        self.tree.blockSignals(True)
        self.tree.clear()
        self.assignment.clear()
        restore = None

        def item_for(path, kind, parent=None):
            nonlocal restore
            stamp = filename_time(path)
            item = QTreeWidgetItem([path.name, stamp.strftime("%d/%m/%Y %H:%M:%S") if stamp else "Sin fecha", names[path], ""])
            item.setData(0, Qt.ItemDataRole.UserRole, (kind, path))
            item.setToolTip(0, str(path))
            item.setToolTip(2, names[path])
            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            if selected_data == (kind, path):
                restore = item
            return item

        for number, group in enumerate(self.groups, 1):
            stamp = filename_time(group.strip)
            self.assignment.addItem(f"{number:03d} · {stamp.strftime('%d/%m %H:%M:%S') if stamp else group.strip.name}", group.strip)
            parent = item_for(group.strip, "strip")
            parent.setText(0, f"Tira {number:03d} · {group.strip.name}")
            parent.setForeground(0, QColor("#73e0b9"))
            notes = list(group.notes)
            if len(group.photos) != self.photos_count.value():
                notes.insert(0, f"Revisar: {len(group.photos)} de {self.photos_count.value()} fotos")
            else:
                notes.insert(0, f"{len(group.photos)} fotos")
            parent.setText(3, " · ".join(notes))
            parent.setToolTip(3, parent.text(3))
            for photo in group.photos:
                item_for(photo, "photo", parent)
            parent.setExpanded(True)
        if self.unassigned:
            orphan = QTreeWidgetItem([f"Sin asignar · {len(self.unassigned)} fotos", "", "Se guardarán al final", "Asignación manual disponible"])
            orphan.setData(0, Qt.ItemDataRole.UserRole, ("unassigned", None))
            orphan.setForeground(0, QColor("#f1c27d"))
            self.tree.addTopLevelItem(orphan)
            for photo in self.unassigned:
                child = item_for(photo, "photo", orphan)
                child.setText(3, "Sin tira asignada")
            orphan.setExpanded(True)
        if restore:
            self.tree.setCurrentItem(restore)
        self.tree.blockSignals(False)
        self.counts.setText(f"{len(self.strips)} tiras · {len(self.photos)} fotos · {len(self.unassigned)} sin asignar")
        self.save_button.setEnabled(bool(self.plan) and not self.busy)
        self.selection_changed()

    def selection_changed(self):
        current = self.tree.currentItem()
        data = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        path = data[1] if data else None
        if getattr(self, "preview_path", None) != path:
            self.preview_path = path
            self.preview.display(path)
        self.preview_name.setText(path.name if path else "")
        has_photos = bool(self.selected_photos())
        self.assign_button.setEnabled(has_photos and bool(self.groups) and not self.busy)
        self.unassign_button.setEnabled(has_photos and not self.busy)
        self.remove_button.setEnabled(bool(self.tree.selectedItems()) and not self.busy)
        can_move = bool(data and data[0] != "unassigned" and len(self.tree.selectedItems()) == 1)
        self.move_up.setEnabled(can_move and not self.busy)
        self.move_down.setEnabled(can_move and not self.busy)
        if data and data[0] == "strip":
            self.assignment.setCurrentIndex(self.assignment.findData(path))

    def selected_photos(self):
        return [data[1] for item in self.tree.selectedItems()
                if (data := item.data(0, Qt.ItemDataRole.UserRole)) and data[0] == "photo"]

    def detach_photo(self, path):
        for group in self.groups:
            if path in group.photos:
                group.photos.remove(path)
        if path in self.unassigned:
            self.unassigned.remove(path)

    def assign_selected(self):
        target = self.assignment.currentData()
        group = next((g for g in self.groups if g.strip == target), None)
        if group:
            for path in self.selected_photos():
                self.detach_photo(path)
                group.photos.append(path)
            self.manual_edits = True
            self.refresh_tree()

    def unassign_selected(self):
        for path in self.selected_photos():
            self.detach_photo(path)
            self.unassigned.append(path)
        self.manual_edits = True
        self.refresh_tree()

    def move_selected(self, direction):
        current = self.tree.currentItem()
        if not current:
            return
        kind, path = current.data(0, Qt.ItemDataRole.UserRole)
        if kind == "strip":
            values = self.groups
            index = next(i for i, group in enumerate(values) if group.strip == path)
        elif kind == "photo":
            values = next((g.photos for g in self.groups if path in g.photos), self.unassigned)
            index = values.index(path)
        else:
            return
        target = index + direction
        if 0 <= target < len(values):
            values[index], values[target] = values[target], values[index]
            self.manual_edits = True
            self.refresh_tree()

    def remove_selected(self):
        selected = [item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()]
        for kind, path in selected:
            if kind == "strip":
                group = next(g for g in self.groups if g.strip == path)
                self.unassigned.extend(group.photos)
                self.groups.remove(group)
                self.strips.remove(path)
            elif kind == "photo":
                self.detach_photo(path)
                self.photos.remove(path)
        self.manual_edits = True
        self.refresh_tree()

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Dónde crear la carpeta de copias ordenadas")
        if folder:
            self.save_to(folder)

    def save_to(self, folder):
        if self.busy or not self.plan:
            return
        self.busy = True
        for control in self.controls:
            control.setEnabled(False)
        self.save_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.open_button.hide()
        self.progress.setRange(0, len(self.plan))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("Copiando los archivos con sus nuevos nombres…")
        self.worker = CopyWorker(list(self.plan), Path(folder), self)
        self.worker.progress.connect(self.copy_progress)
        self.worker.completed.connect(self.copy_complete)
        self.worker.failed.connect(self.copy_failed)
        self.worker.start()

    def copy_progress(self, count, name):
        self.progress.setValue(count)
        self.status.setText(f"Copiados {count} de {len(self.plan)} · {name}")

    def finish_work(self):
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self.busy = False
        for control in self.controls:
            control.setEnabled(True)
        self.save_button.setEnabled(bool(self.plan))
        self.cancel_button.hide()
        self.progress.hide()
        self.selection_changed()

    def copy_complete(self, result):
        self.output, outputs, errors, stopped = result
        self.finish_work()
        self.open_button.show()
        self.status.setText(f"{'Copia cancelada' if stopped else 'Listo'} · {len(outputs)} archivos guardados · {len(errors)} errores. "
                            f"{self.output}")
        if errors:
            dialog = QMessageBox(QMessageBox.Icon.Warning, "Archivos con problemas",
                                 f"{len(errors)} archivos no se pudieron copiar.", parent=self)
            dialog.setDetailedText("\n".join(errors))
            dialog.exec()

    def copy_failed(self, error):
        self.finish_work()
        self.status.setText(f"No se pudo completar la copia: {error}")

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelando…")

    def open_output(self):
        if self.output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output)))
