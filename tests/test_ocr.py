"""Unit tests for OCR service and Vietnamese text matching with real game images."""
import unittest
import os
import cv2
import numpy as np
from PIL import Image, ImageDraw
from bot.cv.ocr_service import OCRService, normalize_text, remove_vietnamese_tones


class TestOCRService(unittest.TestCase):
    def setUp(self):
        self.ocr = OCRService()
        self.img1_path = "/Users/hoangson/.gemini/antigravity/brain/713e9e95-1cd0-4b93-8f33-b38b09fac9bb/.user_uploaded/media_1789194683106.png"
        self.img2_path = "/Users/hoangson/.gemini/antigravity/brain/713e9e95-1cd0-4b93-8f33-b38b09fac9bb/.user_uploaded/media_1789194755276.png"

    def test_text_normalization(self):
        self.assertEqual(normalize_text("  BẮT ĐẦU   KHIÊU CHIẾN  "), "bắt đầu khiêu chiến")
        self.assertEqual(remove_vietnamese_tones("sức mạnh khai phá"), "suc manh khai pha")
        self.assertEqual(remove_vietnamese_tones("Đài hoa nhân tạo"), "Dai hoa nhan tao")
        self.assertEqual(remove_vietnamese_tones("Hư Ảnh Ngưng Đọng"), "Hu Anh Ngung Dong")

    def test_power_and_fuel_extraction(self):
        if os.path.exists(self.img1_path):
            img = cv2.imread(self.img1_path)
            power = self.ocr.extract_trailblaze_power(img)
            self.assertIsNotNone(power)
            self.assertEqual(power, (164, 300))

            fuel = self.ocr.extract_fuel_count(img)
            self.assertIsNotNone(fuel)
            self.assertEqual(fuel, 11)

    def test_action_button_on_row(self):
        if os.path.exists(self.img1_path):
            img = cv2.imread(self.img1_path)
            btn = self.ocr.find_action_button_on_row(img, "De Xuat Di Vat Hang Dong", tolerance_y=85.0)
            self.assertIsNotNone(btn)
            self.assertIn("Vao", btn.text)

        if os.path.exists(self.img2_path):
            img2 = cv2.imread(self.img2_path)
            btn2 = self.ocr.find_action_button_on_row(img2, "Nu Hoa Hoi Uc", tolerance_y=85.0)
            self.assertIsNotNone(btn2)
            self.assertIn("Vao", btn2.text)


if __name__ == "__main__":
    unittest.main()
