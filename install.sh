#!/bin/bash
set -e
echo "Multi HID Proxy をインストールします..."

if [ "$(id -u)" -ne 0 ]; then
  echo "このスクリプトはroot権限で実行する必要があります。sudo ./install.sh をお試しください。" >&2
  exit 1
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# --- 依存関係のチェック ---
echo "必須パッケージの依存関係をチェックしています..."

# 1. python3-evdev (evdev)
if ! python3 -c "import evdev" &> /dev/null; then
    echo "エラー: Pythonライブラリ 'evdev' が見つかりません。"
    echo "解決策: 以下のいずれかのコマンドを実行してください:"
    echo "  sudo apt-get update && sudo apt-get install python3-evdev"
    echo "  pip3 install evdev"
    exit 1
fi

# 2. jq (JSONパーサー)
if ! command_exists jq; then
    echo "エラー: 'jq' コマンドが見つかりません。"
    echo "解決策: 以下のコマンドを実行してください:"
    echo "  sudo apt-get update && sudo apt-get install jq"
    exit 1
fi

echo "依存関係は満たされています。"
echo ""

# --- スクリプトのインストール ---
INSTALL_DIR="/usr/local/bin"
SERVICE_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/multi-hid-proxy"

echo "ファイルをインストールしています..."

# ディレクトリの作成
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$CONFIG_DIR"

# ファイルのコピー
sudo cp multi_device_proxy.py "$INSTALL_DIR/"
sudo cp hid_keys.py "$INSTALL_DIR/"
sudo cp setup_hid_gadget.sh "$INSTALL_DIR/"
# config.jsonは/etc配下に
if [ -f "config.json" ]; then
    sudo cp config.json "$CONFIG_DIR/"
else
    echo "警告: config.jsonが見つかりません。サンプルをコピーします。"
    sudo cp config.json.sample "$CONFIG_DIR/config.json"
fi

# 実行権限の付与
sudo chmod +x "$INSTALL_DIR/multi_device_proxy.py"
sudo chmod +x "$INSTALL_DIR/setup_hid_gadget.sh"

# Systemdサービスのコピー
sudo cp multi-hid-gadget.service "$SERVICE_DIR/"
sudo cp multi-hid-proxy.service "$SERVICE_DIR/"

# --- Systemdサービスの設定 ---
echo "Systemdサービスをリロードして有効化しています..."
sudo systemctl daemon-reload
sudo systemctl enable multi-hid-gadget.service
sudo systemctl enable multi-hid-proxy.service

echo ""
echo "インストールが完了しました。"
echo "システムを再起動して変更を適用してください:"
echo "  sudo reboot"

