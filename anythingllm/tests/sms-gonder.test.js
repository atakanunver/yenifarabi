const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { handler } = require('../skills/sms-gonder/handler.js').runtime;
const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });
const args = { tur: 'veli', sinif: '9-A', metin: 'Merhaba' };
function mockApi(sinif = '9-A') {
  const calls = [];
  global.fetch = async (url) => {
    calls.push(url);
    return { ok: true, json: async () => calls.length === 1
      ? { taslak_id: 'abc', sinif, alici_sayisi: 2, metin: 'Merhaba' }
      : { alici_sayisi: 2, gonderim_id: 'test' } };
  };
  return calls;
}
function context(approval) {
  return { runtimeArgs: { SMS_API_KEY: 'test' }, super: { requestToolApproval: approval } };
}
test('gerçek kullanıcı onayı sonrasında gönderim ucunu çağırır', async () => {
  const calls = mockApi();
  const result = await handler.call(context(async () => ({ approved: true, message: 'User approved the tool execution.' })), args);
  assert.match(result, /gönderime alındı/);
  assert.equal(calls.length, 2);
});
test('ret ve otomatik onay göndermez', async () => {
  for (const approval of [{approved:false}, {approved:true,message:'Auto-approved by scheduled job runner.'}, {approved:true,message:'Skill is whitelisted - auto-approved.'}]) {
    const calls = mockApi();
    assert.match(await handler.call(context(async () => approval), args), /SMS gönderilmedi/);
    assert.equal(calls.length, 1);
  }
});
test('onay kanalı yoksa taslak bile oluşturmaz', async () => {
  const calls = mockApi();
  assert.match(await handler.call({runtimeArgs:{SMS_API_KEY:'test'},super:{}}, args), /SMS gönderilmedi/);
  assert.equal(calls.length, 0);
});
test('tüm okul taslağını göndermeden arayüze yönlendirir', async () => {
  const calls = mockApi('TÜM OKUL');
  assert.match(await handler.call(context(async () => { throw Error('onay istenmemeli'); }), args), /SMS gönderilmedi/);
  assert.equal(calls.length, 1);
});
test('gönderim hatasında tekrar denemeden kayıt kontrolü ister', async () => {
  let n = 0;
  global.fetch = async () => { if (++n === 2) throw Error('timeout'); return {ok:true,json:async()=>({taslak_id:'abc',sinif:'9-A',alici_sayisi:2,metin:'Merhaba'})}; };
  const result = await handler.call(context(async () => ({approved:true,message:'User approved the tool execution.'})), args);
  assert.match(result, /kayıtlarını kontrol/);
});
