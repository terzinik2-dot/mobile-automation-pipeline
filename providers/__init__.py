"""
Device Farm Providers Package

Each provider wraps a specific device farm (BrowserStack, AWS Device Farm, local ADB)
behind a common interface defined in base.py.
"""

from providers.base import DeviceProvider
from providers.local_device import LocalDeviceProvider

__all__ = ["DeviceProvider", "LocalDeviceProvider"]
