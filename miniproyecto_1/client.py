#Cliente para enviar mensajes al servidor
import json
import socket
import threading
import sys
from typing import Optional, Dict, Any, List

HOST = "127.0.0.1"
PORT = 65432

def print_board_ascii(board: List[List[int]]):
    symbols = {0:'.', 1:'X', 2:'O'}
    for row in board:
        print(' '.join(symbols.get(cell, '?') for cell in row))
    print(' '.join(str(c) for c in range(len(board[0]))))
    print()

def send_json(conn: socket.socket, payload: dict):
    line = json.dumps(payload, ensure_ascii=False)
    conn.sendall((line + "\n").encode("utf-8"))

def receiver_loop(conn: socket.socket):
    buf = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                print("Conexión cerrada por el servidor.")
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    print("<< Mensaje no-JSON:", line.decode("utf-8"))
                    continue
                handle_server_message(msg)
    except Exception as e:
        print("Error de recepción:", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass

def handle_server_message(msg: Dict[str, Any]):
    t = msg.get("type")

    if t == "WELCOME":
        print(msg.get("msg", ""))
    elif t == "ERROR":
        print(f"[ERROR] {msg.get('error')}")
    elif t == "HELLO_OK":
        print(f"Conectado como: {msg.get('name')}")
    elif t == "ROOMS":
        print("Salas:")
        for r in msg.get("rooms", []):
            print(f"  - {r['room']} | players={r['players']} | spectators={r['spectators']} | started={r['started']} | ended={r['ended']} | vs_server={r['vs_server']}")
    elif t == "JOINED":
        print(f"Unido a sala {msg.get('room')} como jugador (mark={msg.get('mark')}).")
    elif t == "SPECTATE_OK":
        print(f"Espectando sala {msg.get('room')}.")
    elif t == "INFO":
        print(f"[INFO] {msg.get('msg')}")
    elif t == "STARTED":
        print(f"Partida iniciada en sala={msg.get('room')} turn={msg.get('turn')} vs_server={msg.get('vs_server', False)}")
    elif t == "RESET_OK":
        print(f"Partida reiniciada por ={msg.get('by')}.")
    elif t == "MOVE_OK":
        by = msg.get("by")
        col = msg.get("col")
        nxt = msg.get("next")
        if by:
            print(f"Movimiento de {by} en columna {col}. Siguiente turno: {nxt}")
    elif t == "BOARD":
        print("\n=== TABLERO ===")
        print(f"Sala: {msg.get('room')} | Turno: {msg.get('turn')} | Jugadores: {msg.get('players')}")
        board = msg.get("board")
        if board:
            print_board_ascii(board)
        if msg.get("ended"):
            w = msg.get("winner")
            if w == 0:
                print(">>> EMPATE")
            else:
                inv = {1:"P1 (X)", 2:"P2 (O)"}
                print(f">>> GANADOR: {inv.get(w, w)}")
    elif t == "GAME_OVER":
        w = msg.get("winner")
        if w == 0:
            print("Juego terminado: EMPATE.")
        else:
            inv = {1:"P1 (X)", 2:"P2 (O)"}
            print(f"Juego terminado. Ganador: {inv.get(w, w)} (by={msg.get('by')})")
    elif t == "BYE":
        print("Servidor: BYE")
        sys.exit(0)
    else:
        print("<<", msg)

def help_text():
    print("""
Comandos (escribe y presiona Enter):
  /hello <nombre>                  -> identifica tu usuario
  /list                            -> lista salas
  /create <sala>                   -> crea sala (te une como jugador)
  /join <sala>                     -> unirse como jugador
  /spectate <sala>                 -> entrar como espectador
  /start                           -> iniciar partida (2 jugadores o vs IA)
  /start_vs <sala>                 -> crea/inicia sala vs servidor (IA es P2)
  /reset                           -> reinicia la partida actual
  /move <col>                      -> jugar en columna (0-6)
  /quit                            -> salir
  /help                            -> ver ayuda
""")

def main():
    host = HOST
    port = PORT
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    print(f"Conectando a {host}:{port} ...")
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.connect((host, port))
    threading.Thread(target=receiver_loop, args=(conn,), daemon=True).start()
    help_text()

    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith("/hello "):
                name = line.split(" ", 1)[1].strip()
                send_json(conn, {"type": "HELLO", "name": name})

            elif line == "/list":
                send_json(conn, {"type": "LIST"})

            elif line.startswith("/create "):
                sala = line.split(" ", 1)[1].strip()
                send_json(conn, {"type": "CREATE", "room": sala})

            elif line.startswith("/join "):
                sala = line.split(" ", 1)[1].strip()
                send_json(conn, {"type": "JOIN", "room": sala})

            elif line.startswith("/spectate "):
                sala = line.split(" ", 1)[1].strip()
                send_json(conn, {"type": "SPECTATE", "room": sala})

            elif line == "/start":
                send_json(conn, {"type": "START"})

            elif line.startswith("/start_vs "):
                sala = line.split(" ", 1)[1].strip()
                send_json(conn, {"type": "START_VS_SERVER", "room": sala})

            elif line == "/reset":
                send_json(conn, {"type": "RESET"})

            elif line.startswith("/move "):
                try:
                    col = int(line.split(" ", 1)[1].strip())
                except Exception:
                    print("Columna inválida.")
                    continue
                send_json(conn, {"type": "MOVE", "col": col})

            elif line == "/quit":
                send_json(conn, {"type": "QUIT"})
                break

            elif line == "/help":
                help_text()

            else:
                print("Comando no reconocido. Usa /help")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
