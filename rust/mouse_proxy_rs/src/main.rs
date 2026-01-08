use anyhow::{Context, Result};
use clap::Parser;
use evdev::{Device, InputEventKind, Key, RelativeAxisType};
use log::{error, info};
use std::fs::OpenOptions;
use std::io::Write;

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[arg(required = true)]
    input_device: String,
    #[arg(required = true)]
    output_device: String,
}

const REPORT_SIZE: usize = 7;

struct MouseState {
    btn_left: u8,
    btn_right: u8,
    btn_middle: u8,
    btn_side: u8,
    btn_extra: u8,
    move_x: i16,
    move_y: i16,
    scroll_y: i16,
}

impl MouseState {
    fn new() -> Self {
        Self {
            btn_left: 0,
            btn_right: 0,
            btn_middle: 0,
            btn_side: 0,
            btn_extra: 0,
            move_x: 0,
            move_y: 0,
            scroll_y: 0,
        }
    }

    fn to_report(&self) -> [u8; REPORT_SIZE] {
        let buttons = self.btn_left | self.btn_right | self.btn_middle | self.btn_side | self.btn_extra;
        let mut report = [0u8; REPORT_SIZE];
        report[0] = buttons;
        // Padding is removed as per descriptor change (7 bytes)
        let x = self.move_x.to_le_bytes();
        let y = self.move_y.to_le_bytes();
        let w = self.scroll_y.to_le_bytes();
        report[1] = x[0]; report[2] = x[1];
        report[3] = y[0]; report[4] = y[1];
        report[5] = w[0]; report[6] = w[1];
        report
    }

    fn reset_rel(&mut self) {
        self.move_x = 0;
        self.move_y = 0;
        self.scroll_y = 0;
    }
}

async fn run_proxy(device_path: &str, output_path: &str) -> Result<()> {
    let device = Device::open(device_path).context("Failed to open input device")?;
    let name = device.name().unwrap_or("Unknown");
    
    info!("Starting MouseProxy for {} ({}) -> {}", name, device_path, output_path);

    let mut output_file = OpenOptions::new()
        .write(true)
        .read(true)
        .open(output_path)
        .context(format!("Failed to open output {}", output_path))?;

    let mut state = MouseState::new();
    let mut input_stream = device.into_event_stream()?;

    loop {
        match input_stream.next_event().await {
            Ok(event) => {
                match event.kind() {
                    InputEventKind::Key(key) => {
                        let is_press = event.value() == 1;
                        match key {
                            Key::BTN_LEFT => state.btn_left = if is_press { 1 } else { 0 },
                            Key::BTN_RIGHT => state.btn_right = if is_press { 2 } else { 0 },
                            Key::BTN_MIDDLE => state.btn_middle = if is_press { 4 } else { 0 },
                            Key::BTN_SIDE => state.btn_side = if is_press { 8 } else { 0 },
                            Key::BTN_EXTRA => state.btn_extra = if is_press { 16 } else { 0 },
                            _ => {}
                        }
                    }
                    InputEventKind::RelAxis(axis) => {
                        match axis {
                            RelativeAxisType::REL_X => state.move_x = event.value() as i16,
                            RelativeAxisType::REL_Y => state.move_y = event.value() as i16,
                            RelativeAxisType::REL_WHEEL => state.scroll_y = event.value() as i16,
                            _ => {}
                        }
                    }
                    InputEventKind::Synchronization(_) => {
                        let report = state.to_report();
                        if let Err(e) = output_file.write_all(&report) {
                            error!("Failed to write report: {}", e);
                            break;
                        }
                        state.reset_rel();
                    }
                    _ => {}
                }
            }
            Err(e) => {
                error!("Input device error: {}", e);
                break;
            }
        }
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    env_logger::init();
    let args = Args::parse();

    if let Err(e) = run_proxy(&args.input_device, &args.output_device).await {
        error!("Proxy error: {}", e);
        std::process::exit(1);
    }
    Ok(())
}
