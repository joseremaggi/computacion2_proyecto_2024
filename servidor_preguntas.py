import asyncio
import json
import random
import argparse
import multiprocessing
import socket  # Agregar al inicio del archivo
import datetime  # <-- Importado para agregar timestamps en logs

# Lista de clientes conectados
clients = []
puntos_jugadores = {}
preguntas_enviadas = 0
juego_terminado = asyncio.Event()
game_semaphore = asyncio.Semaphore()
ganador_anunciado = False  # Variable para evitar múltiples registros

# Cola de mensajes para logging
log_queue = multiprocessing.Queue()

# ---------------- FUNCIONES PARA LOGS ----------------

def escribir_log(log_queue):
    """Escribe logs usando la ruta absoluta del contenedor."""
    log_path = "logs/log_partidas.txt"  # Ruta absoluta
    with open(log_path, "a", encoding="utf-8", buffering=1) as log_file:  # buffering=1 (line-buffered)
        while True:
            mensaje = log_queue.get()
            if mensaje == "TERMINAR":
                break
            log_file.write(mensaje + "\n")
            log_file.flush()  # Fuerza escritura inmediata (redundante con buffering=1)
def loggear(mensaje):
    """Añade la fecha y hora al mensaje y lo envía a la cola de logs."""
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")  # Formato: [YYYY-MM-DD HH:MM:SS]
    log_queue.put(f"{timestamp} {mensaje}")  # Guarda el mensaje con la fecha

# ---------------- FUNCIONES DEL JUEGO ----------------

def cargar_preguntas_desde_archivo(archivo):
    with open(archivo, 'r', encoding='utf-8') as f:
        preguntas = json.load(f)
    return preguntas

def obtener_pregunta_aleatoria():
    return random.choice(preguntas)

async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    async with game_semaphore:
        puntos_jugadores[addr] = 0
        clients.append((reader, writer))
        print(f"Clientes conectados: {len(clients)}")
        loggear(f"Jugador {addr} se ha conectado")

    try:
        while not juego_terminado.is_set():
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print(f"Jugador {addr} desconectado debido a una cancelación")
    finally:
        print(f"Jugador desconectado: {addr}")
        loggear(f"Jugador {addr} se ha desconectado")
        async with game_semaphore:
            if (reader, writer) in clients:
                clients.remove((reader, writer))
            if addr in puntos_jugadores:
                del puntos_jugadores[addr]
        writer.close()
        await writer.wait_closed()

async def broadcast_pregunta(num_preguntas):
    global preguntas_enviadas, ganador_anunciado
    while preguntas_enviadas < num_preguntas:
        if not clients:  # Si no hay jugadores, cancelar el juego
            loggear("Partida cancelada: Todos los jugadores se desconectaron.")
            return  # Salir de la función sin anunciar ganador

        pregunta = obtener_pregunta_aleatoria()
        pregunta_texto = (
            f"PREGUNTA:{pregunta['pregunta']}\nA) {pregunta['opciones']['A']}\nB) {pregunta['opciones']['B']}\n"
            f"C) {pregunta['opciones']['C']}\nD) {pregunta['opciones']['D']}\n"
        )

        # Enviar pregunta a los clientes conectados
        for _, writer in clients.copy():
            try:
                writer.write(pregunta_texto.encode())
                await writer.drain()
            except (ConnectionResetError, ConnectionAbortedError):
                clients.remove((_, writer))
                addr = writer.get_extra_info('peername')
                if addr in puntos_jugadores:
                    del puntos_jugadores[addr]
                loggear(f"Jugador {addr} se desconectó durante la pregunta")

        loggear(f"Enviada pregunta {preguntas_enviadas + 1}: {pregunta['pregunta']}")

        respuestas = await obtener_respuestas(pregunta['respuesta_correcta'])

        # Procesar respuestas
        for addr, (status, reader, writer) in respuestas.items():
            if addr not in puntos_jugadores:
                continue  # Jugador ya desconectado

            if status == "correcta":
                puntos_jugadores[addr] += 1
                loggear(f"Jugador {addr} respondió correctamente")
            elif status == "incorrecta":
                loggear(f"Jugador {addr} respondió incorrectamente")
            else:
                loggear(f"Jugador {addr} no respondió a tiempo")

            # Enviar resultado al jugador
            try:
                mensaje = f"RESULTADO: {'Correcto' if status == 'correcta' else 'Incorrecto'}\n"
                writer.write(mensaje.encode())
                await writer.drain()
            except (ConnectionResetError, ConnectionAbortedError):
                clients.remove((reader, writer))
                del puntos_jugadores[addr]
                loggear(f"Jugador {addr} se desconectó durante el resultado")

        preguntas_enviadas += 1
        await asyncio.sleep(10)

    # Anunciar ganador solo si hay jugadores
    if puntos_jugadores:
        await anunciar_ganador()
    else:
        loggear("No hay jugadores para anunciar ganador")

    juego_terminado.set()


async def obtener_respuestas(respuesta_correcta):
    respuestas = {}

    for reader, writer in clients:
        try:
            data = await asyncio.wait_for(reader.read(100), timeout=10)
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

async def anunciar_ganador():
    global ganador_anunciado

    max_puntos = max(puntos_jugadores.values())
    ganadores = [addr for addr, puntos in puntos_jugadores.items() if puntos == max_puntos]

    if len(ganadores) > 1:
        mensaje = f"¡Empate con {max_puntos} puntos entre: {', '.join(map(str, ganadores))}"
    else:
        mensaje = f"¡Ganador: {ganadores[0]} con {max_puntos} puntos!"

    # Registrar en el log ANTES de enviar a los clientes
    loggear(mensaje)

    # Enviar mensaje a los clientes
    for _, writer in clients.copy():
        try:
            writer.write(f"{mensaje}\nFIN".encode())
            await writer.drain()
        except (ConnectionResetError, ConnectionAbortedError):
            addr = writer.get_extra_info('peername')
            clients.remove((_, writer))
            if addr in puntos_jugadores:
                del puntos_jugadores[addr]
            loggear(f"Jugador {addr} se desconectó durante el anuncio")

# ---------------- FUNCIÓN PRINCIPAL ----------------

async def main(file, num_preguntas):
    global preguntas, juego_terminado, preguntas_enviadas, ganador_anunciado, clients, puntos_jugadores
    preguntas = cargar_preguntas_desde_archivo(file)

    log_process = multiprocessing.Process(target=escribir_log, args=(log_queue,))
    log_process.start()

    server = await asyncio.start_server(
        handle_client,
        host='0.0.0.0',
        port=8888,
        family=socket.AF_UNSPEC,  # Acepta IPv4 e IPv6
        reuse_address=True,
        reuse_port=False
    )
    try:
        while True:
            if clients:
                # Reiniciar estado solo para jugadores conectados
                juego_terminado.clear()
                preguntas_enviadas = 0
                ganador_anunciado = False
                puntos_jugadores = {writer.get_extra_info('peername'): 0 for _, writer in clients}
                await broadcast_pregunta(num_preguntas)
            else:
                await asyncio.sleep(5)
    finally:
        log_queue.put("TERMINAR")
        log_process.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de trivia Pokémon")
    parser.add_argument('file', type=str, help="Archivo JSON con las preguntas")
    parser.add_argument('num_preguntas', type=int, help="Número de preguntas para el juego")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.file, args.num_preguntas))
    except KeyboardInterrupt:
        print("Servidor detenido")
        loggear("Servidor detenido por interrupción manual")
