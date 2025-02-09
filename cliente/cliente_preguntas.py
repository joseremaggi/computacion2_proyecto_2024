import asyncio
import json
import argparse
import aioconsole
import time  # Para medir tiempos de reconexión

async def background_input(queue: asyncio.Queue):
    """
    Tarea de fondo que lee continuamente la entrada del usuario
    y la coloca en una cola.
    """
    while True:
        try:
            line = await aioconsole.ainput("")
            await queue.put(line)
        except (asyncio.CancelledError, EOFError):
            break
        except Exception as e:
            print("Error leyendo la entrada:", e)
            break

async def tcp_client(config_path, name):
    shutdown = False  # Bandera para saber si se debe finalizar el cliente
    input_queue = asyncio.Queue()
    # Iniciar la tarea de fondo que lee de la entrada estándar
    bg_task = asyncio.create_task(background_input(input_queue))

    # Cargar la configuración desde el archivo
    with open(config_path, 'r') as f:
        config = json.load(f)

    servidor = config['servidor']
    puerto = config['puerto']

    reconnection_start = None

    try:
        while not shutdown:
            try:
                reader, writer = await asyncio.open_connection(servidor, puerto)
                # Si se conecta, reiniciamos el contador de reconexión
                reconnection_start = None
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
                            # Mostrar prompt; la tarea de fondo ya lee la entrada
                            print("Ingresa tu respuesta (A/B/C/D): ", end='', flush=True)
                            try:
                                # Espera a obtener la respuesta desde la cola con timeout
                                respuesta = await asyncio.wait_for(input_queue.get(), timeout=10)
                            except asyncio.TimeoutError:
                                # Vaciar la cola para descartar inputs tardíos
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
                except asyncio.CancelledError:
                    shutdown = True
                    break
                except ConnectionResetError:
                    print("Conexión cerrada por el servidor.")
                finally:
                    writer.close()
                    await writer.wait_closed()
                    if not shutdown:
                        print("Desconectado del servidor. Intentando reconectar en 5 segundos...\n")
                        await asyncio.sleep(5)
            except ConnectionRefusedError:
                if reconnection_start is None:
                    reconnection_start = time.time()
                else:
                    elapsed = time.time() - reconnection_start
                    if elapsed > 15:
                        print("Se perdió la conexión con el servidor.")
                        shutdown = True
                        break

                if not shutdown:
                    print(f"No se pudo conectar a {servidor}:{puerto}. Intentando reconectar en 5 segundos...\n")
                    await asyncio.sleep(5)
    except KeyboardInterrupt:
        shutdown = True
    finally:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
        # Mostrar mensaje de despedida al salir
        print(f"\nAdiós {args.name}, gracias por jugar.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cliente de trivia Pokémon')
    parser.add_argument('--config', type=str, required=True, help='Ruta al archivo de configuración')
    parser.add_argument('--name', type=str, required=True, help='Nombre del jugador')
    args = parser.parse_args()

    try:
        asyncio.run(tcp_client(args.config, args.name))
    except KeyboardInterrupt:
        print(f"\nAdiós {args.name}, gracias por jugar.")