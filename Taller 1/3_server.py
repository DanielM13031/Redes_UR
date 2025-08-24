import socket
import threading
import cv2
import numpy as np
import time

current_frame = None  # variable compartida
video_finished = False  # bandera de fin de video

def handle_client(client_socket, videoCapture, frame_interval):
    global current_frame, video_finished
    while True:
        try:
            ret, frame = videoCapture.read()
            if not ret:
                print("Video terminado.")
                video_finished = True
                break

            # Guardar frame para mostrar en el servidor
            current_frame = frame.copy()

            _, buffer = cv2.imencode('.jpg', frame)
            data = buffer.tobytes()
            
            # Enviar tamaño + frame
            client_socket.sendall(len(data).to_bytes(4, byteorder='big'))
            client_socket.sendall(data)

            # Respetar FPS
            time.sleep(frame_interval)

        except Exception as e:
            print(f"Client Disconnected: {e}")
            client_socket.close()
            break

def show():
    global current_frame, video_finished
    while True:
        if video_finished:
            break  # salimos cuando acaba el video

        if current_frame is not None:
            cv2.imshow('Frame', current_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cv2.destroyAllWindows()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('0.0.0.0', 5000))
    server.listen(5)
    print("Server started, waiting for connection...")

    videoCapture = cv2.VideoCapture("zapato.mp4")
    
    # Calcular FPS
    fps = videoCapture.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 25
    frame_interval = 1.0 / fps

    # Lanzar hilo que solo muestra, no lee video
    show_camera = threading.Thread(target=show)
    show_camera.start()

    while True:
        if video_finished:
            print("Cerrando servidor: video terminado.")
            break

        client_socket, addr = server.accept()
        print(f"Connection from {addr} has been established!")
        client_handler = threading.Thread(target=handle_client, args=(client_socket, videoCapture, frame_interval))
        client_handler.start()

    server.close()

if __name__ == '__main__':
    main()
