# Dry-run (Sanal İşlem) Kontrol Listesi — Aşama 4

İki bot çalışır, ikisi de **sanal** (gerçek emir yok), her biri 100 USDT sanal bakiyeyle:

| Bot | Strateji | Ayar | Amaç |
|---|---|---|---|
| `freqtrade` (FreqUI: http://127.0.0.1:8080) | **EmaAdxTrend** | 3.0 × ATR stop, takip eden stop, 5x | Aşama 5'te gerçek paraya geçecek aday |
| `freqtrade-combo` (FreqUI: http://127.0.0.1:8081) | ComboTrend | 2.0 × ATR stop, sabit kâr al (2R), 5x | **Sadece gözlem.** Kurallara göre seçilmedi |

Backtest beklentisi (`reports/dryrun_expectations.json`, 2025-01 → 2026-10 out-of-sample):

| | İşlem / hafta | Haftalık getiri | Kazanma oranı | Kâr faktörü | Backtestteki en kötü düşüş | Ort. işlem süresi |
|---|---|---|---|---|---|---|
| EmaAdxTrend | ~0.4 | ~%0.16 | %45 | 1.20 | %29 | ~4.5 gün |
| ComboTrend | ~0.7 | ~%0.9 | %46 | 1.42 | %26 | ~3.3 gün |

---

## 1. Ne izlenecek?

### Her gün (1-2 dakika)
- [ ] Telegram'da `/status` yaz. Cevap geliyorsa bot çalışıyor; gelmiyorsa bot (veya bilgisayar) durmuştur.
- [ ] Hata/uyarı mesajı (⚠️) geldi mi? Geldiyse içeriğine bak; aynı hata tekrar ediyorsa bana göster.
- [ ] Bilgisayar uykuya geçmedi mi? Bilgisayar kapalıyken bot da kapalıdır.

### Her işlem açıldığında
- [ ] FreqUI'de işlemi aç: **stop fiyatı** var mı ve giriş fiyatından makul uzaklıkta mı (genelde %3-8)?
- [ ] **Risk** doğru mu? Pozisyon büyüklüğü × stop mesafesi ≈ bakiyenin en fazla %5'i (5 USDT civarı veya altı).
- [ ] **Marjin** bakiyenin %25'inden (~25 USDT) fazla değil mi?
- [ ] Kaldıraç 5x veya altı mı, marjin modu "isolated" mı?

### Her pazartesi sabahı (haftalık rapor)
- [ ] Haftalık rapor Telegram'a geldi mi?
- [ ] Ödenen ücret + funding makul mü? (İşlem başına ~0.1-0.2 USDT ücret beklenir.)
- [ ] Düşüş backtestteki en kötü düşüşü (%29) aştı mı? Rapor aşarsa ⚠️ ile uyarır.
- [ ] İşlem sayısı beklentiyle uyumlu mu? (EmaAdxTrend için 4 haftada 0-5 işlem normal.)

### Bir kez (ilk hafta içinde) — kurtarma testi
- [ ] Açık işlem varken `docker compose restart freqtrade` yap. Aynı işlem aynı stop ile devam etmeli, **ikinci bir emir açılmamalı**.
- [ ] Bilgisayarı yeniden başlat. Docker Desktop açılınca botlar kendiliğinden çalışmalı.
- [ ] İnterneti 5 dakika kes ve geri aç. Bot hata verip sonra kendiliğinden devam etmeli.

---

## 2. Korumalar nasıl çalışıyor (bilmen gerekenler)

| Koruma | Ne yapar |
|---|---|
| CooldownPeriod | Bir coinde işlem kapanınca o coinde 4 saat yeni işlem açılmaz |
| StoplossGuard | 24 saatte 3 stop olursa 12 saat hiç yeni işlem açılmaz |
| **MaxDrawdown** | Son 30 günde hesap **%25'ten fazla** düşerse **1 hafta** yeni işlem açılmaz (açık işlemler stopla korunmaya devam eder) |
| LowProfitPairs | Son 14 günde 3+ işlemde zararda olan coin 2 gün kilitlenir |

**Önemli:** MaxDrawdown botu **kalıcı** olarak durdurmaz, 1 hafta ara verdirir. Kalıcı durdurmak her
zaman senin kararın: Telegram'da `/stopentry` (yeni işlem açma, açıkları yönet) veya `/stop`.
Sınırlar `config.json` → `swing_protections` içinden değiştirilebilir.

---

## 3. Gerçek paraya (Aşama 5) geçiş kriterleri

### A) Teknik kriterler — EN AZ 4 HAFTA, HEPSİ şart
- [ ] Bot 4 hafta boyunca çalıştı; kesintiler sadece bilgisayar kapanmasından kaynaklandı.
- [ ] Tekrarlayan hata yok; çözülmemiş ⚠️ uyarısı yok.
- [ ] Takılı kalan emir yok (FreqUI'de "open order" olarak bekleyen eski emir yok).
- [ ] Açılan **her** işlemde stop vardı.
- [ ] Her işlemde risk ≤ %5 ve marjin ≤ %25 kuralları tuttu.
- [ ] Yeniden başlatma/kurtarma testleri (Bölüm 1) başarılı.
- [ ] Telegram bildirimleri ve haftalık rapor düzenli geldi.

### B) Performans kriterleri — "backtestle çelişmiyor mu?"
- [ ] En büyük düşüş backtestteki en kötü düşüşten (%29) **küçük**.
- [ ] İşlem sıklığı makul (EmaAdxTrend: 4 haftada 0-5 işlem).
- [ ] İşlemler backtest mantığıyla aynı: ortalama süre günler mertebesinde, stoplar ATR mesafesinde, çıkışlar takip eden stop / sinyal ile.

### ⚠️ Dürüst uyarı
EmaAdxTrend haftada ~0.4 işlem açıyor. **4 haftada beklenen işlem sayısı ~1.6.** Bu kadar işlemle
"strateji kârlı mı?" sorusu **cevaplanamaz**. 4 haftalık dry-run sadece botun **teknik olarak doğru**
çalıştığını kanıtlar. Kârlılık hakkında anlamlı bir fikir için **en az 3-6 ay** ve **15-20+ kapanmış
işlem** gerekir.

Seçeneklerin:
1. **4 hafta sonra (A ve B tamamsa) küçük parayla canlıya geç.** 100 USDT'yi kaybetmeyi göze alabileceğin
   bir "öğrenme ücreti" olarak gör. Dry-run'ı paralel sürdürmek istersen ComboTrend gözlem botu zaten
   sanal çalışmaya devam eder.
2. **3-6 ay dry-run'a devam et**, sonra karar ver (daha temkinli).

---

## 4. ComboTrend gözlem botu — ÖNCEDEN SABİTLENEN karar kuralı

ComboTrend Aşama 3'te önceden konan iki kuralı geçemedi. Sonuçlar iyi çıktı diye sonradan onu "kazanan"
ilan etmemek için kural **şimdi**, dry-run başlamadan yazılıyor ve değiştirilmeyecek:

ComboTrend, EmaAdxTrend'in yerine **ancak şu şartların HEPSİ** sağlanırsa aday olabilir:
- [ ] En az **6 ay** dry-run ve en az **25 kapanmış işlem**,
- [ ] Dry-run kâr faktörü **≥ 1.2**,
- [ ] Dry-run en büyük düşüş **≤ %30**,
- [ ] Aynı dönemde EmaAdxTrend'den (dry-run veya canlı) **daha yüksek** Calmar oranı (getiri / düşüş),
- [ ] Teknik kriterlerin (Bölüm 3A) hepsi.

Bunlar sağlanmazsa ComboTrend sadece gözlem olarak kalır veya kapatılır.

---

## 5. Hemen müdahale gerektiren durumlar
- Bot bir işlemi **stopsuz** açtıysa → `/stopentry`, bana haber ver.
- Bir işlemde kayıp bakiyenin **%5'inden çok fazla** olduysa → `/stopentry`, bana haber ver.
- Aynı hata mesajı sürekli tekrar ediyorsa → `docker compose logs --tail 200 freqtrade` çıktısını bana gönder.
- Hesap düşüşü **%29'u** (backtestteki en kötü) geçtiyse → dur ve birlikte değerlendirelim.
