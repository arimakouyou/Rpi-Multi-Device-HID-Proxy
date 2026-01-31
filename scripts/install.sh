#!/bin/bash
# =============================================================================
# Multi HID Proxy インストールスクリプト
# =============================================================================
#
# このスクリプトは、Multi HID Proxyシステムをインストールします。
#
# インストールされるコンポーネント:
#   - Pythonスクリプト（キーボードプロキシ、共通モジュール）
#   - Rustバイナリ（マウスプロキシ）
#   - systemdサービスファイル
#   - udevルール
#   - 設定ファイル
#
# 前提条件:
#   - root権限での実行
#   - python3-evdev パッケージ
#   - jq コマンド
#   - python3-gpiozero（オプション、GPIO機能用）
#   - rpi_ws281x（オプション、LED機能用）
#
# 使用方法:
#   sudo ./install.sh
#
# =============================================================================

# エラー発生時にスクリプトを終了
set -e

echo "Multi HID Proxy をインストールします..."

# =============================================================================
# root権限チェック
# =============================================================================
if [ "$(id -u)" -ne 0 ]; then
  echo "このスクリプトはroot権限で実行する必要があります。sudo ./install.sh をお試しください。" >&2
  exit 1
fi

# =============================================================================
# ヘルパー関数
# =============================================================================

# コマンドの存在を確認する関数
# 引数: $1 - コマンド名
# 戻り値: 存在する場合は0、しない場合は1
command_exists() {
    command -v "$1" &> /dev/null
}

# =============================================================================
# 依存関係のチェック
# =============================================================================
echo "必須パッケージの依存関係をチェックしています..."

# -----------------------------------------------------------------------------
# 1. python3-evdev（必須）
# -----------------------------------------------------------------------------
# evdevライブラリはキーボードプロキシで入力デバイスのイベントを
# 読み取るために使用されます
if ! python3 -c "import evdev" &> /dev/null; then
    echo "警告: Pythonライブラリ 'evdev' が見つかりません。"
    echo "キーボード機能を使用する場合はインストールが必要です:"
    echo "  sudo apt-get update && sudo apt-get install python3-evdev"
    exit 1
fi

# -----------------------------------------------------------------------------
# 2. jq（必須）
# -----------------------------------------------------------------------------
# jqはJSONファイルのパースに使用されます
# setup_hid_gadget.sh で設定ファイルから値を読み取るために必要
if ! command_exists jq; then
    echo "エラー: 'jq' コマンドが見つかりません。"
    echo "解決策: 以下のコマンドを実行してください:"
    echo "  sudo apt-get update && sudo apt-get install jq"
    exit 1
fi

# -----------------------------------------------------------------------------
# 3. gpiozero（オプション、自動インストール試行）
# -----------------------------------------------------------------------------
# gpiozeroはGPIOボタン制御に使用されます
# KeyBowManagerクラスでボタン入力を処理するために必要
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

# -----------------------------------------------------------------------------
# 4. rpi_ws281x（オプション、自動インストール試行）
# -----------------------------------------------------------------------------
# rpi_ws281xはNeoPixel LED制御に使用されます
# リマップ状態の視覚的フィードバックを提供
if ! python3 -c "import rpi_ws281x" &> /dev/null; then
    echo "警告: Pythonライブラリ 'rpi_ws281x' が見つかりません。"
    echo "LED制御機能を使用する場合はインストールが必要です。"
    echo "自動インストールを試みます..."
    
    # pip3の存在確認とインストール
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
    
    # rpi_ws281xのビルドに必要なsconsのインストール
    if ! command_exists scons; then
        echo "ビルドツール 'scons' をインストールしています..."
        apt-get install -y scons
    fi
    
    # rpi_ws281xをシステムワイドにインストール
    # --break-system-packages: Python 3.11以降で外部管理されたパッケージへの
    # インストールを許可するオプション
    # systemdサービスはシステムのPython環境を使用するため、
    # システムワイドなインストールが必要
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

# =============================================================================
# パス設定
# =============================================================================
# スクリプトが存在するディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# プロジェクトルート（scriptsディレクトリの親）
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# インストール先ディレクトリ
INSTALL_DIR="/usr/local/bin"           # 実行ファイル
SERVICE_DIR="/etc/systemd/system"       # systemdサービス
CONFIG_DIR="/etc/multi-hid-proxy"       # 設定ファイル

echo "ファイルをインストールしています..."

# =============================================================================
# ディレクトリ作成
# =============================================================================
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$CONFIG_DIR"

# =============================================================================
# Pythonスクリプトのインストール
# =============================================================================
echo "Pythonスクリプトを配置します..."

# キーボードプロキシ関連ファイルをコピー
sudo cp "$PROJECT_ROOT/src/proxy_core.py" "$INSTALL_DIR/"      # 共通モジュール
sudo cp "$PROJECT_ROOT/src/keyboard_proxy.py" "$INSTALL_DIR/"  # キーボードプロキシ
sudo cp "$PROJECT_ROOT/src/hid_keys.py" "$INSTALL_DIR/"        # HIDキーマッピング
sudo cp "$SCRIPT_DIR/setup_hid_gadget.sh" "$INSTALL_DIR/"      # ガジェット設定スクリプト

# 実行権限を付与
sudo chmod +x "$INSTALL_DIR/keyboard_proxy.py"
sudo chmod +x "$INSTALL_DIR/setup_hid_gadget.sh"

# =============================================================================
# Rustバイナリのインストール
# =============================================================================
echo "Mouse Proxy (Rust) を配置します..."

# バイナリの検索
# 1. カレントディレクトリ（アーカイブ展開時）
# 2. プロジェクトルート
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

# =============================================================================
# 設定ファイルのインストール
# =============================================================================
# 設定ディレクトリが存在しない場合は作成
if [ ! -d "$CONFIG_DIR" ]; then
    sudo mkdir -p "$CONFIG_DIR"
fi

# 既存の設定ファイルがない場合のみサンプルからコピー
# ユーザーの設定を上書きしないように注意
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    echo "設定ファイルを配置します..."
    sudo cp "$PROJECT_ROOT/config/config.json.sample" "$CONFIG_DIR/config.json"
fi

# =============================================================================
# systemdサービスのインストール
# =============================================================================
echo "systemdサービスをインストールします..."

# サービスファイルをコピー
sudo cp "$PROJECT_ROOT/systemd/keyboard-proxy.service" "$SERVICE_DIR/"
sudo cp "$PROJECT_ROOT/systemd/mouse-proxy@.service" "$SERVICE_DIR/"  # テンプレートサービス（@）
sudo cp "$PROJECT_ROOT/systemd/multi-hid-gadget.service" "$SERVICE_DIR/"

# =============================================================================
# UDEVルールのインストール
# =============================================================================
echo "UDEVルールをインストールします..."

# マウスプロキシ用のudevルール
# マウスデバイスが接続されたときに自動的にプロキシサービスを起動
sudo cp "$PROJECT_ROOT/udev/99-mouse-proxy.rules" "/etc/udev/rules.d/"

# =============================================================================
# サービスの有効化
# =============================================================================
echo "Systemdサービスをリロードして有効化しています..."

# systemdに新しいサービスファイルを認識させる
sudo systemctl daemon-reload

# udevルールをリロード
sudo udevadm control --reload-rules
sudo udevadm trigger

# サービスを有効化（ブート時に自動起動）
sudo systemctl enable keyboard-proxy.service
sudo systemctl enable multi-hid-gadget.service

# =============================================================================
# 完了メッセージ
# =============================================================================
echo ""
echo "インストールが完了しました。"
echo "システムを再起動して変更を適用してください:"
echo "  sudo reboot"
