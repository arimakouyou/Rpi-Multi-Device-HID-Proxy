# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## コマンド

### インストール/アンインストール
```bash
sudo ./install.sh      # システムにインストール
sudo ./uninstall.sh    # システムからアンインストール
```

### 設定ファイル
```bash
cp config.json.sample config.json  # 設定ファイルを作成
```

### テスト/動作確認
```bash
# デバイス名の確認
python3 -c "import evdev; [print(f'Path: {p}, Name: \"{evdev.InputDevice(p).name}\"') for p in evdev.list_devices()]"

# プロキシプログラムの手動実行（デバッグ用）
python3 multi_device_proxy.py

# サービスの状態確認
sudo systemctl status multi-hid-gadget.service
sudo systemctl status multi-hid-proxy.service

# ログの確認
sudo journalctl -u multi-hid-proxy.service -f
```

### 依存関係の確認とインストール
```bash
# 必須パッケージの確認
python3 -c "import evdev"  # evdevライブラリ
command -v jq              # jqコマンド

# パッケージのインストール
sudo apt-get update && sudo apt-get install python3-evdev jq
```

## アーキテクチャ

### システム構成
このプロジェクトは、Raspberry PiをBluetoothキーボード・マウスのUSBプロキシデバイスとして機能させるシステムです。

**コア機能**:
- 複数のBluetoothデバイス（キーボード・マウス）を単一のUSB HIDガジェットとして統合
- 動的なデバイス接続・切断への対応
- US配列→日本語配列のキーリマップ機能
- GPIO連携による追加機能

### メインコンポーネント

1. **multi_device_proxy.py** - メインのプロキシプログラム
   - evdevを使用したデバイス監視とイベント処理
   - 非同期I/Oによる複数デバイスの同時処理
   - HIDレポートの生成と送信

2. **setup_hid_gadget.sh** - USB HIDガジェット設定スクリプト
   - USB compositeガジェットの設定（キーボード+マウス）
   - `/sys/kernel/config/usb_gadget`での設定
   - HIDデスクリプタの定義

3. **hid_keys.py** - HIDキーコードマッピング
   - evdevキーコード → USB HIDキーコードの変換テーブル

### 設定システム
- **設定ファイルの優先順位**:
  1. `/etc/multi-hid-proxy/config.json` (システム設定)
  2. `<script_dir>/config.json` (ローカル設定)
  3. `config.json` (カレントディレクトリ)
- **hot reload**: 設定変更時はサービス再起動が必要

### HIDガジェット構成
- **キーボード**: `/dev/hidg0` (boot protocol対応)
- **マウス**: `/dev/hidg1`, `/dev/hidg2` (2デバイス分)
- **USB設定**: Linux Foundation VID/複数機能ガジェット

### サービス管理
- **multi-hid-gadget.service**: USB HIDガジェット設定（起動時実行）
- **multi-hid-proxy.service**: プロキシプログラム（常駐）
- **依存関係**: gadget → proxy の順序で起動

## 重要な設計原則

### デバイス検出とマッチング
- 正規表現パターンによるデバイス名マッチング (`keyboard_patterns`, `mouse_patterns`)
- デバイスのホットプラグ対応（5秒間隔での監視）
- 入力イベントの種類によるデバイス分類（EV_KEY/EV_REL）

### HIDレポート処理
- キーボード: 8バイトboot protocol形式
- マウス: 4バイトレポート（ボタン+X/Y移動+ホイール）
- 複数デバイスからの入力を単一HIDストリームに統合

### エラーハンドリング
- ファイルI/O例外の適切な処理（BlockingIOError等）
- デバイス切断時の自動復旧
- サービス間の依存関係管理

### メモリとパフォーマンス
- デバイススキャンの最適化が課題（EFFICIENCY_REPORT.md参照）
- 非同期処理による応答性確保
- HIDデバイスファイルの適切なopen/close管理

## デバッグのヒント

### よくある問題
1. **デバイスが認識されない**: パターンマッチングの確認
2. **HIDガジェットが作成されない**: configfs mount状態とroot権限の確認
3. **キー入力が効かない**: HIDレポート形式とデスクリプタの整合性確認
4. **パフォーマンス問題**: デバイススキャン頻度の調整

### ログとモニタリング
- journaldでサービスログを確認
- プロキシプログラムはprint文とloggingの両方を使用
- GPIO機能使用時はgpiozeroライブラリが必要