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

# 1. python3-evdev (evdev) - keyboard_proxy.py 等で使用
if ! python3 -c "import evdev" &> /dev/null; then
    echo "警告: Pythonライブラリ 'evdev' が見つかりません。"
    echo "キーボード機能を使用する場合はインストールが必要です:"
    echo "  sudo apt-get update && sudo apt-get install python3-evdev"
    exit 1
fi

# 2. jq (JSONパーサー)
if ! command_exists jq; then
    echo "エラー: 'jq' コマンドが見つかりません。"
    echo "解決策: 以下のコマンドを実行してください:"
    echo "  sudo apt-get update && sudo apt-get install jq"
    exit 1
fi

# 3. gpiozero - GPIOボタン制御用
if ! python3 -c "import gpiozero" &> /dev/null; then
    echo "警告: Pythonライブラリ 'gpiozero' が見つかりません。"
    echo "GPIOボタン機能を使用する場合はインストールが必要です。"
    echo "自動インストールを試みます..."
    if apt-get install -y python3-gpiozero; then
        echo "gpiozero のインストールが完了しました。"
    else
        echo "エラー: gpiozero のインストールに失敗しました。"
        echo "手動でインストールしてください: sudo apt-get install python3-gpiozero"
        exit 1
    fi
fi

# 4. rpi_ws281x - NeoPixel LED制御用
if ! python3 -c "import rpi_ws281x" &> /dev/null; then
    echo "警告: Pythonライブラリ 'rpi_ws281x' が見つかりません。"
    echo "LED制御機能を使用する場合はインストールが必要です。"
    echo "自動インストールを試みます..."
    
    # pip3のインストール確認
    if ! command_exists pip3 && ! python3 -m pip --version &> /dev/null; then
        echo "pip3 が見つかりません。python3-pip をインストールしています..."
        if apt-get install -y python3-pip; then
            echo "python3-pip のインストールが完了しました。"
        else
            echo "警告: python3-pip のインストールに失敗しました。"
            echo "手動でインストールしてください: sudo apt-get install python3-pip"
            echo "LED機能は無効化されますが、他の機能は動作します。"
        fi
    fi
    
    # 必要なビルドツールの確認
    if ! command_exists scons; then
        echo "ビルドツール 'scons' をインストールしています..."
        apt-get install -y scons
    fi
    
    # rpi_ws281xのインストール (--break-system-packagesオプション付き)
    # systemdサービスで使用するため、システムワイドインストールが必要
    if python3 -m pip install --break-system-packages rpi_ws281x 2>/dev/null; then
        echo "rpi_ws281x のインストールが完了しました。"
    elif pip3 install --break-system-packages rpi_ws281x 2>/dev/null; then
        echo "rpi_ws281x のインストールが完了しました。"
    else
        echo "警告: rpi_ws281x のインストールに失敗しました。"
        echo "LED機能は無効化されますが、他の機能は動作します。"
        echo "手動でインストールする場合:"
        echo "  sudo apt-get install python3-pip"
        echo "  sudo python3 -m pip install --break-system-packages rpi_ws281x"
        # LED機能はオプショナルなので、失敗してもexitしない
    fi
fi

echo "依存関係は満たされています。"
echo ""

# --- スクリプトのインストール ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

INSTALL_DIR="/usr/local/bin"
SERVICE_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/multi-hid-proxy"

echo "ファイルをインストールしています..."

# ディレクトリの作成
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$CONFIG_DIR"

# Pythonスクリプトの配置
echo "Pythonスクリプトを配置します..."
sudo cp "$PROJECT_ROOT/src/proxy_core.py" "$INSTALL_DIR/"
sudo cp "$PROJECT_ROOT/src/keyboard_proxy.py" "$INSTALL_DIR/"
sudo cp "$PROJECT_ROOT/src/hid_keys.py" "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR/setup_hid_gadget.sh" "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/keyboard_proxy.py"
sudo chmod +x "$INSTALL_DIR/setup_hid_gadget.sh"

# Rustバイナリの配置
echo "Mouse Proxy (Rust) を配置します..."
# アーカイブを展開した場合はカレントディレクトリ、それ以外はプロジェクトルートを参照
if [ -f "./mouse_proxy_rs" ]; then
    echo "同梱のバイナリを使用します..."
    sudo cp ./mouse_proxy_rs "$INSTALL_DIR/"
elif [ -f "$PROJECT_ROOT/mouse_proxy_rs" ]; then
    echo "プロジェクトルートのバイナリを使用します..."
    sudo cp "$PROJECT_ROOT/mouse_proxy_rs" "$INSTALL_DIR/"
else
    echo "エラー: 'mouse_proxy_rs' バイナリが見つかりません。"
    echo "ビルドアーカイブが正しく展開されているか確認してください。"
    exit 1
fi

# 設定ファイルの配置
if [ ! -d "$CONFIG_DIR" ]; then
    sudo mkdir -p "$CONFIG_DIR"
fi

if [ ! -f "$CONFIG_DIR/config.json" ]; then
    echo "設定ファイルを配置します..."
    sudo cp "$PROJECT_ROOT/config/config.json.sample" "$CONFIG_DIR/config.json"
fi

# サービスのインストール
echo "systemdサービスをインストールします..."
sudo cp "$PROJECT_ROOT/systemd/keyboard-proxy.service" "$SERVICE_DIR/"
sudo cp "$PROJECT_ROOT/systemd/mouse-proxy@.service" "$SERVICE_DIR/"
sudo cp "$PROJECT_ROOT/systemd/multi-hid-gadget.service" "$SERVICE_DIR/"

# UDEVルールのインストール
echo "UDEVルールをインストールします..."
sudo cp "$PROJECT_ROOT/udev/99-mouse-proxy.rules" "/etc/udev/rules.d/"

# --- Systemdサービスの設定 ---
echo "Systemdサービスをリロードして有効化しています..."
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo systemctl enable keyboard-proxy.service
sudo systemctl enable multi-hid-gadget.service

echo ""
echo "インストールが完了しました。"
echo "システムを再起動して変更を適用してください:"
echo "  sudo reboot"
