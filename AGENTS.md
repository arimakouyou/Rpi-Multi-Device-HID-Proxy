# AGENTS.md

このファイルは AI コーディングエージェント (Claude Code 等) がリポジトリの全体像を短時間で把握し、安全に変更点に到達するための要約です。詳細は本書末尾の「関連ドキュメント」リンク先で。

## プロジェクト概要

Raspberry Pi を **USB HID プロキシ**として動作させ、Pi に繋いだ複数のキーボード・マウスを 1 つの合成 HID デバイスとしてホスト PC に出力する。**Python (キーボード+GPIO+LED) + Rust (マウス) + systemd/ConfigFS (HID ガジェット)** の三層構成。物理ターゲットは **Pimoroni Keybow Mini** (3 キー + APA102 RGB LED 3 個、SPI 駆動)。

## リポジトリレイアウト

```
Rpi-Multi-Device-HID-Proxy/
├── AGENTS.md              # 本ファイル
├── README.md              # 一般ユーザー向け概要・クイックスタート
├── LICENSE
├── config/                # 設定ファイル（config.json と sample）
├── docs/                  # 詳細ドキュメント
│   ├── ARCHITECTURE.md    # 設計（三層構造、起動順序、データフロー、HIDレポート仕様）
│   ├── BUILD.md           # ビルド手順
│   ├── CONFIGURATION.md   # config.json と udev のリファレンス
│   ├── DEVELOPMENT.md     # 開発者ガイド（拡張方法、テスト戦略、PR ルール）
│   ├── HARDWARE.md        # 物理配線（GPIO / Keybow Mini APA102 / USB OTG）
│   └── INSTALL.md         # インストール手順
├── rust/mouse_proxy_rs/   # マウスプロキシ（Rust + tokio、単一ファイル実装）
├── scripts/               # ライフサイクル系シェルスクリプト
├── src/                   # キーボード/共通基盤の Python 実装
│   ├── hid_keys.py        # evdev → HID コード変換辞書
│   ├── keyboard_proxy.py  # キーボードプロキシ + GPIO/LED マネージャ
│   └── proxy_core.py      # 設定/ロギング/シャットダウン/デバイス管理
├── systemd/               # systemd ユニットファイル
└── udev/                  # マウスデバイス検出ルール
```

## 主要エントリポイント

| 種別 | ファイル | 行 | 補足 |
|---|---|---|---|
| Keyboard | `src/keyboard_proxy.py` | 781 | `if __name__ == "__main__"` |
| Mouse | `rust/mouse_proxy_rs/src/main.rs` | 271 | `#[tokio::main] async fn main` |
| HID Gadget | `scripts/setup_hid_gadget.sh` | — | bash + ConfigFS |
| 共通基盤 | `src/proxy_core.py` | — | `load_config`, `setup_logging`, `shutdown`, `manage_device_connections` |

## ビルド・実行コマンド

```bash
# リリースアーカイブ作成 (aarch64 クロスコンパイル)
./scripts/build_release.sh

# インストール (実機 Pi)
sudo ./scripts/install.sh

# 単体実行 (デバッグ用)
sudo python3 src/keyboard_proxy.py
cargo run --manifest-path rust/mouse_proxy_rs/Cargo.toml -- /dev/input/eventX /dev/hidg1

# ログ確認
sudo journalctl -u keyboard-proxy.service -f
sudo journalctl -u 'mouse-proxy@*.service' -f
sudo journalctl -u multi-hid-gadget.service
```

## 設計上の重要事実（嵌まりやすい順）

1. **マウス HID 出力が `/dev/hidg1` ハードコード**: `systemd/mouse-proxy@.service:8` が全インスタンスで `/dev/hidg1` を指定しており、複数マウス時の自動分配ロジックは現状コードに無い。`config.json` で `mouse_outputs` を複数並べても自動では使われない。
2. **hidg 番号の割当順**: `scripts/setup_hid_gadget.sh:146-200` がキーボード関数を先、マウス関数を後に作るため、標準構成では `/dev/hidg0` = Keyboard、`/dev/hidg1`,`/dev/hidg2` = Mouse。
3. **GPIO ピン**: Btn1=GPIO 6、Btn2=GPIO 22、Btn3=GPIO 17（`src/keyboard_proxy.py` の `KeyBowManager.__init__` でハードコード）。**LED は GPIO 直結ではなく SPI バス経由 (Pimoroni Keybow Mini の APA102)**。`/dev/spidev0.0` (= GPIO10/MOSI + GPIO11/SCLK) を `python3-spidev` で叩く実装。`led_settings.spi_bus / spi_device` で切替可能。
4. **HID レポートサイズ**: Keyboard=8 バイト（modifier/reserved/key×6）、Mouse=7 バイト（button/X i16/Y i16/wheel i16、リトルエンディアン）。**水平ホイール (REL_HWHEEL) 非対応**（`rust/mouse_proxy_rs/src/main.rs:232`）。
5. **設定ファイル検索順**: `/etc/multi-hid-proxy/config.json` → スクリプト同階層 → CWD（`src/proxy_core.py:84-89`、`scripts/setup_hid_gadget.sh:40-48`）。`load_config` は組み込みデフォルト (`DEFAULT_CONFIG`) とユーザー設定を **深い再帰マージ** する。ネスト辞書同士は再帰、それ以外は上書き。`DEFAULT_CONFIG` に無いキーもユーザー設定からそのまま取り込まれる (`src/proxy_core.py:_deep_merge`)。
6. **キーボード grab で排他取得**: `src/keyboard_proxy.py:142` の `device.grab()` により Pi のローカル端末からは入力が見えなくなる。デバッグ時は注意。
7. **テスト基盤なし**: 自動テストは未整備。動作確認は実機での手動検証に依存。
8. **systemd 起動順**: `systemd-modules-load (dwc2,libcomposite)` → `multi-hid-gadget` (`Before=sysinit.target`, oneshot) → `keyboard-proxy` ／ udev → `mouse-proxy@event*`。

## 編集時のハマりどころ

- **HID Descriptor 変更**: `scripts/setup_hid_gadget.sh:168` (KB) / `:199` (Mouse) のバイト列を変える場合、同ファイルの `protocol` と `report_length`、および送信側 (`src/keyboard_proxy.py` の `update_state` / `rust/mouse_proxy_rs/src/main.rs` の `to_report`) を**3 点同時に**揃える必要がある。1 つでもズレるとホスト側で「Code 10」エラー。
- **udev ルール変更後**: `sudo udevadm control --reload-rules && sudo udevadm trigger` を必ず実行。
- **`REMAP_ENABLED` グローバル**: `src/keyboard_proxy.py:48` のモジュールスコープ変数。GPIO Btn1 長押しで書き換わる (`keyboard_proxy.py:620`)。テストで初期値を仮定するなら明示リセットが必要。
- **`CONFIGURATION.md` の GPIO ピン**: 旧版で誤記があったが訂正済み (5/6/17 → 6/22/17)。引用元として参照する場合は最新版を確認。
- **メールアドレス入力機能**: `config.json` の `email_address` を Btn1+Btn2 同時長押しで HID 経由で打鍵する。秘密にしたい値ではないが、サンプル以外の本番値をコミットしないよう注意。
- **systemd ファイル変更**: `/etc/systemd/system/` への配置変更後に `sudo systemctl daemon-reload` を忘れると古い定義が動き続ける。

## 関連ドキュメント

- [README.md](README.md) — プロジェクト概要・クイックスタート
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 設計の単一ソース（why）
- [docs/HARDWARE.md](docs/HARDWARE.md) — 物理配線・ピンマップ
- [docs/INSTALL.md](docs/INSTALL.md) — インストール手順
- [docs/BUILD.md](docs/BUILD.md) — ビルド手順
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — 設定値リファレンス（how）
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — 拡張方法・テスト戦略・PR ガイドライン
