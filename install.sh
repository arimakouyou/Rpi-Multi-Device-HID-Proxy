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
# 1. python3-evdev (evdev) - keyboard_proxy.py 等で使用
if ! python3 -c "import evdev" &> /dev/null; then
    echo "警告: Pythonライブラリ 'evdev' が見つかりません。"
    echo "キーボード機能を使用する場合はインストールが必要です:"
    echo "  sudo apt-get update && sudo apt-get install python3-evdev"
    # 必須ではなく警告にするか、キーボードを使うなら必須のままにするか。
    # ここでは既存のロジックに従いエラー終了としますが、メッセージを少し修正。
    # Mouse Proxy (Rust) はこれに依存しませんが、Keyboard Proxy は依存します。
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

# Pythonスクリプトの配置
echo "Pythonスクリプトを配置します..."
sudo cp proxy_core.py "$INSTALL_DIR/"
sudo cp keyboard_proxy.py "$INSTALL_DIR/"
# sudo cp mouse_proxy.py "$INSTALL_DIR/" # Rust版に置き換え
sudo cp hid_keys.py "$INSTALL_DIR/"
sudo cp setup_hid_gadget.sh "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/keyboard_proxy.py"
# sudo chmod +x "$INSTALL_DIR/mouse_proxy.py" # Removed
sudo chmod +x "$INSTALL_DIR/setup_hid_gadget.sh"

# Rustバイナリの配置
echo "Mouse Proxy (Rust) を配置します..."
# Rustバイナリの配置
echo "Mouse Proxy (Rust) を配置します..."
# アーカイブを展開したカレントディレクトリにあることを想定
if [ -f "./mouse_proxy_rs" ]; then
    echo "同梱のバイナリを使用します..."
    sudo cp ./mouse_proxy_rs "$INSTALL_DIR/"
else
    echo "エラー: 'mouse_proxy_rs' バイナリがカレントディレクトリに見つかりません。"
    echo "ビルドアーカイブが正しく展開されているか確認してください。"
    exit 1
fi

# 設定ファイルの配置
if [ ! -d "$CONFIG_DIR" ]; then
    sudo mkdir -p "$CONFIG_DIR"
fi

if [ ! -f "$CONFIG_DIR/config.json" ]; then
    echo "設定ファイルを配置します..."
    sudo cp config.json.sample "$CONFIG_DIR/config.json"
fi

# サービスのインストール
echo "systemdサービスをインストールします..."
sudo cp keyboard-proxy.service "$SERVICE_DIR/"
sudo cp mouse-proxy@.service "$SERVICE_DIR/"
sudo cp multi-hid-gadget.service "$SERVICE_DIR/"

# UDEVルールのインストール
echo "UDEVルールをインストールします..."
sudo cp 99-mouse-proxy.rules "/etc/udev/rules.d/"

# --- Systemdサービスの設定 ---
echo "Systemdサービスをリロードして有効化しています..."
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo systemctl enable keyboard-proxy.service
sudo systemctl enable multi-hid-gadget.service
sudo systemctl disable mouse-proxy.service # Disable old service

echo ""
echo "インストールが完了しました。"
echo "以下のコマンドでサービスを開始してください:"
echo "sudo systemctl start multi-hid-gadget.service"
echo "sudo systemctl start keyboard-proxy.service"
echo "sudo systemctl start mouse-proxy.service"

echo ""
echo "インストールが完了しました。"
echo "システムを再起動して変更を適用してください:"
echo "  sudo reboot"
