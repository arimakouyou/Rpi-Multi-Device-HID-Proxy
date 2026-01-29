#!/usr/bin/python3
"""
Proxy Core Module
Shared logic for keyboard and mouse proxies
"""

import logging
import asyncio
import json
import os
import signal

# Default configuration
DEFAULT_CONFIG = {
    "email_address": "test@example.com",
    "gpio_settings": {
        "hold_time": 1.5,
        "bounce_time": 0.05,
        "combination_check_delay": 0.2
    },
    "logging": {
        "level": "ERROR"
    },
    "hid_paths": {
        "keyboard": "/dev/hidg0",
        "mouse_outputs": ["/dev/hidg1", "/dev/hidg2"]
    }
}

def load_config(config_path=None):
    """Load configuration file"""
    if config_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        search_paths = [
            "/etc/multi-hid-proxy/config.json",
            os.path.join(script_dir, "config.json"),
            "config.json"
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                config_path = path
                print(f"[Proxy-Core-DEBUG] Loading config from: {config_path}")
                break
        
        if config_path is None:
            logging.warning("Config file not found. Searched: " + ", ".join(search_paths))
            config_path = search_paths[0]
    
    config = DEFAULT_CONFIG.copy()
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                print(f"[Proxy-Core] Loaded config: {config_path}")
                
                # Merge logic
                for key in config:
                    if key not in user_config:
                        continue
                    if isinstance(config[key], dict) and isinstance(user_config[key], dict):
                        config[key].update(user_config[key])
                    else:
                        config[key] = user_config[key]
                return config
        else:
            logging.warning(f"Config file {config_path} not found. Using defaults.")
            return config
    except Exception as e:
        logging.error(f"Error loading config: {e}. Using defaults.")
        return config

def setup_logging(config):
    """Setup logging based on config"""
    log_level_str = config.get("logging", {}).get("level", "ERROR")
    log_level = getattr(logging, log_level_str.upper(), logging.ERROR)
    
    if os.getenv('INVOCATION_ID'):
        logging.basicConfig(level=log_level, format='[%(name)s|%(levelname)s] %(message)s')
    else:
        logging.basicConfig(level=log_level, format='[%(asctime)s|%(name)s|%(levelname)s] %(message)s')
        
    logging.info(f"Logger initialized. Level: {log_level_str}")

async def shutdown(loop, signal=None):
    """Graceful shutdown"""
    if signal: 
        logging.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks: 
        task.cancel()
    logging.info(f"Cancelling {len(tasks)} tasks.")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()
    logging.info("Service shutdown complete.")

def handle_exception(loop, context):
    """Global exception handler"""
    msg = context.get("exception", context["message"])
    logging.error(f"Unhandled exception: {msg}", exc_info=context.get('exception'))
    asyncio.create_task(shutdown(loop=loop))

def reap_dead_tasks(managed_devices, available_hids, device_type_name):
    """Cleanup completed tasks and free HID outputs"""
    dead_tasks_paths = [path for path, info in managed_devices.items() if info['task'].done()]
    for path in dead_tasks_paths:
        logging.info(f"Cleaning up finished {device_type_name} task: {path}")
        info = managed_devices.pop(path)
        if info['task'].exception():
            logging.error(f"{device_type_name} task {path} ended with exception: {info['task'].exception()}")
        available_hids.add(info['hid_output'])

def manage_device_connections(current_devices, managed_devices, available_hids, proxy_class, device_type_name, loop):
    """Manage device connections and proxy tasks"""
    current_paths = set(current_devices.keys())
    managed_paths = set(managed_devices.keys())
    
    # New devices
    for path in (current_paths - managed_paths):
        if not available_hids:
            logging.warning(f"New {device_type_name} {path} found, but no available HID outputs.")
            continue
        output_path = available_hids.pop()
        device = current_devices[path]
        logging.info(f"Detected new {device_type_name}: {path} ({device.name}) -> {output_path}")
        proxy = proxy_class(input_device_path=path, hid_output_path=output_path, loop=loop)
        task = asyncio.create_task(proxy.run())
        managed_devices[path] = {'task': task, 'hid_output': output_path}
    
    # Disconnected devices
    for path in (managed_paths - current_paths):
        logging.info(f"{device_type_name} {path} disconnected. Cleaning up.")
        info = managed_devices.pop(path)
        info['task'].cancel()
        available_hids.add(info['hid_output'])
        logging.info(f"Task cancelled, HID output {info['hid_output']} freed.")
