import tempfile
import unittest
from pathlib import Path

from PIL import Image

from crop_core import crop_box, export_image, inspect_image


class CropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "salida"

    def tearDown(self):
        self.temp.cleanup()

    def test_maximum_rectangle_and_edges(self):
        self.assertEqual(crop_box((1600, 900), 1), (350, 0, 1250, 900))
        self.assertEqual(crop_box((1600, 900), 1, (0, 0)), (0, 0, 900, 900))
        self.assertEqual(crop_box((1600, 900), 1, (1, 1)), (700, 0, 1600, 900))
        for size in ((401, 803), (1920, 1080), (1, 1), (40, 30)):
            for ratio in (16 / 9, 9 / 16, 4 / 5, 1, 10000, 0.00001):
                for center in ((0, 0), (0.5, 0.5), (1, 1), (-4, 3)):
                    l, t, r, b = crop_box(size, ratio, center)
                    self.assertTrue(0 <= l < r <= size[0])
                    self.assertTrue(0 <= t < b <= size[1])
                    self.assertTrue(r - l == size[0] or b - t == size[1])

    def test_exif_orientation_matches_preview_and_output(self):
        source = self.root / "camara.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (120, 80), "red").save(source, exif=exif)
        size, thumb = inspect_image(source)
        self.assertEqual(size, (80, 120))
        self.assertEqual(thumb.size, (80, 120))
        target, dimensions = export_image(source, self.output, 4 / 5, (0.5, 0.5), "JPEG")
        self.assertEqual(dimensions, (80, 100))
        with Image.open(target) as saved:
            self.assertIsNone(saved.getexif().get(274))

    def test_transparency_png_and_white_background_jpeg(self):
        source = self.root / "transparente.png"
        Image.new("RGBA", (100, 60), (255, 0, 0, 0)).save(source)
        target, _ = export_image(source, self.output, 1, (0.5, 0.5), "PNG")
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((0, 0)), (255, 0, 0, 0))
        target, _ = export_image(source, self.output, 1, (0.5, 0.5), "JPEG")
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((0, 0)), (255, 255, 255))

    def test_preserve_original_and_existing_outputs(self):
        source = self.root / "foto.png"
        Image.new("RGB", (90, 60), "blue").save(source)
        before = source.read_bytes()
        first, _ = export_image(source, self.root, 1, (0.5, 0.5), "PNG")
        exported = first.read_bytes()
        second, _ = export_image(source, self.root, 1, (0.5, 0.5), "PNG")
        self.assertNotEqual(first, second)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(first.read_bytes(), exported)

    def test_selected_position_controls_pixels(self):
        source = self.root / "mitades.png"
        image = Image.new("RGB", (200, 100), "red")
        image.paste("blue", (100, 0, 200, 100))
        image.save(source)
        target, _ = export_image(source, self.output, 1, (1, 0.5), "PNG")
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((0, 0)), (0, 0, 255))
            self.assertEqual(saved.size, (100, 100))

    def test_webp_and_changed_image_detection(self):
        source = self.root / "foto.png"
        Image.new("RGB", (160, 90), "green").save(source)
        target, size = export_image(source, self.output, 16 / 9, (0.5, 0.5), "WEBP")
        self.assertEqual(size, (160, 90))
        with Image.open(target) as image:
            self.assertEqual(image.format, "WEBP")
        with self.assertRaisesRegex(ValueError, "cambió"):
            export_image(source, self.output, 1, (0.5, 0.5), "PNG", expected_size=(90, 160))

    def test_invalid_input_does_not_create_output(self):
        source = self.root / "rota.png"
        source.write_text("no soy una imagen")
        with self.assertRaises(Exception):
            export_image(source, self.output, 1, (0.5, 0.5), "PNG")
        self.assertEqual(list(self.output.iterdir()), [])
        for ratio in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                crop_box((100, 100), ratio)

    def test_lossless_exports_preserve_crop_pixels(self):
        source = self.root / "detalle.png"
        original = Image.new("RGBA", (160, 90))
        original.putdata([(x % 256, (x * 17) % 256, (x * 43) % 256, x % 256)
                          for x in range(160 * 90)])
        original.save(source)
        expected = original.crop(crop_box(original.size, 950 / 1250))
        for fmt in ("PNG", "WEBP"):
            target, size = export_image(source, self.output, 950 / 1250, (0.5, 0.5), fmt)
            with Image.open(target) as saved:
                self.assertEqual(size, expected.size)
                self.assertEqual(saved.convert("RGBA").tobytes(), expected.tobytes())

    def test_png_preserves_16_bit_grayscale(self):
        source = self.root / "profundidad.png"
        original = Image.new("I;16", (100, 60))
        original.putpixel((50, 30), 32000)
        original.save(source)
        target, _ = export_image(source, self.output, 1, (0.5, 0.5), "PNG")
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((30, 30)), 32000)


if __name__ == "__main__":
    unittest.main()

