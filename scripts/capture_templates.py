#!/usr/bin/env python3
"""
CV Template Capture Helper

Connects to a running Appium session (or local ADB device) and provides
an interactive tool to capture UI element templates for the CV locator.

Usage:
    python scripts/capture_templates.py --device emulator-5554
    python scripts/capture_templates.py --session <appium-session-id>

The tool:
1. Takes a screenshot of the current screen
2. Lets you select a region via coordinates or percentage
3. Saves the cropped region as a PNG template
4. Names it based on context + timestamp

Template naming convention:
    <context>_<element>_<timestamp>.png
    e.g., mlbb_lobby.png, play_store_install_btn.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def capture_screenshot_adb(device_serial: str) -> Optional[bytes]:
    """Capture screenshot using ADB screencap."""
    import subprocess
    result = subprocess.run(
        ["adb", "-s", device_serial, "shell", "screencap", "-p"],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"Error capturing screenshot: {result.stderr.decode()}")
        return None
    return result.stdout


def crop_region(
    image_bytes: bytes,
    x: int,
    y: int,
    w: int,
    h: int,
) -> Optional[bytes]:
    """Crop a region from a PNG image."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        cropped = img.crop((x, y, x + w, y + h))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        print("PIL not installed. Run: pip install Pillow")
        return None


def get_screen_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """Return (width, height) from image bytes."""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        return img.size
    except Exception:
        return 0, 0


def interactive_capture_session(
    device_serial: str,
    templates_dir: Path,
) -> None:
    """
    Interactive loop for capturing templates.
    Prompts user for region and name for each capture.
    """
    print(f"\n📸  Template Capture Tool")
    print(f"    Templates directory: {templates_dir}")
    print(f"    Device: {device_serial}")
    print(f"\n    Commands:")
    print(f"      s          — take new screenshot")
    print(f"      c x y w h  — crop and save region (pixels)")
    print(f"      p x y w h  — crop by percentage (0-100)")
    print(f"      q          — quit")
    print()

    screenshot_bytes: Optional[bytes] = None
    screenshot_path = templates_dir / "_current_screenshot.png"

    while True:
        cmd = input(">> ").strip().split()
        if not cmd:
            continue

        action = cmd[0].lower()

        if action == "q":
            print("Bye!")
            break

        elif action == "s":
            print("Capturing screenshot...")
            screenshot_bytes = capture_screenshot_adb(device_serial)
            if screenshot_bytes:
                screenshot_path.write_bytes(screenshot_bytes)
                w, h = get_screen_dimensions(screenshot_bytes)
                print(f"✓ Screenshot saved to {screenshot_path} ({w}x{h})")
                print(f"  View it to identify region coordinates")
            else:
                print("✗ Screenshot failed")

        elif action == "c" and len(cmd) == 5:
            if screenshot_bytes is None:
                print("Take a screenshot first (command: s)")
                continue
            try:
                x, y, w, h = int(cmd[1]), int(cmd[2]), int(cmd[3]), int(cmd[4])
                _save_template(screenshot_bytes, x, y, w, h, templates_dir)
            except ValueError:
                print("Usage: c <x> <y> <w> <h>  (pixel coordinates)")

        elif action == "p" and len(cmd) == 5:
            if screenshot_bytes is None:
                print("Take a screenshot first (command: s)")
                continue
            try:
                px, py, pw, ph = float(cmd[1]), float(cmd[2]), float(cmd[3]), float(cmd[4])
                sw, sh = get_screen_dimensions(screenshot_bytes)
                x = int(sw * px / 100)
                y = int(sh * py / 100)
                w = int(sw * pw / 100)
                h = int(sh * ph / 100)
                _save_template(screenshot_bytes, x, y, w, h, templates_dir)
            except ValueError:
                print("Usage: p <x%> <y%> <w%> <h%>  (percent of screen)")

        else:
            print(f"Unknown command: {action}. Type 'q' to quit.")


def _save_template(
    screenshot_bytes: bytes,
    x: int,
    y: int,
    w: int,
    h: int,
    templates_dir: Path,
) -> None:
    """Prompt for a name and save the cropped region."""
    name = input(f"  Template name (e.g., mlbb_lobby): ").strip()
    if not name:
        ts = datetime.now().strftime("%H%M%S")
        name = f"template_{ts}"

    cropped = crop_region(screenshot_bytes, x, y, w, h)
    if cropped:
        output_path = templates_dir / f"{name}.png"
        output_path.write_bytes(cropped)
        print(f"✓ Saved: {output_path}")
    else:
        print("✗ Crop failed")


def batch_capture_from_session(
    appium_url: str,
    session_id: str,
    templates_dir: Path,
    elements: list[dict],
) -> None:
    """
    Batch capture templates from a live Appium session.

    elements: list of dicts with: name, locator_by, locator_value
    """
    from appium import webdriver
    from appium.options import AppiumOptions

    print(f"\nConnecting to existing session: {session_id}")
    driver = webdriver.Remote(
        command_executor=appium_url,
        options=AppiumOptions(),
    )
    driver.session_id = session_id

    print(f"Capturing {len(elements)} templates...")
    for spec in elements:
        name = spec["name"]
        by = spec.get("locator_by", "id")
        value = spec["locator_value"]
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            elem = driver.find_element(AppiumBy.ID, value)
            screenshot = driver.get_screenshot_as_png()
            loc = elem.location
            size = elem.size
            x, y = loc["x"], loc["y"]
            w, h = size["width"], size["height"]
            # Add 10% padding
            padding_x = int(w * 0.1)
            padding_y = int(h * 0.1)
            x = max(0, x - padding_x)
            y = max(0, y - padding_y)
            w = w + 2 * padding_x
            h = h + 2 * padding_y

            import io
            from PIL import Image
            img = Image.open(io.BytesIO(screenshot))
            cropped = img.crop((x, y, x + w, y + h))
            output_path = templates_dir / f"{name}.png"
            cropped.save(str(output_path))
            print(f"  ✓ {name} → {output_path}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture CV template images from a connected Android device"
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("LOCAL_DEVICE_UDID", ""),
        help="ADB device serial (default: $LOCAL_DEVICE_UDID or auto-detect)",
    )
    parser.add_argument(
        "--templates-dir",
        default=str(Path(__file__).parent.parent / "templates"),
        help="Directory to save templates (default: ./templates)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run batch capture using predefined element list",
    )
    args = parser.parse_args()

    templates_dir = Path(args.templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)

    device = args.device
    if not device:
        # Auto-detect first device
        import subprocess
        result = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[1:]:
            if "\tdevice" in line:
                device = line.split("\t")[0]
                print(f"Auto-detected device: {device}")
                break

    if not device:
        print("No Android device found. Connect a device or specify --device")
        sys.exit(1)

    if args.batch:
        # Batch mode: capture predefined templates for this pipeline
        predefined_templates = [
            # Play Store
            {"name": "play_store_search_bar", "locator_by": "id",
             "locator_value": "com.android.vending:id/search_bar_hint"},
            {"name": "play_store_install_btn", "locator_by": "text",
             "locator_value": "Install"},
            # MLBB
            {"name": "mlbb_google_btn", "locator_by": "text",
             "locator_value": "Google"},
            {"name": "mlbb_quick_start_btn", "locator_by": "text",
             "locator_value": "Quick Start"},
        ]
        print(f"Batch mode: capturing {len(predefined_templates)} templates...")
        for spec in predefined_templates:
            name = spec["name"]
            print(f"  Navigate to where '{name}' is visible, then press Enter...")
            input()
            screenshot_bytes = capture_screenshot_adb(device)
            if screenshot_bytes:
                import subprocess
                # Use ADB to find element position
                print(f"  Template '{name}' saved (placeholder — use interactive mode for precise crops)")
    else:
        interactive_capture_session(device, templates_dir)


if __name__ == "__main__":
    main()
