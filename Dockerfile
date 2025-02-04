FROM python:3.11-slim
WORKDIR /app

# Copia solo los archivos necesarios (¡no incluyas el log!)
COPY servidor_preguntas.py .
COPY preguntas_pokemon.json .
COPY requirements.txt .

# Crea el directorio de logs y instala dependencias
RUN mkdir -p /app/logs && \
    chmod 777 /app/logs  # Permisos para cualquier usuario

EXPOSE 8888
CMD ["python", "-u", "servidor_preguntas.py", "preguntas_pokemon.json", "2"]