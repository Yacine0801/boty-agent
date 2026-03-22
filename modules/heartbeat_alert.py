"""
heartbeat_alert.py — Checks agent heartbeat in Firestore, writes alert file if down.
Usage: python3 heartbeat_alert.py --config agents/boty/config.json
"""
import argparse, json, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import load_config, get_config

ALERT_FILE = "/tmp/boty-alert.json"
DOWN_THRESHOLD = timedelta(minutes=5)

def check_heartbeat_alert(config: dict = None) -> None:
    cfg = config or get_config()
    agent_id = cfg["agent_id"]
    sa_path = cfg["firestore_sa_path"]
    db_id = cfg.get("firestore_db", "agents")
    node_doc = cfg.get("firestore_node_doc", f"nodes_status/{agent_id}")

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        # Fallback: use node heartbeat.js instead
        print(f"[heartbeat_alert] firebase_admin not installed, skipping")
        return

    cred = credentials.Certificate(sa_path)
    app_name = f"heartbeat-alert-{agent_id}"
    try:
        app = firebase_admin.get_app(app_name)
    except ValueError:
        app = firebase_admin.initialize_app(cred, name=app_name)

    db = firestore.client(app, database_id=db_id)
    collection, doc_id = node_doc.split("/", 1)
    doc = db.collection(collection).document(doc_id).get()

    now = datetime.now(timezone.utc)

    if not doc.exists:
        _write_alert(agent_id, "never seen")
        return

    data = doc.to_dict()
    last_updated = data.get("last_updated")

    if not last_updated:
        _write_alert(agent_id, "no last_updated field")
        return

    if hasattr(last_updated, 'timestamp'):
        last_dt = datetime.fromtimestamp(last_updated.timestamp(), tz=timezone.utc)
    else:
        last_dt = datetime.fromisoformat(str(last_updated).replace("Z", "+00:00"))

    if now - last_dt > DOWN_THRESHOLD:
        _write_alert(agent_id, last_dt.isoformat())
    else:
        # All good — remove stale alert if any
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)

def _write_alert(agent_id: str, since: str):
    alert = {"type": "down", "agent": agent_id, "since": since,
             "detected_at": datetime.now(timezone.utc).isoformat()}
    with open(ALERT_FILE, "w") as f:
        json.dump(alert, f, indent=2)
    print(f"[heartbeat_alert] ALERT: {agent_id} down since {since}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    check_heartbeat_alert()
