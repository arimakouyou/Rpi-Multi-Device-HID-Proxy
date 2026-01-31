#!/usr/bin/python3
"""
Keyboard Proxy - キーボードプロキシ
====================================

このモジュールは、複数のUSBキーボードデバイスからの入力を受け取り、
USB HIDガジェットデバイスに転送するプロキシサービスを提供します。

主な機能:
- 複数キーボードの同時管理
- USキー配列からJIS配列への自動リマップ
- GPIOボタンによる特殊機能（メール入力、シャットダウン等）
- NeoPixel LEDによる状態表示

動作環境:
- Raspberry Pi（USB HIDガジェットモードが有効な環境）
- Python 3.7以降
- evdevライブラリ
- gpiozeroライブラリ（GPIO機能用、オプション）
- rpi_ws281xライブラリ（LED機能用、オプション）

使用方法:
    直接実行:
        python3 keyboard_proxy.py
    
    systemdサービスとして:
        sudo systemctl start keyboard-proxy.service
"""

import logging
import asyncio
import signal
import re
import evdev
from evdev import InputDevice, ecodes
from hid_keys import hid_key_map as hid_keys
import proxy_core

# =============================================================================
# 初期化処理
# =============================================================================
# 設定ファイルを読み込み、ロギングを設定
CONFIG = proxy_core.load_config()
proxy_core.setup_logging(CONFIG)

# リマップ機能の有効/無効フラグ（グローバル変数）
# GPIOボタンまたは他の方法でトグル可能
REMAP_ENABLED = True

# =============================================================================
# GPIOライブラリのインポート（オプション）
# =============================================================================
# gpiozeroライブラリが利用できない環境（非Raspberry Pi）でも
# プロキシの基本機能は動作するように、フォールバッククラスを定義
try:
    from gpiozero import Button
except ImportError:
    logging.warning("gpiozero library not found. GPIO button functions disabled.")
    # ダミーのButtonクラス - すべての操作を無視
    class Button:
        def __init__(self, *args, **kwargs): pass
        def __getattr__(self, name): return lambda *args, **kwargs: None

# =============================================================================
# NeoPixelライブラリのインポート（オプション）
# =============================================================================
# rpi_ws281xライブラリが利用できない環境でもプロキシは動作
try:
    from rpi_ws281x import PixelStrip, Color
    NEOPIXEL_AVAILABLE = True
except ImportError:
    logging.warning("rpi_ws281x library not found. LED functions disabled.")
    NEOPIXEL_AVAILABLE = False
    # ダミークラス定義
    class PixelStrip:
        def __init__(self, *args, **kwargs): pass
        def begin(self): pass
        def setPixelColor(self, *args, **kwargs): pass
        def show(self): pass
        def setBrightness(self, *args, **kwargs): pass
    Color = lambda r, g, b: 0


class KeyboardProxy:
    """
    キーボードプロキシクラス
    
    1つの入力デバイス（キーボード）からイベントを受け取り、
    USB HIDガジェットデバイスに転送します。
    キー配列のリマップ機能も提供します。
    
    Attributes:
        input_device_path (str): 入力デバイスのパス（例: /dev/input/event0）
        hid_output_path (str): HID出力デバイスのパス（例: /dev/hidg0）
        device (evdev.InputDevice): 入力デバイスオブジェクト
        modifier (int): 現在押されているモディファイアキーのビットマスク
        pressed_keys (set): 現在押されているキーのセット
    """
    
    def __init__(self, input_device_path, hid_output_path, loop):
        """
        キーボードプロキシを初期化します。
        
        Args:
            input_device_path (str): 入力デバイスのパス
            hid_output_path (str): HID出力デバイスのパス
            loop (asyncio.AbstractEventLoop): 非同期イベントループ
        """
        # インスタンス固有のロガーを作成（デバイスパスをサフィックスに使用）
        self.log = logging.getLogger(f"KeyboardProxy-{input_device_path.split('/')[-1]}")
        self.loop = loop
        self.input_device_path = input_device_path
        self.hid_output_path = hid_output_path
        self.device = None
        
        # モディファイアキーとビット位置のマッピング
        # HIDレポートの最初のバイトは8ビットのモディファイアビットマスク:
        #   bit 0: 左Ctrl,  bit 1: 左Shift, bit 2: 左Alt,  bit 3: 左Meta(Win)
        #   bit 4: 右Ctrl,  bit 5: 右Shift, bit 6: 右Alt,  bit 7: 右Meta(Win)
        self.modifiers_map = {
            'KEY_LEFTCTRL': 0, 'KEY_LEFTSHIFT': 1, 'KEY_LEFTALT': 2, 'KEY_LEFTMETA': 3, 
            'KEY_RIGHTCTRL': 4, 'KEY_RIGHTSHIFT': 5, 'KEY_RIGHTALT': 6, 'KEY_RIGHTMETA': 7
        }
        
        # 状態をリセット
        self.reset_state()

    def connect_device(self):
        """
        入力デバイスに接続し、排他的にキャプチャします。
        
        Returns:
            bool: 接続に成功した場合はTrue、失敗した場合はFalse
        
        Note:
            grab()によりデバイスを排他的に取得するため、
            他のプロセス（Xサーバーなど）はこのキーボードからの入力を受け取りません。
        """
        try:
            self.device = InputDevice(self.input_device_path)
            # デバイスを排他的に取得（他のプロセスからのアクセスをブロック）
            self.device.grab()
            self.log.info(f"Keyboard captured: {self.device.path} ({self.device.name}) -> {self.hid_output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to connect to {self.input_device_path}: {e}")
            return False

    def reset_state(self):
        """
        キーボードの内部状態をリセットします。
        
        デバイス再接続時やエラー発生時に呼び出し、
        押されっぱなしのキーやモディファイアをクリアします。
        """
        self.modifier = 0b00000000    # モディファイアビットマスク
        self.pressed_keys = set()      # 押下中の通常キー
        self.is_shift_up = False       # Shiftを一時的に押す必要があるフラグ
        self.is_shift_down = False     # Shiftを一時的に離す必要があるフラグ
        self.shift_bit = 0b00100010    # 左右Shiftのビットマスク（bit 1 と bit 5）

    async def run(self):
        """
        プロキシのメインループを実行します。
        
        入力デバイスからのイベントを継続的に読み取り、処理します。
        デバイスが切断された場合は再接続を試みます。
        """
        while True:
            # デバイス未接続または接続失敗時は5秒待機して再試行
            if not self.device and not self.connect_device():
                await asyncio.sleep(5)
                continue
            try:
                while True:
                    # 非同期でイベントを読み取り
                    # run_in_executor を使用してブロッキング読み取りを非同期化
                    event = await self.loop.run_in_executor(None, self.device.read_one)
                    if event is None:
                        # イベントがない場合は短時間待機
                        await asyncio.sleep(0.01)
                        continue
                    # イベントを処理
                    self.process_event(event)
            except (OSError, asyncio.CancelledError) as e:
                # デバイス切断またはタスクキャンセル
                self.log.error(f"Keyboard {self.input_device_path} disconnected: {type(e).__name__}")
                if self.device:
                    self.device.close()
                self.device = None
                break
            except Exception as e:
                self.log.error(f"Unexpected error: {e}", exc_info=True)
                break

    def process_event(self, event):
        """
        入力イベントを処理します。
        
        キーイベント（EV_KEY）のみを処理し、他のイベントタイプは無視します。
        
        Args:
            event (evdev.InputEvent): 処理するイベント
        """
        # キーイベント以外は無視
        if event.type != ecodes.EV_KEY:
            return

        try:
            # イベントコードからキー名を取得
            keycode = ecodes.KEY[event.code]
        except (IndexError, KeyError):
            self.log.debug(f"Ignoring unknown keycode: {event.code}")
            return
        
        # 一部のキーコードはリスト（複数のエイリアス）として返される
        if isinstance(keycode, list):
            keycode = keycode[0]

        # キーの状態: 0=リリース, 1=プレス, 2=リピート
        keystate = event.value

        # モディファイアキーは別処理
        if keycode in self.modifiers_map:
            self.update_modifier(keycode, keystate)
        elif keystate == 0:  # キーリリース
            self.release(keycode)
        elif keystate == 1 or keystate == 2:  # キープレスまたはリピート
            self.press(keycode)

    def update_modifier(self, keycode, keystate):
        """
        モディファイアキーの状態を更新します。
        
        Args:
            keycode (str): モディファイアキーのキーコード
            keystate (int): キーの状態（0=リリース, 1=プレス, 2=リピート）
        """
        if keystate == 0:
            # キーリリース: 対応するビットをクリア
            self.modifier &= ~(1 << self.modifiers_map[keycode])
        else:
            # キープレス: 対応するビットをセット
            self.modifier |= (1 << self.modifiers_map[keycode])
        # HIDレポートを送信
        self.update_state()

    def release(self, keycode):
        """
        通常キーのリリースを処理します。
        
        Args:
            keycode (str): リリースされたキーのキーコード
        """
        if keycode in self.pressed_keys:
            self.pressed_keys.remove(keycode)
            self.update_state()

    def press(self, keycode):
        """
        通常キーのプレスを処理します。
        
        Args:
            keycode (str): プレスされたキーのキーコード
        """
        if keycode not in self.pressed_keys:
            self.pressed_keys.add(keycode)
            self.update_state()

    def remap(self, keycode):
        """
        キーコードをリマップ（USキー配列からJIS配列へ変換）します。
        
        REMAP_ENABLEDがFalseの場合、リマップなしでそのまま返します。
        
        主なリマップ:
        - [ -> ]
        - ] -> \
        - Shift+7 -> Shift+6 (&を^に)
        - Shift+8 -> ' (アスタリスクをアポストロフィに)
        - など
        
        Args:
            keycode (str): リマップ前のキーコード
        
        Returns:
            int: リマップ後のHIDキーコード
        """
        global REMAP_ENABLED
        if not REMAP_ENABLED:
            # リマップ無効時はそのまま変換
            return hid_keys.get(keycode, 0)
        if keycode not in hid_keys: 
            return 0
        
        # === 基本的なキーリマップ ===
        # 左角括弧 -> 右角括弧
        if keycode == 'KEY_LEFTBRACE': 
            keycode = 'KEY_RIGHTBRACE'
        # 右角括弧 -> バックスラッシュ
        elif keycode == 'KEY_RIGHTBRACE': 
            keycode = 'KEY_BACKSLASH'
        # === Shiftキーが押されている場合のリマップ ===
        elif self.modifier & self.shift_bit:
            if keycode == 'KEY_7': keycode = 'KEY_6'        # Shift+7(&) -> Shift+6(^)
            elif keycode == 'KEY_8': keycode = 'KEY_APOSTROPHE'  # Shift+8(*) -> '
            elif keycode == 'KEY_9': keycode = 'KEY_8'      # Shift+9(() -> Shift+8(*)
            elif keycode == 'KEY_0': keycode = 'KEY_9'      # Shift+0()) -> Shift+9(()
            elif keycode == 'KEY_EQUAL': keycode = 'KEY_SEMICOLON'  # Shift+=(+) -> Shift+;(:)
            elif keycode == 'KEY_GRAVE': keycode = 'KEY_EQUAL'     # Shift+`(~) -> Shift+=(+)
            elif keycode == 'KEY_MINUS': keycode = 'KEY_RO'        # Shift+-(_) -> _（JIS配列）
            elif keycode == 'KEY_2': keycode = 'KEY_LEFTBRACE'; self.is_shift_down = True  # Shift+2(@) -> [
            elif keycode == 'KEY_6': keycode = 'KEY_EQUAL'; self.is_shift_down = True      # Shift+6(^) -> =
            elif keycode == 'KEY_BACKSLASH': keycode = 'KEY_YEN'    # Shift+\(|) -> |（JIS配列）
            elif keycode == 'KEY_SEMICOLON': keycode = 'KEY_APOSTROPHE'; self.is_shift_down = True  # Shift+;(:) -> '
            elif keycode == 'KEY_APOSTROPHE': keycode = 'KEY_2'     # Shift+'(") -> Shift+2(@)
        # === Shiftキーが押されていない場合のリマップ ===
        else:
            if keycode == 'KEY_APOSTROPHE': keycode = 'KEY_7'; self.is_shift_up = True  # '(') -> Shift+7(&)
            elif keycode == 'KEY_GRAVE': keycode = 'KEY_LEFTBRACE'; self.is_shift_up = True  # `(`) -> Shift+[({)
            elif keycode == 'KEY_EQUAL': keycode = 'KEY_MINUS'; self.is_shift_up = True  # =(=) -> Shift+-(_)
            elif keycode == 'KEY_BACKSLASH': keycode = 'KEY_RO'  # \(\) -> \（JIS配列）
            
        return hid_keys.get(keycode, 0)

    def update_state(self):
        """
        現在のキー状態からHIDレポートを生成し、送信します。
        
        HIDキーボードレポートの構造（8バイト）:
        - byte 0: モディファイアビットマスク
        - byte 1: 予約（常に0）
        - bytes 2-7: 押されているキーのHIDコード（最大6キー）
        """
        # リマップ用フラグをリセット
        self.is_shift_up = False
        self.is_shift_down = False
        
        # 8バイトのHIDレポートを初期化
        report = bytearray(8)
        
        # 押されているキーをHIDコードに変換
        pressed_hid_codes = [self.remap(k) for k in self.pressed_keys]
        modifier = self.modifier
        
        # Shiftを一時的に押す必要がある場合
        if self.is_shift_up:
            modifier |= 0x02  # 左Shiftビットをセット
            report[0] = 0x02
            self.write_report(bytes(report))  # Shiftのみのレポートを先に送信
        # Shiftを一時的に離す必要がある場合
        elif self.is_shift_down: 
            modifier &= ~self.shift_bit  # Shiftビットをクリア
            
        # モディファイアをセット
        report[0] = modifier
        
        # 押されているキー（最大6つ）をレポートに設定
        # 0以外のHIDコードのみをフィルタリング
        for i, code in enumerate(filter(None, pressed_hid_codes[:6])):
            report[2 + i] = code
        
        # レポートを送信
        self.write_report(bytes(report))

    def write_report(self, buffer):
        """
        HIDレポートをガジェットデバイスに書き込みます。
        
        Args:
            buffer (bytes): 送信する8バイトのHIDレポート
        
        Raises:
            OSError: デバイスへの書き込みに失敗した場合
        """
        try:
            with open(self.hid_output_path, 'rb+') as fd:
                fd.write(buffer)
        except BlockingIOError:
            # バッファがいっぱいの場合（通常は一時的な問題）
            self.log.warning(f"BlockingIOError on {self.hid_output_path}")
        except OSError as e:
            # デバイスエラー（切断など）
            self.log.error(f"OSError on {self.hid_output_path}: {e}")
            raise e


class KeyBowManager:
    """
    GPIOボタンマネージャークラス
    
    Raspberry Pi のGPIOピンに接続されたボタンを管理し、
    ボタン操作に応じた特殊機能を提供します。
    
    機能:
    - ボタン1: 短押し=Alt+A、長押し=リマップ切り替え
    - ボタン2: 短押し=Alt+Y
    - ボタン3: 短押し=スペース
    - ボタン1+2長押し: メールアドレス入力
    - ボタン1+3長押し: シャットダウン
    
    Attributes:
        keyboard_hid_path (str): キーボードHIDデバイスのパス
        email_address (str): 自動入力用のメールアドレス
        led_strip (PixelStrip): NeoPixel LEDストリップオブジェクト
    """
    
    def __init__(self, loop):
        """
        GPIOボタンマネージャーを初期化します。
        
        Args:
            loop (asyncio.AbstractEventLoop): 非同期イベントループ
        """
        self.loop = loop
        
        # HIDパスの設定を取得
        hid_paths = CONFIG["hid_paths"]
        if "keyboard_outputs" in hid_paths:
            self.keyboard_hid_path = hid_paths["keyboard_outputs"][0]
        else:
            self.keyboard_hid_path = hid_paths.get("keyboard", "/dev/hidg0")
        
        # メールアドレスの取得
        self.email_address = CONFIG.get("email_address", "")
        
        # gpiozeroのButtonクラスにカスタム属性を追加
        Button.was_held = False
        
        # GPIO設定の取得
        gpio_settings = CONFIG.get("gpio_settings", {})
        hold_time = gpio_settings.get("hold_time", 1.5)           # 長押し判定時間
        bounce_time = gpio_settings.get("bounce_time", 0.05)      # チャタリング防止時間
        self.combination_check_delay = gpio_settings.get("combination_check_delay", 0.2)
        
        # ボタン状態の追跡用辞書
        # was_held: 長押しが発生したか
        # combination_detected: 組み合わせ押しが検出されたか
        self.button_states = {
            1: {"was_held": False, "combination_detected": False},
            2: {"was_held": False, "combination_detected": False},
            3: {"was_held": False, "combination_detected": False}
        }
        
        # === ボタン1の設定（GPIO 6）===
        self.btn1 = Button(6, hold_time=hold_time, bounce_time=bounce_time)
        self.btn1.when_held = self.held1     # 長押しコールバック
        self.btn1.when_released = self.released1  # リリースコールバック
        
        # === ボタン2の設定（GPIO 22）===
        self.btn2 = Button(22, hold_time=hold_time, bounce_time=bounce_time)
        self.btn2.when_held = self.held2
        self.btn2.when_released = self.released2
        
        # === ボタン3の設定（GPIO 17）===
        self.btn3 = Button(17, hold_time=hold_time, bounce_time=bounce_time)
        self.btn3.when_held = self.held3
        self.btn3.when_released = self.released3
        
        # === LED初期化 ===
        self.led_strip = None
        self.led_enabled = False
        led_settings = CONFIG.get("led_settings", {})
        
        if led_settings.get("enabled", False) and NEOPIXEL_AVAILABLE:
            try:
                led_pin = led_settings.get("gpio_pin", 18)       # データピン
                led_count = led_settings.get("led_count", 3)     # LED数
                brightness = led_settings.get("brightness", 50)   # 明るさ（0-255）
                
                # LED色の設定
                self.led_colors = led_settings.get("colors", {
                    "remap_enabled": [0, 255, 0],    # リマップ有効時: 緑
                    "remap_disabled": [255, 0, 0]   # リマップ無効時: 赤
                })
                
                # NeoPixelストリップを作成
                self.led_strip = PixelStrip(
                    led_count,    # LED数
                    led_pin,      # GPIOピン
                    800000,       # 信号周波数（800kHz = WS2812B標準）
                    10,           # DMAチャネル（通常は10）
                    False,        # 信号反転（通常はFalse）
                    brightness    # 明るさ
                )
                self.led_strip.begin()  # LEDを初期化
                self.led_enabled = True
                self.update_led_status()  # 初期状態を表示
                logging.info(f"LED initialized: {led_count} LEDs on GPIO {led_pin}")
            except Exception as e:
                logging.error(f"Failed to initialize LED: {e}")
                self.led_enabled = False
        
        logging.info(f"KeyBow initialized. Hold time: {hold_time}s")

    async def send_key_combination(self, modifier_bits, key_code, send_alt_after=False):
        """
        キーの組み合わせをHIDデバイスに送信します。
        
        Args:
            modifier_bits (int): モディファイアビットマスク（例: 0x04 = Alt）
            key_code (int): HIDキーコード
            send_alt_after (bool): キー送信後にAlt単独を送信するか
        """
        try:
            # キープレスレポートを作成
            press_report = bytearray(8)
            press_report[0] = modifier_bits
            press_report[2] = key_code
            
            # キーリリースレポート（すべてゼロ）
            release_report = bytearray(8)

            with open(self.keyboard_hid_path, 'rb+') as fd:
                # キープレスを送信
                fd.write(bytes(press_report))
                await asyncio.sleep(0.01)  # 短い遅延
                # キーリリースを送信
                fd.write(bytes(release_report))
                await asyncio.sleep(0.01)

                # 追加のAlt送信が必要な場合
                if send_alt_after:
                    alt_only_press = bytearray(8)
                    alt_only_press[0] = 0x04  # Altのみ
                    alt_only_release = bytearray(8)

                    fd.write(bytes(alt_only_press))
                    await asyncio.sleep(0.01)
                    fd.write(bytes(alt_only_release))

        except Exception as e:
            logging.error(f"Error sending key combination: {e}")

    async def send_email_address(self):
        """
        設定されたメールアドレスを1文字ずつキー入力として送信します。
        
        各文字をHIDキーコードに変換し、適切なモディファイア（Shift）と
        組み合わせてレポートを送信します。
        """
        email = self.email_address
        logging.info(f"Typing email: {email}")
        
        try:
            with open(self.keyboard_hid_path, 'rb+') as fd:
                for char in email:
                    press_report = bytearray(8)
                    release_report = bytearray(8)
                    shift = False

                    # === 小文字アルファベット (a-z) ===
                    if 'a' <= char <= 'z':
                        key_name = f'KEY_{char.upper()}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    # === 大文字アルファベット (A-Z) ===
                    elif 'A' <= char <= 'Z':
                        shift = True
                        key_name = f'KEY_{char}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    # === 数字 (0-9) ===
                    elif '0' <= char <= '9':
                        key_name = f'KEY_{char}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    # === 記号 ===
                    else:
                        # 記号のマッピング: (Shift必要か, キー名)
                        symbol_map = {
                            '@': (True, 'KEY_2'),      # Shift+2 = @
                            '-': (False, 'KEY_MINUS'), # - キー
                            '.': (False, 'KEY_DOT'),   # . キー
                            '_': (True, 'KEY_MINUS'),  # Shift+- = _
                            '+': (True, 'KEY_EQUAL')   # Shift+= = +
                        }
                        if char in symbol_map:
                            shift, key_name = symbol_map[char]
                            press_report[2] = hid_keys.get(key_name, 0)
                        else:
                            # サポートされていない文字はスキップ
                            continue

                    # Shiftが必要な場合はモディファイアをセット
                    if shift:
                        press_report[0] = 0x02  # 左Shift

                    # キープレスとリリースを送信
                    fd.write(bytes(press_report))
                    await asyncio.sleep(0.02)
                    fd.write(bytes(release_report))
                    await asyncio.sleep(0.02)
                        
        except Exception as e:
            logging.error(f"Error typing email: {e}")

    def held1(self, btn):
        """
        ボタン1の長押しハンドラ
        
        単独長押し: リマップ機能のトグル
        ボタン2と同時長押し: メールアドレス入力
        ボタン3と同時長押し: シャットダウン
        """
        global REMAP_ENABLED
        self.button_states[1]["was_held"] = True
        
        if self.button_states[3]["was_held"]:
            # ボタン1+3長押し: シャットダウン
            logging.info("Btn 1+3 Held: Shutdown initiated.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[3]["combination_detected"] = True
            asyncio.create_task(proxy_core.shutdown(self.loop))
        elif self.button_states[2]["was_held"]:
            # ボタン1+2長押し: メールアドレス入力
            logging.info("Btn 1+2 Held: Typing email.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[2]["combination_detected"] = True
            asyncio.run_coroutine_threadsafe(self.send_email_address(), self.loop)
        else:
            # ボタン1単独長押し: リマップ切り替え
            REMAP_ENABLED = not REMAP_ENABLED
            state = "Enabled" if REMAP_ENABLED else "Disabled"
            logging.info(f"Btn 1 Held: Remap {state}")
            self.update_led_status()

    def released1(self, btn):
        """ボタン1のリリースハンドラ"""
        # 長押しでも組み合わせ検出でもない場合は短押しとして処理
        if not self.button_states[1]["was_held"] and not self.button_states[1]["combination_detected"]: 
            self.pressed1(btn)
        # 状態をリセット
        self.button_states[1]["was_held"] = False
        self.button_states[1]["combination_detected"] = False

    def pressed1(self, btn): 
        """ボタン1の短押しハンドラ: Alt+A を送信"""
        logging.info("Btn 1 Pressed: Alt+A")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x04, 0x04), self.loop)

    def held2(self, btn):
        """ボタン2の長押しハンドラ"""
        self.button_states[2]["was_held"] = True
        if self.button_states[1]["was_held"]:
            # ボタン1+2長押し: メールアドレス入力
            logging.info("Btn 1+2 Held: Typing email.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[2]["combination_detected"] = True
            asyncio.run_coroutine_threadsafe(self.send_email_address(), self.loop)

    def released2(self, btn):
        """ボタン2のリリースハンドラ"""
        if not self.button_states[2]["was_held"] and not self.button_states[2]["combination_detected"]: 
            self.pressed2(btn)
        self.button_states[2]["was_held"] = False
        self.button_states[2]["combination_detected"] = False

    def pressed2(self, btn): 
        """ボタン2の短押しハンドラ: Alt+Y を送信"""
        logging.info("Btn 2 Pressed: Alt+Y")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x04, 0x1c), self.loop)

    def held3(self, btn):
        """ボタン3の長押しハンドラ"""
        self.button_states[3]["was_held"] = True
        if self.button_states[1]["was_held"]:
            # ボタン1+3長押し: シャットダウン
            logging.info("Btn 1+3 Held: Shutdown initiated.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[3]["combination_detected"] = True
            asyncio.create_task(proxy_core.shutdown(self.loop))

    def released3(self, btn):
        """ボタン3のリリースハンドラ"""
        if not self.button_states[3]["was_held"] and not self.button_states[3]["combination_detected"]: 
            self.pressed3(btn)
        self.button_states[3]["was_held"] = False
        self.button_states[3]["combination_detected"] = False

    def pressed3(self, btn):
        """ボタン3の短押しハンドラ: スペースキーを送信"""
        logging.info("Btn 3 Pressed: Space")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x00, 0x2c), self.loop)

    def update_led_status(self):
        """
        REMAP_ENABLEDの状態に応じてLED色を更新します。
        
        リマップ有効時: 緑色
        リマップ無効時: 赤色
        """
        if not self.led_enabled or self.led_strip is None:
            return
        
        try:
            global REMAP_ENABLED
            # 状態に応じた色を選択
            color_key = "remap_enabled" if REMAP_ENABLED else "remap_disabled"
            rgb = self.led_colors.get(color_key, [0, 255, 0])
            color = Color(rgb[0], rgb[1], rgb[2])
            
            # すべてのLEDを同じ色に設定
            for i in range(self.led_strip.numPixels()):
                self.led_strip.setPixelColor(i, color)
            self.led_strip.show()  # 変更を適用
            
            logging.info(f"LED updated: {color_key} -> RGB{tuple(rgb)}")
        except Exception as e:
            logging.error(f"Failed to update LED: {e}")


async def device_monitor(loop):
    """
    デバイスモニタータスク
    
    定期的にシステムの入力デバイスをスキャンし、
    対象のキーボードデバイスを検出・管理します。
    
    Args:
        loop (asyncio.AbstractEventLoop): 非同期イベントループ
    """
    # 対象キーボードの名前パターン（正規表現）
    # HHKB Studio、HHKB Hybrid、PFU製キーボードにマッチ
    KEYBOARD_DEVICE_NAME_PATTERN = re.compile(r'HHKB-Studio[1-4] Keyboard|HHKB-Hybrid.*|PFU.*')
    
    # HID出力パスの設定を取得
    hid_paths = CONFIG.get("hid_paths", {})
    if "keyboard_outputs" in hid_paths:
        KEYBOARD_HID_OUTPUTS = hid_paths["keyboard_outputs"]
    elif "keyboard" in hid_paths:
        KEYBOARD_HID_OUTPUTS = [hid_paths["keyboard"]]
    else:
        KEYBOARD_HID_OUTPUTS = []
        logging.warning("No keyboard HID paths configured.")

    # 管理状態の初期化
    managed_keyboards = {}  # 管理中のキーボード: {パス: {task, hid_output}}
    available_keyboard_hids = set(KEYBOARD_HID_OUTPUTS)  # 利用可能なHID出力
    cached_device_paths = set()  # キャッシュされたデバイスパス
    cached_devices = {}  # キャッシュされたデバイスオブジェクト
    
    logging.info("Starting Keyboard Monitor...")

    while True:
        try:
            # 完了したタスクのクリーンアップ
            proxy_core.reap_dead_tasks(managed_keyboards, available_keyboard_hids, "Keyboard")
            
            # デバイスリストを取得
            current_device_paths = set(evdev.list_devices())
            
            # デバイスリストが変化した場合のみキャッシュを更新
            if current_device_paths != cached_device_paths:
                cached_devices = {}
                for path in current_device_paths:
                    try:
                        cached_devices[path] = evdev.InputDevice(path)
                    except (OSError, PermissionError):
                        # アクセス権限がないデバイスはスキップ
                        continue
                cached_device_paths = current_device_paths
            
            # 対象のキーボードデバイスをフィルタリング
            current_keyboards = {p: d for p, d in cached_devices.items() 
                               if KEYBOARD_DEVICE_NAME_PATTERN.match(d.name)}
            
            # デバイス接続管理
            proxy_core.manage_device_connections(
                current_keyboards, managed_keyboards, available_keyboard_hids, 
                KeyboardProxy, "Keyboard", loop
            )
            
        except Exception as e:
            logging.error(f"Monitor error: {e}", exc_info=True)
        
        # 5秒間隔でスキャン
        await asyncio.sleep(5)


# =============================================================================
# メインエントリーポイント
# =============================================================================
if __name__ == "__main__":
    # 非同期イベントループを取得
    loop = asyncio.get_event_loop()
    
    # グローバル例外ハンドラを設定
    loop.set_exception_handler(proxy_core.handle_exception)
    
    # シグナルハンドラを登録（SIGHUP, SIGTERM, SIGINT）
    # これらのシグナルを受信するとグレースフルシャットダウンを実行
    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(proxy_core.shutdown(loop, s)))
    
    try:
        # GPIOボタンマネージャーを初期化
        keybow = KeyBowManager(loop)
        
        # デバイスモニタータスクを開始
        loop.create_task(device_monitor(loop))
        
        # イベントループを実行（無限ループ）
        loop.run_forever()
    finally:
        # クリーンアップ
        loop.close()
