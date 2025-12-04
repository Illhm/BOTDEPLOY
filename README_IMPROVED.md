# 🤖 Bot Deploy Manager v2.0

Bot Telegram profesional untuk deployment dan manajemen skrip Python secara remote dengan monitoring otomatis, auto-restart, dan logging lengkap.

## ✨ Fitur Utama

### 🚀 Deployment Fleksibel
- Deploy skrip dari URL atau file upload
- Validasi file otomatis
- Isolasi proses dengan subprocess

### 📊 Monitoring Real-time
- Status monitoring untuk semua proses
- Auto-restart pada failure (maksimal 3x)
- Notifikasi real-time via Telegram
- Log rotation otomatis

### 🔒 Keamanan
- User authorization dengan whitelist
- Tidak ada hardcoded credentials
- Protected shutdown endpoint
- Thread-safe process management

### 📝 Logging Lengkap
- Rotating file handler (10MB per file)
- Separate log per process
- Log retrieval via Telegram
- Structured logging format

### 🌐 Web Interface
- Health check endpoint
- RESTful API
- Process statistics
- Protected management endpoints

## 📋 Persyaratan

- Python 3.9+
- Telegram Bot Token (dari [@BotFather](https://t.me/botfather))
- Telegram API credentials (dari [my.telegram.org](https://my.telegram.org))

## 🔧 Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/Ilham311/BOTDEPLOY.git
cd BOTDEPLOY
```

### 2. Install Dependencies

```bash
pip install -r requirements_improved.txt
```

### 3. Konfigurasi Environment

```bash
# Copy template konfigurasi
cp .env.example .env

# Edit dengan credentials Anda
nano .env
```

**Konfigurasi Wajib:**
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
```

**Konfigurasi Opsional:**
```env
# Whitelist user IDs (comma-separated)
ALLOWED_USERS=123456789,987654321

# Shutdown token untuk API
SHUTDOWN_TOKEN=your_secure_token

# Process limits
MAX_PROCESSES=10
MONITOR_INTERVAL=5
```

### 4. Jalankan Bot

```bash
python run_improved.py
```

## 📖 Cara Penggunaan

### Command Bot

#### `/start` atau `/help`
Menampilkan pesan welcome dan daftar command.

```
/start
```

#### `/deploy <url>`
Deploy skrip Python dari URL.

```
/deploy https://raw.githubusercontent.com/user/repo/main/script.py
```

Atau kirim file Python langsung ke bot.

#### `/status`
Cek status semua proses yang berjalan.

```
/status
```

**Output:**
```
📊 Process Status

PID: 12345
Status: ✅ Running
File: script.py
Runtime: 0h 15m 30s
Restarts: 0/3
──────────────────────────────
```

#### `/log <pid>`
Download log file dari proses tertentu.

```
/log 12345
```

#### `/stop <pid>`
Hentikan proses yang berjalan.

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
  "processes": {
    "total": 3,
    "running": 2,
    "max": 10
  },
  "timestamp": "2024-12-04T10:30:00"
}
```

#### Shutdown (Protected)
```bash
curl -X POST http://localhost:5000/shutdown \
  -H "Authorization: Bearer your_shutdown_token"
```

## 🏗️ Arsitektur

### Komponen Utama

```
┌─────────────────────────────────────────────────┐
│           Bot Deploy Manager v2.0               │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐      ┌──────────────┐       │
│  │   Telegram   │      │    Flask     │       │
│  │   Bot (API)  │      │  Web Server  │       │
│  └──────┬───────┘      └──────┬───────┘       │
│         │                     │                │
│         └──────────┬──────────┘                │
│                    │                           │
│         ┌──────────▼───────────┐               │
│         │   Process Manager    │               │
│         │  (Thread-Safe)       │               │
│         └──────────┬───────────┘               │
│                    │                           │
│         ┌──────────▼───────────┐               │
│         │  Process Monitor     │               │
│         │  (Auto-Restart)      │               │
│         └──────────────────────┘               │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Process Lifecycle

```
┌─────────┐
│ Deploy  │
└────┬────┘
     │
     ▼
┌─────────────┐
│  Validate   │
└────┬────────┘
     │
     ▼
┌─────────────┐      ┌──────────┐
│   Start     │─────▶│ Running  │
└─────────────┘      └────┬─────┘
                          │
                          ▼
                     ┌─────────┐
                     │ Monitor │
                     └────┬────┘
                          │
                ┌─────────┴─────────┐
                │                   │
                ▼                   ▼
           ┌─────────┐         ┌─────────┐
           │ Success │         │ Failure │
           └─────────┘         └────┬────┘
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                          ▼                   ▼
                    ┌──────────┐        ┌─────────┐
                    │ Restart  │        │ Cleanup │
                    │ (Max 3x) │        └─────────┘
                    └──────────┘
```

## 🔐 Keamanan

### Best Practices

1. **Jangan Commit Credentials**
   - Gunakan `.env` file (sudah di `.gitignore`)
   - Jangan hardcode API keys di kode

2. **Whitelist Users**
   ```env
   ALLOWED_USERS=123456789,987654321
   ```

3. **Secure Shutdown Token**
   ```bash
   # Generate secure token
   openssl rand -hex 32
   ```

4. **Firewall Configuration**
   - Batasi akses ke Flask port (5000)
   - Gunakan reverse proxy (nginx/caddy) untuk production

5. **Process Isolation**
   - Setiap skrip berjalan di subprocess terpisah
   - Tidak ada shared state antar proses

### Vulnerability Fixes (v2.0)

| Issue | Status | Solution |
|-------|--------|----------|
| Hardcoded credentials | ✅ Fixed | Environment variables only |
| Arbitrary code execution | ⚠️ Mitigated | User whitelist + monitoring |
| Race conditions | ✅ Fixed | Thread-safe with locks |
| Memory leaks | ✅ Fixed | Proper cleanup mechanism |
| Unsecured endpoints | ✅ Fixed | Token authentication |

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

```
2024-12-04 10:30:00 - __main__ - INFO - Process 12345 started by user 123456789
2024-12-04 10:30:05 - __main__ - WARNING - Process 12345 failed with code 1
2024-12-04 10:30:06 - __main__ - INFO - Attempting to restart process 12345
```

### Metrics

Bot menyimpan metrics berikut:
- Total processes started
- Active processes
- Failed processes
- Restart attempts
- Runtime per process

## 🐳 Docker Deployment

### Build Image

```bash
docker build -t botdeploy:v2 .
```

### Run Container

```bash
docker run -d \
  --name botdeploy \
  --env-file .env \
  -p 5000:5000 \
  -v $(pwd)/logs:/app/logs \
  botdeploy:v2
```

### Docker Compose

```yaml
version: '3.8'

services:
  botdeploy:
    build: .
    env_file: .env
    ports:
      - "5000:5000"
    volumes:
      - ./logs:/app/logs
      - ./temp:/app/temp
    restart: unless-stopped
```

## 🧪 Testing

### Manual Testing

1. **Test Deployment**
   ```
   /deploy https://raw.githubusercontent.com/python/cpython/main/Tools/scripts/md5sum.py
   ```

2. **Test Status**
   ```
   /status
   ```

3. **Test Log Retrieval**
   ```
   /log <pid>
   ```

4. **Test Stop**
   ```
   /stop <pid>
   ```

### Health Check

```bash
# Check if bot is running
curl http://localhost:5000/health

# Expected output
{
  "status": "healthy",
  "processes": {...}
}
```

## 🐛 Troubleshooting

### Bot Tidak Start

**Gejala:** Error saat menjalankan `python run_improved.py`

**Solusi:**
1. Cek environment variables:
   ```bash
   python -c "from run_improved import Config; Config.validate()"
   ```

2. Cek credentials Telegram:
   - API_ID dan API_HASH dari [my.telegram.org](https://my.telegram.org)
   - BOT_TOKEN dari [@BotFather](https://t.me/botfather)

### Process Tidak Start

**Gejala:** Deploy berhasil tapi process langsung crash

**Solusi:**
1. Cek log file:
   ```
   /log <pid>
   ```

2. Cek dependencies skrip:
   - Pastikan semua library terinstall
   - Cek Python version compatibility

### Memory Usage Tinggi

**Gejala:** Bot menggunakan banyak memory

**Solusi:**
1. Kurangi MAX_PROCESSES:
   ```env
   MAX_PROCESSES=5
   ```

2. Implementasi log rotation lebih agresif

3. Cleanup old logs:
   ```bash
   find logs/ -name "*.log" -mtime +7 -delete
   ```

## 📝 Changelog

### v2.0.0 (2024-12-04)

#### 🔒 Security Improvements
- ✅ Removed hardcoded credentials
- ✅ Added user authorization whitelist
- ✅ Protected shutdown endpoint with token
- ✅ Thread-safe process management

#### 🚀 Features
- ✅ Auto-restart on failure (max 3 attempts)
- ✅ Real-time monitoring with notifications
- ✅ Rotating log handler (10MB limit)
- ✅ Health check API endpoint
- ✅ Process statistics tracking

#### 🐛 Bug Fixes
- ✅ Fixed race condition in process monitoring
- ✅ Fixed async/await inconsistencies
- ✅ Fixed memory leak in process registry
- ✅ Fixed temporary file cleanup
- ✅ Fixed log file growth issue

#### 📚 Documentation
- ✅ Comprehensive README
- ✅ Code analysis document
- ✅ Environment configuration template
- ✅ Architecture diagrams

### v1.0.0 (Original)
- Basic deployment functionality
- Simple process management
- Flask web server

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

### Code Style

- Follow PEP 8
- Use type hints
- Add docstrings
- Write tests

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👥 Authors

- **Original Version** - Initial work
- **v2.0 Improvements** - Professional refactoring and security enhancements

## 🙏 Acknowledgments

- [Pyrogram](https://docs.pyrogram.org/) - Telegram Bot framework
- [Flask](https://flask.palletsprojects.com/) - Web framework
- Community contributors

## 📞 Support

- 📧 Email: support@example.com
- 💬 Telegram: @yourusername
- 🐛 Issues: [GitHub Issues](https://github.com/Ilham311/BOTDEPLOY/issues)

---

**⚠️ Disclaimer:** Bot ini dapat menjalankan kode Python arbitrary. Gunakan dengan hati-hati dan hanya deploy skrip dari sumber terpercaya. Implementasikan whitelist user untuk production use.
