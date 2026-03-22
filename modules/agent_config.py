"""
agent_config.py — Loads agent config from JSON file.
Resolution order: --config arg > AGENT_CONFIG_PATH env var > default.
"""
import json
import os

_config = None

def load_config(path=None):
    global _config
    path = path or os.environ.get("AGENT_CONFIG_PATH")
    if not path:
        raise RuntimeError("No config: pass --config or set AGENT_CONFIG_PATH")
    with open(path, "r") as f:
        _config = json.load(f)
    from config_validator import validate_config
    validate_config(_config, [
        "agent_id", "gws_config_dir", "firestore_sa_path",
        "firestore_db", "firestore_node_doc",
    ])
    return _config

def get_config():
    if _config is None:
        load_config()
    return _config
