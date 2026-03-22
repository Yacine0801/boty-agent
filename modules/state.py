"""
state.py — Gestion d'etat persistant pour les agents de polling.
Stockage : fichiers JSON locaux dans /home/node/.config/gws/accounts/state/
Parametrable : chaque agent a son propre fichier d'etat (agent_id).
"""
import json
import os
from datetime import datetime, timezone

STATE_DIR = "/home/node/.config/gws/accounts/state"

def get_state_file(agent_id: str) -> str:
    return os.path.join(STATE_DIR, f"{agent_id}.json")

def read_state(agent_id: str) -> dict:
    path = get_state_file(agent_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def write_state(agent_id: str, state: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(get_state_file(agent_id), "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def get_processed_ids(agent_id: str) -> set:
    return set(read_state(agent_id).get("processed_ids", []))

def add_processed_ids(agent_id: str, new_ids: list):
    state = read_state(agent_id)
    ids = list(set(state.get("processed_ids", []) + new_ids))
    state["processed_ids"] = ids[-500:]
    write_state(agent_id, state)

def set_last_check(agent_id: str, timestamp: str = None):
    state = read_state(agent_id)
    state["last_check_at"] = timestamp or datetime.now(timezone.utc).isoformat()
    write_state(agent_id, state)

def get_last_check(agent_id: str) -> str | None:
    return read_state(agent_id).get("last_check_at")
