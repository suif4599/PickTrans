# PickTrans

PickTrans is a text-selection translator for Linux Wayland.

It uses [`hotkey_manager`](https://github.com/suif4599/hotkey-manager) to bypass Wayland limits on global hotkeys and Primary Selection access, so you can trigger translation popups from any window.

## Features

- Works on Wayland
- Global hotkey trigger from any application
- Reads Primary Selection and shows a popup near cursor
- Pluggable translation engines
- Built-in engines:
  - `SDCVEngine` for local dictionary lookup (`sdcv`)
  - `OllamaEngine` for Ollama API translation
- Tray menu actions:
  - Authenticate
  - Register/Restart user service (`systemd --user`)
  - Open `config.json`

## Requirements

- Linux (Wayland)
- Python 3.10+
- `PyQt6`
- `pexpect`
- `psutil`
- `hotkey_manager` built and installed from source (not available from PyPI)
- `sdcv` (if using `SDCVEngine`)
- Running Ollama service and model (if using `OllamaEngine`)

## Install

1. Clone this repository.
2. Install Python dependencies:

```bash
pip install PyQt6 pexpect psutil
```

3. Build and install `hotkey_manager` from source:

[`hotkey_manager` source repository](https://github.com/suif4599/hotkey-manager)

4. (Optional) Install and configure external engines:
- `sdcv` + dictionaries for `SDCVEngine`
- Ollama + model for `OllamaEngine`

## Run

```bash
python main.py
```

After launch, use the tray icon to authenticate and enable hotkey support or register the program as user service.

## Configuration

Edit `config.json`:

- `engines`: engine definitions and parameters
- `engine-order`: load order and fallback order
- `app.trigger_hotkey`: popup trigger hotkey (default example: `Double(LEFTALT)`)
- `app.exit_hotkey`: close popup hotkey (default: `ESC`)
- `app.width` / `app.height`:
  - integer: fixed pixel size
  - float: ratio of current screen size

Example engine setup is already included in `config.json`.

## License

GPL-3.0 (see `LICENSE`).
