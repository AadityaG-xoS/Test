FROM python:3.11-slim

# Install system dependencies for Playwright and other tools
RUN apt-get update && apt-get install -y \
    libnss3 libxss1 libasound2 libatk1.0-0 \
    libgtk-3-0 libdrm2 libgbm1 libxcb-dri3-0 \
    libxcomposite1 libxrandr2 libpangocairo-1.0-0 \
    libenchant-2-2 libsecret-1-0 libmanette-0.2-0 \
    libgstreamer-gl1.0-0 gstreamer1.0-plugins-bad \
    libgles2-mesa \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set the working directory and copy application files
COPY . /app
WORKDIR /app

# Expose a port (replace 8000 if your app uses a different port)
EXPOSE 8000

# Run the app
CMD ["python", "app.py"]
