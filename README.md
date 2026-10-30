# ProCoin by ProKuiz

App **indicator** untuk coin crypto besar (BTC, ETH, XRP, BNB, SOL dan lain-lain): harga, isyarat teknikal, backtest, Robot ujian maya dan **berita crypto**. Guna **GitHub sahaja** (tiada pelayan, tiada log masuk). Data pengguna kekal dalam telefon pengguna.

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
Untuk coin yang ticker Yahoo-nya pelik (cth. SUI = `SUI20947-USD`, UNI = `UNI7083-USD`), semak di finance.yahoo.com. Medan pilihan `alt` = senarai ticker ganti jika ticker utama tiada harga. Toncoin (TON) tidak dimasukkan kerana Yahoo tiada sejarah harganya.

Yahoo kadang-kadang lewat menerbitkan bar harian crypto terkini; robot mengisi bar harian yang tertinggal (hari UTC yang sudah lengkap) daripada data sejam.

## Isyarat & backtest

Isyarat hanya datang daripada strategi yang **lulus backtest** robot kajian (`scripts/research.py`, setiap Ahad, keputusan dalam `data/research.json` dan helaian 🧪 Keputusan backtest dalam app):

| Strategi | Gred | Peraturan |
|---|---|---|
| RSI(2) bawah 10 dalam trend menaik | **Isyarat aktif** | Beli harga buka esok; keluar bila harga tutup atas EMA5 atau selepas 10 hari; cut loss 2.5× ATR |
| Breakout 20 hari | **Pemerhatian** | Trailing stop 3× ATR di bawah harga tertinggi sejak beli |

Strategi ditakrifkan dalam `scripts/strategies.py`; pilihan strategi & gred dalam `USE` di `scripts/market.py`.
% untung dan purata pulangan ialah statistik gabungan semua coin (5 tahun, selepas kos 0.2%), bukan satu coin, supaya tidak terlebih yakin.
Penapis tambahan (BTC, carta 4 jam, kekuatan vs BTC, Fear & Greed) diuji tetapi belum terbukti, jadi dipaparkan sebagai maklumat sahaja.
Ini statistik sejarah, bukan jaminan.

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

Tab: **Coin · News · G & L · Robot · Tetapan**

- **Coin**: graf 1 jam terus (boleh tukar 30m hingga tahunan), kotak Bitcoin dengan harga masa nyata & berita BTC terkini, **Isyarat aktif**, **Berita Berpotensi**, **Isyarat Pemerhatian**, dan grid penuh semua coin & isyarat teknikal.
- **News**: semua tajuk berita crypto 7 hari (▲ positif / ▼ negatif / • neutral), tapis ikut nada atau coin.
- **G & L**: Gainers & Losers (hari ini, 7 hari, 30 hari) guna harga terkini.
- **Robot**: Manual & Auto (ujian maya, modal dibahagi 5). Robot Auto masuk untuk Isyarat Kuat dan Berita Berpotensi yang kukuh.
- **Berita Berpotensi** hanya berita positif yang kukuh: peristiwa sebenar (kelulusan, aliran masuk dana, penyenaraian, kerjasama, pelancaran), bukan ramalan/andaian ("if", "could", soalan), dan tiada berita negatif pada hari sama.
- Setiap coin: Meter ProCoin (isyarat 40% + skor teknikal 40% + nada berita 20%), isyarat & paras harga, rekod backtest, bacaan teknikal, maklumat coin (nilai pasaran, bekalan, ATH), berita, amaran harga, kongsi gambar.
- Harga masa nyata dari CoinGecko setiap 1 minit bila app dibuka. Amaran (loceng) & notifikasi telefon, dwibahasa BM | EN.

## Penting sebelum dilancarkan kepada orang awam

- **Lesen data**: yfinance (Yahoo Finance) untuk kegunaan peribadi. Untuk edaran awam/komersial, dapatkan penyedia data berlesen.
- **Peraturan**: isyarat teknikal crypto kepada orang awam boleh dianggap nasihat pelaburan di bawah peraturan SC Malaysia. Dapatkan nasihat undang-undang sebelum mengkomersialkan.
