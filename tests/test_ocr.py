"""Unit tests for OCR service and Vietnamese text matching."""
import unittest
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from bot.cv.ocr_service import OCRService, normalize_text, remove_vietnamese_tones


class TestOCRService(unittest.TestCase):
    def test_text_normalization(self):
        self.assertEqual(normalize_text("  BẮT ĐẦU   KHIÊU CHIẾN  "), "bắt đầu khiêu chiến")
        self.assertEqual(remove_vietnamese_tones("sức mạnh khai phá"), "suc manh khai pha")
        self.assertEqual(remove_vietnamese_tones("Đài hoa nhân tạo"), "Dai hoa nhan tao")

    def test_synthetic_ocr_detection(self):
        # Create a synthetic image with Vietnamese text
        img = Image.new("RGB", (600, 200), color=(20, 20, 30))
        draw = ImageDraw.Draw(img)
        # Use default PIL font or simple text
        draw.text((50, 40), "Bat Dau Khieu Chien", fill=(255, 255, 255))
        draw.text((50, 120), "Suc Manh Khai Pha", fill=(255, 255, 255))

        cv_img = np.array(img)

        ocr = OCRService()
        result = ocr.find_text(cv_img, "Bat Dau Khieu Chien", min_score=0.4)
        self.assertIsNotNone(result, "OCR should find 'Bat Dau Khieu Chien'")
        if result:
            self.assertTrue(result.box.x1 >= 0)
            self.assertTrue(result.box.y1 >= 0)

        result_fuel = ocr.find_text(cv_img, "Suc Manh", min_score=0.4)
        self.assertIsNotNone(result_fuel, "OCR should find 'Suc Manh'")


if __name__ == "__main__":
    unittest.main()
