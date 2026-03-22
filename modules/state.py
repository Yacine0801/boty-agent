"""
state.py — Gestion d'etat persistant pour les agents de polling.
Stockage : fichiers JSON locaux dans /home/node/.config/gws/accounts/state/
L'agent_id vient du config.json — un seul fichier d'etat par agent.
"""
import json
import os
from datetime import datetime, timezone

STATE_DIR = "/home/node/.config/gws/accounts/state"

def get_state_file(agent_id: str, channel: str = None) -> str:
    name = f"{agent_id}-{channel}" if channel else agent_id
    return os.path.join(STATE_DIR, f"{name}.json")

def read_state(agent_id: str, channel: str = None) -> dict:
    path = get_state_file(agent_id, channel)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def write_state(agent_id: str, state: dict, channel: str = None):
    os.makedirs(STATE_DIR, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(get_state_file(agent_id, channel), "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def get_processed_ids(agent_id: str, channel: str = None) -> set:
    return set(read_state(agent_id, channel).get("processed_ids", []))

def add_processed_ids(agent_id: str, new_ids: list, channel: str = None):
    state = read_state(agent_id, channel)
    ids = list(set(state.get("processed_ids", []) + new_ids))
    state["processed_ids"] = ids[-500:]
    write_state(agent_id, state, channel)

def set_last_check(agent_id: str, timestamp: str = None, channel: str = None):
    state = read_state(agent_id, channel)
    state["last_check_at"] = timestamp or datetime.now(timezone.utc).isoformat()
    write_state(agent_id, state, channel)

def get_last_check(agent_id: str, channel: str = None) -> str | None:
    return read_state(agent_id, channel).get("last_check_at")
