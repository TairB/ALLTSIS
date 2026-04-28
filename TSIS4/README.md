# TSIS 4 Snake

Pygame Snake with:

- PostgreSQL leaderboard via `psycopg2`
- username entry on the main menu
- automatic session saving on game over
- personal best in the HUD
- weighted timed food from Practice 11
- poison food
- three power-ups
- level-based obstacles
- JSON settings screen

## Files

- `main.py` - entry point
- `game.py` - screens and gameplay
- `db.py` - database access
- `config.py` - constants and DB defaults
- `schema.sql` - PostgreSQL schema
- `settings.json` - saved local preferences

## Install

```bash
pip install -r requirements.txt
```

## PostgreSQL

Create a database, then either:

1. create a local `.env` file in the project folder from `.env.example`
2. or set env vars manually
3. or edit DB defaults in `config.py`

Recommended:

```bash
cp .env.example .env
```

Then fill `.env` like this:

```env
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

You can also use:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/your_database
```

## Run

```bash
python main.py
```

The schema is created automatically on startup.
