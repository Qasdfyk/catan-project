# 1. BASE: Use official Python 3.12 slim image
FROM python:3.12-slim

# 2. ENV VARS: 
# PYTHONDONTWRITEBYTECODE=1 -> Prevent .pyc files
# PYTHONUNBUFFERED=1 -> Log to console immediately (crucial for Docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. WORKDIR: Set working directory inside the container
WORKDIR /app

# 4. SYSTEM DEPENDENCIES: Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 5. INSTALL DEPENDENCIES:
# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. COPY CODE: Copy local source code to container
COPY . .

# 7. PORT: Expose port 8000
EXPOSE 8000

# 8. START: Run uvicorn server
# Host 0.0.0.0 is required to make the server accessible outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]