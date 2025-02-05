import asyncio
import json
import argparse
import aioconsole  # Importar aioconsole

async def tcp_client(config_path, name):
    # Cargar configuración desde el archivo
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
                        print(f'Pregunta recibida: {mensaje[9:]}')
                        respuesta = input('Ingresa tu respuesta (A/B/C/D): ').strip().upper()
                        writer.write(respuesta.encode())
                        await writer.drain()
                    elif mensaje.startswith("RESULTADO:"):
                        print(mensaje[10:])
                    elif mensaje.endswith("FIN"):
                        print(mensaje[:-3])
                        print("Esperando nueva ronda...")

            except ConnectionResetError:
                print("Conexión cerrada por el servidor.")
            finally:
                writer.close()
                await writer.wait_closed()
                print("Desconectado del servidor. Intentando reconectar en 5 segundos...")
                await asyncio.sleep(5)

        except ConnectionRefusedError:
            print(f"No se pudo conectar a {servidor}:{puerto}. Intentando reconectar en 5 segundos...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cliente de trivia Pokémon')
    parser.add_argument('--config', type=str, required=True, help='Ruta al archivo de configuración')
    parser.add_argument('--name', type=str, required=True, help='Nombre del jugador')
    args = parser.parse_args()

    asyncio.run(tcp_client(args.config, args.name))