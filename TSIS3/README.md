# TSIS 3 – Racer Game

## Repository structure
```
TSIS3/
├── main.py            ← Entry point
├── racer.py           ← Game engine (gameplay logic)
├── ui.py              ← All Pygame screens (menu, settings, leaderboard, game-over)
├── persistence.py     ← JSON save/load for leaderboard & settings
├── settings.json      ← Saved preferences (auto-created on first run)
├── leaderboard.json   ← Top-10 scores (auto-created on first run)
├── README.md
└── assets/
    ├── AnimatedStreet.png
    ├── Player.png
    ├── Enemy.png
    ├── background.wav
    └── crash.wav
```

## How to run
```bash
pip install pygame
python main.py
```

## Controls
| Key | Action |
|-----|--------|
| ← → | Move car left / right |
| ↑ ↓ | Move car forward / back (within lower half) |
| ESC | Pause → Main Menu |

## Features (TSIS 3)
- **Main Menu** – Play, Leaderboard, Settings, Quit
- **Name Entry** – username stored for leaderboard
- **Settings Screen** – toggle sound, car colour (blue/red), difficulty (easy/normal/hard)
- **Lane Hazards** – oil spills (slow), slow zones
- **Road Events** – barriers (damage), speed bumps (slow), nitro strips (boost)
- **Traffic Cars** – multiple enemies, safe-spawn, difficulty scaling
- **Obstacles** – potholes and debris scattered randomly
- **Power-Ups**
  - ⚡ Nitro – 1.7× speed for 4 seconds
  - 🛡 Shield – absorbs one collision
  - 🔧 Repair – recovers one crash counter
- **Score** = coins × 10 + distance ÷ 5
- **Distance meter** – 3 000 m race with progress bar
- **Persistent leaderboard** – top-10 saved to `leaderboard.json`
- **Game Over screen** – shows score / distance / coins, Retry or Main Menu

## Difficulty scaling
| Difficulty | Start speed | Enemies | Obstacle interval |
|-----------|-------------|---------|------------------|
| Easy      | 4           | 1       | 4 000 ms         |
| Normal    | 5           | 2       | 2 800 ms         |
| Hard      | 7           | 3       | 1 800 ms         |

Speed auto-increases every 1.2 s regardless of difficulty.
New traffic cars are added whenever the current enemy count is below the cap.
