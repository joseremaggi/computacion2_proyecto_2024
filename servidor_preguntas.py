import asyncio
import json
import random
import argparse
import multiprocessing
import socket
import datetime
import os  # Importar os para borrar el archivo

round_in_progress = asyncio.Event()
new_client_event = asyncio.Event()

# Lista de clientes conectados: cada elemento es (reader, writer, nombre_jugador)
clients = []
puntos_jugadores = {}
preguntas_enviadas = 0
juego_terminado = asyncio.Event()
game_semaphore = asyncio.Semaphore()
ganador_anunciado = False

# Cola de mensajes para logging
log_queue = multiprocessing.Queue()


# ---------------- FUNCIONES PARA LOGS ----------------

def escribir_log(log_queue):
    log_path = "logs/log_partidas.txt"
    # Asegurarse de que el directorio exista
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8", buffering=1) as log_file:
        while True:
            try:
                mensaje = log_queue.get(timeout=1)
                if mensaje == "TERMINAR":
                    break
                log_file.write(mensaje + "\n")
                log_file.flush()
            except multiprocessing.queues.Empty:
                continue
            except KeyboardInterrupt:
                break
            except Exception:
                break


def loggear(mensaje):
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    log_queue.put(f"{timestamp} {mensaje}")


# ---------------- FUNCIONES DEL JUEGO ----------------

def cargar_preguntas_desde_archivo(archivo):
    with open(archivo, 'r', encoding='utf-8') as f:
        preguntas = json.load(f)
    return preguntas


def obtener_pregunta_aleatoria():
    return random.choice(preguntas)


async def flush_reader(reader):
    """
    Intenta leer y descartar cualquier dato pendiente en el buffer del reader.
    Se usa un timeout muy corto para que, si no hay datos, se salga rápidamente.
    """
    while True:
        try:
            extra = await asyncio.wait_for(reader.read(100), timeout=0.01)
            if not extra:
                break
        except asyncio.TimeoutError:
            break


async def broadcast_pregunta(num_preguntas):
    global preguntas_enviadas, ganador_anunciado
    while preguntas_enviadas < num_preguntas:
        if not clients:
            loggear("Partida cancelada: Todos los jugadores se desconectaron.")
            return

        pregunta = obtener_pregunta_aleatoria()
        print("Pregunta seleccionada:", pregunta)  # Debug
        pregunta_texto = (
            f"PREGUNTA: {pregunta['pregunta']}\n"
            f"A) {pregunta['opciones']['A']}\n"
            f"B) {pregunta['opciones']['B']}\n"
            f"C) {pregunta['opciones']['C']}\n"
            f"D) {pregunta['opciones']['D']}\n"
        )
        print("Enviando pregunta:", pregunta_texto)  # Debug

        for reader, writer, nombre_jugador in clients.copy():
            try:
                writer.write(pregunta_texto.encode())
                await writer.drain()
                print(f"Pregunta enviada a {nombre_jugador}")  # Debug
            except Exception as e:
                print(f"Error al enviar pregunta a {nombre_jugador}: {e}")
                # Eliminar el cliente de forma segura:
                async with game_semaphore:
                    for c in clients.copy():
                        r, w, n = c
                        if r == reader and w == writer:
                            clients.remove(c)
                            break
                    addr = writer.get_extra_info('peername')
                    if addr in puntos_jugadores:
                        del puntos_jugadores[addr]
                loggear(f"Jugador {nombre_jugador} ({addr}) se desconectó durante la pregunta")

        loggear(f"Enviada pregunta {preguntas_enviadas + 1}: {pregunta['pregunta']}")
        respuestas = await obtener_respuestas(pregunta['respuesta_correcta'])
        print("Respuestas recibidas:", respuestas)  # Debug

        for addr, (status, reader, writer, nombre_jugador) in respuestas.items():
            if addr not in puntos_jugadores:
                continue

            if status == "correcta":
                puntos_jugadores[addr] += 1
                loggear(f"Jugador {nombre_jugador} ({addr}) respondió correctamente")
            elif status == "incorrecta":
                loggear(f"Jugador {nombre_jugador} ({addr}) respondió incorrectamente")
            else:
                loggear(f"Jugador {nombre_jugador} ({addr}) no respondió a tiempo")

            try:
                mensaje_resultado = f"RESULTADO: {'Correcto' if status == 'correcta' else 'Incorrecto'}\n"
                writer.write(mensaje_resultado.encode())
                await writer.drain()
            except Exception as e:
                print(f"Error al enviar resultado a {nombre_jugador}: {e}")
                async with game_semaphore:
                    for c in clients.copy():
                        r, w, n = c
                        if r == reader and w == writer:
                            clients.remove(c)
                            break
                    if addr in puntos_jugadores:
                        del puntos_jugadores[addr]
                loggear(f"Jugador {nombre_jugador} ({addr}) se desconectó durante el resultado")

        preguntas_enviadas += 1
        await asyncio.sleep(10)

    if puntos_jugadores:
        await anunciar_ganador()
    else:
        loggear("No hay jugadores para anunciar ganador")
    juego_terminado.set()


async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    # Recibir el nombre del jugador
    data = await reader.read(100)
    try:
        nombre_jugador = data.decode().strip().split("NAME:")[1]
    except IndexError:
        nombre_jugador = "JugadorDesconocido"

    async with game_semaphore:
        puntos_jugadores[addr] = 0
        clients.append((reader, writer, nombre_jugador))
        new_client_event.set()
        loggear(f"Jugador {nombre_jugador} ({addr}) se ha conectado")

    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, ConnectionResetError, ConnectionAbortedError):
        loggear(f"Jugador {nombre_jugador} ({addr}) desconectado inesperadamente.")
    finally:
        async with game_semaphore:
            for c in clients.copy():
                r, w, n = c
                if r == reader and w == writer:
                    clients.remove(c)
                    break
            if addr in puntos_jugadores:
                del puntos_jugadores[addr]
        loggear(f"Jugador {nombre_jugador} ({addr}) se ha desconectado")


async def obtener_respuestas(respuesta_correcta):
    respuestas = {}
    for reader, writer, nombre_jugador in clients.copy():
        addr = writer.get_extra_info('peername')
        try:
            data = await asyncio.wait_for(reader.read(100), timeout=10)
            respuesta = data.decode().strip().upper()
            if respuesta == respuesta_correcta:
                respuestas[addr] = ("correcta", reader, writer, nombre_jugador)
            else:
                respuestas[addr] = ("incorrecta", reader, writer, nombre_jugador)
        except asyncio.TimeoutError:
            # Limpia cualquier dato pendiente en el buffer del cliente para evitar inputs tardíos
            await flush_reader(reader)
            print(f"Jugador {nombre_jugador} {addr} no respondió a tiempo")
            loggear(f"Jugador {nombre_jugador} {addr} no respondió a tiempo")
            respuestas[addr] = ("incorrecta", reader, writer, nombre_jugador)
        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Jugador {nombre_jugador} {addr} se desconectó mientras respondía")
            loggear(f"Jugador {nombre_jugador} {addr} se desconectó mientras respondía")
            async with game_semaphore:
                for c in clients.copy():
                    r, w, n = c
                    if r == reader and w == writer:
                        clients.remove(c)
                        break
                if addr in puntos_jugadores:
                    del puntos_jugadores[addr]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    print(f"Clientes conectados después de respuestas: {len(clients)}")
    return respuestas


async def anunciar_ganador():
    global ganador_anunciado
    if preguntas_enviadas == 0:
        return  # No anunciar ganador si no se enviaron preguntas

    max_puntos = max(puntos_jugadores.values())
    if max_puntos == 0:
        mensaje = "¡Nadie ganó! Todos los jugadores tienen 0 puntos."
    else:
        ganadores = [addr for addr, puntos in puntos_jugadores.items() if puntos == max_puntos]
        if len(ganadores) > 1:
            nombres_ganadores = [
                f"{nombre} ({writer.get_extra_info('peername')})"
                for _, writer, nombre in clients
                if writer.get_extra_info('peername') in ganadores
            ]
            mensaje = f"¡Empate con {max_puntos} puntos entre: {', '.join(nombres_ganadores)}"
        else:
            ganador_info = [(nombre, writer.get_extra_info('peername'))
                            for _, writer, nombre in clients
                            if writer.get_extra_info('peername') in ganadores][0]
            ganador, addr = ganador_info
            mensaje = f"¡Ganador: {ganador} ({addr}) con {max_puntos} puntos!"

    loggear(mensaje)
    for _, writer, nombre_jugador in clients.copy():
        try:
            writer.write(f"{mensaje}\nFIN".encode())
            await writer.drain()
        except (ConnectionResetError, ConnectionAbortedError):
            addr = writer.get_extra_info('peername')
            async with game_semaphore:
                for c in clients.copy():
                    r, w, n = c
                    if w == writer:
                        clients.remove(c)
                        break
            loggear(f"Jugador {nombre_jugador} ({addr}) se desconectó durante el anuncio")


# ---------------- FUNCIÓN PRINCIPAL ----------------

log_process = None  # Definir log_process en un ámbito global

async def main(file, num_preguntas):
    global preguntas, clients, puntos_jugadores, preguntas_enviadas, log_process

    preguntas = cargar_preguntas_desde_archivo(file)

    # Iniciar el proceso para escribir logs
    log_process = multiprocessing.Process(
        target=escribir_log,
        args=(log_queue,),
        daemon=True  # Marcar como daemon para que termine con el proceso principal
    )
    log_process.start()

    # Crear un socket dual-stack (IPv6 e IPv4)
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # Desactivar IPV6_V6ONLY para aceptar conexiones IPv4 y IPv6
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    # Enlazar a todas las interfaces en el puerto 8888 usando '::'
    sock.bind(('::', 8888))
    sock.listen(100)
    sock.setblocking(False)

    # Pasar el socket creado manualmente a asyncio.start_server
    server = await asyncio.start_server(handle_client, sock=sock)

    # Mantener el servidor activo durante todo el bucle de juego
    async with server:
        await server.start_serving()
        while True:
            # Esperar a que se conecte al menos un cliente
            while not clients:
                try:
                    await asyncio.wait_for(new_client_event.wait(), timeout=5.0)
                    new_client_event.clear()
                except asyncio.TimeoutError:
                    pass

            # Enviar mensaje de espera a los clientes
            for _ in range(5):
                mensaje_espera = "Esperando nueva ronda...\n"
                for _, writer, nombre_jugador in clients.copy():
                    try:
                        writer.write(mensaje_espera.encode())
                        await writer.drain()
                    except (ConnectionResetError, ConnectionAbortedError):
                        async with game_semaphore:
                            for c in clients.copy():
                                r, w, n = c
                                if w == writer:
                                    clients.remove(c)
                                    break
                await asyncio.sleep(2)

            preguntas_enviadas = 0
            puntos_jugadores = {writer.get_extra_info('peername'): 0 for _, writer, _ in clients}
            await broadcast_pregunta(num_preguntas)

        # Al salir del bucle, se cerrarán las conexiones automáticamente al salir del "async with"
        await server.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de trivia Pokémon")
    parser.add_argument('file', type=str, help="Archivo JSON con las preguntas")
    parser.add_argument('num_preguntas', type=int, help="Número de preguntas para el juego")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.file, args.num_preguntas))
    except KeyboardInterrupt:
        print("\nServidor detenido por el usuario")
        # Asegurar que el proceso de logging termine
        if log_queue:
            log_queue.put("TERMINAR")
        if log_process:
            log_process.join(timeout=1)
            if log_process.is_alive():
                log_process.terminate()
