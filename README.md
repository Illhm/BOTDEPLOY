# 🤖 Bot Deploy Manager v2.1

Professional Telegram bot untuk deployment dan manajemen skrip Python secara remote dengan **automatic dependency management**, virtual environment isolation, monitoring otomatis, auto-restart, dan logging lengkap.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-2.0-green.svg)](https://docs.pyrogram.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-red.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ Fitur Utama

### 🚀 Deployment Fleksibel
Deploy skrip Python dari URL atau file upload langsung melalui Telegram dengan validasi otomatis dan isolasi proses.

### 📦 Dependency Management (NEW!)
Auto-detect dan install dependencies dari script imports, virtual environment per process untuk isolasi lengkap, support upload requirements.txt untuk custom dependencies, dan fallback mechanism untuk cloud platforms dengan restrictions.

### 📊 Monitoring Real-time
Status monitoring untuk semua proses dengan auto-restart pada failure (maksimal 3 kali percobaan), notifikasi real-time via Telegram, dan log rotation otomatis untuk mencegah disk penuh.

### 🔒 Keamanan
User authorization dengan whitelist untuk membatasi akses, tidak ada hardcoded credentials di kode, protected shutdown endpoint dengan token authentication, dan thread-safe process management untuk stabilitas.

### 📝 Logging Lengkap
Rotating file handler dengan limit 10MB per file dan 5 backup files, separate log per process untuk mudah debugging, log retrieval via Telegram, dan structured logging format untuk parsing.

### 🌐 Web API
Health check endpoint untuk monitoring eksternal, RESTful API untuk integrasi, process statistics endpoint, dan protected management endpoints.

## 📋 Persyaratan

Aplikasi ini memerlukan Python 3.9 atau lebih baru, Telegram Bot Token dari [@BotFather](https://t.me/botfather), dan Telegram API credentials dari [my.telegram.org](https://my.telegram.org).

## 🔧 Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/Illhm/BOTDEPLOY.git
cd BOTDEPLOY
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Konfigurasi

```bash
# Opsi A: gunakan file config
cp config.py.example config.py
nano config.py

# Opsi B: gunakan environment variables (cocok untuk Zeabur/railway)
export API_ID=12345678
export API_HASH=0123456789abcdef0123456789abcdef
export BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
export PORT=8080  # override port Flask jika platform mewajibkan
```

**Konfigurasi Wajib di config.py:**

```python
# Telegram API credentials
API_ID = "12345678"  # Dari my.telegram.org
API_HASH = "0123456789abcdef0123456789abcdef"  # Dari my.telegram.org
BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"  # Dari @BotFather

# Whitelist user IDs (opsional, kosongkan untuk allow all)
ALLOWED_USERS = [123456789, 987654321]  # Telegram user IDs
```

### 4. Jalankan Bot

```bash
python run.py
```

## 📖 Cara Penggunaan

### Deployment dengan Dependencies

**Method 1: Auto-Detection (Recommended)**
```
1. Send your Python script to the bot
2. Bot will auto-detect imports (e.g., requests, pandas, etc.)
3. Bot creates isolated venv and installs dependencies
4. Script runs in isolated environment
```

**Method 2: Custom Requirements**
```
1. Send your Python script to the bot
2. Within 10 seconds, send requirements.txt
3. Bot installs all packages from requirements.txt
4. Script runs with custom dependencies
```

**Method 3: URL Deployment**
```
/deploy https://example.com/script.py
```

### Command Bot

#### `/start` atau `/help`
Menampilkan pesan welcome dan daftar command yang tersedia.

#### `/deploy <url>`
Deploy skrip Python dari URL atau kirim file Python langsung ke bot.

**Contoh:**
```
/deploy https://raw.githubusercontent.com/user/repo/main/script.py
```

#### `/status`
Cek status semua proses yang berjalan dengan informasi detail.

**Output:**
```
📊 Process Status

Total: 2 / 10
Running: 2
──────────────────────────────

PID: 12345
Status: ✅ Running
File: script.py
Runtime: 0h 15m 30s
Restarts: 0/3
──────────────────────────────
```

#### `/log <pid>`
Download log file dari proses tertentu. Jika file terlalu besar (>50MB), bot akan mengirim 1000 baris terakhir.

**Contoh:**
```
/log 12345
```

#### `/stop <pid>`
Hentikan proses yang berjalan dan cleanup resources.

**Contoh:**
```
/stop 12345
```

### Web API

#### Health Check
```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "processes": {
    "total": 3,
    "running": 2,
    "max": 10
  },
  "timestamp": "2024-12-04T10:30:00"
}
```

#### Process Statistics
```bash
curl http://localhost:5000/stats
```

**Response:**
```json
{
  "total": 2,
  "processes": [
    {
      "pid": 12345,
      "status": "✅ Running",
      "file": "script.py",
      "runtime": "0h 15m 30s",
      "restarts": 0,
      "max_restarts": 3
    }
  ],
  "timestamp": "2024-12-04T10:30:00"
}
```

#### Shutdown (Protected)
```bash
curl -X POST http://localhost:5000/shutdown \
  -H "Authorization: Bearer your_shutdown_token"
```

## 🏗️ Arsitektur

Aplikasi ini terdiri dari tiga komponen utama yang bekerja secara bersamaan. **Telegram Bot** menggunakan Pyrogram untuk komunikasi dengan user dan menerima command untuk deployment dan manajemen. **Flask Web Server** menyediakan REST API untuk health check, statistics, dan management endpoints. **Process Manager** mengelola lifecycle semua proses yang di-deploy dengan thread-safe operations dan auto-restart mechanism.

### Process Lifecycle

Setiap proses yang di-deploy melalui lifecycle berikut: dimulai dari **Deploy** (user mengirim script), kemudian **Validate** (bot memvalidasi file), lalu **Start** (process dimulai dengan subprocess), masuk ke state **Running** dengan monitoring aktif, kemudian **Monitor** terus menerus mengecek status. Jika proses berhasil, masuk ke state **Success**, jika gagal masuk ke **Failure** yang akan trigger **Restart** (maksimal 3 kali) atau **Cleanup** jika sudah melebihi batas restart.

## 🔐 Keamanan

### Best Practices

**Jangan Commit Credentials:** File `config.py` sudah ada di `.gitignore`. Jangan pernah commit file ini ke repository.

**Whitelist Users:** Untuk production, selalu set `ALLOWED_USERS` di config.py untuk membatasi akses hanya ke user tertentu.

**Secure Shutdown Token:** Generate secure token untuk shutdown endpoint menggunakan Python:
```python
import secrets
print(secrets.token_urlsafe(32))
```

**Firewall Configuration:** Batasi akses ke Flask port (5000) hanya dari IP yang dipercaya. Gunakan reverse proxy (nginx/caddy) untuk production deployment.

**Process Isolation:** Setiap skrip berjalan di subprocess terpisah dengan working directory yang isolated. Tidak ada shared state antar proses.

### Vulnerability Fixes (v2.0)

Versi 2.0 ini mengatasi semua masalah keamanan dari versi sebelumnya:

- **Hardcoded credentials:** ✅ Fixed - Menggunakan config.py yang tidak di-commit
- **Arbitrary code execution:** ⚠️ Mitigated - User whitelist + monitoring
- **Race conditions:** ✅ Fixed - Thread-safe dengan locks
- **Memory leaks:** ✅ Fixed - Proper cleanup mechanism
- **Unsecured endpoints:** ✅ Fixed - Token authentication

## 📊 Monitoring & Logging

### Log Structure

```
logs/
├── bot.log              # Main bot log (rotated at 10MB)
├── bot.log.1            # Backup log
├── bot.log.2
└── process_*.log        # Individual process logs
```

### Log Format

Setiap log entry menggunakan format terstruktur:
```
2024-12-04 10:30:00 - __main__ - INFO - Process 12345 started by user 123456789
2024-12-04 10:30:05 - __main__ - WARNING - Process 12345 failed with exit code 1
2024-12-04 10:30:06 - __main__ - INFO - Attempting to restart process 12345
```

### Metrics

Bot menyimpan dan melaporkan metrics berikut: total processes started, active processes, failed processes, restart attempts, dan runtime per process.

## 🐳 Docker Deployment

### Build dan Run

```bash
# Build image
docker build -t botdeploy:v2 .

# Run container
docker run -d \
  --name botdeploy \
  -v $(pwd)/config.py:/app/config.py \
  -v $(pwd)/logs:/app/logs \
  -p 5000:5000 \
  --restart unless-stopped \
  botdeploy:v2
```

### Docker Compose (Coming Soon)

Docker Compose configuration akan ditambahkan di versi mendatang untuk memudahkan deployment.

## 🧪 Testing

### Manual Testing

Test semua fitur utama setelah instalasi:

1. **Test Deployment dari URL:**
   ```
   /deploy https://raw.githubusercontent.com/python/cpython/main/Tools/scripts/md5sum.py
   ```

2. **Test Status:**
   ```
   /status
   ```

3. **Test Log Retrieval:**
   ```
   /log <pid>
   ```

4. **Test Stop:**
   ```
   /stop <pid>
   ```

### Health Check

```bash
# Check if bot is running
curl http://localhost:5000/health

# Expected: {"status": "healthy", ...}
```

## 🐛 Troubleshooting

### Bot Tidak Start

**Gejala:** Error saat menjalankan `python run.py`

**Solusi:**
1. Pastikan `config.py` sudah dibuat dari `config.py.example`
2. Cek credentials di `config.py` sudah benar
3. Pastikan semua dependencies terinstall: `pip install -r requirements.txt`

### Process Tidak Start

**Gejala:** Deploy berhasil tapi process langsung crash

**Solusi:**
1. Cek log file dengan command `/log <pid>`
2. Pastikan script yang di-deploy tidak memiliki syntax error
3. Cek dependencies script sudah terinstall di environment

### Memory Usage Tinggi

**Gejala:** Bot menggunakan banyak memory

**Solusi:**
1. Kurangi `MAX_PROCESSES` di config.py
2. Cleanup old logs: `find logs/ -name "*.log" -mtime +7 -delete`
3. Monitor dengan `/status` dan stop process yang tidak perlu

### Port Already in Use

**Gejala:** Error "Address already in use"

**Solusi:**
1. Cari proses yang menggunakan port: `lsof -i :5000`
2. Kill proses: `kill -9 <PID>`
3. Atau ubah `FLASK_PORT` di config.py

## 📝 Changelog

### v2.1.0 (2024-12-04)

#### 📦 Dependency Management
- ✅ Auto-detect imports from script
- ✅ Virtual environment per process
- ✅ Support requirements.txt upload
- ✅ Isolated package installation
- ✅ Fallback for cloud restrictions

#### 🔧 Improvements
- ✅ Better error messages
- ✅ Enhanced logging for dependencies
- ✅ Configurable venv cleanup
- ✅ Support for both auto and manual deps

### v2.0.0 (2024-12-04)

#### 🔒 Security
- ✅ Removed hardcoded credentials
- ✅ Added user authorization whitelist
- ✅ Protected shutdown endpoint
- ✅ Thread-safe process management

#### 🚀 Features
- ✅ Auto-restart on failure (max 3 attempts)
- ✅ Real-time monitoring with notifications
- ✅ Rotating log handler
- ✅ Health check API endpoint
- ✅ Process statistics tracking

#### 🐛 Bug Fixes
- ✅ Fixed race conditions
- ✅ Fixed memory leaks
- ✅ Fixed async/await inconsistencies
- ✅ Fixed temporary file cleanup

#### 📚 Documentation
- ✅ Comprehensive README
- ✅ Configuration template
- ✅ Code documentation

## 🤝 Contributing

Contributions are welcome! Untuk berkontribusi:

1. Fork repository
2. Create feature branch: `git checkout -b feature/AmazingFeature`
3. Commit changes: `git commit -m 'Add some AmazingFeature'`
4. Push to branch: `git push origin feature/AmazingFeature`
5. Open Pull Request

### Code Style

- Follow PEP 8 style guide
- Use type hints untuk semua functions
- Add docstrings untuk dokumentasi
- Write tests untuk new features

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 👥 Authors

- **Original Version** - Initial work
- **v2.0 Professional Edition** - Complete refactoring with security and stability improvements

## 🙏 Acknowledgments

- [Pyrogram](https://docs.pyrogram.org/) - Modern Telegram Bot framework
- [Flask](https://flask.palletsprojects.com/) - Lightweight web framework
- Community contributors and testers

## 📞 Support

Jika Anda menemukan bug atau memiliki pertanyaan:

- 🐛 **Issues:** [GitHub Issues](https://github.com/Illhm/BOTDEPLOY/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/Illhm/BOTDEPLOY/discussions)

---

**⚠️ Disclaimer:** Bot ini dapat menjalankan kode Python arbitrary. Gunakan dengan hati-hati dan hanya deploy skrip dari sumber terpercaya. Implementasikan whitelist user untuk production use.

**Made with ❤️ by Bot Deploy Manager Team**
