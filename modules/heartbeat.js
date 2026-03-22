// heartbeat.js — Met à jour nodes_status/boty dans adp-413110 toutes les 15 min
const admin = require('/app/node_modules/firebase-admin');
const fs = require('fs');

const key = JSON.parse(fs.readFileSync('/workspace/project/adp-service-account.json'));
const appName = 'heartbeat-' + Date.now();
const app = admin.initializeApp({ credential: admin.credential.cert(key) }, appName);
const db = admin.firestore(app);
db.settings({ databaseId: 'agents' });

db.collection('nodes_status').doc('boty').update({
  status: 'active',
  last_updated: new Date(),
  source: 'agent-self-report'
}).then(() => {
  process.exit(0);
}).catch(e => {
  console.error('[heartbeat] ERR', e.message);
  process.exit(1);
});
