"""
chat_poll.py — Module Google Chat polling parametrable.
Usage : python3 chat_poll.py --account sam --space-id spaces/AAQAF8zXzRE
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import get_processed_ids, add_processed_ids, set_last_check

ACCOUNT_CONFIGS = {
    "sam":   "/home/node/.config/gws/accounts/sam",
    "yacine":"/home/node/.config/gws",
    "eline": "/home/node/.config/gws/accounts/eline",
}
DEFAULT_SPACE = "spaces/AAQAF8zXzRE"

def run_gws(args, config_dir):
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)

def poll(account="sam", config_dir=None, space_id=DEFAULT_SPACE, dry_run=False):
    config_dir = config_dir or ACCOUNT_CONFIGS.get(account, ACCOUNT_CONFIGS["sam"])
    space_slug = space_id.replace("spaces/","")
    agent_id = f"{account}-chat-{space_slug}"
    try:
        data = run_gws(["chat","spaces","messages","list","--params",
                        json.dumps({"parent":space_id,"pageSize":20,"orderBy":"createTime desc"})], config_dir)
    except RuntimeError as e:
        return [{"error": str(e), "agent_id": agent_id}]
    messages = data.get("messages", [])
    if not messages:
        set_last_check(agent_id); return []
    processed = get_processed_ids(agent_id)
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
        add_processed_ids(agent_id, [m["id"] for m in new])
        set_last_check(agent_id)
    return new

def send_reply(space_id, text, account="sam", config_dir=None):
    config_dir = config_dir or ACCOUNT_CONFIGS.get(account)
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    subprocess.run(["gws","chat","+send","--space",space_id,"--text",text],
                   capture_output=True, text=True, env=env)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--account", default="sam")
    p.add_argument("--config-dir", default=None)
    p.add_argument("--space-id", default=DEFAULT_SPACE)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    msgs = poll(args.account, args.config_dir, args.space_id, args.dry_run)
    print(json.dumps(msgs, ensure_ascii=False, indent=2))
