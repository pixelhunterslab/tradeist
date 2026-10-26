## Sonuç (önce bunu oku)

**Önceden sabitlenen kurallara göre seçilen strateji: `EmaAdxTrend`**, ATR stop çarpanı **3.0**,
çıkış modu **takip eden stop**, kaldıraç **5x**. Beş stratejiden kuralların hepsini geçen tek strateji bu.

**Dürüst değerlendirmem: kuralları geçti ama zar zor ve kırılgan.** Bunu "sağlam, güvenilir bir
kazanç makinesi bulduk" diye okuma. Gerçek parayla kullanmadan önce dry-run (sanal işlem) şart;
kâr edip etmediğini görmek için 4 hafta da yetmeyecek (aşağıya bak).

### Neden kazandı?
- **Tek bir şanslı ayara bağlı değil:** 8 varyantın (ATR 1.5 / 2 / 2.5 / 3 × takip eden stop /
  sabit kâr al) 7'si 2020-2024'te kârlı. Kazanan Donchian ve Supertrend'de ise 8 varyanttan
  sadece 1'i belirgin şekilde kârlı. Bu, onların sonucunun büyük ihtimalle tesadüf olduğunu
  gösterir.
- **Düşüşleri en sınırlı strateji:** en büyük düşüş 2020-2024'te %27, 2025-2026'da %29.
  Diğer trend stratejilerinde bu %45-75.
- Long ve short işlemlerin ikisi de kârlı. İşlemler ortalama 4-5 gün açık kalıyor, yani
  gerçek swing trading.
- Stopların çok az bir kısmı "gürültü" (stop olup 48 saat içinde fiyatın girişe dönmesi):
  2025-2026'da 9 stoptan 0.

### Zayıf yanları (bilmen gerekenler)
1. **Getirisi düşük, riski görece yüksek.** 2025-2026'da 22 ayda **+%16** (yıllık ~%9), bu arada
   **%29 düşüş** yaşadı. Yani bir dönem 100 USDT'nin ~71'e indiğini görmeye hazır olmalısın.
2. **Sadece 5x'te kuralları geçiyor.** 3x'te son sınav kâr faktörü 1.07, 1x-2x'te ise
   2025-2026 sonucu ~%0. Avantajı ince: birkaç büyük kazançtan geliyor, küçük pozisyonlarda
   neredeyse kayboluyor.
3. **Çok az işlem:** ayda ~2 işlem. 2025-2026'da sadece 38 işlem (alt sınır 30). İstatistiksel
   güven düşük.
4. **Uzun süre yeni zirve yapmayabilir:** 2025-2026'da hesap **381 gün** bir önceki zirvenin
   altında kaldı ve dönem sonunda hâlâ altında. 2020-2024'te en uzun süre 331 gün.
5. **Sadece yükseliş aylarında para kazanıyor:** BTC'nin %10'dan fazla yükseldiği aylarda ortalama
   +%4.4/ay; düşüş ve yatay aylarda ortalama ~%0 (aylarının üçte ikisi zararda).
6. **En kötü seri:** 2020-2024'te 9, 2025-2026'da 8 işlem üst üste zarar. Walk-forward'da
   2024'ün ilk yarısı **-%35**.

### ComboTrend neden seçilmedi?
2025-2026 son sınavında en iyi sonucu ComboTrend verdi: **+%131**, en büyük düşüş %25, kâr faktörü 1.42.
Ama önceden sabitlediğimiz iki kuralı geçemedi:
- 2020-2024'te düşüşü %45 (sınır %40),
- 6 walk-forward penceresinin sadece 3'ü kârlı (biri **-%50**).

Son sınav sonucuna bakıp kuralı esnetirsem, bu tam da kaçınmamız gereken şey olur: sonuca göre
seçim yapmak. Bu yüzden onu **seçmiyorum.** Yine de istersen dry-run'da ikinci bir sanal bot
olarak sadece gözlem amaçlı çalıştırılabilir; Aşama 4'te gelecek veri onun için de yeni bir test olur.

### Diğer bulgular
- **ATR çarpanı:** trend stratejilerinde dar stop (1.5 × ATR) genelde kötü; fiyatın normal
  dalgalanmasıyla erken stop oluyor. 2.5-3.0 daha iyi sonuç verdi.
- **Takip eden stop mu, sabit kâr al mı:** net bir kazanan yok; strateji başına değişiyor
  (EmaAdx'te takip eden stop, Combo/Supertrend/Donchian'da sabit kâr al daha iyi). Bu yüzden her
  stratejide kendi in-sample sonucuna göre seçildi.
- **Ortalamaya dönüş (RsiBb)** her dönemde ve her varyantta zararda. Bu coinlerde ve bu
  maliyetlerle işe yaramıyor.
- **Kaldıraç:** bu risk kurallarıyla kaldıraç düşürmek her işlemin riskini de düşürüyor
  (aynı %25 marjinle daha küçük pozisyon). 1x'te bütün stratejiler çok daha sakin ama getirisi de
  çok düşük. Ayrıntı Bölüm 6'da.

### Aşama 4 için önemli bir gerçek
EmaAdxTrend ayda ~2 işlem açıyor. **4 haftalık bir dry-run'da sadece 1-3 işlem olur.** Bu kadar
işlemle "kârlı mı" sorusunun cevabı istatistiksel olarak anlamsızdır. 4 haftalık dry-run sadece
**teknik doğrulama** için iyidir: emirler doğru açılıyor mu, stop Binance'te duruyor mu,
yeniden başlatmada sorun var mı, işlemler backtestteki kurallara uyuyor mu. Kârlılık hakkında
fikir edinmek için en az 3-6 ay gerekir.

---
