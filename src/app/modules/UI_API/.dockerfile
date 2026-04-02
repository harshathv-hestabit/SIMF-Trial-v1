FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY requirements.txt ./requirements.txt
COPY requirements ./requirements
RUN pip install --no-cache-dir -r requirements.txt -r requirements/ui_api.txt

COPY app/__init__.py ./app/__init__.py
COPY app/modules/__init__.py ./app/modules/__init__.py
COPY app/modules/UI_API ./app/modules/UI_API
COPY app/modules/DPS ./app/modules/DPS
COPY app/common ./app/common

EXPOSE 8088

CMD ["uvicorn", "app.modules.UI_API.main:app", "--host", "0.0.0.0", "--port", "8088"]
