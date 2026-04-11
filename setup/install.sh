#!/usr/bin/env bash
# grandma-watcher full system setup for Raspberry Pi 5 (Raspberry Pi OS Lite 64-bit)
# Run as root or with sudo from the project root directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_USER="${SUDO_USER:-pi}"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

cd "$PROJECT_DIR"

# --- Config bootstrap -----------------------------------------------------------
if [ ! -f config.yaml ]; then
  cp config.yaml.example config.yaml
  echo "Created config.yaml from config.yaml.example - fill in API keys before running."
fi

# --- Helper: install a systemd service with path/user substitution --------------
install_service() {
  local name="$1"
  local src="$SCRIPT_DIR/systemd/${name}.service"
  local dest="/etc/systemd/system/${name}.service"

  sed \
    -e "s|User=pi|User=${SERVICE_USER}|g" \
    -e "s|Group=pi|Group=${SERVICE_USER}|g" \
    -e "s|/home/pi/eldercare/.venv/bin/python|${VENV_PYTHON}|g" \
    -e "s|/home/pi/eldercare|${PROJECT_DIR}|g" \
    "$src" > "$dest"

  systemctl daemon-reload
  systemctl enable "${name}.service"
  systemctl restart "${name}.service"
  echo "Installed and started ${name}.service"
}

# --- Python venv ----------------------------------------------------------------
if [ ! -f "$VENV_PYTHON" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$PROJECT_DIR/.venv"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

# --- go2rtc binary --------------------------------------------------------------
if [ ! -x /usr/local/bin/go2rtc ]; then
  echo "Downloading go2rtc ARM64 binary..."
  curl -fsSL -o /usr/local/bin/go2rtc \
    https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64
  chmod +x /usr/local/bin/go2rtc
fi

# --- systemd services -----------------------------------------------------------
install_service go2rtc
install_service web_server
install_service monitor

echo ""
echo "Setup complete."
echo "Check logs:  journalctl -u grandma-monitor -f"
echo "Dashboard:   http://localhost:8080"
