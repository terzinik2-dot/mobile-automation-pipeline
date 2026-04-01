"""
Executors Package

Low-level execution layer:
- AppiumDriver: session management and driver wrapper
- MultiLayerLocator: self-healing element location cascade
- CVEngine: OpenCV template matching + Tesseract OCR
- GestureEngine: tap, swipe, scroll, long-press
"""

from executors.appium_driver import AppiumDriver
from executors.locator_engine import MultiLayerLocator, LocatorStrategy
from executors.cv_engine import CVEngine
from executors.gesture_engine import GestureEngine

__all__ = [
    "AppiumDriver",
    "MultiLayerLocator",
    "LocatorStrategy",
    "CVEngine",
    "GestureEngine",
]
