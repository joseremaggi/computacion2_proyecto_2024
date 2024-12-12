import asyncio
import json
import random
import argparse

# Lista de clientes conectados
clients = []

# Diccionario para almacenar los puntos de los jugadores
puntos_jugadores = {}

# Semáforo para controlar acceso concurrente
game_semaphore = asyncio.Semaphore()

# Contador de preguntas enviadas
preguntas_enviadas = 0

# Variable para detener el juego
juego_terminado = asyncio.Event()


# Función para cargar preguntas desde un archivo JSON
def cargar_preguntas_desde_archivo(archivo):
    with open(archivo, 'r', encoding='utf-8') as f:
        preguntas = json.load(f)
    return preguntas


# Función para obtener una pregunta aleatoria
def obtener_pregunta_aleatoria():
    return random.choice(preguntas)


# Función para manejar los clientes
async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"Jugador conectado: {addr}")

    # Inicializar puntos del jugador
    async with game_semaphore:
        puntos_jugadores[addr] = 0
        clients.append((reader, writer))  # Añadir cliente a la lista de clientes conectados

    try:
        while not juego_terminado.is_set():  # Esperar hasta que el juego termine
            await asyncio.sleep(1)

    except ConnectionResetError:
        pass
    finally:
        print(f"Jugador desconectado: {addr}")
        async with game_semaphore:  # Protección al acceder a la lista `clients`
            if (reader, writer) in clients:  # Verificar si el cliente aún está en la lista
                clients.remove((reader, writer))  # Remover cliente desconectado
        writer.close()
        await writer.wait_closed()



# Función para enviar preguntas y manejar respuestas
# Modificación en la función broadcast_pregunta para indicar tipos de mensajes
async def broadcast_pregunta(num_preguntas):
    global preguntas_enviadas
    while preguntas_enviadas < num_preguntas:
        if clients:  # Verifica si hay clientes conectados
            pregunta = obtener_pregunta_aleatoria()
            pregunta_texto = (
                f"PREGUNTA:{pregunta['pregunta']}\nA) {pregunta['opciones']['A']}\nB) {pregunta['opciones']['B']}\n"
                f"C) {pregunta['opciones']['C']}\nD) {pregunta['opciones']['D']}\n"
            )

            # Enviar la pregunta a todos los clientes conectados
            for _, writer in clients:
                writer.write(pregunta_texto.encode())
                await writer.drain()

            # Recibir respuestas de todos los clientes
            respuestas = await obtener_respuestas(pregunta['respuesta_correcta'])

            # Enviar resultados a todos los clientes
            for addr, (status, reader, writer) in respuestas.items():
                if status == "correcta":
                    async with game_semaphore:
                        puntos_jugadores[addr] += 1
                    mensaje = f"RESULTADO:¡Correcto! Tienes {puntos_jugadores[addr]} puntos.\n"
                elif status == "incorrecta":
                    mensaje = f"RESULTADO:Incorrecto. La respuesta correcta era {pregunta['respuesta_correcta']}. Tienes {puntos_jugadores[addr]} puntos.\n"
                else:  # Timeout o desconexión
                    mensaje = "RESULTADO:No respondiste a tiempo.\n"

                writer.write(mensaje.encode())
                await writer.drain()

            preguntas_enviadas += 1

        await asyncio.sleep(10)  # Intervalo entre preguntas

    # Fin del juego: mostrar al ganador
    await anunciar_ganador()
    juego_terminado.set()  # Señalar que el juego ha terminado


# Función para recibir respuestas de todos los clientes
async def obtener_respuestas(respuesta_correcta):
    respuestas = {}

    for reader, writer in clients:
        try:
            data = await asyncio.wait_for(reader.read(100), timeout=10)  # Timeout para evitar bloqueos
            respuesta = data.decode().strip().upper()

            addr = writer.get_extra_info('peername')
            if respuesta == respuesta_correcta:
                respuestas[addr] = ("correcta", reader, writer)
            else:
                respuestas[addr] = ("incorrecta", reader, writer)

        except asyncio.TimeoutError:
            addr = writer.get_extra_info('peername')
            respuestas[addr] = ("timeout", reader, writer)

    return respuestas
# Función para anunciar al ganador

async def anunciar_ganador():
    if puntos_jugadores:
        # Obtener la puntuación máxima
        max_puntos = max(puntos_jugadores.values())

        if max_puntos == 0:  # Si nadie sumó puntos
            mensaje_final = "¡Juego terminado! No hay ganador porque nadie sumó puntos.\n"
        else:
            # Filtrar jugadores con la puntuación máxima
            ganadores = [jugador for jugador, puntos in puntos_jugadores.items() if puntos == max_puntos]

            if len(ganadores) > 1:  # Si hay más de un ganador, es un empate
                mensaje_final = f"¡Juego terminado! Es un empate entre los siguientes jugadores con {max_puntos} puntos:\n"
                mensaje_final += "\n".join([str(ganador) for ganador in ganadores])
            else:  # Hay un solo ganador
                ganador = ganadores[0]
                mensaje_final = f"¡Juego terminado! El ganador es {ganador} con {max_puntos} puntos.\n"

        # Enviar el mensaje final a todos los clientes
        for _, writer in clients:
            try:
                writer.write((mensaje_final + "\nFIN").encode())  # Agregar indicador "FIN"
                await writer.drain()
            except Exception as e:
                print(f"Error enviando mensaje a cliente: {e}")

    print("El juego ha terminado. Cerrando servidor.")
    for _, writer in clients:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            print(f"Error cerrando conexión de cliente: {e}")

    clients.clear()


# Función principal del servidor
async def main(file, num_preguntas):
    global preguntas
    preguntas = cargar_preguntas_desde_archivo(file)

    # Configuración del servidor para IPv4 e IPv6
    server = await asyncio.start_server(handle_client, host=None, port=8888)

    # Mostrar las direcciones en las que está escuchando
    for sock in server.sockets:
        addr = sock.getsockname()
        print(f"Servidor corriendo en {addr}")

    # Correr la tarea de broadcasting en paralelo
    await asyncio.gather(server.serve_forever(), broadcast_pregunta(num_preguntas))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de trivia Pokémon")
    parser.add_argument('file', type=str, help="Archivo JSON con las preguntas")
    parser.add_argument('num_preguntas', type=int, help="Número de preguntas para el juego")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.file, args.num_preguntas))
    except KeyboardInterrupt:
        print("Servidor detenido")
