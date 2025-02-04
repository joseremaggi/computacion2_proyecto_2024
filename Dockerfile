FROM python:3.9-slim

WORKDIR /app

COPY servidor_preguntas.py .
COPY preguntas_pokemon.json .
COPY log_partidas.txt .

CMD ["python", "servidor_preguntas.py", "preguntas_pokemon.json", "1"]