FROM python:3.11-slim

# Avoid generating .pyc files and make logs appear immediately.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies.
# build-essential/cmake are useful for some RAG-related dependencies.
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.ustc.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://deb.debian.org/debian-security|http://mirrors.ustc.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files.
COPY . .

# Use a faster PyPI mirror inside the container.
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.timeout 120 \
    && pip install --upgrade pip setuptools wheel \
    && pip install -e .

# Expose FastAPI port.
EXPOSE 8000

# Start FastAPI service.
CMD ["uvicorn", "research_pilot.api.server:app", "--host", "0.0.0.0", "--port", "8000"]