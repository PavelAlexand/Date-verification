FROM python:3.11-slim

# Установим зависимости для OpenCV и Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Копируем код
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Запуск
CMD ["python", "bot.py"]
