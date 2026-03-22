"""
chat_poll.py — Module Google Chat polling parametrable.
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

def poll(config_path=None, space_id=None, dry_run=False):
    cfg = get_config() if config_path is None else load_config(config_path)
    agent_id = cfg["agent_id"]
    config_dir = cfg["gws_config_dir"]
    space_id = space_id or cfg.get("chat_space", "spaces/AAQAF8zXzRE")
    try:
        data = run_gws(["chat","spaces","messages","list","--params",
                        json.dumps({"parent":space_id,"pageSize":20,"orderBy":"createTime desc"})], config_dir)
    except RuntimeError as e:
        return [{"error": str(e), "agent_id": agent_id}]
    messages = data.get("messages", [])
    if not messages:
        set_last_check(agent_id, channel=CHANNEL); return []
    processed = get_processed_ids(agent_id, channel=CHANNEL)
    new = []
    for m in messages:
        mid = m.get("name","").split("/")[-1]
        if not mid or mid in processed: continue
        if m.get("sender",{}).get("type") == "BOT": continue
        new.append({"id":mid,"name":m.get("name",""),"space_id":space_id,
                    "text":m.get("text",m.get("argumentText","")),"sender_type":"HUMAN",
                    "create_time":m.get("createTime",""),
                    "detected_at":datetime.now(timezone.utc).isoformat()})
    if not dry_run and new:
        add_processed_ids(agent_id, [m["id"] for m in new], channel=CHANNEL)
        set_last_check(agent_id, channel=CHANNEL)
    return new

def send_reply(text, config_path=None, space_id=None):
    cfg = get_config() if config_path is None else load_config(config_path)
    space_id = space_id or cfg.get("chat_space")
    config_dir = cfg["gws_config_dir"]
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    subprocess.run(["gws","chat","+send","--space",space_id,"--text",text],
                   capture_output=True, text=True, env=env)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--space-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    msgs = poll(space_id=args.space_id, dry_run=args.dry_run)
    print(json.dumps(msgs, ensure_ascii=False, indent=2))
