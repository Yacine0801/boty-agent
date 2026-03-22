"""
gmail_poll.py — Module Gmail polling parametrable.
Usage : python3 gmail_poll.py --config agents/boty/config.json --summary
"""
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from state import get_processed_ids, add_processed_ids, set_last_check
from agent_config import load_config, get_config

CHANNEL = "gmail"
AUTO_KEYWORDS = ["unsubscribe","noreply","no-reply","newsletter","notification","google.com","mail-noreply"]

def run_gws(args, config_dir=None):
    env = os.environ.copy()
    if config_dir:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    r = subprocess.run(["gws"] + args, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return json.loads(r.stdout)

def classify(email, cfg):
    s = email.get("from","").lower()
    subj = email.get("subject","").lower()
    if any(x in s for x in cfg.get("gmail_urgent_senders", [])): return "URGENT"
    if any(x in s for x in cfg.get("gmail_important_senders", [])): return "IMPORTANT"
    if any(x in s or x in subj for x in AUTO_KEYWORDS): return "INFO"
    return "IMPORTANT"

def poll(config_path=None, max_results=20, dry_run=False):
    cfg = get_config() if config_path is None else load_config(config_path)
    agent_id = cfg["agent_id"]
    config_dir = cfg["gws_config_dir"]
    try:
        data = run_gws(["gmail","users","messages","list","--params",
                        json.dumps({"userId":"me","q":"is:unread","maxResults":max_results})], config_dir)
    except RuntimeError as e:
        return [{"error": str(e), "agent_id": agent_id}]
    messages = data.get("messages", [])
    if not messages:
        set_last_check(agent_id, channel=CHANNEL); return []
    processed = get_processed_ids(agent_id, channel=CHANNEL)
    new_ids = [m["id"] for m in messages if m["id"] not in processed]
    if not new_ids:
        set_last_check(agent_id, channel=CHANNEL); return []
    emails = []
    for mid in new_ids[:10]:
        try:
            d = run_gws(["gmail","users","messages","get","--params",
                         json.dumps({"userId":"me","id":mid,"format":"metadata",
                                     "metadataHeaders":["From","Subject","Date"]})], config_dir)
            hdrs = {h["name"]:h["value"] for h in d.get("payload",{}).get("headers",[])}
            e = {"id":mid,"from":hdrs.get("From",""),"subject":hdrs.get("Subject",""),
                 "date":hdrs.get("Date",""),"snippet":d.get("snippet",""),
                 "detected_at":datetime.now(timezone.utc).isoformat()}
            e["urgency"] = classify(e, cfg)
            emails.append(e)
        except: continue
    if not dry_run and emails:
        add_processed_ids(agent_id, [e["id"] for e in emails], channel=CHANNEL)
        set_last_check(agent_id, channel=CHANNEL)
    return emails

def format_summary(emails):
    if not emails: return ""
    urgent = [e for e in emails if e["urgency"]=="URGENT"]
    important = [e for e in emails if e["urgency"]=="IMPORTANT"]
    info = [e for e in emails if e["urgency"]=="INFO"]
    lines = [f"Nouveaux emails ({len(emails)}) :"]
    if urgent:
        lines.append(f"\nURGENT ({len(urgent)}) :")
        for e in urgent:
            lines.append(f"  {e['from'].split('<')[0].strip()} : {e['subject']}")
            if e.get("snippet"): lines.append(f"  -> {e['snippet'][:80]}")
    if important:
        lines.append(f"\nIMPORTANT ({len(important)}) :")
        for e in important:
            lines.append(f"  {e['from'].split('<')[0].strip()} : {e['subject']}")
    if info:
        lines.append(f"\nInfo : {len(info)} notification(s) auto")
    return "\n".join(lines)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--max-results", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--summary", action="store_true")
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    emails = poll(max_results=args.max_results, dry_run=args.dry_run)
    print(format_summary(emails) if args.summary else json.dumps(emails, ensure_ascii=False, indent=2))
