# ============================================================================
# Bot Deploy Manager v2.0 - Production Dockerfile
# ============================================================================

FROM python:3.11-slim

# Metadata
LABEL maintainer="Bot Deploy Manager Team"
LABEL version="2.0.0"
LABEL description="Telegram bot for Python script deployment and management"

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
    # Cleanup
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* && \
    # Create non-root user for security
    useradd -m -u 1000 botuser && \
    # Create directories
    mkdir -p /app/logs /app/temp && \
    chown -R botuser:botuser /app

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=botuser:botuser run.py .
COPY --chown=botuser:botuser config.py.example .

# Switch to non-root user
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${FLASK_PORT:-5000}/health || exit 1

# Expose port
EXPOSE 5000

# Run application
CMD ["python", "run.py"]
