# Base image with Python 3.11
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install deemix globally
RUN pip install --no-cache-dir deemix

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY SpotifyApiCall.py .
COPY DeezerApiCall.py .
COPY bot.py .

# Create necessary directories
RUN mkdir -p /app/downloads /app/data /root/.config/deemix

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DOWNLOAD_DIR=/app/downloads

# Volume for persistent data
VOLUME ["/app/data", "/app/downloads", "/root/.config/deemix"]

# Health check
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/data/config.json') else 1)"

# Run the bot
CMD ["python", "-u", "bot.py"]