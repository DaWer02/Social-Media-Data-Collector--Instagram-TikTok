# Panduan Integrasi Resmi Meta Graph API untuk Instagram Slang NLP

Dokumen ini menjelaskan tata cara resmi memperoleh Access Token dan izin (permissions) yang sah dari Meta for Developers, perbedaan URL vs Media ID, serta batasan arsitektural resmi platform Meta.

---

## 1. Status Pengujian Konektor

> [!IMPORTANT]
> **Catatan Kejujuran Teknis:**  
> Konektor [`InstagramGraphAPICollector`](file:///d:/WEBKU/NLP/src/collectors/instagram_api.py) telah diuji dan divalidasi secara komprehensif menggunakan **unit test mock / fixture respons resmi Graph API v21.0**.  
> Konektor ini **tidak melakukan panggilan live ke Meta API selama pengujian otomatis** untuk mencegah pemborosan kuota rate limit dan kebocoran kredensial.

---

## 2. Keterbatasan Resmi Meta Graph API

1. **Hanya Akun Profesional Terotorisasi:**
   - Endpoint `GET /{ig-media-id}/comments` **hanya** dapat membaca komentar dari media milik akun **Instagram Business** atau **Instagram Creator** yang terhubung langsung dengan aplikasi Meta Anda.
2. **Tidak Mendukung Sembarang URL Publik:**
   - Meta Graph API **tidak menyediakan akses** untuk membaca daftar teks komentar dari akun pihak ketiga / URL sembarang orang lain.
   - Endpoint `Business Discovery` hanya mengembalikan jumlah total komentar (`comments_count`), bukan teks komentar individu.
   - Endpoint `oEmbed` hanya mengembalikan kode HTML iframe embed.
   - *Scraping* halaman HTML publik (misalnya dengan BeautifulSoup, Selenium, atau Playwright) dilarang dalam PRD untuk mematuhi Ketentuan Layanan (ToS) Meta dan etika penelitian.
3. **Instagram Basic Display API Telah Dimatikan Total:**
   - Meta resmi mematikan (*sunset*) Basic Display API per **4 Desember 2024**. Akun Personal biasa tidak lagi memiliki jalur API resmi.

---

## 3. Perbedaan URL vs Media ID

| Parameter | URL Postingan | Media ID |
|---|---|---|
| **Bentuk** | `https://www.instagram.com/p/C_abc123/` atau `/reel/D_xyz987/` | `17970528943031455` (string numerik) |
| **Resolusi** | Diekstrak shortcode-nya, lalu dicocokkan dengan postingan akun terotorisasi via `GET /me/media`. | Langsung digunakan untuk membaca komentar via `GET /{media-id}/comments`. |
| **Keterbatasan** | Jika URL bukan milik akun profesional Anda, pemetaan akan gagal (`MediaUnavailableError`). | Jika Media ID bukan milik akun profesional Anda, Meta API mengembalikan HTTP 400 (Code 100/Subcode 33). |

---

## 4. Pilihan Varian Login Meta

Konektor mendukung dua varian resmi Meta yang dapat diatur melalui variabel lingkungan `INSTAGRAM_API_VARIANT`:

| Parameter | Varian 1: `facebook_login` (Default) | Varian 2: `instagram_login` |
| :--- | :--- | :--- |
| **Host Base URL** | `https://graph.facebook.com/{version}` | `https://graph.instagram.com/{version}` |
| **Prasyarat Akun** | Akun Instagram Business/Creator terhubung ke Facebook Page | Akun Instagram Business/Creator mandiri |
| **Jenis Token** | Page Access Token / User Access Token | Instagram User Access Token |
| **Izin Dasar** | `instagram_basic`, `pages_read_engagement` | `instagram_business_basic` |
| **Izin Komentar** | `instagram_manage_comments` | `instagram_business_manage_comments` |

---

## 5. Langkah Memperoleh Token Resmi Meta

### Varian 1: Facebook Login (Direkomendasikan)
1. **Daftar Akun Pengembang:**
   - Kunjungi [Meta for Developers](https://developers.facebook.com/) dan login dengan akun Facebook Anda.
2. **Buat Aplikasi Meta:**
   - Pilih **My Apps** $\rightarrow$ **Create App**.
   - Pilih jenis use-case: **Other** $\rightarrow$ **Business**.
3. **Hubungkan Akun Instagram Profesional:**
   - Pastikan akun Instagram Anda telah diubah menjadi akun **Business** atau **Creator** (gratis melalui aplikasi Instagram di ponsel).
   - Hubungkan akun Instagram tersebut ke sebuah **Facebook Page** yang Anda kelola.
4. **Buka Graph API Explorer:**
   - Masuk ke [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
   - Pilih Meta App Anda di sudut kanan atas.
5. **Pilih Izin (Permissions):**
   - Tambahkan izin:
     - `instagram_basic`
     - `instagram_manage_comments`
     - `pages_show_list`
     - `pages_read_engagement`
6. **Generate User Access Token:**
   - Klik **Generate Access Token** dan setujui dialog otorisasi Meta.
   - Untuk penggunaan jangka panjang (60 hari), Anda dapat mengonversi token menjadi Long-Lived Token melalui endpoint OAuth Meta.

### Varian 2: Instagram Login
1. Buat Aplikasi Meta tipe **Consumer** atau **Business**.
2. Tambahkan produk **Instagram**.
3. Daftarkan akun Instagram profesional Anda ke dalam daftar peran **Instagram Testers**.
4. Lakukan otorisasi untuk menghasilkan User Access Token dengan izin:
   - `instagram_business_basic`
   - `instagram_business_manage_comments`

---

## 6. Konfigurasi ke File `.env`

```dotenv
# Kredensial Meta Graph API (JANGAN PERNAH COMMIT KE GIT!)
INSTAGRAM_ACCESS_TOKEN=EAAB...

# Varian API & Versi
INSTAGRAM_API_VARIANT=facebook_login
GRAPH_API_VERSION=v21.0

# Target Jumlah Komentar Maksimum
TARGET_COMMENTS=3000

# Konfigurasi Lingkungan
APP_ENV=development
LOG_LEVEL=INFO
```
