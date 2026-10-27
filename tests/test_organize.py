import csv
import hashlib
from pathlib import Path
import tempfile
import unittest

from organize_core import filename_time, suggest_groups, make_plan, copy_plan


class OrganizeTests(unittest.TestCase):
    def setUp(self):
        self.strips = [Path("20261025_101004_994_1x.jpg"), Path("20261025_101141_899_1x.jpg")]
        self.photos = [Path(f"IMG_{number}_20261025_{stamp}_recortada.png") for number, stamp in
                       ((8614, "100948"), (8615, "101001"), (8616, "101125"), (8617, "101138"))]

    def test_user_examples_and_shuffled_input(self):
        groups, left = suggest_groups(self.strips[::-1], self.photos[::-1])
        self.assertFalse(left)
        self.assertEqual(groups[0].photos, self.photos[:2])
        self.assertEqual(groups[1].photos, self.photos[2:])
        plan = make_plan(groups)
        self.assertEqual([row.source for row in plan],
                         [self.strips[0], *self.photos[:2], self.strips[1], *self.photos[2:]])
        self.assertEqual([row.filename for row in plan], sorted(row.filename for row in plan))

    def test_dates_milliseconds_and_invalid_dates(self):
        self.assertEqual(filename_time(self.strips[0]).microsecond, 994000)
        self.assertEqual(filename_time(Path("IMG_8612_20261024_124413_recortada_2.png")).day, 24)
        self.assertIsNone(filename_time(Path("20261350_101010.png")))
        self.assertIsNone(filename_time(Path("sin_fecha.jpg")))

    def test_no_matching_future_distant_or_other_day(self):
        others = [Path("IMG_9000_20261025_101005.png"), Path("IMG_9001_20261025_090000.png"),
                  Path("IMG_9002_20261024_100959.png"), Path("sin_fecha.png")]
        groups, left = suggest_groups(self.strips[:1], self.photos[:2] + others)
        self.assertEqual(groups[0].photos, self.photos[:2])
        self.assertEqual(set(left), set(others))

    def test_candidates_and_unmatched_are_visible(self):
        earlier = Path("IMG_8613_20261025_100940.png")
        groups, left = suggest_groups(self.strips[:1], [earlier, *self.photos[:2]])
        self.assertEqual(groups[0].photos, self.photos[:2])
        self.assertEqual(left, [earlier])
        self.assertTrue(groups[0].notes)
        self.assertEqual(make_plan(groups, left)[-1].kind, "Sin_asignar")

    def test_manual_edits_numbering_prefix_and_duplicate_detection(self):
        groups, _ = suggest_groups(self.strips, self.photos)
        groups.reverse()
        groups[0].photos.reverse()
        plan = make_plan(groups, prefix="Festival/2026", start=12)
        self.assertTrue(plan[0].filename.startswith("Festival_2026_000012_Tira_"))
        self.assertEqual(plan[1].source, self.photos[-1])
        groups[1].photos.append(self.photos[-1])
        with self.assertRaisesRegex(ValueError, "más de una vez"):
            make_plan(groups)

    def test_copies_identical_originals_intact_and_repeat_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strips, photos = [], []
            for source, collection in [(p, strips) for p in self.strips] + [(p, photos) for p in self.photos]:
                path = root / source
                path.write_bytes(b"original bytes\0" + path.name.encode() * 1000)
                collection.append(path)
            before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in strips + photos}
            groups, left = suggest_groups(strips, photos)
            plan = make_plan(groups, left)
            output, copied, errors, stopped = copy_plan(plan, root)
            self.assertEqual(len(copied), 6)
            self.assertFalse(errors)
            self.assertFalse(stopped)
            for item in plan:
                self.assertEqual(hashlib.sha256((output / item.filename).read_bytes()).hexdigest(), before[item.source])
                self.assertEqual(hashlib.sha256(item.source.read_bytes()).hexdigest(), before[item.source])
            second, _, _, _ = copy_plan(plan, root)
            self.assertNotEqual(second, output)
            with (output / "orden.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0]["tipo"], "Tira")

    def test_copy_error_continues_and_cancellation_keeps_completed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strips = []
            for name in self.strips:
                path = root / name
                path.write_bytes(b"data")
                strips.append(path)
            groups, _ = suggest_groups(strips, [])
            plan = make_plan(groups)
            strips[0].unlink()
            _, outputs, errors, _ = copy_plan(plan, root)
            self.assertEqual(len(outputs), 1)
            self.assertEqual(len(errors), 1)
            strips[0].write_bytes(b"restored")
            copied_count = []
            output, outputs, errors, stopped = copy_plan(plan, root,
                progress=lambda number, name: copied_count.append(number), cancelled=lambda: bool(copied_count))
            self.assertEqual(len(outputs), 1)
            self.assertTrue(stopped)
            self.assertEqual(len(list(output.glob("*.jpg"))), 1)


if __name__ == "__main__":
    unittest.main()
