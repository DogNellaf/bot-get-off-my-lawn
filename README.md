# Get Off My Lawn — Bot

> 🇬🇧 English | [🇷🇺 Русский](README.ru.md)

A computer-vision bot that plays the arcade shooter **Get Off My Lawn** by itself. It captures the game window, finds the blue aliens by colour, decides which lane is most dangerous, and drives the character with keyboard input to keep an endless run going — restarting after death and shopping for upgrades between runs.

## Features

- Live capture of the game window by title (no screen recording, no injection)
- Alien detection by HSV colour inside the perspective lawn trapezoid
- Per-lane threat scoring with decay memory (survives the white flash of a hit alien)
- Wide-target handling (the multi-lane alien car spreads its threat across lanes)
- Automatic restart on death — declines the "spend 1000 balls to continue" dialog
- Automatic shop visits every few runs to buy upgrades
- Pause detection: recovers when the game shows its "click to continue" focus overlay
- Position resync after any in-game mouse click that nudges the character
- `--debug` mode: per-lane threat logging and annotated frame ring-buffer capture
- Calibration tools for the field geometry and UI button templates

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Computer vision | OpenCV (HSV masking, connected components, template matching) |
| Numerics | NumPy |
| Screen capture | mss |
| Window lookup | pywin32 (win32gui) |
| Input | pydirectinput (DirectInput-compatible keyboard/mouse) |

## Requirements

- Windows 10/11
- Python 3.11+
- The game **Get Off My Lawn** running at 1920×1080

## Installation

```powershell
# Clone the repository
git clone https://github.com/DogNellaf/bot-get-off-my-lawn
cd bot-get-off-my-lawn

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows (PowerShell)

# Install dependencies
pip install -r requirements.txt
```

## Usage

1. Launch **Get Off My Lawn** and make sure it runs at 1920×1080 in a window titled `Get Off My Lawn`.
2. Calibrate the field once (see below) so the bot knows where the lanes are.
3. Start the bot:

```powershell
python main.py
```

The bot focuses the game window, dismisses the pause overlay, and starts playing. Leave the game window visible and on top — the game pauses whenever it loses focus. Stop the bot with `Ctrl+C`.

### Debug mode

```powershell
python main.py --debug
```

Prints per-lane threat estimates once a second and continuously saves annotated frames into `calibration/debug_frames/`, so you can review exactly what the bot saw after a run.

## Calibration

Run these before the first launch (and again if the game resolution or layout changes). Each tool gives a short countdown, captures a frame while the game is focused, then opens an OpenCV window for you to make a selection.

```powershell
# Mark the four corners of the lawn trapezoid (TL, TR, BR, BL)
python calibrate.py field

# Capture the "Play Again" restart button template
python calibrate.py gameover
```

Utility scripts for tuning:

```powershell
# Save 20 annotated gameplay frames to calibration/captures/
python debug_capture.py

# Save 60 shop-screen frames to calibration/shop/
python explore_shop.py
```

## Configuration

Settings live in `config.json` (created automatically on first run from the defaults in `bot/config.py`). Key fields:

| Key | Description | Default |
|---|---|---|
| `window_title` | Title of the game window to capture | `Get Off My Lawn` |
| `lane_count` | Number of lanes on the lawn | `7` |
| `field_corners` | Lawn trapezoid corners (TL, TR, BR, BL) in client pixels | calibrated |
| `alien_hsv_lower` / `alien_hsv_upper` | HSV colour range for blue aliens | `[105,80,100]` / `[130,255,255]` |
| `min_blob_area` | Smallest blob (px²) counted as an alien | `300` |
| `move_left_key` / `move_right_key` / `fire_key` | Control keys | `a` / `d` / `space` |
| `step_cooldown` | Delay between lane moves (seconds) | `0.0` |
| `powerup_enabled` | Use emergency power-ups | `false` |
| `shop_enabled` | Visit the shop between runs | `true` |
| `shop_every_runs` | Runs between shop visits | `3` |

If the config's major version differs from the app version, it is regenerated from defaults.

## Project Structure

```
bot-get-off-my-lawn/
├── main.py                 # Entry point: loads config and runs the bot loop
├── bot/
│   ├── bot.py              # LawnBot: main capture → detect → decide → act loop
│   ├── config.py           # Config dataclass, load/save, versioning
│   ├── vision.py           # Field geometry, alien detection, pause/button detectors
│   ├── input_controller.py # DirectInput keyboard/mouse control and lane tracking
│   ├── window.py           # Locates the game window and its client area
│   └── logger.py           # Console logging helpers
├── calibrate.py            # Field-corner and button-template calibration
├── debug_capture.py        # Saves annotated gameplay frames
├── explore_shop.py         # Captures shop screens for tuning
├── config.json             # Runtime configuration (git-ignored)
├── calibration/            # Templates and captured frames (git-ignored)
└── requirements.txt
```

## License

[MIT](LICENSE)
