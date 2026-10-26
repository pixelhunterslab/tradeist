# Futures Swing Botu (Freqtrade + Docker)

**Binance USDⓈ-M Vadeli İşlemler** (izole marjin, long + short) için otomatik swing-trading botu.
[Freqtrade](https://www.freqtrade.io) üzerine kurulu, Docker ile çalışır.

> **Güvenlik varsayılanı:** Bot **dry-run (kağıt üzerinde / sanal işlem)** modunda çalışır.
> `dry_run` bilinçli olarak kapatılana kadar (Aşama 5, senin açık onayınla) **gerçek emir
> gönderilmez.**

## Klasör yapısı

```
futures-swing-bot/
├── docker-compose.yml        # resmi Freqtrade imajını çalıştırır (sabit sürüm)
├── .env.example              # gizli bilgiler için şablon -> .env olarak kopyala (git'e girmez)
├── scripts/
│   ├── download_data.ps1     # geçmiş veriyi indir (Windows PowerShell)
│   └── download_data.sh      # aynısı, Linux / VPS için
├── user_data/
│   ├── config.json           # tüm bot ayarları (içinde gizli bilgi YOK)
│   ├── strategies/           # strateji dosyaları (Aşama 2)
│   ├── tools/check_pairs.py  # hangi coinlerin ~100 USDT hesaba uygun olduğunu kontrol eder
│   ├── data/                 # indirilen piyasa verisi (git'e girmez)
│   └── logs/                 # bot kayıtları (git'e girmez)
└── reports/                  # backtest raporları, kontrol listeleri
```

## Hızlı başlangıç (Windows, Docker Desktop)

Proje klasöründe **PowerShell** aç:

```powershell
Copy-Item .env.example .env          # sonra .env'yi Not Defteri ile düzenle (anahtarlar şimdilik boş kalabilir)
docker compose pull                  # Freqtrade imajını indir
.\scripts\download_data.ps1          # geçmiş veriyi indir (biraz sürer)
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py
```

Linux/VPS'te `cp .env.example .env` ve `./scripts/download_data.sh` kullan.

## Ayarlar nerede?

| Ne | Nerede |
|---|---|
| Dry-run / gerçek mod, coinler, en fazla açık işlem, emir tipleri | `user_data/config.json` |
| Risk kuralları (kaldıraç, işlem başına en fazla zarar, marjin sınırı, ATR stop) | `user_data/config.json` → `"swing_risk"` |
| Gizli bilgiler (API anahtarları, Telegram, arayüz şifresi) | sadece `.env` |

Her ayar `.env` içinden `FREQTRADE__BOLUM__ANAHTAR` kalıbıyla değiştirilebilir. Örnekler:
`FREQTRADE__SWING_RISK__LEVERAGE=3` veya `FREQTRADE__MAX_OPEN_TRADES=2`.

## Binance API anahtarı oluşturma

Backtest veya veri indirmek için anahtar **gerekmez**. Dry-run/gerçek işlem aşamasına
gelince oluşturursun.

1. **binance.com**'a giriş yap → profil simgesi → **API Yönetimi** → **API Oluştur** →
   *Sistem tarafından oluşturulan* (HMAC). Adı mesela `freqtrade-bot` olsun.
2. Güvenlik doğrulamasını tamamla. **API Key** ve **Secret Key**'i kopyala. Secret
   **sadece bir kez** gösterilir.
3. **Kısıtlamaları düzenle**'ye tıkla ve şunları ayarla:
   - ✅ **Okumayı etkinleştir** (Enable Reading)
   - ✅ **Vadeli işlemleri etkinleştir** (Enable Futures): botun USDⓈ-M vadeli işlem
     yapabilmesini sağlayan ayar bu
   - ✅ Spot & Marjin işlemleri: **gerekmez**, kapalı bırak
   - ❌ **Para çekmeyi etkinleştir (Enable Withdrawals): KESİNLİKLE KAPALI kalmalı.** Böylece
     anahtar çalınsa bile kimse hesaptan para çekemez.
   - ❌ Diğer her şeyi kapalı bırak (iç transfer, evrensel transfer, opsiyonlar vb.).
4. **IP erişim kısıtlaması:**
   - Ev bilgisayarında IP adresin genelde değişir. Bu yüzden şimdilik *Kısıtlamasız*
     seçmen gerekebilir. Binance kısıtlamasız anahtarların işlem iznini zaman zaman
     kapatabilir. Bot bir gün aniden "izin" hatası verirse sebebi budur.
   - **VPS'te (Aşama 6): mutlaka "Sadece güvenilir IP'lere izin ver"** seç ve VPS'in genel IP
     adresini gir. Böylece anahtar başka hiçbir bilgisayardan kullanılamaz.
5. Anahtarı `.env` dosyasına yaz (başka hiçbir yere değil):
   ```
   FREQTRADE__EXCHANGE__KEY=senin_anahtarin
   FREQTRADE__EXCHANGE__SECRET=senin_secretin
   ```
6. Vadeli işlem hesabı ayarları (Binance web → Vadeli → ⚙ Tercihler). Freqtrade şunları ister:
   - **Pozisyon Modu: Tek yönlü (One-way)**, Hedge modu DEĞİL
   - **Varlık Modu: Tek varlık (Single-Asset)**, Çoklu varlık (Multi-Assets) DEĞİL
   - Marjin modu ve kaldıracı **bot her işlemde kendisi ayarlar** (izole, en fazla 5x).
     Elle ayarlaman gerekmez.
7. USDT'ni Spot cüzdandan **USDⓈ-M Vadeli** cüzdana aktar (Cüzdan → Transfer).

## Türkiye'den erişim: hesabında kontrol etmen gerekenler

Hesabını göremiyorum ve Binance'in güncel kurallarını senin yerine kontrol edemiyorum.
Aşama 4/5'ten önce şunları kendin doğrula:

1. **Doğru platform.** **Binance.com (global)** hesabı gerekiyor. **Binance TR**
   (binance.tr) ayrı bir şirket ve API anahtarları da ayrı. Bildiğim kadarıyla USDⓈ-M
   vadeli işlem sunmuyor. Binance TR anahtarları burada çalışmaz.
2. **Vadeli işlemler sana gerçekten açık mı?** Türkiye'nin kripto yasası (7518 sayılı
   Kanun, 2024), Türkiye'de yaşayanlara hizmet veren kripto platformlarının SPK lisansı
   almasını şart koşuyor. Bu yüzden platformlar Türk kullanıcılar için bazı ürünleri
   kısıtlayabiliyor. Kontrol et:
   - USDⓈ-M Vadeli sayfasını açabiliyor musun, vadeli hesabın aktif mi (kısa test
     tamamlandı mı)?
   - API anahtarını düzenlerken **Vadeli işlemleri etkinleştir** seçeneği görünüyor ve
     işaretli kalıyor mu?
   - Binance'ten Türkiye'de yaşayanlar için türev ürün kısıtlaması veya hesap taşıma
     hakkında bir bildirim/e-posta geldi mi?
   - Binance kaldıracını sınırlıyorsa (bazı bölgelerde/yeni hesaplarda üst sınır daha
     düşük olabiliyor) bana söyle. O zaman 5x varsayılanını düşürmemiz gerekir.
3. **Kimlik doğrulama (KYC).** Vadeli işlem ve API ile işlem için kimlik doğrulamanın
   tamamlanmış olması gerekir.
4. **Vergi / hukuk.** Kripto işlem kazançları Türkiye'de vergiye tabi olabilir. Bu senin
   sorumluluğunda, bu konuda tavsiye veremem.

Anahtarı aldıktan sonra hızlı teknik test (emir göndermez):
```powershell
docker compose run --rm freqtrade list-markets --config /freqtrade/user_data/config.json --trading-mode futures --quote USDT -1 | Select-Object -First 5
```
Bu çalışıyor ama işlem açarken "not eligible", "restricted" veya
"-2015 Invalid API-key, IP, or permissions" gibi bir hata geliyorsa, sorun bot değil,
hesap veya bölge kısıtlamasıdır.

## Geçmiş veri

`scripts/download_data.ps1` (veya `.sh`), `config.json`'daki her coin için Binance'in
herkese açık veri arşivinden (data.binance.vision) şunları indirir:

- **15dk, 1s, 4s, 1g** mumları: Ocak 2020'den (arşivin başlangıcı) veya coinin listelenme
  tarihinden dünün sonuna kadar. 1s/4s strateji zaman dilimleri, 1g üst zaman dilimindeki
  trend filtresi için. 15dk ise backtestlerde stop/trailing dolumlarını daha gerçekçi simüle
  etmek için kullanılır.
- **Mark fiyatı** (1s) ve **funding (fonlama) oranı** geçmişi. Backtestlerde likidasyon
  fiyatı ve funding ücretlerini hesaplamak için gerekli. Funding arşivi sadece aylık
  yayınlanıyor, yani içinde bulunduğumuz ayın funding verisi ay bitince eklenir.

Arşiv kullanılmasının sebebi: Binance'in canlı API'si bazı sunuculardan/ülkelerden erişime
kapalı (HTTP 451), arşiv ise her yerden erişilebilir ve aynı veriyi içerir. Yeni mumları
eklemek için scripti istediğin zaman tekrar çalıştır; sadece eksik dosyalar indirilir.

## Coin seçimi

`user_data/tools/check_pairs.py`, Binance'in emir limitlerini okur ve bunları risk
kurallarımızın ~100 USDT hesapta gerçekten açacağı pozisyon büyüklüğüyle karşılaştırır
(işlem başına %5 risk, en fazla %25 marjin, 5x). En küçük emri çok büyük olan veya işlem
hacmi düşük olan coinler `ÇIKAR` olarak işaretlenir.

```powershell
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py
```

**Sonuç (26.10.2026):** ETH, SOL, XRP, BNB, DOGE, ADA uygun. BTC elendi: en küçük emir
0.001 BTC ≈ 80 USDT ve bu, en fazla 125 USDT'lik pozisyonla hassas boyutlamaya izin
vermiyor. LINK, AVAX, LTC düşük hacim nedeniyle elendi. 24 saatlik hacim tek günün
verisidir; sınırdaki coinler (LINK) başka bir gün geçebilir.

## Stratejiler (Aşama 2)

Hepsi long + short açabilir, parametre sayısı az (2-3), ve aynı ortak risk kurallarını
`user_data/strategies/swing_risk.py` dosyasından alır (kopyala-yapıştır yok).

| Strateji | Zaman dilimi | Ne zaman girer | Ne zaman çıkar |
|---|---|---|---|
| `EmaAdxTrend` | 4s | Hızlı EMA yavaşı keser + ADX güçlü trend der | Ters kesişim |
| `DonchianBreakout` | 4s | Fiyat son N mumun zirvesini/dibini hacimle kırar | Kısa kanalın ters ucu kırılır |
| `SupertrendTrend` | 4s | Supertrend yön değiştirir | Supertrend ters döner |
| `RsiBbMeanReversion` | 1s (+4s trend) | 4s trend yönünde, 1s'te aşırı düşüş/yükseliş (RSI + Bollinger) | Fiyat Bollinger ortasına döner |

**Ortak risk kuralları** (`config.json` → `swing_risk`):
- **Stop:** giriş ± `atr_stop_multiplier` × ATR, en az `min_stop_distance_pct` %. Stop Binance'te durur.
- **Pozisyon büyüklüğü:** stop olursa kayıp bakiyenin en fazla `max_loss_per_trade_pct_of_balance` %'si.
- **Sınırlar:** marjin en fazla bakiyenin `max_margin_per_trade_pct_of_balance` %'si, kaldıraç en fazla
  `max_leverage`. Stop likidasyona fazla yakın kalacaksa kaldıraç o işlem için otomatik düşürülür.
- **Çıkış modu** (`exit_mode`): `trailing` (kâr 1R'yi geçince stop ATR mesafesinden takip eder) veya
  `fixed_tp` (`take_profit_rr` × risk kadar kârda kapat).

## Aşama 4: Dry-run'ı (sanal işlem) bilgisayarında başlatma

Dry-run için **Binance API anahtarı GEREKMEZ**; bot herkese açık piyasa verisiyle sanal işlem yapar.
Anahtarı Aşama 5'e kadar `.env`'e koyma.

### 1. Dosyaları bilgisayarına al
GitHub'da https://github.com/pixelhunterslab/tradeist → yeşil **Code** düğmesi → **Download ZIP** →
örneğin `C:\tradeist` klasörüne çıkar. (Git kullanıyorsan: `git clone https://github.com/pixelhunterslab/tradeist C:\tradeist`)

### 2. Telegram botu oluştur
1. Telegram'da **@BotFather**'a yaz → `/newbot` → bir isim ve kullanıcı adı ver. Sana bir **token** verir
   (`123456:ABC...` gibi).
2. Yeni botuna Telegram'da bir mesaj gönder (örn. "merhaba").
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini aç (`<TOKEN>` yerine kendi
   token'ın). Çıkan yazıda `"chat":{"id":123456789` kısmındaki sayı senin **chat id**'n.
4. (İsteğe bağlı) ComboTrend gözlem botu için de bildirim istersen @BotFather'dan **ikinci** bir bot
   oluştur. Aynı token iki botta çalışmaz.

### 3. `.env` dosyasını doldur
PowerShell'de proje klasöründe:
```powershell
Copy-Item .env.example .env
notepad .env
```
Doldur: `FREQTRADE__TELEGRAM__TOKEN`, `FREQTRADE__TELEGRAM__CHAT_ID`, `FREQTRADE__TELEGRAM__ENABLED=true`,
FreqUI için `FREQTRADE__API_SERVER__USERNAME` / `PASSWORD`, ve rastgele uzun birer değer olarak
`JWT_SECRET_KEY` / `WS_TOKEN` (`.env.example` içinde nasıl üretileceği yazıyor). Binance anahtarlarını
**boş bırak**.

### 4. Başlat
```powershell
docker compose up -d
docker compose ps                    # 3 servis "running" olmalı
docker compose logs -f freqtrade     # canlı log (çıkmak için Ctrl+C; bot çalışmaya devam eder)
```
Telegram'da botun "başladı" mesajı gelmeli; `/status` ve `/balance` yazarak dene.

### 5. FreqUI (web arayüzü)
Tarayıcıda **http://127.0.0.1:8080** → `.env`'deki kullanıcı adı/şifre ile giriş. ComboTrend botunu
eklemek için: sağ üstteki bot menüsü → **Add new bot** → URL `http://127.0.0.1:8081`, aynı kullanıcı
adı/şifre. Arayüz sadece bu bilgisayardan açılır, internete kapalıdır.

### 6. Haftalık raporu dene
```powershell
docker compose run --rm --no-deps weekly-report --now
```
Telegram'a şimdiki haftanın özeti gelmeli. Normalde her **pazartesi 09:00 (İstanbul)** kendiliğinden gelir.

### 7. Bilgisayar ayarları (önemli)
- Docker Desktop → Settings → General → **Start Docker Desktop when you sign in** işaretli olsun.
- Windows → Güç ayarları → prize takılıyken **uyku: Hiçbir zaman**. Bilgisayar uyursa bot da durur.
- Bot yeniden başladığında açık işlemlerini veritabanından (`user_data/tradesv3*.sqlite`) okur, aynı
  işlem için ikinci emir açmaz.

### Durdurma / yeniden başlatma
```powershell
docker compose restart freqtrade     # sadece ana botu yeniden başlat
docker compose down                  # hepsini durdur (açık sanal işlemler veritabanında kalır)
docker compose up -d                 # tekrar başlat
```
Telegram komutları: `/status`, `/profit`, `/balance`, `/daily`, `/weekly`, `/stopentry` (yeni işlem
açma), `/stop` (botu durdur), `/start`, `/forceexit <id|all>` (işlemi kapat), `/help`.

Neyi izleyeceğin ve gerçek paraya geçiş kriterleri: **`reports/dryrun_checklist.md`**.

## Binance API'sine erişilemiyorsa (çevrimdışı mod)

Binance'in canlı API'si bazı ülkelerden/sunuculardan kapalıdır (HTTP 451). Backtest için
gereken işlem kuralları o zaman `user_data/market_snapshot/` içindeki dosyalardan okunur
(tarayıcıda kaydedilmiş `fapi/v1/exchangeInfo` ve `fapi/v1/ticker/24hr`):

```powershell
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/ft_offline.py backtesting --strategy ...
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py --offline
```

`ft_offline.py` sadece backtest/analiz komutlarını çalıştırır; botu işlem modunda
başlatmayı reddeder. Gerçek bot her zaman canlı Binance bilgisini kullanır.
