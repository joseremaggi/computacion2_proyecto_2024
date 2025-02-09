FROM python:3.9-slim

WORKDIR /app/cliente

# Copiar código y configuración
COPY cliente_preguntas.py config.json configipv4.json ./

# Instalar dependencias del cliente (si las tiene)
RUN pip install asyncio aioconsole

# Comando para ejecutar el cliente
CMD ["python", "cliente_preguntas.py"]