// Render the real table functions against an in-memory DOM stub, no game/RPC.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, 'Animus_loader/web/app.js'), 'utf8');
const tableCode = source.slice(source.indexOf('function updateStatusCell('), source.indexOf('function addLog('));
const escapeCode = source.slice(source.indexOf('function escapeHtml('), source.indexOf('function normalizeReplacementSlot('));
for (const tab of ['mods', 'outfits', 'weapons', 'crew', 'sails']) {
  const nodes = {};
  const context = {
    app: { tab },
    $: key => nodes[key] ||= {},
    currentRows: () => [{id: 'test', name: '<Long & name>', version: '2.0', author: 'Tester',
      enabled: false, replaces: ['Vanilla'], previous_version: '1.0', updated_version: '2.0',
      updated_at: '2026-09-15T12:00:00-06:00'}],
    rowTooltip: () => '', normalizeReplacementSlot: value => value,
  };
  vm.runInNewContext(escapeCode + tableCode + '\nrenderTable();', context);
  const body = nodes['#table-body'].innerHTML;
  const head = nodes['#table-head'].innerHTML;
  assert.equal((head.match(/<th[ >]/g) || []).length, 7, tab);
  assert.equal((body.match(/<td[ >]/g) || []).length, 7, tab);
  assert.match(body, /Updated/);
  assert.match(body, /1.0 → 2.0/);
  assert.match(body, /Disabled/);
  assert.match(body, /&lt;Long &amp; name&gt;/);
}
console.log('PASS: version/status rendering and escaped names in all five tabs.');
