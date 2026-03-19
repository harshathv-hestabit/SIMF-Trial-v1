FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/__init__.py ./app/__init__.py
COPY app/modules/__init__.py ./app/modules/__init__.py
COPY app/modules/MAS ./app/modules/MAS

EXPOSE 8502

CMD ["sh", "-c", "\
    python -m app.modules.MAS & PY_PID=$! ; \
    streamlit run app/modules/MAS/ui/main.py \
        --server.headless=true \
        --server.port=8502 & ST_PID=$! ; \
    wait $PY_PID ; EXIT=$? ; kill $ST_PID 2>/dev/null ; exit $EXIT \
"]
