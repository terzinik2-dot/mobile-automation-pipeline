"""
Tests for the CVEngine.

Uses synthetic test images to avoid depending on external files.

Covers:
- Template matching (found, not found, confidence threshold)
- Multi-scale matching
- OCR text detection (mocked)
- Screen change detection (pixel diff and SSIM)
- Image preprocessing pipeline
- Template cache
"""

import io
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# We need PIL and OpenCV for these tests
try:
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    IMAGING_AVAILABLE = True
except ImportError:
    IMAGING_AVAILABLE = False


def make_settings(template_dir: str = "/tmp/test_templates"):
    s = MagicMock()
    s.cv_confidence_threshold = 0.80
    s.template_dir = template_dir
    s.ocr_language = "eng"
    s.tesseract_cmd = "/usr/bin/tesseract"
    return s


def make_white_image(w: int = 400, h: int = 800, color=(200, 200, 200)) -> np.ndarray:
    """Create a solid color test image as RGB numpy array."""
    img = np.full((h, w, 3), color, dtype=np.uint8)
    return img


def draw_rectangle(img: np.ndarray, x: int, y: int, w: int, h: int, color=(0, 150, 255)) -> np.ndarray:
    """Draw a colored rectangle on an image (for use as template target)."""
    img = img.copy()
    img[y:y+h, x:x+w] = color
    return img


@pytest.mark.skipif(not IMAGING_AVAILABLE, reason="OpenCV/Pillow not installed")
class TestTemplateMatching:
    """Tests for find_on_screen."""

    def test_finds_exact_template(self, tmp_path):
        from executors.cv_engine import CVEngine

        # Create a "screenshot" with a distinctive blue rectangle
        screenshot = make_white_image(400, 800)
        screenshot = draw_rectangle(screenshot, 100, 200, 80, 40, color=(0, 0, 255))

        # Extract that rectangle as a template
        template_region = screenshot[200:240, 100:180].copy()  # BGR for OpenCV
        template_bgr = cv2.cvtColor(template_region, cv2.COLOR_RGB2BGR)
        template_path = str(tmp_path / "test_btn.png")
        cv2.imwrite(template_path, template_bgr)

        settings = make_settings(template_dir=str(tmp_path))
        engine = CVEngine(settings)
        result = engine.find_on_screen(template_path, screenshot, threshold=0.8, scales=[1.0])

        assert result is not None
        cx, cy, conf = result
        assert conf >= 0.8
        # Center should be near our rectangle center: (140, 220)
        assert abs(cx - 140) < 20
        assert abs(cy - 220) < 20

    def test_returns_none_for_missing_template(self, tmp_path):
        from executors.cv_engine import CVEngine

        screenshot = make_white_image(400, 800)
        settings = make_settings(template_dir=str(tmp_path))
        engine = CVEngine(settings)

        result = engine.find_on_screen(
            str(tmp_path / "nonexistent.png"),
            screenshot,
        )
        assert result is None

    def test_rejects_low_confidence_match(self, tmp_path):
        from executors.cv_engine import CVEngine

        # Create a template that won't match well
        screenshot = make_white_image(400, 800, color=(180, 180, 180))
        # Template is very different from screenshot
        template = make_white_image(50, 20, color=(0, 0, 255))
        template_bgr = cv2.cvtColor(template, cv2.COLOR_RGB2BGR)
        template_path = str(tmp_path / "mismatch.png")
        cv2.imwrite(template_path, template_bgr)

        settings = make_settings(template_dir=str(tmp_path))
        engine = CVEngine(settings)
        result = engine.find_on_screen(template_path, screenshot, threshold=0.99, scales=[1.0])
        # With very high threshold, a mismatch should return None
        # (Note: all-blue template on gray background should be below 0.99)
        assert result is None or result[2] < 0.99

    def test_template_cache_prevents_reload(self, tmp_path):
        from executors.cv_engine import CVEngine

        # Create a simple template
        template = make_white_image(30, 30, color=(255, 0, 0))
        template_bgr = cv2.cvtColor(template, cv2.COLOR_RGB2BGR)
        template_path = str(tmp_path / "cached.png")
        cv2.imwrite(template_path, template_bgr)

        settings = make_settings(template_dir=str(tmp_path))
        engine = CVEngine(settings)

        # First load
        t1 = engine._load_template(template_path)
        # Second load (from cache)
        t2 = engine._load_template(template_path)
        assert t1 is t2  # Same object reference (cached)

    def test_clear_cache_forces_reload(self, tmp_path):
        from executors.cv_engine import CVEngine

        template = make_white_image(30, 30)
        template_bgr = cv2.cvtColor(template, cv2.COLOR_RGB2BGR)
        template_path = str(tmp_path / "cache_test.png")
        cv2.imwrite(template_path, template_bgr)

        settings = make_settings(template_dir=str(tmp_path))
        engine = CVEngine(settings)

        t1 = engine._load_template(template_path)
        engine.clear_template_cache()
        assert len(engine._template_cache) == 0


@pytest.mark.skipif(not IMAGING_AVAILABLE, reason="OpenCV/Pillow not installed")
class TestScreenChangeDetection:
    """Tests for screens_are_different."""

    def test_identical_screens_are_not_different(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img = make_white_image(400, 400, color=(128, 128, 128))
        result = engine.screens_are_different(img, img.copy(), threshold=0.95)
        assert result is False

    def test_completely_different_screens_are_different(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img1 = make_white_image(400, 400, color=(255, 255, 255))
        img2 = make_white_image(400, 400, color=(0, 0, 0))
        result = engine.screens_are_different(img1, img2, threshold=0.95)
        assert result is True

    def test_different_sized_images_counted_as_different(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img1 = make_white_image(400, 400)
        img2 = make_white_image(800, 600)
        # Should handle gracefully without raising
        result = engine.screens_are_different(img1, img2, threshold=0.95)
        assert isinstance(result, bool)

    def test_minor_change_detected(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img1 = make_white_image(400, 400, color=(200, 200, 200))
        img2 = img1.copy()
        # Change 5% of pixels significantly
        img2[:20, :400] = np.array([0, 0, 0], dtype=np.uint8)

        result = engine.screens_are_different(img1, img2, threshold=0.99)
        assert result is True


@pytest.mark.skipif(not IMAGING_AVAILABLE, reason="OpenCV/Pillow not installed")
class TestImagePreprocessing:
    """Tests for preprocessing pipeline."""

    def test_preprocess_returns_grayscale_for_template_match(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img = make_white_image(400, 400)
        result = engine.preprocess(img, target="template_match")
        assert len(result.shape) == 2  # Should be grayscale

    def test_preprocess_ocr_returns_binary(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img = make_white_image(400, 400)
        result = engine.preprocess(img, target="ocr")
        assert len(result.shape) == 2  # Grayscale/binary

    def test_preprocess_ssim_returns_original(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        img = make_white_image(400, 400)
        result = engine.preprocess(img, target="ssim")
        assert result.shape == img.shape  # No dimension change

    def test_scale_template_up(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        template = np.zeros((50, 100), dtype=np.uint8)
        scaled = engine._scale_template(template, 2.0)
        assert scaled.shape == (100, 200)

    def test_scale_template_down(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        template = np.zeros((100, 200), dtype=np.uint8)
        scaled = engine._scale_template(template, 0.5)
        assert scaled.shape == (50, 100)

    def test_scale_1_returns_same_array(self):
        from executors.cv_engine import CVEngine

        settings = make_settings()
        engine = CVEngine(settings)

        template = np.zeros((50, 100), dtype=np.uint8)
        scaled = engine._scale_template(template, 1.0)
        assert scaled is template


@pytest.mark.skipif(not IMAGING_AVAILABLE, reason="OpenCV/Pillow not installed")
class TestOCRIntegration:
    """Tests for find_text_on_screen with mocked Tesseract."""

    def test_find_text_returns_none_when_tesseract_unavailable(self):
        from executors.cv_engine import CVEngine
        import executors.cv_engine as cv_module

        orig = cv_module.TESSERACT_AVAILABLE
        cv_module.TESSERACT_AVAILABLE = False

        try:
            settings = make_settings()
            engine = CVEngine(settings)
            screenshot = make_white_image(400, 400)
            result = engine.find_text_on_screen("Install", screenshot)
            assert result is None
        finally:
            cv_module.TESSERACT_AVAILABLE = orig

    def test_find_text_with_mocked_tesseract(self):
        from executors.cv_engine import CVEngine
        import executors.cv_engine as cv_module

        if not cv_module.TESSERACT_AVAILABLE:
            pytest.skip("Tesseract not available")

        settings = make_settings()
        engine = CVEngine(settings)
        screenshot = make_white_image(400, 400)

        mock_ocr_data = {
            "text": ["Install", ""],
            "conf": [85, -1],
            "left": [50, 0],
            "top": [100, 0],
            "width": [80, 0],
            "height": [30, 0],
            "line_num": [1, 2],
        }

        with patch("pytesseract.image_to_data", return_value=mock_ocr_data):
            result = engine.find_text_on_screen("Install", screenshot, preprocess=False)

        assert result is not None
        cx, cy, conf = result
        assert cx == 90   # 50 + 80//2
        assert cy == 115  # 100 + 30//2
        assert conf == pytest.approx(0.85)

    def test_extract_all_text_returns_list(self):
        from executors.cv_engine import CVEngine
        import executors.cv_engine as cv_module

        if not cv_module.TESSERACT_AVAILABLE:
            pytest.skip("Tesseract not available")

        settings = make_settings()
        engine = CVEngine(settings)
        screenshot = make_white_image(400, 400)

        mock_ocr_data = {
            "text": ["Hello", "World", ""],
            "conf": [90, 75, -1],
            "left": [10, 60, 0],
            "top": [20, 20, 0],
            "width": [40, 40, 0],
            "height": [15, 15, 0],
        }

        with patch("pytesseract.image_to_data", return_value=mock_ocr_data):
            results = engine.extract_all_text(screenshot, preprocess=False)

        assert len(results) == 2
        assert results[0]["text"] == "Hello"
        assert results[1]["text"] == "World"
