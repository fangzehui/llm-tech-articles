# GLM-5.2 三通道路由器镜像
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先单独 COPY requirements.txt 以利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再 COPY 业务代码（避免修改源码触发依赖层失效）
COPY router.py .
COPY configs ./configs

EXPOSE 8000

# 默认走 realtime profile，可通过 docker run -e ROUTER_CONFIG=... 覆盖
ENV ROUTER_CONFIG=/app/configs/profile_realtime.yml \
    ROUTER_HOST=0.0.0.0 \
    ROUTER_PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "router:app", "--host", "0.0.0.0", "--port", "8000"]
