# -*- coding: utf-8 -*-
"""Explicit configuration for the local file exchange; no substring system guesses."""
import os
import sys
ENGINE_REPO_PATH = os.environ.get('PLUMBING_ENGINE_REPO_PATH') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
ENGINE_DB_PATH = os.environ.get('PLUMBING_ENGINE_DB_PATH') or os.path.join(ENGINE_REPO_PATH, 'database', 'plumbing_engine.db')
if ENGINE_REPO_PATH not in sys.path:
    sys.path.insert(0, ENGINE_REPO_PATH)
SYSTEM_NAME_MAP = {}  # Explicit project-approved custom names, e.g. {'Project CW': 'cold_water'}.
SYSTEM_CLASSIFICATION_MAP = {'domesticcoldwater': 'cold_water', 'domestichotwater': 'hot_water',
    'sanitary': 'drainage', 'vent': 'vent', 'storm': 'storm'}

def classify_system(name):
    if not name:
        return None
    if name in SYSTEM_NAME_MAP:
        return SYSTEM_NAME_MAP[name]
    return SYSTEM_CLASSIFICATION_MAP.get(''.join(c for c in name.lower() if c.isalnum()))

def get_engine_db_connection():
    import sqlite3
    if not os.path.isfile(ENGINE_DB_PATH):
        raise ValueError('Select an existing engine database; do not create a database from Revit.')
    conn = sqlite3.connect(ENGINE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn
