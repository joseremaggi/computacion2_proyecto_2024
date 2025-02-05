import asyncio
import json
import argparse
import aioconsole

async def background_input(queue: asyncio.Queue):
    """
    Tarea de fondo que lee continuamente la entrada del usuario
    y la coloca en una cola.
    """
    while True:
        try:
            # Lee una línea (sin prompt) de forma asíncrona
            line = await aioconsole.ainput("")
            await queue.put(line)
        except Exception as e:
            print("Error leyendo la entrada:", e)
            break

async def tcp_client(config_path, name):
    # Crear la cola para almacenar las entradas del usuario
    input_queue = asyncio.Queue()
    # Iniciar la tarea de fondo que lee de la entrada estándar
    asyncio.create_task(background_input(input_queue))

    # Cargar la configuración desde el archivo
    with open(config_path, 'r') as f:
        config = json.load(f)

    servidor = config['servidor']
    puerto = config['puerto']

    while True:
        try:
            reader, writer = await asyncio.open_connection(servidor, puerto)
            print(f"Conectado al servidor {servidor}:{puerto}. Esperando preguntas...")

            # Enviar el nombre del jugador al servidor
            writer.write(f"NAME:{name}".encode())
            await writer.drain()

            try:
                while True:
                    data = await reader.read(1000)
                    if not data:
                        break

                    mensaje = data.decode().strip()

                    if mensaje.startswith("PREGUNTA:"):
                        print(f'\nPregunta recibida: {mensaje[9:]}')
                        # Se muestra el prompt (sin esperar input acá, ya que la tarea de fondo lo hace)
                        print("Ingresa tu respuesta (A/B/C/D): ", end='', flush=True)
                        try:
                            # Espera a obtener la respuesta desde la cola con timeout
                            respuesta = await asyncio.wait_for(input_queue.get(), timeout=10)
                        except asyncio.TimeoutError:
                            # Si se agota el tiempo, se vacía la cola para descartar input tardío
                            while not input_queue.empty():
                                try:
                                    input_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break
                            print("\nNo respondiste a tiempo.")
                            respuesta = ""
                        respuesta = respuesta.strip().upper()
                        writer.write(respuesta.encode())
                        await writer.drain()

                    elif mensaje.startswith("RESULTADO:"):
                        print(mensaje[10:])
                    elif mensaje.endswith("FIN"):
                        print(mensaje[:-3])
                        print("Esperando nueva ronda...\n")

            except ConnectionResetError:
                print("Conexión cerrada por el servidor.")
            finally:
                writer.close()
                await writer.wait_closed()
                print("Desconectado del servidor. Intentando reconectar en 5 segundos...\n")
                await asyncio.sleep(5)

        except ConnectionRefusedError:
            print(f"No se pudo conectar a {servidor}:{puerto}. Intentando reconectar en 5 segundos...\n")
            await asyncio.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cliente de trivia Pokémon')
    parser.add_argument('--config', type=str, required=True, help='Ruta al archivo de configuración')
    parser.add_argument('--name', type=str, required=True, help='Nombre del jugador')
    args = parser.parse_args()

    asyncio.run(tcp_client(args.config, args.name))
