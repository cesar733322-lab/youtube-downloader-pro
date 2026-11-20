FROM python:3.11-slim

WORKDIR /app

# Instalar FFmpeg, Node.js (para ejecutar JS de YouTube en la nube) y certificados SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar archivos de la aplicación
COPY . .

# Puerto dinámico
ENV PORT=10000

# Ejecutar el servidor web
CMD ["python", "web_server.py"]
