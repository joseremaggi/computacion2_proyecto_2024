FROM python:3.11-slim

WORKDIR /app/cliente

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Copiar código y configuración
COPY cliente_preguntas.py config.json configipv4.json ./

# Comando para ejecutar el cliente
CMD ["python", "cliente_preguntas.py"]