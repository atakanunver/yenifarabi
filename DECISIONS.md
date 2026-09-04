## 2026-09-04 - HTTP sürüm el sıkışması
- İstemci başlangıcında kimliği doğrulanmış `GET /api/version` çağrısıyla iki tarafın semantic sürümü karşılaştırılır.
- İletişim zaten HTTP/REST olduğundan kalıcı bağlantı protokolü eklenmeden MAJOR uyumsuzluğu ders başlamadan engellenir; MINOR/PATCH farkı uyarı olarak kalır.
