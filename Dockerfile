FROM python:3.11-slim
WORKDIR /app
ENV TZ=America/Argentina/Buenos_Aires
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY servidor_preguntas.py .
COPY preguntas_pokemon.json .

# Crea el directorio de logs y instala dependencias
RUN mkdir -p /app/logs && \
    chmod 777 /app/logs  # Permisos para cualquier usuario

EXPOSE 8888
CMD ["python", "servidor_preguntas.py", "preguntas_pokemon.json", "2"]