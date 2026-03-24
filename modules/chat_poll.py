"""
chat_poll.py — Module Google Chat polling parametrable.
Auto-discovers all spaces where the account is a member.
Usage : python3 chat_poll.py --config agents/boty/config.json
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import get_processed_ids, add_processed_ids, set_last_check
from agent_config import load_config, get_config

CHANNEL = "chat"

def run_gws(args, config_dir):
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)

def list_spaces(config_dir):
    """List all spaces where the account is a member."""
    try:
        data = run_gws(["chat", "spaces", "list", "--params",
                        json.dumps({"pageSize": 100})], config_dir)
        spaces = data.get("spaces", [])
        # Filter to GROUP_CHAT and SPACE types (skip DMs unless wanted)
        return [s for s in spaces if s.get("type") in ("ROOM", "SPACE", "GROUP_CHAT")]
    except RuntimeError:
        return []

def poll_space(agent_id, config_dir, space_id, dry_run=False):
    """Poll a single space for new messages."""
    try:
        data = run_gws(["chat", "spaces", "messages", "list", "--params",
                        json.dumps({"parent": space_id, "pageSize": 20, "orderBy": "createTime desc"})], config_dir)
    except RuntimeError as e:
        return [{"error": str(e), "agent_id": agent_id, "space_id": space_id}]
    messages = data.get("messages", [])
    if not messages:
        return []
    processed = get_processed_ids(agent_id, channel=CHANNEL)
    new = []
    for m in messages:
        mid = m.get("name", "").split("/")[-1]
        if not mid or mid in processed:
            continue
        if m.get("sender", {}).get("type") == "BOT":
            continue
        new.append({"id": mid, "name": m.get("name", ""), "space_id": space_id,
                    "text": m.get("text", m.get("argumentText", "")), "sender_type": "HUMAN",
                    "create_time": m.get("createTime", ""),
                    "detected_at": datetime.now(timezone.utc).isoformat()})
    if not dry_run and new:
        add_processed_ids(agent_id, [m["id"] for m in new], channel=CHANNEL)
    return new

def poll(config_path=None, space_id=None, dry_run=False):
    """Poll all spaces (or a specific one) for new messages."""
    cfg = get_config() if config_path is None else load_config(config_path)
    agent_id = cfg["agent_id"]
    config_dir = cfg["gws_config_dir"]

    if space_id:
        # Single space mode
        results = poll_space(agent_id, config_dir, space_id, dry_run)
        if not dry_run:
            set_last_check(agent_id, channel=CHANNEL)
        return results

    # Auto-discover all spaces
    spaces = list_spaces(config_dir)
    all_new = []
    for space in spaces:
        sid = space.get("name", "")
        if not sid:
            continue
        new = poll_space(agent_id, config_dir, sid, dry_run)
        all_new.extend([m for m in new if "error" not in m])

    if not dry_run:
        set_last_check(agent_id, channel=CHANNEL)
    return all_new

def send_reply(text, config_path=None, space_id=None):
    cfg = get_config() if config_path is None else load_config(config_path)
    space_id = space_id or cfg.get("chat_space")
    config_dir = cfg["gws_config_dir"]
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    subprocess.run(["gws", "chat", "+send", "--space", space_id, "--text", text],
                   capture_output=True, text=True, env=env)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--space-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--list-spaces", action="store_true")
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    if args.list_spaces:
        cfg = get_config()
        spaces = list_spaces(cfg["gws_config_dir"])
        for s in spaces:
            print(f"  {s.get('name')}  {s.get('displayName', '?')}  ({s.get('type', '?')})")
    else:
        msgs = poll(space_id=args.space_id, dry_run=args.dry_run)
        print(json.dumps(msgs, ensure_ascii=False, indent=2))
