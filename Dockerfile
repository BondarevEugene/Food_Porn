FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Проверяем синтаксис всех Python-файлов приложения
RUN python -m compileall -q app main.py run.py

# Проверяем, что модуль нормализации меню действительно импортируется
RUN python -c "from app.services.dish_input import normalize_dish_payload; print('Dish input OK')"

RUN mkdir -p storage/uploads storage/generated storage/cache

CMD ["python", "run.py"]

