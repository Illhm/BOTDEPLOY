# ============================================================================
# Bot Deploy Manager v2.0 - Modal Compatible
# ============================================================================

FROM python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/usr/local/bin:${PATH}"

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Setup user and directories
RUN useradd -m -u 1000 botuser && \
    mkdir -p /app/logs /app/temp

# Set working directory
WORKDIR /app

# Copy requirements & install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- PERUBAHAN DI SINI ---
# Salin file tanpa flag --chown (karena Modal tidak mendukungnya)
COPY config.py .
COPY run.py .
COPY config.py.example .

# Jalankan chown secara manual untuk seluruh direktori kerja
RUN chown -R botuser:botuser /app

# Pindah ke user non-root
USER botuser

# Expose port (opsional di Modal, tapi baik untuk dokumentasi)
EXPOSE 5000

# Run application
CMD ["python", "run.py"]
