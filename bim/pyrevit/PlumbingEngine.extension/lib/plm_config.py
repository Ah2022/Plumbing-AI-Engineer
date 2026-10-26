# -*- coding: utf-8 -*-
"""
plm_config.py -- shared helper for both PlumbingEngine pushbuttons.

WHAT NEEDS EDITING BEFORE FIRST USE
------------------------------------
1. ENGINE_REPO_PATH and ENGINE_DB_PATH below -- point them at wherever
   this repo and its plumbing_engine.db actually live on your machine
   (or on the shared drive, if the engine DB is centralized).
2. SYSTEM_NAME_KEYWORDS -- Revit Piping System Type NAMES are whatever
   your project template calls them (e.g. "CW - Cold Water", "Domestic
   Cold", "DCW"...). I do not know your template's actual naming, so
   this is a keyword-matching guess, not verified data -- check it
   against your real system type names before trusting the extract,
   and edit the keyword lists to match exactly if they don't hit.
"""

import os
import sys

# --- 1. Locate the engine repo + DB (EDIT THESE) ---------------------------
ENGINE_REPO_PATH = r"C:\path\to\plumbing_engine"          # folder containing bim/, database/, calculations/
ENGINE_DB_PATH = os.path.join(ENGINE_REPO_PATH, "plumbing_engine.db")

if ENGINE_REPO_PATH not in sys.path:
    sys.path.insert(0, ENGINE_REPO_PATH)


# --- 2. Piping System Type name -> engine's 'system' vocabulary ------------
# engine vocabulary is fixed (bim/schemas.py:VALID_PIPE_SYSTEMS):
#   'cold_water' | 'hot_water' | 'drainage' | 'vent' | 'storm'
SYSTEM_NAME_KEYWORDS = {
    "cold_water": ["cold", "cw", "dcw"],
    "hot_water": ["hot", "hw", "dhw"],
    "drainage": ["sanitary", "san", "waste", "soil", "drain"],
    "vent": ["vent"],
    "storm": ["storm", "roof drain", "rwl", "rain"],
}


def classify_system(revit_system_type_name):
    """Best-effort keyword match against SYSTEM_NAME_KEYWORDS. Returns None
    (not a guess) if nothing matches -- an unclassified pipe is dropped
    from the extract with a warning rather than silently mis-tagged,
    since bim/schemas.py rejects any 'system' value outside the fixed
    vocabulary anyway."""
    if not revit_system_type_name:
        return None
    name = revit_system_type_name.lower()
    for engine_system, keywords in SYSTEM_NAME_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            return engine_system
    return None


def get_engine_db_connection():
    """CPython3 pyRevit engine ships stdlib sqlite3 -- no extra install
    needed. Returns a connection matching database/db.py's row_factory
    convention (sqlite3.Row) so the imported engine functions behave the
    same as when called from the Streamlit app."""
    import sqlite3
    conn = sqlite3.connect(ENGINE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
