import socket
import cv2
import numpy as np

def recvall(sock, n):
    """Recibe exactamente n bytes o devuelve None si falla."""
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_ip = ""
    client.connect(('192.168.80.13', 5000))

    print("Connected to the server.")

    while True:
        # Recibir el tamaño de la imagen (4 bytes)
        size_data = recvall(client, 4)
        if not size_data:
            break

        size = int.from_bytes(size_data, byteorder='big')

        # Recibir la imagen completa
        image_data = recvall(client, size)
        if not image_data:
            break

        # Decodificar la imagen
        frame_data = np.frombuffer(image_data, dtype=np.uint8)
        frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)

        # Mostrar la imagen
        if frame is not None:
            cv2.imshow('Video', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    client.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
