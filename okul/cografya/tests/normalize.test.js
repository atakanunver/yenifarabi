const { test } = require('node:test');
const assert = require('node:assert/strict');
const { eslesir } = require('../static/normalize.js');
test('Türkçe büyük-küçük harf ve aksanlar', () => {
  for (const s of ['İslamabad', 'islamabad', 'ISLAMABAD', 'Islamabad']) assert.ok(eslesir(s, 'İslamabad'));
  for (const [a,b] of [['Aşkabat','askabat'], ['Üsküp','uskup'], ['Türkiye','turkiye'], ['  Yeni   Zelanda ', 'yeni zelanda']]) assert.ok(eslesir(a,b));
  assert.ok(eslesir('Turkiye', 'Türkiye', ['Anadolu']));
  assert.ok(eslesir('Anadolu', 'Türkiye', [['Anadolu', 'diğer ad']]));
  assert.equal(eslesir('Ankara', 'İstanbul'), false);
});

test('oyun ülke ve başkent eş adlarını ayrı kullanır', () => {
  const vm = require('node:vm');
  const fs = require('node:fs');
  const context = vm.createContext({
    window: { addEventListener() {} },
    fuzzysort: { prepare: s => s },
    CografyaNormalize: require('../static/normalize.js'),
    console,
  });
  vm.runInContext(fs.readFileSync(require.resolve('../static/script.js'), 'utf8'), context);
  vm.runInContext(`
    setupDataStructs({PAK: {name: 'Pakistan', capital: 'İslamabad', capitalAliases: ['Islamabad'], region: 'Asya'}});
    setAliases({PAK: [['Pakistan İslam Cumhuriyeti', 'türkçe alternatif']]});
    game = {mode: 2, answer: 'PAK', modeData: {a: 'capital'}};
    submitAnswer = id => { globalThis.result = id; };
    onFRKeyDown({key: 'Enter', preventDefault() {}}, {value: 'Islamabad'});
  `, context);
  assert.equal(context.result, 'PAK');
  assert.ok(vm.runInContext("capital2codeEx('Islamabad').includes('PAK')", context));
  assert.ok(vm.runInContext("name2codeEx('Pakistan İslam Cumhuriyeti').includes('PAK')", context));
  vm.runInContext("game.modeData.a = 'name'; onFRKeyDown({key: 'Enter', preventDefault() {}}, {value: 'İslamabad'});", context);
  assert.equal(context.result, null);
  vm.runInContext("onFRKeyDown({key: 'Enter', preventDefault() {}}, {value: 'Pakistan İslam Cumhuriyeti'});", context);
  assert.equal(context.result, 'PAK');
});
