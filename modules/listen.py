"""
listen.py — Orchestrateur Mode Ecoute. Combine Gmail + Chat polling.
Usage : python3 listen.py [gmail|chat|all] --config agents/boty/config.json
"""
import argparse, json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_config import load_config, get_config
import gmail_poll, chat_poll

def listen(config_path=None, channels=None, space_id=None, dry_run=False):
    cfg = get_config() if config_path is None else load_config(config_path)
    channels = channels or ["gmail","chat"]
    results = {"agent_id":cfg["agent_id"],"timestamp":datetime.now(timezone.utc).isoformat(),"channels":{}}
    if "gmail" in channels:
        try:
            emails = gmail_poll.poll(dry_run=dry_run)
            results["channels"]["gmail"] = {"status":"ok","new_count":len(emails),"items":emails,
                                             "summary":gmail_poll.format_summary(emails)}
        except Exception as e:
            results["channels"]["gmail"] = {"status":"error","error":str(e)}
    if "chat" in channels:
        sid = space_id or cfg.get("chat_space")
        try:
            msgs = chat_poll.poll(space_id=sid, dry_run=dry_run)
            results["channels"]["chat"] = {"status":"ok","new_count":len(msgs),"items":msgs}
        except Exception as e:
            results["channels"]["chat"] = {"status":"error","error":str(e)}
    total = sum(r.get("new_count",0) for r in results["channels"].values() if isinstance(r,dict))
    results["total_new"] = total
    results["has_new"] = total > 0
    return results

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("channel", nargs="?", default="all", choices=["gmail","chat","all"])
    p.add_argument("--config", default=None)
    p.add_argument("--space-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    if args.config:
        load_config(args.config)
    channels = ["gmail","chat"] if args.channel=="all" else [args.channel]
    result = listen(channels=channels, space_id=args.space_id, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n[Mode Ecoute] {result['agent_id']} — {result['timestamp']}")
        print(f"Nouveaux : {result['total_new']}")
        for ch, d in result["channels"].items():
            if isinstance(d,dict):
                print(f"  {ch}: {d.get('status')} — {d.get('new_count',0)} nouveau(x)")
                if d.get("summary"): print(f"\n{d['summary']}")
                if d.get("error"): print(f"  ERREUR: {d['error']}")
