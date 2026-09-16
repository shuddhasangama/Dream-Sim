const { registerPlugin } = require('@capacitor/core');

// Same plugin name the app already binds to directly via
// registerPlugin('SessionVault') in src/main.js — this export exists so
// 'session-vault' behaves like a normal Capacitor plugin package if anything
// ever imports it that way, not because anything currently does.
const SessionVault = registerPlugin('SessionVault');

module.exports = SessionVault;
module.exports.SessionVault = SessionVault;
