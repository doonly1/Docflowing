FROM python:3.11-slim

# 安装 LibreOffice（无头模式 -nogui，不依赖 X11）+ 中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Railway 会自动注入 PORT 环境变量覆盖默认 5000
CMD ["python", "server.py"]
