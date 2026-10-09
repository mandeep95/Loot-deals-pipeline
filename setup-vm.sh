#!/bin/bash
# One-command setup for a fresh Ubuntu VM (Oracle Cloud Always Free, or any VPS).
# Upload deals-pipeline.zip to the VM first (scp), then run:  bash setup-vm.sh
set -e

echo "== Installing Python =="
sudo apt update -qq && sudo apt install -y -qq python3 python3-venv python3-pip unzip

echo "== Unpacking =="
mkdir -p ~/deals-pipeline
unzip -o ~/deals-pipeline.zip -d ~/
cd ~/deals-pipeline

echo "== Installing dependencies =="
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python tests/run_tests.py 2>&1 | tail -1

echo "== Installing auto-restart services =="
sudo cp systemd/deals-reader.service systemd/deals-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

echo ""
echo "=== NEXT STEPS (one-time) ==="
echo "1. Log the reader in (needs the OTP Telegram sends your phone):"
echo "     cd ~/deals-pipeline && .venv/bin/python reader.py"
echo "   Enter the code, wait for 'Watching: ...' lines, then Ctrl+C."
echo "2. Enable 24x7 auto-restart:"
echo "     sudo systemctl enable --now deals-reader deals-bot"
echo "3. Check they're alive:"
echo "     sudo systemctl status deals-reader deals-bot"
echo ""
echo "Logs anytime:  sudo journalctl -u deals-reader -f   /   sudo journalctl -u deals-bot -f"
