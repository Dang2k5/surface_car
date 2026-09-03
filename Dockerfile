# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
# GPU branch: install PyTorch from the default PyPI index. On Linux this wheel
# bundles the matching CUDA 12.x runtime libs (nvidia-cublas-cu12,
# nvidia-cudnn-cu12, ...) needed for torch.cuda -- no system CUDA toolkit or
# nvidia/cuda base image required inside the container. The EC2 host only
# needs the NVIDIA driver + nvidia-container-toolkit (both preinstalled on the
# AWS Deep Learning AMI) so `docker run --gpus all` passes the GPU through;
# ultralytics then runs inference on MODEL_DEVICE=cuda:0.
RUN pip install --no-cache-dir --user torch
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# start-period is longer than the CPU branch's 90s: CUDA context init plus
# loading the model onto VRAM adds to cold-start time.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
