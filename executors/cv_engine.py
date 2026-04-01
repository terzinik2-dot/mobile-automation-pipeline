"""
Computer Vision Engine

Provides template matching (OpenCV) and text detection (Tesseract OCR)
capabilities for the locator cascade.

Key features:
- Multi-scale template matching (handles different screen resolutions)
- Confidence-based result filtering
- SSIM screen-change detection
- Bounding box extraction from OCR results
- Preprocessing pipeline (grayscale, contrast, denoising)
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Optional, Tuple

import cv2
import numpy as np
from loguru import logger
from PIL import Image

# Try to import pytesseract; log warning if unavailable
try:
    import pytesseract
    from pytesseract import Output as TesseractOutput
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed — OCR locator disabled")

# Try SSIM
try:
    from skimage.metrics import structural_similarity as ssim
    SSIM_AVAILABLE = True
except ImportError:
    SSIM_AVAILABLE = False


class CVEngine:
    """
    Computer vision engine for UI element detection.

    Provides:
    - find_on_screen: OpenCV multi-scale template matching
    - find_text_on_screen: Tesseract OCR with bounding box extraction
    - screens_are_different: SSIM-based screen change detection
    - preprocess: Image preprocessing for improved matching
    """

    def __init__(self, settings: Any) -> None:
        """
        Args:
            settings: Settings instance (from orchestrator.config)
        """
        self.settings = settings
        self.confidence_threshold = getattr(
            settings, "cv_confidence_threshold", 0.80
        )
        self.template_dir = Path(getattr(settings, "template_dir", "./templates"))
        self.ocr_language = getattr(settings, "ocr_language", "eng")

        # Configure Tesseract binary path
        tesseract_cmd = getattr(settings, "tesseract_cmd", "/usr/bin/tesseract")
        if TESSERACT_AVAILABLE and tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # Cache for loaded templates
        self._template_cache: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    def find_on_screen(
        self,
        template_path: str,
        screenshot: np.ndarray,
        threshold: Optional[float] = None,
        scales: Optional[list[float]] = None,
    ) -> Optional[Tuple[int, int, float]]:
        """
        Find a template image within a screenshot using multi-scale matching.

        Args:
            template_path: Path to template PNG (absolute or relative to template_dir).
            screenshot: Current screen as numpy array (BGR or RGB).
            threshold: Minimum confidence [0, 1]. Defaults to settings value.
            scales: List of scale factors to try. Defaults to [0.75, 1.0, 1.25, 1.5].

        Returns:
            (center_x, center_y, confidence) if found, None otherwise.
        """
        min_confidence = threshold or self.confidence_threshold
        scale_factors = scales or [0.75, 0.85, 1.0, 1.15, 1.25, 1.5]

        # Resolve template path
        template = self._load_template(template_path)
        if template is None:
            logger.error(f"[CVEngine] Template not found: {template_path}")
            return None

        # Convert screenshot to grayscale for matching
        if len(screenshot.shape) == 3 and screenshot.shape[2] == 3:
            screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
        else:
            screenshot_gray = screenshot

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template

        best_confidence = 0.0
        best_location: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h

        for scale in scale_factors:
            scaled_template = self._scale_template(template_gray, scale)
            th, tw = scaled_template.shape[:2]

            # Skip if template is larger than screenshot at this scale
            sh, sw = screenshot_gray.shape[:2]
            if th > sh or tw > sw:
                continue

            # Template matching with normalized cross-correlation
            result = cv2.matchTemplate(
                screenshot_gray, scaled_template, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_confidence:
                best_confidence = max_val
                best_location = (max_loc[0], max_loc[1], tw, th)

        if best_confidence < min_confidence or best_location is None:
            logger.debug(
                f"[CVEngine] Template '{Path(template_path).name}' not found "
                f"(best confidence: {best_confidence:.3f} < {min_confidence})"
            )
            return None

        x, y, w, h = best_location
        cx = x + w // 2
        cy = y + h // 2
        logger.debug(
            f"[CVEngine] Template '{Path(template_path).name}' found at "
            f"({cx}, {cy}) confidence={best_confidence:.3f}"
        )
        return cx, cy, best_confidence

    def find_all_on_screen(
        self,
        template_path: str,
        screenshot: np.ndarray,
        threshold: Optional[float] = None,
    ) -> list[Tuple[int, int, float]]:
        """
        Find ALL occurrences of a template on screen.

        Returns list of (center_x, center_y, confidence) sorted by confidence desc.
        """
        min_confidence = threshold or self.confidence_threshold
        template = self._load_template(template_path)
        if template is None:
            return []

        screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY) if len(screenshot.shape) == 3 else screenshot
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if len(template.shape) == 3 else template
        th, tw = template_gray.shape[:2]

        result = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= min_confidence)

        # Group nearby matches (NMS-like)
        points = list(zip(locations[1], locations[0]))  # (x, y)
        if not points:
            return []

        # Non-maximum suppression using groupRectangles
        rects = [[x, y, x + tw, y + th] for x, y in points]
        rects_array = np.array([[x, y, x + tw, y + th] for x, y in points])
        # Simple deduplication: cluster by distance
        used = set()
        results = []
        for i, (x, y) in enumerate(points):
            if i in used:
                continue
            cx, cy = x + tw // 2, y + th // 2
            conf = float(result[y, x])
            results.append((cx, cy, conf))
            # Mark nearby points as used
            for j, (x2, y2) in enumerate(points):
                if abs(x2 - x) < tw // 2 and abs(y2 - y) < th // 2:
                    used.add(j)

        return sorted(results, key=lambda r: r[2], reverse=True)

    # ------------------------------------------------------------------
    # OCR text detection
    # ------------------------------------------------------------------

    def find_text_on_screen(
        self,
        text: str,
        screenshot: np.ndarray,
        partial_match: bool = True,
        preprocess: bool = True,
        min_confidence: int = 60,
    ) -> Optional[Tuple[int, int, float]]:
        """
        Find text in a screenshot using Tesseract OCR.

        Args:
            text: The text to find.
            screenshot: Current screen as numpy array.
            partial_match: If True, allow substring/partial matches.
            preprocess: Apply image enhancement before OCR.
            min_confidence: Minimum Tesseract word confidence [0, 100].

        Returns:
            (center_x, center_y, normalized_confidence) if found, None otherwise.
        """
        if not TESSERACT_AVAILABLE:
            logger.warning("[CVEngine] Tesseract not available — OCR skipped")
            return None

        img = self._preprocess_for_ocr(screenshot) if preprocess else screenshot

        try:
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.ocr_language,
                output_type=TesseractOutput.DICT,
                config="--psm 3 --oem 3",
            )
        except Exception as e:
            logger.error(f"[CVEngine] OCR failed: {e}")
            return None

        search_text = text.lower().strip()
        n_boxes = len(ocr_data["text"])

        # Strategy 1: Find single-word matches
        for i in range(n_boxes):
            word = str(ocr_data["text"][i]).strip()
            conf = int(ocr_data.get("conf", [0] * n_boxes)[i])
            if conf < min_confidence:
                continue
            word_lower = word.lower()
            if (partial_match and search_text in word_lower) or (
                not partial_match and word_lower == search_text
            ):
                x = ocr_data["left"][i]
                y = ocr_data["top"][i]
                w = ocr_data["width"][i]
                h = ocr_data["height"][i]
                cx = x + w // 2
                cy = y + h // 2
                normalized_conf = conf / 100.0
                logger.debug(
                    f"[CVEngine] OCR found '{text}' at ({cx}, {cy}) "
                    f"conf={normalized_conf:.2f}"
                )
                return cx, cy, normalized_conf

        # Strategy 2: Concatenate adjacent words and look for multi-word phrases
        if " " in search_text:
            result = self._find_multiword_text(ocr_data, search_text, min_confidence)
            if result:
                return result

        logger.debug(f"[CVEngine] OCR could not find '{text}'")
        return None

    def extract_all_text(
        self,
        screenshot: np.ndarray,
        preprocess: bool = True,
        min_confidence: int = 50,
    ) -> list[dict]:
        """
        Extract all text blocks from a screenshot with bounding boxes.

        Returns list of dicts with: text, x, y, width, height, confidence.
        """
        if not TESSERACT_AVAILABLE:
            return []
        img = self._preprocess_for_ocr(screenshot) if preprocess else screenshot
        try:
            data = pytesseract.image_to_data(
                img, lang=self.ocr_language, output_type=TesseractOutput.DICT
            )
            results = []
            for i in range(len(data["text"])):
                text = str(data["text"][i]).strip()
                conf = int(data.get("conf", [0] * len(data["text"]))[i])
                if text and conf >= min_confidence:
                    results.append({
                        "text": text,
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "width": data["width"][i],
                        "height": data["height"][i],
                        "confidence": conf / 100.0,
                    })
            return results
        except Exception as e:
            logger.error(f"[CVEngine] extract_all_text failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Screen change detection
    # ------------------------------------------------------------------

    def screens_are_different(
        self,
        screenshot1: np.ndarray,
        screenshot2: np.ndarray,
        threshold: float = 0.95,
    ) -> bool:
        """
        Return True if the two screenshots are meaningfully different.

        Uses SSIM if available, falls back to pixel difference.

        Args:
            threshold: SSIM score below which screens are considered different.
        """
        if SSIM_AVAILABLE:
            return self._ssim_diff(screenshot1, screenshot2, threshold)
        return self._pixel_diff(screenshot1, screenshot2, threshold=0.02)

    def wait_for_screen_change(
        self,
        baseline: np.ndarray,
        screenshot_fn: Any,
        timeout: float = 15.0,
        poll_interval: float = 0.5,
        threshold: float = 0.95,
    ) -> Optional[np.ndarray]:
        """
        Poll screenshots until the screen changes from baseline.

        Args:
            baseline: Reference screenshot.
            screenshot_fn: Callable that returns a new screenshot.
            timeout: Max wait in seconds.
            threshold: SSIM threshold for "different".

        Returns:
            The new screenshot when the screen changes, None on timeout.
        """
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new_screenshot = screenshot_fn()
            if self.screens_are_different(baseline, new_screenshot, threshold):
                return new_screenshot
            time.sleep(poll_interval)
        return None

    # ------------------------------------------------------------------
    # Image preprocessing
    # ------------------------------------------------------------------

    def _preprocess_for_ocr(self, screenshot: np.ndarray) -> np.ndarray:
        """
        Enhance image for better OCR accuracy.

        Pipeline:
        1. Convert to grayscale
        2. Increase contrast (CLAHE)
        3. Remove noise (Gaussian blur)
        4. Adaptive threshold for binarization
        """
        # Convert to grayscale
        if len(screenshot.shape) == 3 and screenshot.shape[2] >= 3:
            gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
        else:
            gray = screenshot.copy()

        # Upscale for better OCR (2x)
        h, w = gray.shape[:2]
        upscaled = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(upscaled)

        # Denoising
        denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

        # Adaptive threshold for text extraction
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )
        return binary

    def preprocess(
        self,
        screenshot: np.ndarray,
        target: str = "template_match",
    ) -> np.ndarray:
        """
        Preprocess screenshot for a specific task.

        Args:
            target: "template_match" | "ocr" | "ssim"
        """
        if target == "ocr":
            return self._preprocess_for_ocr(screenshot)
        elif target == "template_match":
            if len(screenshot.shape) == 3:
                return cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
            return screenshot
        return screenshot

    # ------------------------------------------------------------------
    # Template cache management
    # ------------------------------------------------------------------

    def _load_template(self, template_path: str) -> Optional[np.ndarray]:
        """Load a template image, checking the template_dir for relative paths."""
        if template_path in self._template_cache:
            return self._template_cache[template_path]

        # Resolve path
        path = Path(template_path)
        if not path.is_absolute():
            path = self.template_dir / template_path

        if not path.exists():
            # Also try with .png extension
            png_path = path.with_suffix(".png")
            if png_path.exists():
                path = png_path
            else:
                logger.warning(f"[CVEngine] Template not found: {template_path}")
                return None

        template = cv2.imread(str(path))
        if template is None:
            logger.error(f"[CVEngine] Failed to load template: {path}")
            return None

        self._template_cache[template_path] = template
        return template

    def clear_template_cache(self) -> None:
        """Clear the in-memory template cache."""
        self._template_cache.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scale_template(self, template: np.ndarray, scale: float) -> np.ndarray:
        """Scale a template by the given factor."""
        if scale == 1.0:
            return template
        h, w = template.shape[:2]
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _find_multiword_text(
        self,
        ocr_data: dict,
        search_text: str,
        min_confidence: int,
    ) -> Optional[Tuple[int, int, float]]:
        """
        Find a multi-word phrase by joining adjacent OCR words.
        Sliding window over words within the same line.
        """
        words = search_text.lower().split()
        n = len(words)
        texts = [str(t).strip().lower() for t in ocr_data["text"]]
        confs = [int(c) for c in ocr_data.get("conf", [0] * len(texts))]
        lines = ocr_data.get("line_num", list(range(len(texts))))

        # Group words by line
        line_words: dict[int, list[int]] = {}
        for i, line in enumerate(lines):
            if texts[i]:
                line_words.setdefault(line, []).append(i)

        for line_idxs in line_words.values():
            for start in range(len(line_idxs) - n + 1):
                window = line_idxs[start:start + n]
                window_texts = [texts[i] for i in window]
                window_confs = [confs[i] for i in window]
                phrase = " ".join(window_texts)
                avg_conf = sum(window_confs) / len(window_confs) if window_confs else 0

                if avg_conf < min_confidence:
                    continue

                if (search_text in phrase) or (phrase in search_text):
                    # Compute bounding box of the phrase
                    xs = [ocr_data["left"][i] for i in window]
                    ys = [ocr_data["top"][i] for i in window]
                    ws = [ocr_data["width"][i] for i in window]
                    hs = [ocr_data["height"][i] for i in window]
                    x = min(xs)
                    y = min(ys)
                    w = max(xs[i] + ws[i] for i in range(len(window))) - x
                    h = max(hs)
                    cx = x + w // 2
                    cy = y + h // 2
                    return cx, cy, avg_conf / 100.0
        return None

    def _ssim_diff(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        threshold: float,
    ) -> bool:
        """Return True if SSIM score is below threshold (screens are different)."""
        try:
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            g1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY) if len(img1.shape) == 3 else img1
            g2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY) if len(img2.shape) == 3 else img2
            score, _ = ssim(g1, g2, full=True)
            return score < threshold
        except Exception as e:
            logger.debug(f"[CVEngine] SSIM failed: {e}")
            return self._pixel_diff(img1, img2)

    def _pixel_diff(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        threshold: float = 0.02,
    ) -> bool:
        """Return True if more than `threshold` fraction of pixels differ."""
        if img1.shape != img2.shape:
            return True
        diff = np.abs(img1.astype(np.int32) - img2.astype(np.int32))
        changed_pixels = np.sum(diff > 10)
        total_pixels = img1.shape[0] * img1.shape[1]
        fraction = changed_pixels / total_pixels
        return fraction > threshold
