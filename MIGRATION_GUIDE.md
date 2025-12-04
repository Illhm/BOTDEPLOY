# 📘 Migration Guide: v1.0 → v2.0

Panduan lengkap untuk migrasi dari versi lama ke Bot Deploy Manager v2.0.

## ⚠️ Perhatian

Versi 2.0 memiliki **breaking changes** yang memerlukan konfigurasi ulang. Harap baca panduan ini dengan seksama sebelum melakukan upgrade.

## 🔍 Apa yang Berubah?

### Breaking Changes

1. **Environment Variables Wajib**
   - `API_ID`, `API_HASH`, `BOT_TOKEN` tidak lagi memiliki default values
   - Bot akan **gagal start** jika environment variables tidak diset

2. **Shutdown Endpoint Protected**
   - Endpoint `/shutdown` sekarang memerlukan authentication token
   - Harus set `SHUTDOWN_TOKEN` di environment

3. **File Structure**
   - File utama: `run.py` → `run_improved.py`
   - Dependencies: `requirements.txt` → `requirements_improved.txt`

## 📋 Langkah-langkah Migrasi

### Step 1: Backup Konfigurasi Lama

```bash
# Backup file penting
cp run.py run.py.v1.backup
cp requirements.txt requirements.txt.v1.backup

# Backup environment variables jika ada
env | grep -E "API_ID|API_HASH|BOT_TOKEN" > env.backup
```

### Step 2: Pull Perubahan dari GitHub

```bash
# Fetch branch baru
git fetch origin feature/v2.0-professional-refactoring

# Checkout ke branch baru
git checkout feature/v2.0-professional-refactoring
```

### Step 3: Setup Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit dengan credentials Anda
nano .env
```

**Isi file .env:**
```env
# WAJIB - Dapatkan dari https://my.telegram.org/apps
API_ID=your_api_id_here
API_HASH=your_api_hash_here

# WAJIB - Dapatkan dari @BotFather
BOT_TOKEN=your_bot_token_here

# OPSIONAL - Whitelist user IDs (comma-separated)
# Contoh: ALLOWED_USERS=123456789,987654321
ALLOWED_USERS=

# OPSIONAL - Token untuk shutdown endpoint
# Generate dengan: openssl rand -hex 32
SHUTDOWN_TOKEN=your_secure_token_here

# OPSIONAL - Konfigurasi lainnya
PORT=5000
MAX_PROCESSES=10
MONITOR_INTERVAL=5
```

### Step 4: Update Dependencies

```bash
# Uninstall dependencies lama (opsional)
pip freeze > old_requirements.txt
pip uninstall -r old_requirements.txt -y

# Install dependencies baru
pip install -r requirements_improved.txt
```

**Atau dengan virtual environment (recommended):**
```bash
# Buat virtual environment baru
python -m venv venv_v2
source venv_v2/bin/activate  # Linux/Mac
# atau
venv_v2\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements_improved.txt
```

### Step 5: Update File Utama

```bash
# Ganti file utama
mv run_improved.py run.py
mv requirements_improved.txt requirements.txt
```

**Atau tetap menggunakan nama baru:**
```bash
# Jalankan dengan nama baru
python run_improved.py
```

### Step 6: Test Konfigurasi

```bash
# Test validasi environment variables
python -c "from run_improved import Config; Config.validate(); print('✅ Configuration valid!')"
```

**Expected output:**
```
✅ Configuration valid!
```

**Jika error:**
```
ERROR: API_ID environment variable is required
ERROR: API_HASH environment variable is required
ERROR: BOT_TOKEN environment variable is required
```
→ Cek file `.env` Anda

### Step 7: Start Bot

```bash
# Start bot
python run_improved.py
```

**Expected output:**
```
==================================================
Bot Deploy Manager v2.0.0
==================================================
2024-12-04 10:30:00 - __main__ - INFO - Configuration validated successfully
2024-12-04 10:30:00 - __main__ - INFO - Starting Flask server on 0.0.0.0:5000
2024-12-04 10:30:01 - __main__ - INFO - Flask server started
2024-12-04 10:30:01 - __main__ - INFO - Telegram bot started
2024-12-04 10:30:01 - __main__ - INFO - Process monitor started
```

### Step 8: Verify Functionality

Test semua fitur utama:

```bash
# 1. Test health check
curl http://localhost:5000/health

# 2. Test bot commands di Telegram
/start
/status
/deploy https://example.com/script.py
```

## 🔧 Troubleshooting

### Problem 1: Bot Tidak Start

**Error:**
```
ValueError: Configuration validation failed
```

**Solusi:**
1. Pastikan file `.env` ada di directory yang sama dengan `run_improved.py`
2. Cek isi file `.env`:
   ```bash
   cat .env
   ```
3. Pastikan tidak ada spasi di sekitar `=`:
   ```env
   API_ID=123456  # ✅ Benar
   API_ID = 123456  # ❌ Salah
   ```

### Problem 2: Import Error

**Error:**
```
ModuleNotFoundError: No module named 'pyrogram'
```

**Solusi:**
```bash
# Install dependencies
pip install -r requirements_improved.txt

# Atau install manual
pip install pyrogram tgcrypto flask requests
```

### Problem 3: Permission Denied

**Error:**
```
PermissionError: [Errno 13] Permission denied: 'logs'
```

**Solusi:**
```bash
# Buat directory logs
mkdir -p logs temp

# Set permissions
chmod 755 logs temp
```

### Problem 4: Port Already in Use

**Error:**
```
OSError: [Errno 98] Address already in use
```

**Solusi:**
```bash
# Cari proses yang menggunakan port 5000
lsof -i :5000

# Kill proses
kill -9 <PID>

# Atau gunakan port lain
echo "PORT=5001" >> .env
```

### Problem 5: Unauthorized Access

**Symptom:** Bot tidak merespons command

**Solusi:**
1. Cek `ALLOWED_USERS` di `.env`
2. Jika kosong, semua user diizinkan
3. Jika diisi, pastikan user ID Anda ada di list:
   ```env
   ALLOWED_USERS=123456789,987654321
   ```
4. Cara mendapatkan user ID Anda:
   - Kirim pesan ke @userinfobot di Telegram

## 🐳 Docker Migration

### Jika Menggunakan Docker

```bash
# Build image baru
docker build -f Dockerfile.improved -t botdeploy:v2 .

# Stop container lama
docker stop botdeploy
docker rm botdeploy

# Run container baru
docker run -d \
  --name botdeploy \
  --env-file .env \
  -p 5000:5000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/temp:/app/temp \
  --restart unless-stopped \
  botdeploy:v2
```

### Dengan Docker Compose

```bash
# Stop services lama
docker-compose down

# Build dan start services baru
docker-compose up -d --build

# Check logs
docker-compose logs -f
```

## 📊 Comparison Checklist

Pastikan semua fitur bekerja setelah migrasi:

- [ ] Bot dapat start tanpa error
- [ ] Command `/start` bekerja
- [ ] Command `/status` bekerja
- [ ] Deploy dari URL bekerja
- [ ] Deploy dari file upload bekerja
- [ ] Process monitoring bekerja
- [ ] Auto-restart bekerja (test dengan script yang crash)
- [ ] Command `/log <pid>` bekerja
- [ ] Command `/stop <pid>` bekerja
- [ ] Health check endpoint (`/health`) bekerja
- [ ] Log files ter-rotate dengan benar
- [ ] Authorization bekerja (jika `ALLOWED_USERS` diset)

## 🔄 Rollback Plan

Jika terjadi masalah dan perlu rollback:

```bash
# Checkout ke branch main
git checkout main

# Restore backup
cp run.py.v1.backup run.py
cp requirements.txt.v1.backup requirements.txt

# Reinstall dependencies lama
pip install -r requirements.txt

# Start bot lama
python run.py
```

## 📞 Butuh Bantuan?

Jika mengalami masalah saat migrasi:

1. **Cek dokumentasi:**
   - `README_IMPROVED.md` - Usage guide
   - `ANALISIS_KODE.md` - Code analysis
   - `PULL_REQUEST.md` - Detailed changes

2. **Cek logs:**
   ```bash
   tail -f logs/bot.log
   ```

3. **Test konfigurasi:**
   ```bash
   python -c "from run_improved import Config; Config.validate()"
   ```

4. **Buat issue di GitHub:**
   - Include error message
   - Include log output
   - Include environment (OS, Python version)

## ✅ Post-Migration

Setelah migrasi berhasil:

1. **Update dokumentasi internal** (jika ada)
2. **Backup konfigurasi baru:**
   ```bash
   cp .env .env.backup
   ```
3. **Monitor logs** selama beberapa hari:
   ```bash
   tail -f logs/bot.log
   ```
4. **Test semua edge cases** yang spesifik untuk use case Anda
5. **Update deployment scripts** (jika ada)

## 🎉 Selamat!

Anda telah berhasil migrasi ke Bot Deploy Manager v2.0! Nikmati peningkatan keamanan, stabilitas, dan fitur-fitur baru.

---

**Last Updated:** 2024-12-04  
**Version:** 2.0.0
