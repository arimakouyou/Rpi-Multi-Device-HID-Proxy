#!/bin/bash
# =============================================================================
# Multi HID Proxy アンインストールスクリプト
# =============================================================================
#
# このスクリプトは、Multi HID Proxyシステムを完全に削除します。
#
# 削除されるコンポーネント:
#   - Pythonスクリプト
#   - Rustバイナリ
#   - systemdサービスファイル
#   - udevルール
#   - 設定ファイルディレクトリ
#
# 注意:
#   - このスクリプトはroot権限で実行する必要があります
#   - 設定ファイルも含めてすべて削除されます
#
# 使用方法:
#   sudo ./uninstall.sh
#
# =============================================================================

# エラー発生時にスクリプトを終了
set -e

echo "Multi HID Proxy をアンインストールします..."

# =============================================================================
# root権限チェック
# =============================================================================
if [ "$(id -u)" -ne 0 ]; then
  echo "このスクリプトはroot権限で実行する必要があります。sudo ./uninstall.sh をお試しください。" >&2
  exit 1
fi

# =============================================================================
# サービスの停止と無効化
# =============================================================================
echo "サービスを停止・無効化します..."

# キーボードプロキシサービスを停止・無効化
# || true: サービスが存在しない場合でもエラーにならないようにする
systemctl stop keyboard-proxy.service || true
systemctl disable keyboard-proxy.service || true

# マウスプロキシサービス（テンプレートサービスのインスタンス）を停止・無効化
# ワイルドカードでアクティブなすべてのインスタンスを停止
systemctl stop 'mouse-proxy@*.service' || true
systemctl disable 'mouse-proxy@.service' || true

# HIDガジェット設定サービスを停止・無効化
systemctl stop multi-hid-gadget.service || true
systemctl disable multi-hid-gadget.service || true

# =============================================================================
# ファイルの削除
# =============================================================================
echo "ファイルを削除します..."

# --- 実行ファイル ---
# Pythonスクリプト
rm -f /usr/local/bin/proxy_core.py
rm -f /usr/local/bin/keyboard_proxy.py
rm -f /usr/local/bin/hid_keys.py
rm -f /usr/local/bin/setup_hid_gadget.sh

# Rustバイナリ
rm -f /usr/local/bin/mouse_proxy_rs

# --- systemdサービスファイル ---
rm -f /etc/systemd/system/keyboard-proxy.service
rm -f /etc/systemd/system/mouse-proxy@.service
rm -f /etc/systemd/system/multi-hid-gadget.service

# --- udevルール ---
rm -f /etc/udev/rules.d/99-mouse-proxy.rules

# --- 設定ファイルディレクトリ ---
# -rf: ディレクトリ内のすべてのファイルを再帰的に削除
rm -rf /etc/multi-hid-proxy

# =============================================================================
# systemdとudevのリロード
# =============================================================================
echo "Systemdデーモンをリロードしています..."

# 削除されたサービスファイルの情報をsystemdから消去
systemctl daemon-reload

# udevルールをリロード
udevadm control --reload-rules || true

# =============================================================================
# 完了メッセージ
# =============================================================================
echo "アンインストールが完了しました。"
