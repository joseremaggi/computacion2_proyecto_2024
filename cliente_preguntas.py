import asyncio
async def tcp_client():
    while True:  # Bucle para reconectar automáticamente
        try:
            #reader, writer = await asyncio.open_connection('127.0.0.1', 8888)
            reader, writer = await asyncio.open_connection('::1', 8888)
            print("Conectado al servidor. Esperando preguntas...")

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
                        # No cerrar la conexión, esperar nuevas preguntas
                        print("Esperando nueva ronda...")

            except ConnectionResetError:
                print("Conexión cerrada por el servidor.")
            finally:
                writer.close()
                await writer.wait_closed()
                print("Desconectado del servidor. Intentando reconectar en 5 segundos...")
                await asyncio.sleep(5)

        except ConnectionRefusedError:
            print("No se pudo conectar al servidor. Intentando reconectar en 5 segundos...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(tcp_client())
