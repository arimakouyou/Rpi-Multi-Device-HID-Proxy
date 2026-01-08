#!/usr/bin/python3
"""
Mouse Proxy
Manages multiple mouse devices and outputs to HID gadget
"""

import logging
import asyncio
import signal
import re
import time
import evdev
from evdev import InputDevice, ecodes
from enum import IntEnum
import proxy_core

# Load configuration and setup logging
CONFIG = proxy_core.load_config()
proxy_core.setup_logging(CONFIG)

class MouseIndex(IntEnum):
    """Mouse HID Report Byte Index"""
    TIP_SW, X_LSB, X_MSB, Y_LSB, Y_MSB, WHEEL_LSB, WHEEL_MSB, MAX = range(8)

class MouseProxy:
    """
    Mouse proxy class
    Receives events from input devices and outputs them as HID gadget
    """
    
    def __init__(self, input_device_path, hid_output_path, loop):
        self.log = logging.getLogger(f"MouseProxy-{input_device_path.split('/')[-1]}")
        self.loop = loop
        self.input_device_path = input_device_path
        self.hid_output_path = hid_output_path
        self.device = None
        self.button_state_buffer = {}
        self.last_button_event_time = {}
        self.reset_state()

    def connect_device(self):
        try:
            self.device = InputDevice(self.input_device_path)
            self.device.grab()
            self.log.info(f"Mouse captured: {self.device.path} ({self.device.name}) -> {self.hid_output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to connect to {self.input_device_path}: {e}")
            return False

    def reset_state(self):
        self.button_left = self.button_right = self.button_center = self.back = self.forward = 0
        self.move_x = self.move_y = self.scroll_y = self.btn = 0
        
        if not hasattr(self, 'button_state_buffer'):
            self.button_state_buffer = {}
        if not hasattr(self, 'last_button_event_time'):
            self.last_button_event_time = {}

    async def run(self):
        while True:
            if not self.device and not self.connect_device():
                await asyncio.sleep(5)
                continue
            try:
                async for event in self.device.async_read_loop():
                    if event.type == ecodes.EV_KEY: 
                        self.handle_key_event(event)
                    elif event.type == ecodes.EV_REL: 
                        self.handle_rel_event(event)
                    elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                        self.update_state()
            except (OSError, asyncio.CancelledError) as e:
                self.log.error(f"Mouse {self.input_device_path} disconnected: {type(e).__name__}")
                if self.device: 
                    self.device.close()
                self.device = None
                break
            except Exception as e:
                self.log.error(f"Unexpected error: {e}", exc_info=True)
                break

    def handle_key_event(self, event):
        current_time = time.time()
        is_press = event.value == 1
        
        if event.code == ecodes.BTN_LEFT:
            self.button_state_buffer[ecodes.BTN_LEFT] = is_press
            self.last_button_event_time[ecodes.BTN_LEFT] = current_time
            self.button_left = 1 if is_press else 0
        elif event.code == ecodes.BTN_RIGHT:
            self.button_state_buffer[ecodes.BTN_RIGHT] = is_press
            self.last_button_event_time[ecodes.BTN_RIGHT] = current_time
            self.button_right = (1 << 1) if is_press else 0
        elif event.code == ecodes.BTN_MIDDLE:
            self.button_state_buffer[ecodes.BTN_MIDDLE] = is_press
            self.last_button_event_time[ecodes.BTN_MIDDLE] = current_time
            self.button_center = (1 << 2) if is_press else 0
        elif event.code == ecodes.BTN_SIDE:
            self.button_state_buffer[ecodes.BTN_SIDE] = is_press
            self.last_button_event_time[ecodes.BTN_SIDE] = current_time
            self.back = (1 << 3) if is_press else 0
        elif event.code == ecodes.BTN_EXTRA:
            self.button_state_buffer[ecodes.BTN_EXTRA] = is_press
            self.last_button_event_time[ecodes.BTN_EXTRA] = current_time
            self.forward = (1 << 4) if is_press else 0
        
        self.btn = self.button_left | self.button_right | self.button_center | self.back | self.forward
        self.log.debug(f"Button event: {event.code}={is_press}, State: {self.btn}")

    def handle_rel_event(self, event):
        if event.code == ecodes.REL_X: 
            self.move_x = event.value
        elif event.code == ecodes.REL_Y: 
            self.move_y = event.value
        elif event.code == ecodes.REL_WHEEL: 
            self.scroll_y = event.value

    def update_state(self):
        data = bytearray(MouseIndex.MAX)
        data[MouseIndex.TIP_SW] = self.btn
        data[MouseIndex.X_LSB] = self.move_x & 0xff
        data[MouseIndex.X_MSB] = (self.move_x >> 8) & 0xff
        data[MouseIndex.Y_LSB] = self.move_y & 0xff
        data[MouseIndex.Y_MSB] = (self.move_y >> 8) & 0xff
        data[MouseIndex.WHEEL_LSB] = self.scroll_y & 0xff
        data[MouseIndex.WHEEL_MSB] = (self.scroll_y >> 8) & 0xff
        self.write_report(bytes(data))
        self.move_x = self.move_y = self.scroll_y = 0

    def write_report(self, buffer):
        try:
            with open(self.hid_output_path, 'rb+') as fd:
                fd.write(buffer)
        except BlockingIOError:
            self.log.warning(f"BlockingIOError on {self.hid_output_path}")
        except OSError as e:
            self.log.error(f"OSError on {self.hid_output_path}: {e}")
            raise e

async def device_monitor(loop):
    MOUSE_DEVICE_NAME_PATTERN = re.compile(r'HHKB-Studio[1-4] Mouse|Logitech.*')
    
    hid_paths = CONFIG.get("hid_paths", {})
    MOUSE_HID_OUTPUTS = hid_paths.get("mouse_outputs", [])
    if not MOUSE_HID_OUTPUTS:
        logging.warning("No mouse HID paths configured.")

    managed_mice = {}
    available_mouse_hids = set(MOUSE_HID_OUTPUTS)
    cached_device_paths = set()
    cached_devices = {}
    
    logging.info("Starting Mouse Monitor...")

    while True:
        try:
            proxy_core.reap_dead_tasks(managed_mice, available_mouse_hids, "Mouse")
            
            current_device_paths = set(evdev.list_devices())
            if current_device_paths != cached_device_paths:
                cached_devices = {}
                for path in current_device_paths:
                    try:
                        cached_devices[path] = evdev.InputDevice(path)
                    except (OSError, PermissionError):
                        continue
                cached_device_paths = current_device_paths
            
            current_mice = {p: d for p, d in cached_devices.items() 
                           if MOUSE_DEVICE_NAME_PATTERN.match(d.name)}
            
            proxy_core.manage_device_connections(
                current_mice, managed_mice, available_mouse_hids, 
                MouseProxy, "Mouse", loop
            )
            
        except Exception as e:
            logging.error(f"Monitor error: {e}", exc_info=True)
        await asyncio.sleep(5)

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Mouse Proxy")
    parser.add_argument("device_path", nargs="?", help="Path to input device (e.g., /dev/input/eventX)")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(proxy_core.handle_exception)
    
    for s in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(proxy_core.shutdown(loop, s)))
    
    try:
        if args.device_path:
            # Single device mode (UDEV triggered)
            hid_paths = CONFIG.get("hid_paths", {})
            MOUSE_HID_OUTPUTS = hid_paths.get("mouse_outputs", [])
            if not MOUSE_HID_OUTPUTS:
                logging.error("No mouse HID paths configured.")
                sys.exit(1)
            
            # Use the first available output for simplicity in single-device mode
            # In a more complex setup, we might want to manage which output to use,
            # but for 1:1 mapping or simple pool, taking the first one is a reasonable start.
            # Ideally, we should probably share the pool state, but UDEV services are isolated processes.
            # Assuming strictly one mouse for now or user accepts race on multiple mice -> multiple outputs.
            # Wait, if we spawn multiple processes, they need to grab different HID outputs.
            # Since we can't easily coordinate lock across processes without extra mechanism, 
            # let's try to pick one based on some hash or random, OR just pick the first one 
            # and rely on the file lock (flock) if we implemented it, or OS blocking.
            #
            # The current MouseProxy implementation opens the HID output in 'rb+'.
            # If we want to support multiple mice concurrently via UDEV, we need to map them to different outputs.
            # For this iteration, let's use a simple allocation strategy or just use the first one 
            # if we assume primarily one mouse usage. 
            # 
            # Actually, the original requirement was just "launch program when mouse connected".
            # Multi-device support might still be needed.
            # Let's iterate through outputs and find one that works? 
            # Or just for now, use the first one.
            
            output_path = MOUSE_HID_OUTPUTS[0] 
            
            # Check device name to filter out unwanted devices
            try:
                device = InputDevice(args.device_path)
                MOUSE_DEVICE_NAME_PATTERN = re.compile(r'HHKB-Studio[1-4] Mouse|Logitech.*')
                if not MOUSE_DEVICE_NAME_PATTERN.match(device.name):
                    logging.info(f"Ignored device: {device.name} ({args.device_path})")
                    sys.exit(0)
                
                device.close() # Close to reopen in Proxy
            except Exception as e:
                logging.error(f"Failed to check device {args.device_path}: {e}")
                sys.exit(1)

            logging.info(f"Starting MouseProxy for {args.device_path} -> {output_path}")
            proxy = MouseProxy(args.device_path, output_path, loop)
            loop.create_task(proxy.run())
        else:
            # Monitor mode (Legacy/Manual)
            loop.create_task(device_monitor(loop))
            
        loop.run_forever()
    finally:
        loop.close()
