#!/usr/bin/env bash
# =============================================================================
# Setup script for local Android device testing
# Installs/checks: ADB, Appium 2.x, UiAutomator2 driver, Tesseract, OpenCV
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=================================================="
echo "  Mobile Automation Pipeline — Local Device Setup"
echo "=================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Check OS
# ---------------------------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
    Linux*)  OS_TYPE=Linux ;;
    Darwin*) OS_TYPE=macOS ;;
    CYGWIN*|MINGW*) OS_TYPE=Windows ;;
    *) OS_TYPE=Unknown ;;
esac
log_info "Detected OS: $OS_TYPE"

# ---------------------------------------------------------------------------
# 2. Check Python
# ---------------------------------------------------------------------------
log_info "Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    log_ok "Python found: $PYTHON_VERSION"
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON_VERSION=$(python --version 2>&1)
    log_ok "Python found: $PYTHON_VERSION"
    PYTHON=python
else
    log_error "Python not found. Install Python 3.10+ from https://python.org"
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Install Python dependencies
# ---------------------------------------------------------------------------
log_info "Installing Python dependencies..."
cd "$PROJECT_DIR"
$PYTHON -m pip install -r requirements.txt --quiet || {
    log_warn "pip install failed. Trying with --break-system-packages..."
    $PYTHON -m pip install -r requirements.txt --break-system-packages --quiet
}
log_ok "Python dependencies installed"

# ---------------------------------------------------------------------------
# 4. Check Node.js
# ---------------------------------------------------------------------------
log_info "Checking Node.js..."
if command -v node &>/dev/null; then
    NODE_VERSION=$(node --version 2>&1)
    log_ok "Node.js found: $NODE_VERSION"
else
    log_error "Node.js not found. Install from https://nodejs.org (v18+)"
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Install Appium
# ---------------------------------------------------------------------------
log_info "Checking Appium..."
if command -v appium &>/dev/null; then
    APPIUM_VERSION=$(appium --version 2>&1)
    log_ok "Appium found: $APPIUM_VERSION"
else
    log_info "Installing Appium 2.x globally..."
    npm install -g appium || {
        log_error "Failed to install Appium. Try: sudo npm install -g appium"
        exit 1
    }
    log_ok "Appium installed"
fi

# Install UiAutomator2 driver
log_info "Checking UiAutomator2 driver..."
if appium driver list --installed 2>&1 | grep -q "uiautomator2"; then
    log_ok "UiAutomator2 driver already installed"
else
    log_info "Installing UiAutomator2 driver..."
    appium driver install uiautomator2
    log_ok "UiAutomator2 driver installed"
fi

# ---------------------------------------------------------------------------
# 6. Check ADB
# ---------------------------------------------------------------------------
log_info "Checking ADB..."
ADB_FOUND=false

# Check common locations
for ADB_PATH in adb "$HOME/Library/Android/sdk/platform-tools/adb" \
               "/usr/local/bin/adb" \
               "/opt/android-sdk/platform-tools/adb" \
               "$HOME/Android/Sdk/platform-tools/adb"; do
    if command -v "$ADB_PATH" &>/dev/null 2>&1; then
        ADB_VERSION=$(adb version 2>&1 | head -1)
        log_ok "ADB found: $ADB_VERSION"
        ADB_FOUND=true
        break
    fi
done

if ! $ADB_FOUND; then
    log_warn "ADB not found. Install Android SDK Platform Tools:"
    echo "  - Linux:  sudo apt install android-tools-adb"
    echo "  - macOS:  brew install android-platform-tools"
    echo "  - Or download from: https://developer.android.com/studio/releases/platform-tools"
    echo ""
    echo "  After installing, add to PATH and re-run this script."
fi

# ---------------------------------------------------------------------------
# 7. Check Tesseract OCR
# ---------------------------------------------------------------------------
log_info "Checking Tesseract OCR..."
if command -v tesseract &>/dev/null; then
    TESSERACT_VERSION=$(tesseract --version 2>&1 | head -1)
    log_ok "Tesseract found: $TESSERACT_VERSION"
else
    log_warn "Tesseract not found. Install for OCR fallback:"
    if [[ "$OS_TYPE" == "Linux" ]]; then
        echo "  sudo apt install tesseract-ocr tesseract-ocr-eng"
    elif [[ "$OS_TYPE" == "macOS" ]]; then
        echo "  brew install tesseract"
    fi
fi

# ---------------------------------------------------------------------------
# 8. Check connected devices
# ---------------------------------------------------------------------------
if $ADB_FOUND; then
    log_info "Checking connected Android devices..."
    DEVICES=$(adb devices 2>/dev/null | grep -v "List of" | grep -v "^$" | grep "device" || true)
    if [ -z "$DEVICES" ]; then
        log_warn "No Android devices detected."
        echo ""
        echo "  To connect a physical device:"
        echo "    1. Enable Developer Options (tap Build Number 7 times in Settings > About)"
        echo "    2. Enable USB Debugging"
        echo "    3. Connect via USB and accept the authorization prompt"
        echo ""
        echo "  To start an emulator:"
        echo "    emulator -avd <avd_name>  (requires Android Studio)"
        echo "    or: docker run --rm -p 5554:5554 budtmo/docker-android:emulator_12.0"
    else
        log_ok "Connected devices:"
        echo "$DEVICES" | while read -r line; do
            echo "    $line"
        done
    fi
fi

# ---------------------------------------------------------------------------
# 9. Create .env file if it doesn't exist
# ---------------------------------------------------------------------------
if [ ! -f "$PROJECT_DIR/.env" ]; then
    log_info "Creating .env from .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    log_ok ".env created — please fill in your credentials"
else
    log_ok ".env already exists"
fi

# ---------------------------------------------------------------------------
# 10. Create artifacts/templates directories
# ---------------------------------------------------------------------------
mkdir -p "$PROJECT_DIR/artifacts"
mkdir -p "$PROJECT_DIR/templates"
log_ok "Artifact and template directories ready"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=================================================="
echo "  Setup Complete"
echo "=================================================="
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your Google credentials and provider config"
echo "    2. Connect an Android device (or start an emulator)"
echo "    3. python scripts/demo_run.py        # Run demo"
echo "    4. python api_server.py              # Start API server"
echo "    5. cd dashboard && npm install && npm run dev  # Start dashboard"
echo ""
