"""Unit tests for coordinate system and geometry."""
import unittest
from bot.core.coordinates import Point, BoundingBox, CoordinateSystem, HSRZones


class TestCoordinates(unittest.TestCase):
    def test_point(self):
        p = Point(10.4, 20.6)
        self.assertEqual(p.to_int_tuple(), (10, 21))

    def test_bounding_box(self):
        box = BoundingBox(10.0, 20.0, 50.0, 80.0)
        self.assertEqual(box.width, 40.0)
        self.assertEqual(box.height, 60.0)
        self.assertEqual(box.center, Point(30.0, 50.0))
        self.assertTrue(box.contains(Point(30.0, 50.0)))
        self.assertFalse(box.contains(Point(5.0, 10.0)))

    def test_coordinate_system_conversion(self):
        cs = CoordinateSystem(2000, 1000)
        norm_p = Point(0.5, 0.25)
        abs_p = cs.norm_to_abs_point(norm_p)
        self.assertEqual(abs_p.x, 1000.0)
        self.assertEqual(abs_p.y, 250.0)

        converted_back = cs.abs_to_norm_point(abs_p)
        self.assertAlmostEqual(converted_back.x, 0.5)
        self.assertAlmostEqual(converted_back.y, 0.25)

    def test_hsr_zones_defined(self):
        self.assertTrue(0.0 <= HSRZones.DIALOGUE_SAFE_TAP.x <= 1.0)
        self.assertTrue(0.0 <= HSRZones.DIALOGUE_SAFE_TAP.y <= 1.0)
        self.assertTrue(0.0 <= HSRZones.BATTLE_AUTO_TOGGLE.x1 <= 1.0)


if __name__ == "__main__":
    unittest.main()
