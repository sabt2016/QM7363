"""Local configuration. Copy to config.py and edit. config.py is gitignored.

Every path below is yours alone. Nothing here gets committed, so nobody has to
match anybody else's folder layout.
"""
from pathlib import Path

# Where you put the shared data folder. Use a raw string on Windows.
DATA_DIR = Path(r"C:\Users\you\OneDrive\QM7363\data")

PANEL_FILE = DATA_DIR / "final_panel.xlsx"
CACHE_FILE = DATA_DIR / "final_panel.parquet"   # built on first load, much faster

# One seed for the whole project. Do not change it without a decision log entry.
SEED = 20260928

# Temporal split. Confirm in task 1.4 before anyone reports a number.
TRAIN_END_YEAR = 2017
TEST_START_YEAR = 2018

# API keys come from a .env file, never from here. See README.
