"""Crea el icono vectorial de la app y lo empaqueta como ICNS."""
from pathlib import Path
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication
from PIL import Image

root = Path(__file__).resolve().parent.parent
assets = root / "assets"
assets.mkdir(exist_ok=True)
svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<rect x="48" y="48" width="928" height="928" rx="210" fill="#18222f"/>
<rect x="290" y="290" width="444" height="444" rx="20" fill="#2b514e"/>
<path d="M320 210V704H814 M210 320H704V814" stroke="#73e0b9" stroke-width="66" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
<circle cx="590" cy="430" r="40" fill="#e9f7f2"/>
<path d="M380 630L475 510L560 600L605 545L655 630Z" fill="#73e0b9"/>
</svg>'''
(assets / "icon.svg").write_text(svg)
app = QApplication([])
image = QImage(1024, 1024, QImage.Format.Format_ARGB32)
image.fill(0)
painter = QPainter(image)
QSvgRenderer(QByteArray(svg.encode())).render(painter)
painter.end()
image.save(str(assets / "icon.png"))
with Image.open(assets / "icon.png") as png:
    png.save(assets / "Recorta.icns")

