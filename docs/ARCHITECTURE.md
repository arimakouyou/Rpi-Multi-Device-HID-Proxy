# アーキテクチャ

本ドキュメントは Rpi-Multi-Device-HID-Proxy の内部設計を記述します。インストール手順は [INSTALL.md](INSTALL.md)、設定方法は [CONFIGURATION.md](CONFIGURATION.md)、ビルド手順は [BUILD.md](BUILD.md) を参照してください。

## 1. システム概観

Raspberry Pi を **USB HID ガジェット**として動作させ、Pi に接続された複数の入力デバイス (キーボード・マウス) からのイベントを統合し、ホスト PC からは「単一の合成 HID デバイス」として見えるようにします。

```
   [USB キーボード ×N]
   [USB マウス ×M]    ──┐
                         │ evdev (/dev/input/event*)
                         ▼
   ┌──────────────────────────────────────────────────┐
   │  Raspberry Pi (USB OTG モード)                   │
   │                                                  │
   │  ┌─────────────────────────┐                     │
   │  │ keyboard-proxy.service  │  Python / asyncio   │
   │  │  ・KeyboardProxy        │                     │
   │  │  ・KeyBowManager        │                     │
   │  │  ・device_monitor       │                     │
   │  └────────────┬────────────┘                     │
   │               │                                  │
   │  ┌────────────┴────────────┐                     │
   │  │ mouse-proxy@event*  ×M  │  Rust / tokio       │
   │  └────────────┬────────────┘                     │
   │               │ /dev/hidg0..N                    │
   │               ▼                                  │
   │  ┌─────────────────────────┐                     │
   │  │ multi-hid-gadget.service│  ConfigFS + dwc2    │
   │  │  (USB Composite Gadget) │                     │
   │  └────────────┬────────────┘                     │
   └───────────────┼──────────────────────────────────┘
                   │
   ════════════════╪══════════════════════════ Pi/PC 境界 (USB OTG)
                   │
                   ▼
   [ホスト PC] が「Multi-HID-Proxy」を 1 つの HID デバイスとして認識
```

USB Composite Gadget の正体は **ConfigFS** で構築される単一論理デバイス (`VID=0x1d6b`, `PID=0x013d`, `Product="Multi-HID-Proxy"`、`scripts/setup_hid_gadget.sh:58-66`) で、内部に複数のキーボード機能とマウス機能を持ちます。

## 2. プロセス構成と責務分離

| サービス | 実装 | プロセス数 | 責務 |
|---|---|---|---|
| `multi-hid-gadget.service` | bash + ConfigFS (`scripts/setup_hid_gadget.sh`) | 1 (oneshot) | USB ガジェットの構築。`/dev/hidg0..N` を生成 |
| `keyboard-proxy.service` | Python + asyncio (`src/keyboard_proxy.py`) | 1 (常駐) | 全キーボードの evdev → HID 変換、GPIO ボタン処理、Keybow Mini APA102 LED 制御 |
| `mouse-proxy@.service` | Rust + tokio (`rust/mouse_proxy_rs/src/main.rs`) | デバイス毎に 1 | 単一マウスの evdev → HID 変換 |

### Python と Rust に分けている理由

- マウスは **高頻度・低レイテンシ要求**が強く、Rust + tokio による非同期 I/O で確実に処理する。
- キーボードは **リマップロジックが複雑** (US→JIS 変換、Shift 修飾、リマップ on/off 切替) で、Python の方が見通しよく拡張できる。GPIO/LED も Python ライブラリ (`gpiozero`, `spidev`) との親和性が高い。

## 3. 起動シーケンス

systemd 依存グラフは以下のとおりです:

```
   [systemd-modules-load.service]      (dwc2, libcomposite ロード)
              │
              │ After=
              ▼
   [multi-hid-gadget.service]          (oneshot, ConfigFS 構築)
        Before=sysinit.target
              │
              │ Wants= / udev トリガ
              ▼
   ┌──────────────┴──────────────┐
   │                             │
   ▼                             ▼
[keyboard-proxy.service]    [mouse-proxy@event*.service]
   (Python 常駐)               (Rust、デバイス毎に 1)
                                 ▲
                                 │ ENV{SYSTEMD_WANTS}+=
                                 │
                          [udev/99-mouse-proxy.rules]
                          (デバイス追加検出)
```

参照: `systemd/multi-hid-gadget.service:1-13`, `systemd/keyboard-proxy.service:1-13`, `systemd/mouse-proxy@.service:1-9`, `udev/99-mouse-proxy.rules`

`multi-hid-gadget.service` は `Before=sysinit.target` で sysinit 前に走り、`Type=oneshot` + `RemainAfterExit=yes` のため一度だけ ConfigFS をセットアップして以降は「成功状態」を維持します。

マウスは udev が動的に検出して起動する**テンプレートサービス**です。デバイス名 (`HHKB-Studio[1-4] Mouse`、`Logitech*`) にマッチした `event*` が `/dev/input` に現れると、`mouse-proxy@event2.service` のようにインスタンス化されます。

## 4. データフロー

### 4.1 キーボード

```
   evdev (grab)                     proxy_core              hid_keys
   /dev/input/eventX  ──read_one──▶  KeyboardProxy ──remap──▶ HIDコード変換
                                          │
                                          │ update_state
                                          ▼
                              [8バイト HIDレポート]
                                          │
                                          │ write
                                          ▼
                                    /dev/hidg0
```

主要箇所:
- 排他取得 (`grab()`): `src/keyboard_proxy.py:128-147`
- イベント読取り (`run_in_executor` でブロッキング読みを非同期化): `src/keyboard_proxy.py:162-194`
- イベント処理: `src/keyboard_proxy.py:196-229`
- リマップ (US→JIS、Shift 一時抑制/付与など): `src/keyboard_proxy.py:270-324`
- レポート送信: `src/keyboard_proxy.py:326-364`

### 4.2 マウス

```
   evdev (tokio stream)                MouseState              to_report()
   /dev/input/eventY  ─next_event─▶  状態更新 (btn/X/Y/wheel) ─▶ 7バイト
                                            │  ▲
                                       SYN受信時 │
                                            ▼  │ reset_rel() で X/Y/wheel をクリア
                                  [7バイト HIDレポート]
                                            │
                                            │ write_all
                                            ▼
                                       /dev/hidg1
```

主要箇所: `rust/mouse_proxy_rs/src/main.rs:181-262` (`run_proxy`)。`MouseState::to_report()` は `main.rs:122-148`。

## 5. HID レポート仕様

### 5.1 キーボード (8 バイト)

```
 byte:  0           1           2     3     4     5     6     7
       ┌─────────┐ ┌─────────┐ ┌────┬────┬────┬────┬────┬────┐
       │modifier │ │reserved │ │key1│key2│key3│key4│key5│key6│
       └─────────┘ └─────────┘ └────┴────┴────┴────┴────┴────┘

 modifier ビット割当 (USB HID 標準):
   bit0=LCtrl  bit1=LShift bit2=LAlt   bit3=LGUI
   bit4=RCtrl  bit5=RShift bit6=RAlt   bit7=RGUI
```

- レポート組み立て: `src/keyboard_proxy.py:330-364`
- HID Descriptor: `scripts/setup_hid_gadget.sh:168` (USB HID 標準のキーボード記述子)
- `protocol=1` (Boot Keyboard)、`subclass=1` (Boot Interface) — BIOS でも認識可能

### 5.2 マウス (7 バイト、リトルエンディアン)

```
 byte:   0          1   2          3   4          5   6
        ┌────────┐ ┌──────────┐  ┌──────────┐  ┌──────────┐
        │buttons │ │  X (i16) │  │  Y (i16) │  │ wheel    │
        └────────┘ └──────────┘  └──────────┘  │  (i16)   │
                                               └──────────┘

 buttons ビット割当:
   bit0=Left   bit1=Right  bit2=Middle  bit3=Side  bit4=Extra
```

- レポート組み立て: `rust/mouse_proxy_rs/src/main.rs:122-148`
- HID Descriptor: `scripts/setup_hid_gadget.sh:199` (5 ボタン + XYWheel 各 16bit)
- `protocol=2` (Mouse)、`subclass=0`

## 6. デバイス検出と HID 出力割り当て

### 6.1 hidg 番号の割り付け

`scripts/setup_hid_gadget.sh` は `config.json` の `hid_paths.keyboard_outputs` と `mouse_outputs` の **配列長**から動的に hidg 数を決めます (`setup_hid_gadget.sh:51-52`)。生成順は **キーボードが先**、その後マウスです (`setup_hid_gadget.sh:146-200`)。

したがって標準構成 (KB×1、Mouse×2) では:

| デバイス | hidg |
|---|---|
| キーボード合成出力 | `/dev/hidg0` |
| マウス合成出力 #1 | `/dev/hidg1` |
| マウス合成出力 #2 | `/dev/hidg2` |

### 6.2 キーボードプロキシのデバイス検出

`device_monitor` (`src/keyboard_proxy.py:710-775`) が 5 秒間隔で `/dev/input/event*` をポーリングし、正規表現で対象デバイス名 (`HHKB-Studio[1-4] Keyboard|HHKB-Hybrid.*|PFU.*` 等) にマッチするものを `KeyboardProxy` に割り当てます。利用可能な `/dev/hidgN` は `available_keyboard_hids` プールから払い出されます (`src/proxy_core.py:268-327`)。

### 6.3 マウスプロキシのデバイス検出

udev (`udev/99-mouse-proxy.rules`) がデバイス名 (`HHKB-Studio[1-4] Mouse`、`Logitech*`) にマッチした `event*` を検出し、`SYSTEMD_WANTS` で `mouse-proxy@event*.service` を起動します。

### 6.4 既知の制約: 複数マウス時の出力競合

`systemd/mouse-proxy@.service:8` の ExecStart は **すべてのインスタンスで `/dev/hidg1` を指定**しています。複数のマウスが同時接続されても、各インスタンスが固定で hidg1 に書き込むため出力の取り合いになります。`config.json` で `mouse_outputs` を複数指定して `/dev/hidg2` を生成しても、現状の実装ではマウス側にデバイス→hidg の自動割当ロジックがありません。

実用的な複数マウス対応には以下のいずれかが必要です:
- マウス分の `mouse-proxy@.service` を出力デバイス別にコピーし、ExecStart 引数を変える
- udev ルール側で `ENV{SYSTEMD_WANTS}` を分けて出力デバイス別のテンプレートに振り分ける
- `mouse_proxy_rs` 側に hidg プール払い出し機構を追加する

## 7. 設定ファイル読み込みパス

`load_config` (`src/proxy_core.py:84-89, 113-124`) は次の順で `config.json` を探し、最初に見つかったものを使用します:

1. `/etc/multi-hid-proxy/config.json` (システムインストール時のデフォルト)
2. スクリプトと同じディレクトリ (`SCRIPT_DIR/config.json`)
3. カレントディレクトリ (`./config.json`)

読み込んだ JSON は組み込みのデフォルト辞書と再帰マージされるため、設定ファイル側に書かなかったキーはデフォルト値で補完されます。

`scripts/setup_hid_gadget.sh:40-48` も同等のロジックでスクリプト同階層 → `/etc/multi-hid-proxy/` の順で探します。

## 8. ロギングとシャットダウン

### 8.1 ロギング

`setup_logging` (`src/proxy_core.py:161-166`) は環境変数 `INVOCATION_ID` の有無で出力フォーマットを切り替えます。`INVOCATION_ID` は systemd が起動したプロセスに自動で渡される変数で、これが存在する場合は journald に渡されることを前提としたシンプルなフォーマット、無い場合 (=コマンドラインから直接実行) はタイムスタンプを含むフォーマットになります。

Rust 側 (`rust/mouse_proxy_rs/src/main.rs:271-274`) は `env_logger::init()` を使うため、`RUST_LOG=debug` などで制御します。

### 8.2 シャットダウン

`SIGHUP` / `SIGTERM` / `SIGINT` を受信すると `proxy_core.shutdown()` (`src/proxy_core.py:171-205`) が走ります:

1. すべての asyncio タスクをキャンセル
2. デバイスのリリース (`grab` 解除) と HID 出力のクローズ
3. `loop.stop()` でイベントループ停止

シグナルハンドラ登録は `src/keyboard_proxy.py:790` で行われています。

## 9. 設計上のトレードオフと既知の制約

| 項目 | 内容 | 該当箇所 |
|---|---|---|
| マウス出力ハードコード | 全インスタンスで `/dev/hidg1` 固定 | `systemd/mouse-proxy@.service:8` |
| 水平ホイール非対応 | `REL_HWHEEL` を捨てている | `rust/mouse_proxy_rs/src/main.rs:232` |
| キーボード grab 排他取得 | Pi のローカル端末からは入力が見えなくなる | `src/keyboard_proxy.py:142` |
| LED は SPI バス占有 | Pimoroni Keybow Mini の APA102 を `python3-spidev` 経由で駆動。`/dev/spidev0.0` を使用 | `src/keyboard_proxy.py` 内 `LedStatusManager` |
| GPIO ピンがハードコード | Btn1=GPIO6、Btn2=GPIO22、Btn3=GPIO17 を変更するにはソース改変が必要 | `src/keyboard_proxy.py` 内 `KeyBowManager.__init__` |
| 自動テスト基盤なし | 単体テスト・統合テストの整備は今後の課題 | — |

これらの制約と背景を理解した上での拡張方針は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。
