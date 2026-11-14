// AnythingLLM kalıcı hafıza (memories) yönetim yeteneği.
// Kullanıcı 'hafızana kaydet', 'bunu hatırla', 'hafızandakileri göster' dediğinde devreye girer.
const path = require("path");

module.exports.runtime = {
  handler: async function ({ islem = "kaydet", icerik = "", id = null }) {
    try {
      const SUNUCU = "/opt/anythingllm/app/server";
      const { Memory } = require(path.join(SUNUCU, "models/memory.js"));
      const workspaceId = this.super?.handlerProps?.invocation?.workspace_id || 1;
      const userId = this.super?.handlerProps?.invocation?.user_id || null;

      if (islem === "kaydet") {
        if (!icerik || !icerik.trim()) {
          return "Kaydedilecek içerik boş; lütfen kaydedilecek bilgiyi belirtin.";
        }
        if (typeof this.introspect === "function") {
          this.introspect("Bilgi kalıcı hafızaya kaydediliyor…");
        }
        const { memory, message } = await Memory.create({
          userId,
          workspaceId: Number(workspaceId),
          scope: "workspace",
          content: icerik.trim(),
        });
        if (!memory) {
          return `Hafızaya kaydedilemedi: ${message || "Bilinmeyen hata"}`;
        }
        return `Başarıyla kalıcı hafızaya kaydedildi (Hafıza ID: ${memory.id}). Bu bilgi artık tüm yeni sohbetlerde otomatik olarak hatırlanacaktır.`;
      }

      if (islem === "listele") {
        if (typeof this.introspect === "function") {
          this.introspect("Kayıtlı hafızalar getiriliyor…");
        }
        const memories = await Memory.forUserWorkspace(userId, Number(workspaceId));
        if (!memories.length) return "Kalıcı hafızada şu an kayıtlı bir bilgi bulunmuyor.";
        return "Kayıtlı Hafıza Maddeleri:\n" + memories.map((m) => `- [ID: ${m.id}] ${m.content}`).join("\n");
      }

      if (islem === "sil") {
        if (!id) return "Silinecek hafıza kaydının ID numarası belirtilmedi.";
        if (typeof this.introspect === "function") {
          this.introspect(`Hafıza kaydı (ID: ${id}) siliniyor…`);
        }
        const ok = await Memory.delete(Number(id));
        return ok ? `Hafıza kaydı (ID: ${id}) başarıyla silindi.` : `Hafıza kaydı (ID: ${id}) silinemedi.`;
      }

      return `Bilinmeyen işlem türü: "${islem}". Geçerli işlemler: 'kaydet', 'listele', 'sil'.`;
    } catch (e) {
      return `Hafıza işleminde hata oluştu: ${e.message}`;
    }
  },
};
