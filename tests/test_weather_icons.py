import math
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from weather_widget_v6 import weather_icons


def icon_frame(code, phase, day=True):
    image = QImage(144, 144, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    weather_icons.draw_weather_icon(painter, QRectF(8, 8, 128, 128), code, day, phase=phase)
    painter.end()
    return image


class IconMotionTests(unittest.TestCase):
    def test_cloud_really_occludes_sun_then_uncovers_it(self):
        def sun_pixels(image):
            return sum(
                color.alpha() > 100 and color.red() > 220 and color.green() > 140 and color.blue() < 185
                for y in range(image.height()) for x in range(image.width())
                for color in (image.pixelColor(x, y),)
            )

        revealed = sun_pixels(icon_frame(2, 0))
        covered = sun_pixels(icon_frame(2, math.pi))
        self.assertGreater(revealed, 500)
        self.assertLess(covered, revealed * .65)
        self.assertEqual(icon_frame(2, 0), icon_frame(2, 2 * math.pi))

    def test_sun_rotation_never_reverses_within_cycle(self):
        with patch.object(weather_icons, "_draw_sun", wraps=weather_icons._draw_sun) as sun:
            for phase in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                icon_frame(0, phase)
        angles = [call.args[4] for call in sun.call_args_list]
        self.assertEqual(angles, [0, 22.5, 45, 67.5])

    def test_motion_wrap_is_seamless_for_sun_and_cloud_day_and_night(self):
        for code in (0, 2):
            for day in (True, False):
                with self.subTest(code=code, day=day):
                    self.assertEqual(icon_frame(code, 0, day), icon_frame(code, 2 * math.pi, day))

    def test_cloud_crossing_stays_inside_icon_area(self):
        for step in range(16):
            image = icon_frame(2, step * math.pi / 8)
            for x in range(image.width()):
                self.assertEqual(image.pixelColor(x, 7).alpha(), 0)
                self.assertEqual(image.pixelColor(x, 136).alpha(), 0)
            for y in range(image.height()):
                self.assertEqual(image.pixelColor(7, y).alpha(), 0)
                self.assertEqual(image.pixelColor(136, y).alpha(), 0)
