#!/bin/bash
set -e

# プロジェクトルートディレクトリ (スクリプトのある場所)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
ARCHIVE_NAME="multi-hid-proxy-release.tar.gz"

echo "=== Multi HID Proxy ビルドスクリプト開始 ==="

# 1. Rustプロジェクトのビルド
echo "[1/4] Rustバイナリ (mouse_proxy_rs) をビルドしています..."
cd "${PROJECT_ROOT}/rust/mouse_proxy_rs"
# クロスコンパイルが必要な場合はここで指定しますが、
# ここではネイティブビルド (または環境変数での指定) を想定しています。
# RPi上でビルドする場合は単に cargo build --release

# cargoコマンドがない場合、パスを通してみる
if ! command -v cargo &> /dev/null; then
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
fi

if command -v cargo &> /dev/null; then
    cargo build --release
else
    echo "エラー: cargo コマンドが見つかりません。Rust環境をインストールしてください。"
    exit 1
fi

# ビルド成果物の確認
BINARY_PATH="${PROJECT_ROOT}/rust/mouse_proxy_rs/target/release/mouse_proxy_rs"
if [ ! -f "$BINARY_PATH" ]; then
    echo "エラー: バイナリのビルドに失敗しました ($BINARY_PATH が見つかりません)"
    exit 1
fi

# 2. 配布用ディレクトリの作成とクリーンアップ
echo "[2/4] 配布用ディレクトリ ($DIST_DIR) を準備しています..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 3. ファイルのコピー
echo "[3/4] 必要なファイルをコピーしています..."

# バイナリ
cp "$BINARY_PATH" "$DIST_DIR/"

# スクリプトと設定ファイル
# install.sh はルートにあるものをコピー
cp "${PROJECT_ROOT}/install.sh" "$DIST_DIR/"
cp "${PROJECT_ROOT}/config.json.sample" "$DIST_DIR/"

# Pythonスクリプト (Keyboard Proxy等はまだPythonなので)
cp "${PROJECT_ROOT}/proxy_core.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/keyboard_proxy.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/hid_keys.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/setup_hid_gadget.sh" "$DIST_DIR/"

# systemd サービスファイル
cp "${PROJECT_ROOT}/keyboard-proxy.service" "$DIST_DIR/"
cp "${PROJECT_ROOT}/mouse-proxy@.service" "$DIST_DIR/"
cp "${PROJECT_ROOT}/multi-hid-gadget.service" "$DIST_DIR/"

# udev ルール
cp "${PROJECT_ROOT}/99-mouse-proxy.rules" "$DIST_DIR/"

# 実行権限の付与 (念のため)
chmod +x "$DIST_DIR/install.sh"
chmod +x "$DIST_DIR/mouse_proxy_rs"
chmod +x "$DIST_DIR"/*.py
chmod +x "$DIST_DIR"/*.sh

# 4. アーカイブの作成
echo "[4/4] アーカイブ ($ARCHIVE_NAME) を作成しています..."
cd "${PROJECT_ROOT}"
# dist ディレクトリの中身をアーカイブする (展開時に散らばらないようにフォルダを含めるか、カレントに展開するか)
# ここでは dist の中身をトップレベルとしてアーカイブします。
# ユーザーが mkdir して展開することを想定、または install.sh で配慮。
# 一般的にはフォルダ一つ掘ったほうが親切ですが、install.sh がルートにあると便利なので
# そのままアーカイブします。

tar -czvf "$ARCHIVE_NAME" -C "$DIST_DIR" .

echo "=== ビルド完了 ==="
echo "生成されたアーカイブ: ${PROJECT_ROOT}/${ARCHIVE_NAME}"
