FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY app/modules/DPS/requirements.txt .
RUN pip install --no-cache-dir \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      -r requirements.txt

COPY app/__init__.py ./app/__init__.py
COPY app/modules/__init__.py ./app/modules/__init__.py
COPY app/modules/DPS ./app/modules/DPS

EXPOSE 8501

CMD ["sh", "-c", "\
    python -m app.modules.DPS & PY_PID=$! ; \
    streamlit run app/modules/DPS/streamlit_app.py \
        --server.headless=true \
        --server.port=8501 & ST_PID=$! ; \
    wait $PY_PID ; EXIT=$? ; kill $ST_PID 2>/dev/null ; exit $EXIT \
"]
