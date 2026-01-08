#!/usr/bin/python3
"""
Keyboard Proxy
Manages multiple keyboard devices and GPIO buttons
"""

import logging
import asyncio
import signal
import re
import evdev
from evdev import InputDevice, ecodes
from hid_keys import hid_key_map as hid_keys
import proxy_core

# Load configuration and setup logging
CONFIG = proxy_core.load_config()
proxy_core.setup_logging(CONFIG)

REMAP_ENABLED = True

# GPIO Library Import
try:
    from gpiozero import Button
except ImportError:
    logging.warning("gpiozero library not found. GPIO button functions disabled.")
    class Button:
        def __init__(self, *args, **kwargs): pass
        def __getattr__(self, name): return lambda *args, **kwargs: None

class KeyboardProxy:
    """
    Keyboard proxy class
    Receives events from input devices and outputs them as HID gadget
    """
    
    def __init__(self, input_device_path, hid_output_path, loop):
        self.log = logging.getLogger(f"KeyboardProxy-{input_device_path.split('/')[-1]}")
        self.loop = loop
        self.input_device_path = input_device_path
        self.hid_output_path = hid_output_path
        self.device = None
        self.modifiers_map = {
            'KEY_LEFTCTRL': 0, 'KEY_LEFTSHIFT': 1, 'KEY_LEFTALT': 2, 'KEY_LEFTMETA': 3, 
            'KEY_RIGHTCTRL': 4, 'KEY_RIGHTSHIFT': 5, 'KEY_RIGHTALT': 6, 'KEY_RIGHTMETA': 7
        }
        self.reset_state()

    def connect_device(self):
        try:
            self.device = InputDevice(self.input_device_path)
            self.device.grab()
            self.log.info(f"Keyboard captured: {self.device.path} ({self.device.name}) -> {self.hid_output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to connect to {self.input_device_path}: {e}")
            return False

    def reset_state(self):
        self.modifier = 0b00000000
        self.pressed_keys = set()
        self.is_shift_up = False
        self.is_shift_down = False
        self.shift_bit = 0b00100010

    async def run(self):
        while True:
            if not self.device and not self.connect_device():
                await asyncio.sleep(5)
                continue
            try:
                while True:
                    event = await self.loop.run_in_executor(None, self.device.read_one)
                    if event is None:
                        await asyncio.sleep(0.01)
                        continue
                    self.process_event(event)
            except (OSError, asyncio.CancelledError) as e:
                self.log.error(f"Keyboard {self.input_device_path} disconnected: {type(e).__name__}")
                if self.device:
                    self.device.close()
                self.device = None
                break
            except Exception as e:
                self.log.error(f"Unexpected error: {e}", exc_info=True)
                break

    def process_event(self, event):
        if event.type != ecodes.EV_KEY:
            return

        try:
            keycode = ecodes.KEY[event.code]
        except (IndexError, KeyError):
            self.log.debug(f"Ignoring unknown keycode: {event.code}")
            return
        
        if isinstance(keycode, list):
            keycode = keycode[0]

        keystate = event.value

        if keycode in self.modifiers_map:
            self.update_modifier(keycode, keystate)
        elif keystate == 0:  # release
            self.release(keycode)
        elif keystate == 1 or keystate == 2:  # press or repeat
            self.press(keycode)

    def update_modifier(self, keycode, keystate):
        if keystate == 0: 
            self.modifier &= ~(1 << self.modifiers_map[keycode])
        else: 
            self.modifier |= (1 << self.modifiers_map[keycode])
        self.update_state()

    def release(self, keycode):
        if keycode in self.pressed_keys:
            self.pressed_keys.remove(keycode)
            self.update_state()

    def press(self, keycode):
        if keycode not in self.pressed_keys:
            self.pressed_keys.add(keycode)
            self.update_state()

    def remap(self, keycode):
        global REMAP_ENABLED
        if not REMAP_ENABLED:
            return hid_keys.get(keycode, 0)
        if keycode not in hid_keys: 
            return 0
            
        if keycode == 'KEY_LEFTBRACE': 
            keycode = 'KEY_RIGHTBRACE'
        elif keycode == 'KEY_RIGHTBRACE': 
            keycode = 'KEY_BACKSLASH'
        elif self.modifier & self.shift_bit:
            if keycode == 'KEY_7': keycode = 'KEY_6'
            elif keycode == 'KEY_8': keycode = 'KEY_APOSTROPHE'
            elif keycode == 'KEY_9': keycode = 'KEY_8'
            elif keycode == 'KEY_0': keycode = 'KEY_9'
            elif keycode == 'KEY_EQUAL': keycode = 'KEY_SEMICOLON'
            elif keycode == 'KEY_GRAVE': keycode = 'KEY_EQUAL'
            elif keycode == 'KEY_MINUS': keycode = 'KEY_RO'
            elif keycode == 'KEY_2': keycode = 'KEY_LEFTBRACE'; self.is_shift_down = True
            elif keycode == 'KEY_6': keycode = 'KEY_EQUAL'; self.is_shift_down = True
            elif keycode == 'KEY_BACKSLASH': keycode = 'KEY_YEN'
            elif keycode == 'KEY_SEMICOLON': keycode = 'KEY_APOSTROPHE'; self.is_shift_down = True
            elif keycode == 'KEY_APOSTROPHE': keycode = 'KEY_2'
        else:
            if keycode == 'KEY_APOSTROPHE': keycode = 'KEY_7'; self.is_shift_up = True
            elif keycode == 'KEY_GRAVE': keycode = 'KEY_LEFTBRACE'; self.is_shift_up = True
            elif keycode == 'KEY_EQUAL': keycode = 'KEY_MINUS'; self.is_shift_up = True
            elif keycode == 'KEY_BACKSLASH': keycode = 'KEY_RO'
        return hid_keys.get(keycode, 0)

    def update_state(self):
        self.is_shift_up = False
        self.is_shift_down = False
        report = bytearray(8)
        pressed_hid_codes = [self.remap(k) for k in self.pressed_keys]
        modifier = self.modifier
        
        if self.is_shift_up:
            modifier |= 0x02
            report[0] = 0x02
            self.write_report(bytes(report))
        elif self.is_shift_down: 
            modifier &= ~self.shift_bit
            
        report[0] = modifier
        for i, code in enumerate(filter(None, pressed_hid_codes[:6])):
            report[2 + i] = code
        self.write_report(bytes(report))

    def write_report(self, buffer):
        try:
            with open(self.hid_output_path, 'rb+') as fd:
                fd.write(buffer)
        except BlockingIOError:
            self.log.warning(f"BlockingIOError on {self.hid_output_path}")
        except OSError as e:
            self.log.error(f"OSError on {self.hid_output_path}: {e}")
            raise e

class KeyBowManager:
    """GPIO Button Manager"""
    
    def __init__(self, loop):
        self.loop = loop
        hid_paths = CONFIG["hid_paths"]
        if "keyboard_outputs" in hid_paths:
            self.keyboard_hid_path = hid_paths["keyboard_outputs"][0]
        else:
            self.keyboard_hid_path = hid_paths.get("keyboard", "/dev/hidg0")
        self.email_address = CONFIG.get("email_address", "")
        Button.was_held = False
        
        gpio_settings = CONFIG.get("gpio_settings", {})
        hold_time = gpio_settings.get("hold_time", 1.5)
        bounce_time = gpio_settings.get("bounce_time", 0.05)
        self.combination_check_delay = gpio_settings.get("combination_check_delay", 0.2)
        
        self.button_states = {
            1: {"was_held": False, "combination_detected": False},
            2: {"was_held": False, "combination_detected": False},
            3: {"was_held": False, "combination_detected": False}
        }
        
        self.btn1 = Button(6, hold_time=hold_time, bounce_time=bounce_time)
        self.btn1.when_held = self.held1
        self.btn1.when_released = self.released1
        
        self.btn2 = Button(22, hold_time=hold_time, bounce_time=bounce_time)
        self.btn2.when_held = self.held2
        self.btn2.when_released = self.released2
        
        self.btn3 = Button(17, hold_time=hold_time, bounce_time=bounce_time)
        self.btn3.when_held = self.held3
        self.btn3.when_released = self.released3
        
        logging.info(f"KeyBow initialized. Hold time: {hold_time}s")

    async def send_key_combination(self, modifier_bits, key_code, send_alt_after=False):
        try:
            press_report = bytearray(8)
            press_report[0] = modifier_bits
            press_report[2] = key_code
            release_report = bytearray(8)

            with open(self.keyboard_hid_path, 'rb+') as fd:
                fd.write(bytes(press_report))
                await asyncio.sleep(0.01)
                fd.write(bytes(release_report))
                await asyncio.sleep(0.01)

                if send_alt_after:
                    alt_only_press = bytearray(8)
                    alt_only_press[0] = 0x04
                    alt_only_release = bytearray(8)

                    fd.write(bytes(alt_only_press))
                    await asyncio.sleep(0.01)
                    fd.write(bytes(alt_only_release))

        except Exception as e:
            logging.error(f"Error sending key combination: {e}")

    async def send_email_address(self):
        email = self.email_address
        logging.info(f"Typing email: {email}")
        
        try:
            with open(self.keyboard_hid_path, 'rb+') as fd:
                for char in email:
                    press_report = bytearray(8)
                    release_report = bytearray(8)
                    shift = False

                    if 'a' <= char <= 'z':
                        key_name = f'KEY_{char.upper()}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    elif 'A' <= char <= 'Z':
                        shift = True
                        key_name = f'KEY_{char}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    elif '0' <= char <= '9':
                        key_name = f'KEY_{char}'
                        press_report[2] = hid_keys.get(key_name, 0)
                    else:
                        symbol_map = {
                            '@': (True, 'KEY_2'), '-': (False, 'KEY_MINUS'), '.': (False, 'KEY_DOT'),
                            '_': (True, 'KEY_MINUS'), '+': (True, 'KEY_EQUAL')
                        }
                        if char in symbol_map:
                            shift, key_name = symbol_map[char]
                            press_report[2] = hid_keys.get(key_name, 0)
                        else:
                            continue

                    if shift:
                        press_report[0] = 0x02

                    fd.write(bytes(press_report))
                    await asyncio.sleep(0.02)
                    fd.write(bytes(release_report))
                    await asyncio.sleep(0.02)
                        
        except Exception as e:
            logging.error(f"Error typing email: {e}")

    def held1(self, btn):
        global REMAP_ENABLED
        self.button_states[1]["was_held"] = True
        if self.button_states[3]["was_held"]:
            logging.info("Btn 1+3 Held: Shutdown initiated.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[3]["combination_detected"] = True
            asyncio.create_task(proxy_core.shutdown(self.loop))
        elif self.button_states[2]["was_held"]:
            logging.info("Btn 1+2 Held: Typing email.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[2]["combination_detected"] = True
            asyncio.run_coroutine_threadsafe(self.send_email_address(), self.loop)
        else:
            REMAP_ENABLED = not REMAP_ENABLED
            state = "Enabled" if REMAP_ENABLED else "Disabled"
            logging.info(f"Btn 1 Held: Remap {state}")

    def released1(self, btn):
        if not self.button_states[1]["was_held"] and not self.button_states[1]["combination_detected"]: 
            self.pressed1(btn)
        self.button_states[1]["was_held"] = False
        self.button_states[1]["combination_detected"] = False

    def pressed1(self, btn): 
        logging.info("Btn 1 Pressed: Alt+A")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x04, 0x04), self.loop)

    def held2(self, btn):
        self.button_states[2]["was_held"] = True
        if self.button_states[1]["was_held"]:
            logging.info("Btn 1+2 Held: Typing email.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[2]["combination_detected"] = True
            asyncio.run_coroutine_threadsafe(self.send_email_address(), self.loop)

    def released2(self, btn):
        if not self.button_states[2]["was_held"] and not self.button_states[2]["combination_detected"]: 
            self.pressed2(btn)
        self.button_states[2]["was_held"] = False
        self.button_states[2]["combination_detected"] = False

    def pressed2(self, btn): 
        logging.info("Btn 2 Pressed: Alt+Y")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x04, 0x1c), self.loop)

    def held3(self, btn):
        self.button_states[3]["was_held"] = True
        if self.button_states[1]["was_held"]:
            logging.info("Btn 1+3 Held: Shutdown initiated.")
            self.button_states[1]["combination_detected"] = True
            self.button_states[3]["combination_detected"] = True
            asyncio.create_task(proxy_core.shutdown(self.loop))

    def released3(self, btn):
        if not self.button_states[3]["was_held"] and not self.button_states[3]["combination_detected"]: 
            self.pressed3(btn)
        self.button_states[3]["was_held"] = False
        self.button_states[3]["combination_detected"] = False

    def pressed3(self, btn):
        logging.info("Btn 3 Pressed: Space")
        asyncio.run_coroutine_threadsafe(self.send_key_combination(0x00, 0x2c), self.loop)

async def device_monitor(loop):
    KEYBOARD_DEVICE_NAME_PATTERN = re.compile(r'HHKB-Studio[1-4] Keyboard|HHKB-Hybrid.*|PFU.*')
    
    hid_paths = CONFIG.get("hid_paths", {})
    if "keyboard_outputs" in hid_paths:
        KEYBOARD_HID_OUTPUTS = hid_paths["keyboard_outputs"]
    elif "keyboard" in hid_paths:
        KEYBOARD_HID_OUTPUTS = [hid_paths["keyboard"]]
    else:
        KEYBOARD_HID_OUTPUTS = []
        logging.warning("No keyboard HID paths configured.")

    managed_keyboards = {}
    available_keyboard_hids = set(KEYBOARD_HID_OUTPUTS)
    cached_device_paths = set()
    cached_devices = {}
    
    logging.info("Starting Keyboard Monitor...")

    while True:
        try:
            proxy_core.reap_dead_tasks(managed_keyboards, available_keyboard_hids, "Keyboard")
            
            current_device_paths = set(evdev.list_devices())
            if current_device_paths != cached_device_paths:
                cached_devices = {}
                for path in current_device_paths:
                    try:
                        cached_devices[path] = evdev.InputDevice(path)
                    except (OSError, PermissionError):
                        continue
                cached_device_paths = current_device_paths
            
            current_keyboards = {p: d for p, d in cached_devices.items() 
                               if KEYBOARD_DEVICE_NAME_PATTERN.match(d.name)}
            
            proxy_core.manage_device_connections(
                current_keyboards, managed_keyboards, available_keyboard_hids, 
                KeyboardProxy, "Keyboard", loop
            )
            
        except Exception as e:
            logging.error(f"Monitor error: {e}", exc_info=True)
        await asyncio.sleep(5)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(proxy_core.handle_exception)
    
    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(proxy_core.shutdown(loop, s)))
    
    try:
        keybow = KeyBowManager(loop)
        loop.create_task(device_monitor(loop))
        loop.run_forever()
    finally:
        loop.close()
