# ProCoin by ProKuiz

App **indicator** untuk coin crypto besar (BTC, ETH, XRP, BNB, SOL dan lain-lain): harga, isyarat teknikal, backtest, Robot ujian maya dan **berita crypto**. Dibina atas konsep ProSyariah, tetapi untuk crypto dan **guna GitHub sahaja** (tiada Firebase, tiada log masuk). Data pengguna kekal dalam telefon pengguna.

App: https://alemmaxx.github.io/ProCoin/

## Apa robot buat (GitHub Actions)

| Bila (waktu Malaysia) | Workflow | Apa |
|---|---|---|
| Setiap hari 8.20 pagi (sandaran 11.20 pagi) | Kemas kini data ProCoin | Tarik harga harian semua coin (5 tahun), kira RSI, MACD, EMA, golden cross, skor; backtest; rekod isyarat; maklumat coin; berita; terbitkan app ke GitHub Pages |
| Setiap 30 minit, 24 jam | Harga terkini | Harga semasa semua coin (lewat ±15 minit) |
| Setiap 2 jam | Berita terkini | Tajuk berita setiap coin dari Google News, dengan nada ▲ positif / ▼ negatif / • neutral |
| Setiap jam | Pemantau sistem | Semak data lewat / laman tidak dapat dibuka; jalur amaran dalam app |

Crypto berdagang 24/7. "Harga tutup harian" = harga pada 8 pagi waktu Malaysia (12 tengah malam UTC).

## Senarai coin

Fail `data/coins.json`. Setiap coin: `code` (kod dalam app), `name`, `yf` (ticker Yahoo Finance), `q` (kata carian berita).
Tambah atau buang coin di sini sahaja; robot akan ikut pada larian seterusnya. Stablecoin (USDT, USDC) sengaja tidak dimasukkan.
Untuk coin yang ticker Yahoo-nya pelik (cth. SUI = `SUI20947-USD`, TON = `TON11419-USD`, UNI = `UNI7083-USD`), semak di finance.yahoo.com.

## Kebarangkalian & paras harga

Robot menjalankan **backtest** atas sejarah ~5 tahun setiap coin untuk 4 persediaan beli (koreksi dalam trend menaik, golden cross, momentum MACD, lantunan lebih jualan).
Setiap isyarat dalam sejarah diuji: harga sampai **paras atas (2× ATR)** atau **paras bawah (1.25× ATR)** dahulu, atau tiada dalam **30 hari**. Kos 0.2% diambil kira.
Tetapan di `scripts/backtest.py` (H, TGT_ATR, STP_ATR, FEE). Ini statistik sejarah, bukan jaminan.

## Pemasangan (sekali sahaja)

1. **Cipta repo** `ProCoin` di GitHub (akaun alemmaxx) dan muat naik semua fail dalam folder ini, **termasuk folder tersembunyi `.github`**.
2. **Hidupkan GitHub Pages**: repo → *Settings → Pages → Build and deployment → Source: **GitHub Actions***.
3. **Benarkan robot menulis**: *Settings → Actions → General → Workflow permissions → **Read and write permissions*** → Save.
4. **Jalankan robot kali pertama**: tab *Actions → Kemas kini data ProCoin → Run workflow*. Tunggu ~5–10 minit.
5. Buka https://alemmaxx.github.io/ProCoin/ — app sudah berfungsi dengan data penuh.

Tiada API key diperlukan (harga dari yfinance, berita dari Google News RSS).

### Emel amaran (pilihan)

GitHub sudah emel anda bila robot gagal. Untuk emel tambahan dari Pemantau sistem, tambah *Secrets* (Settings → Secrets and variables → Actions):
`SMTP_USER` (cth. Gmail anda), `SMTP_PASS` (Gmail App Password), `ALERT_EMAIL` (alamat penerima).

## Untuk APK

`index.html` sudah menunjuk ke `https://alemmaxx.github.io/ProCoin/` (`PAGES_URL`). Bina APK sebagai pembungkus yang membuka alamat itu, supaya app sentiasa versi terkini tanpa bina semula.

## Ciri dalam app

- Skrin utama: coin pilihan, carta (30m hingga tahunan), keadaan pasaran (Bitcoin), Penapis, Naik/Turun, Banding, Ringkasan isyarat, **Berita crypto terkini**, Berita Berpotensi, Champion, Isyarat Pemerhatian, 5 isyarat terkuat, semua coin ikut nilai pasaran.
- Setiap coin: Meter ProCoin (isyarat 40% + skor teknikal 40% + nada berita 20%), isyarat & paras harga, rekod backtest, bacaan teknikal, maklumat coin (nilai pasaran, bekalan, ATH), berita, kongsi gambar.
- Robot: Manual & Auto (ujian maya, modal dibahagi 5). Robot Auto berjalan dalam telefon setiap kali app dibuka.
- Portfolio: untung/rugi dalam USD, paras sokongan mengekor.
- Amaran (loceng) & notifikasi telefon, dwibahasa BM | EN.

## Penting sebelum dilancarkan kepada orang awam

- **Lesen data**: yfinance (Yahoo Finance) untuk kegunaan peribadi. Untuk edaran awam/komersial, dapatkan penyedia data berlesen.
- **Peraturan**: isyarat teknikal crypto kepada orang awam boleh dianggap nasihat pelaburan di bawah peraturan SC Malaysia. Dapatkan nasihat undang-undang sebelum mengkomersialkan.
- **Status syariah**: ProCoin tidak menilai status syariah coin. Tiada senarai rasmi SC untuk coin seperti senarai saham patuh syariah.
