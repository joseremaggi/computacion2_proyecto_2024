import asyncio
async def tcp_client():
    reader, writer = await asyncio.open_connection('127.0.0.1', 8888)

    try:
        while True:
            data = await reader.read(1000)
            if not data:
                break

            mensaje = data.decode().strip()

            # Detectar mensajes específicos del servidor
            if mensaje.startswith("PREGUNTA:"):
                print(f'Pregunta recibida: {mensaje[9:]}')  # Mostrar sin el prefijo "PREGUNTA:"
                respuesta = input('Ingresa tu respuesta (A/B/C/D): ').strip().upper()
                writer.write(respuesta.encode())
                await writer.drain()
            elif mensaje.startswith("RESULTADO:"):
                print(mensaje[10:])  # Mostrar sin el prefijo "RESULTADO:"
            elif mensaje.endswith("FIN"):
                print(mensaje[:-3])  # Mostrar mensaje final sin "FIN"
                break

    except ConnectionResetError:
        print("Conexión cerrada por el servidor.")
    finally:
        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(tcp_client())
