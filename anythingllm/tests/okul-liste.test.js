const { test } = require("node:test");
const assert = require("node:assert/strict");
const { handler } = require("../skills/okul-liste/handler.js").runtime;
const cikti = require("../skills/_ortak/cikti.js");
const okul = require("../skills/_ortak/okul.js");

const agent = { runtimeArgs: { OKUL_API_URL: "http://test.invalid/liste", OKUL_API_KEY: "test" } };
const veri = {
  baslik: "Sınıf Listesi", kolonlar: ["Sınıf"], satirlar: [["9-A"]], satir_sayisi: 1,
  okul_adi: "Test Kurumu", mudur_adi: "Test Yöneticisi",
};

function sahteFetch(t, sonuc, status = 200) {
  return t.mock.method(globalThis, "fetch", async () => ({
    ok: status === 200, status, json: async () => sonuc,
  }));
}

test("metin varsayılandır ve istek yalnız liste parametrelerini içerir", async (t) => {
  const fetch = sahteFetch(t, veri);
  assert.equal(await handler.call(agent, { tur: "sinif", sinif: "9-A", dosya_adi: "liste" }), "Sınıf\n9-A");
  const [url, istek] = fetch.mock.calls[0].arguments;
  assert.equal(url, agent.runtimeArgs.OKUL_API_URL);
  assert.equal(istek.method, "POST");
  assert.equal(istek.headers["X-Farabi-Rol"], "admin");
  assert.equal(istek.headers["X-Farabi-Okul-Key"], "test");
  assert.deepEqual(JSON.parse(istek.body), { tur: "sinif", sinif: "9-A" });
});

test("Türkçe liste türleri API değerlerine çevrilir", async (t) => {
  const fetch = sahteFetch(t, veri);
  for (const [girdi, tur] of [["Sınıf", "sinif"], ["KULÜP", "kulup"], ["ÖĞRETMEN", "ogretmen"], ["ÖĞRENCİ", "ogrenci"]]) {
    await handler.call(agent, { tur: girdi });
    assert.equal(JSON.parse(fetch.mock.calls.at(-1).arguments[1].body).tur, tur);
  }
});

for (const [girdi, tur] of [["xlsx", "xlsx"], ["docx", "docx"], ["pdf", "pdf"], ["ExCeL", "xlsx"], ["WORD", "docx"]]) {
  test(`${girdi} çıktısı doğru başlık ve veriyle indirme kartına gönderilir`, async (t) => {
    sahteFetch(t, veri);
    const buffer = Buffer.from("test");
    const uret = t.mock.method(tur === "pdf" ? okul : cikti, tur + "Buffer", async () => buffer);
    const kaydet = t.mock.method(cikti, "dosyaKaydet", async () => {});
    const mesaj = await handler.call(agent, { tur: "sinif", sinif: "9-A", cikti_formati: girdi, dosya_adi: "9/A" });
    assert.match(mesaj, /İndirme kartı/);
    const [baslik, tablo] = uret.mock.calls[0].arguments;
    if (tur === "docx") {
      assert.ok(baslik.tarih);
      assert.deepEqual(baslik, { baslik: veri.baslik, okulAdi: veri.okul_adi, mudurAdi: veri.mudur_adi, tarih: baslik.tarih });
    } else {
      assert.equal(baslik, veri.baslik);
    }
    assert.deepEqual(tablo, veri);
    assert.deepEqual(kaydet.mock.calls[0].arguments, [agent, tur, buffer, "9_A." + tur]);
  });
}

test("boş sonuçta dosya oluşturulmaz", async (t) => {
  sahteFetch(t, { ...veri, satirlar: [], satir_sayisi: 0 });
  const uret = t.mock.method(cikti, "docxBuffer", async () => {});
  const kaydet = t.mock.method(cikti, "dosyaKaydet", async () => {});
  assert.match(await handler.call(agent, { tur: "dyk", cikti_formati: "docx" }), /eşleşen kayıt yok/);
  assert.equal(uret.mock.callCount(), 0);
  assert.equal(kaydet.mock.callCount(), 0);
});

test("HTTP 400 açıklamasını gösterir", async (t) => {
  sahteFetch(t, { hata: "Liste alınamadı." }, 400);
  assert.equal(await handler.call(agent, { tur: "dyk" }), "Liste alınamadı.");
});
