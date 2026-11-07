// SMS: önce sunucuda taslak, ardından gerçek kullanıcı onayı, ardından gönderim.
const TUR = new Set(['veli', 'ogrenci', 'personel']);
async function istek(yol, govde, key) {
  const r = await fetch(`http://127.0.0.1:8020/api/arac/${yol}`, {
    method: 'POST', headers: {'Content-Type':'application/json', 'X-Sms-Arac-Key':key},
    body: JSON.stringify(govde), signal: AbortSignal.timeout(20000),
  });
  const veri = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(veri.detail || `SMS servisi HTTP ${r.status}`);
  return veri;
}
module.exports.runtime = {
  handler: async function ({ tur, sinif, metin }) {
    if (!TUR.has(tur) || typeof metin !== 'string' || !metin.trim()) return 'Alıcı türü ve mesaj gerekli.';
    if (tur !== 'personel' && (typeof sinif !== 'string' || !sinif.trim())) return 'Sınıf adı gerekli.';
    if (!this.runtimeArgs?.SMS_API_KEY) return 'SMS anahtarı yapılandırılmamış; SMS gönderilmedi.';
    if (typeof this.super?.requestToolApproval !== 'function') return 'Kullanıcı onayı bu oturumda desteklenmiyor; SMS gönderilmedi.';
    try {
      const govde = tur === 'personel' ? {metin} : {sinif, metin};
      const taslak = await istek(`${tur}-taslak`, govde, this.runtimeArgs.SMS_API_KEY);
      // Tüm okul gönderimi ayrıca kullanıcının alıcı sayısını yazmasını gerektirir.
      if (taslak.sinif === 'TÜM OKUL') return `Tüm okul gönderimi için SMS arayüzündeki sayı onayını kullanın. SMS gönderilmedi. Taslak: ${taslak.taslak_id}, alıcı: ${taslak.alici_sayisi}.`;
      const hedef = tur === 'personel' ? 'personel' : `${taslak.sinif} ${tur}`;
      const onay = await this.super.requestToolApproval({
        skillName: 'SMS Gönder',
        payload: {hedef, alici_sayisi: taslak.alici_sayisi, mesaj: taslak.metin, taslak_id: taslak.taslak_id},
        description: `${hedef} için ${taslak.alici_sayisi} alıcıya SMS gönderilsin mi? Mesaj: ${taslak.metin}`,
      });
      // Otomatik onay/izin listesi/zamanlanmış görev geçerli kullanıcı onayı değildir.
      if (!onay?.approved || onay.message !== 'User approved the tool execution.') return 'Kullanıcı onayı alınmadı; SMS gönderilmedi.';
      const sonuc = await istek(`${tur}-gonder`, {taslak_id: taslak.taslak_id}, this.runtimeArgs.SMS_API_KEY);
      return `SMS gönderime alındı. Hedef: ${hedef}, alıcı: ${sonuc.alici_sayisi}, gönderim: ${sonuc.gonderim_id}.`;
    } catch (e) {
      // İstek zaman aşımı, gönderimin gerçekleşmediğini kanıtlamaz.
      return `SMS işlemi tamamlanamadı veya sonucu doğrulanamadı: ${e.message}. Tekrar denemeden gönderim kayıtlarını kontrol edin.`;
    }
  },
};
