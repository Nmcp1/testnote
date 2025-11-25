# Imagen base de Python
FROM python:3.11-slim

# Evitar archivos .pyc y forzar logs sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Instalar dependencias del sistema (por si en el futuro agregas algo que las use)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements y instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el proyecto dentro del contenedor
COPY . .

# Exponer el puerto donde correrá Django
EXPOSE 8000

# Comando por defecto:
# 1) Ejecuta migraciones
# 2) Levanta el servidor en 0.0.0.0:8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
