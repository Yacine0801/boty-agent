// heartbeat.js — Met a jour nodes_status/{agent_id} dans Firestore
// Env vars: ADP_SA_PATH, AGENT_ID, FIRESTORE_DB (or reads from AGENT_CONFIG_PATH)
const admin = require('/app/node_modules/firebase-admin');
const fs = require('fs');

let saPath = process.env.ADP_SA_PATH;
let agentId = process.env.AGENT_ID;
let firestoreDb = process.env.FIRESTORE_DB;

// Fallback: read from agent config file
if (!saPath || !agentId) {
  const cfgPath = process.env.AGENT_CONFIG_PATH;
  if (!cfgPath) {
    console.error('[heartbeat] ERR: set ADP_SA_PATH+AGENT_ID or AGENT_CONFIG_PATH');
    process.exit(1);
  }
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  saPath = saPath || cfg.firestore_sa_path;
  agentId = agentId || cfg.agent_id;
  firestoreDb = firestoreDb || cfg.firestore_db;
}

const key = JSON.parse(fs.readFileSync(saPath, 'utf8'));
const appName = 'heartbeat-' + Date.now();
const app = admin.initializeApp({ credential: admin.credential.cert(key) }, appName);
const db = admin.firestore(app);
if (firestoreDb) db.settings({ databaseId: firestoreDb });

db.collection('nodes_status').doc(agentId).set({
  status: 'active',
  last_updated: new Date(),
  source: 'agent-self-report'
}, { merge: true }).then(() => {
  process.exit(0);
}).catch(e => {
  console.error('[heartbeat] ERR', e.message);
  process.exit(1);
});
