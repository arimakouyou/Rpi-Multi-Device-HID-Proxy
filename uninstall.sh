#!/bin/bash
set -e
echo "Multi HID Proxy をアンインストールします..."

if [ "$(id -u)" -ne 0 ]; then
  echo "このスクリプトはroot権限で実行する必要があります。sudo ./uninstall.sh をお試しください。" >&2
  exit 1
fi

echo "サービスを停止・無効化します..."
systemctl stop keyboard-proxy.service || true
systemctl disable keyboard-proxy.service || true
systemctl stop mouse-proxy.service || true
systemctl disable mouse-proxy.service || true
systemctl stop multi-hid-gadget.service || true
systemctl disable multi-hid-gadget.service || true

echo "ファイルを削除します..."
rm -f /usr/local/bin/proxy_core.py
rm -f /usr/local/bin/keyboard_proxy.py
rm -f /usr/local/bin/mouse_proxy.py
rm -f /usr/local/bin/hid_keys.py
rm -f /etc/systemd/system/keyboard-proxy.service
rm -f /etc/systemd/system/mouse-proxy.service
rm -f /etc/systemd/system/multi-hid-gadget.service
rm -f /usr/local/bin/multi_device_proxy.py
rm -f /usr/local/bin/setup_hid_gadget.sh
rm -f /usr/local/bin/config.json

echo "Systemdデーモンをリロードしています..."
systemctl daemon-reload

echo "アンインストールが完了しました。"

