import json
import socket
import threading
import random
from typing import Dict, List, Optional, Tuple

# --- Lógica del juego ---
from game import (
    create_board, clone_board, valid_columns,
    drop_piece, check_winner, is_full,
    print_board, ROWS, COLS, EMPTY, P1, P2
)

HOST = "0.0.0.0"
PORT = 65432

# ========== Utilidades de envío/recepción JSON ==========
def send_json(conn: socket.socket, payload: dict):
    try:
        line = json.dumps(payload, ensure_ascii=False)
        conn.sendall((line + "\n").encode("utf-8"))
    except Exception:
        pass

def recv_json_line(conn: socket.socket) -> Optional[dict]:
    buf = []
    while True:
        ch = conn.recv(1)
        if not ch:
            return None
        if ch == b'\n':
            break
        buf.append(ch)
    line = b''.join(buf).decode("utf-8").strip()
    if not line:
        return {}
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"type": "INVALID_JSON", "raw": line}

# ========== Sala ==========
class Room:
    def __init__(self, name: str):
        self.name = name
        self.board = create_board()
        self.players: Dict[str, Tuple[socket.socket, int]] = {}
        self.spectators: Dict[str, socket.socket] = {}
        self.turn: int = P1
        self.lock = threading.Lock()
        self.started = False
        self.ended = False
        self.winner: int = EMPTY
        self.vs_server = False  # IA ocupa P2
        self.order: List[str] = []  # orden de entrada de jugadores

    def broadcast(self, payload: dict, include_players=True, include_spectators=True):
        if include_players:
            for _, (c, _) in list(self.players.items()):
                send_json(c, payload)
        if include_spectators:
            for _, c in list(self.spectators.items()):
                send_json(c, payload)

    def board_payload(self) -> dict:
        return {
            "type": "BOARD",
            "board": self.board,
            "turn": self.turn,
            "players": {name: mark for name, (_, mark) in self.players.items()},
            "spectators": list(self.spectators.keys()),
            "room": self.name,
            "started": self.started,
            "ended": self.ended,
            "winner": self.winner
        }

# ========== Servidor principal ==========
class Connect4Server:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.rooms: Dict[str, Room] = {}
        self.clients: Dict[socket.socket, str] = {}  
        self.clients_lock = threading.Lock()

    # ---------- IA sencilla ----------
    def ai_choose_column(self, room: Room) -> int:
        """
        1) Si puede ganar en una jugada, hacerlo.
        2) Bloquear victoria inmediata del rival.
        3) Preferir centro, luego columnas cercanas al centro, si son válidas.
        4) Aleatorio de válidas como último recurso.
        """
        board = room.board
        valids = valid_columns(board)
        if not valids:
            return random.choice(range(COLS))

        for c in valids:
            b2 = clone_board(board)
            r = drop_piece(b2, c, P2)
            if r is not None and check_winner(b2, r, c) == P2:
                return c

        for c in valids:
            b2 = clone_board(board)
            r = drop_piece(b2, c, P1)
            if r is not None and check_winner(b2, r, c) == P1:
                return c

        prefs = sorted(valids, key=lambda x: abs(x - COLS//2))
        if prefs:
            return prefs[0]

        return random.choice(valids)

    # ---------- Gestión de salas ----------
    def get_or_create_room(self, name: str) -> Room:
        if name not in self.rooms:
            self.rooms[name] = Room(name)
        return self.rooms[name]

    # ---------- Hilo por cliente ----------
    def handle_client(self, conn: socket.socket, addr):
        username = None
        send_json(conn, {"type": "WELCOME", "msg": "Bienvenido a Conecta-4 Server (JSON por línea). Envia HELLO {name}."})

        current_room: Optional[Room] = None

        try:
            while True:
                msg = recv_json_line(conn)
                if msg is None:
                    break
                if not isinstance(msg, dict):
                    send_json(conn, {"type": "ERROR", "error": "Formato no válido"})
                    continue

                mtype = msg.get("type")

                # ---- HELLO ----
                if mtype == "HELLO":
                    requested = str(msg.get("name", "")).strip()
                    if not requested:
                        send_json(conn, {"type": "ERROR", "error": "Falta name"})
                        continue
                    with self.clients_lock:
                        if requested in self.clients.values():
                            send_json(conn, {"type": "ERROR", "error": "Nombre ya en uso"})
                            continue
                        self.clients[conn] = requested
                        username = requested
                    send_json(conn, {"type": "HELLO_OK", "name": username})
                    continue

                if username is None:
                    send_json(conn, {"type": "ERROR", "error": "Primero envía HELLO"})
                    continue

                if mtype == "LIST":
                    rooms_desc = []
                    for rn, r in self.rooms.items():
                        rooms_desc.append({
                            "room": rn,
                            "players": list(r.players.keys()),
                            "spectators": list(r.spectators.keys()),
                            "started": r.started,
                            "ended": r.ended,
                            "vs_server": r.vs_server
                        })
                    send_json(conn, {"type": "ROOMS", "rooms": rooms_desc})
                    continue

                if mtype == "CREATE":
                    rn = str(msg.get("room", "")).strip()
                    if not rn:
                        send_json(conn, {"type": "ERROR", "error": "Falta room"})
                        continue
                    room = self.get_or_create_room(rn)
                    with room.lock:
                        if username in room.players or username in room.spectators:
                            send_json(conn, {"type": "ERROR", "error": "Ya estás en esa sala"})
                            continue
                        if len(room.players) >= 2:
                            send_json(conn, {"type": "ERROR", "error": "Sala ya tiene 2 jugadores"})
                            continue
                        mark = P1 if P1 not in [m for _, m in room.players.values()] else P2
                        room.players[username] = (conn, mark)
                        room.order.append(username)
                        current_room = room
                        send_json(conn, {"type": "JOINED", "room": rn, "mark": mark})
                        room.broadcast({"type": "INFO", "msg": f"{username} se unió como jugador."})
                        room.broadcast(room.board_payload())
                    continue

                if mtype == "JOIN":
                    rn = str(msg.get("room", "")).strip()
                    if not rn:
                        send_json(conn, {"type": "ERROR", "error": "Falta room"})
                        continue
                    room = self.get_or_create_room(rn)
                    with room.lock:
                        if username in room.players or username in room.spectators:
                            send_json(conn, {"type": "ERROR", "error": "Ya estás en esa sala"})
                            continue
                        if len(room.players) >= 2 or room.vs_server and len(room.players) >= 1:
                            send_json(conn, {"type": "ERROR", "error": "No hay cupo de jugador"})
                            continue
                        mark = P1 if P1 not in [m for _, m in room.players.values()] else P2
                        room.players[username] = (conn, mark)
                        room.order.append(username)
                        current_room = room
                        send_json(conn, {"type": "JOINED", "room": rn, "mark": mark})
                        room.broadcast({"type": "INFO", "msg": f"{username} se unió como jugador."})
                        room.broadcast(room.board_payload())
                    continue


                if mtype == "SPECTATE":
                    rn = str(msg.get("room", "")).strip()
                    if not rn:
                        send_json(conn, {"type": "ERROR", "error": "Falta room"})
                        continue
                    room = self.get_or_create_room(rn)
                    with room.lock:
                        if username in room.players or username in room.spectators:
                            send_json(conn, {"type": "ERROR", "error": "Ya estás en esa sala"})
                            continue
                        room.spectators[username] = conn
                        current_room = room
                        send_json(conn, {"type": "SPECTATE_OK", "room": rn})
                        room.broadcast({"type": "INFO", "msg": f"{username} está como espectador."})
                        send_json(conn, room.board_payload())
                    continue

                # ---- START (cuando haya 2 jugadores) ----
                if mtype == "START":
                    if current_room is None:
                        send_json(conn, {"type": "ERROR", "error": "No estás en ninguna sala"})
                        continue
                    room = current_room
                    with room.lock:
                        if room.started:
                            send_json(conn, {"type": "ERROR", "error": "La partida ya empezó"})
                            continue
                        if room.vs_server:
                            if len(room.players) < 1:
                                send_json(conn, {"type": "ERROR", "error": "Falta jugador humano"})
                                continue
                        else:
                            if len(room.players) < 2:
                                send_json(conn, {"type": "ERROR", "error": "Se requieren 2 jugadores"})
                                continue
                        room.started = True
                        room.turn = P1
                        room.broadcast({"type": "STARTED", "room": room.name, "turn": room.turn})
                        room.broadcast(room.board_payload())
                        self.maybe_ai_move(room)
                    continue

                if mtype == "START_VS_SERVER":
                    rn = str(msg.get("room", "")).strip()
                    if not rn:
                        send_json(conn, {"type": "ERROR", "error": "Falta room"})
                        continue
                    room = self.get_or_create_room(rn)
                    with room.lock:
                        if room.started:
                            send_json(conn, {"type": "ERROR", "error": "La partida ya empezó"})
                            continue
                        if len(room.players) >= 2 or room.vs_server:
                            send_json(conn, {"type": "ERROR", "error": "Sala ocupada"})
                            continue
                        # unir a este usuario como jugador
                        if username not in room.players:
                            mark = P1
                            room.players[username] = (conn, mark)
                            room.order.append(username)
                        room.vs_server = True
                        room.started = True
                        room.turn = P1
                        room.broadcast({"type": "STARTED", "room": room.name, "turn": room.turn, "vs_server": True})
                        room.broadcast(room.board_payload())
                        self.maybe_ai_move(room)
                    current_room = room
                    continue

                if mtype == "RESET":
                    if current_room is None:
                        send_json(conn, {"type": "ERROR", "error": "No estás en ninguna sala"})
                        continue
                    room = current_room
                    with room.lock:
                        room.board = create_board()
                        room.started = False
                        room.ended = False
                        room.winner = EMPTY
                        room.turn = P1
                        room.broadcast({"type": "RESET_OK", "by": username})
                        room.broadcast(room.board_payload())
                    continue

                # ---- MOVE (jugada) ----
                if mtype == "MOVE":
                    col = msg.get("col")
                    if current_room is None:
                        send_json(conn, {"type": "ERROR", "error": "No estás en ninguna sala"})
                        continue
                    room = current_room
                    with room.lock:
                        if room.ended or not room.started:
                            send_json(conn, {"type": "ERROR", "error": "Partida no iniciada o ya finalizada"})
                            continue
                        if username not in room.players:
                            send_json(conn, {"type": "ERROR", "error": "Eres espectador. No puedes jugar"})
                            continue

                        _, my_mark = room.players[username]
                        if my_mark != room.turn:
                            send_json(conn, {"type": "ERROR", "error": "No es tu turno"})
                            continue

                        try:
                            col = int(col)
                        except (TypeError, ValueError):
                            send_json(conn, {"type": "ERROR", "error": "Columna inválida"})
                            continue
                        if col not in range(COLS) or col not in valid_columns(room.board):
                            send_json(conn, {"type": "ERROR", "error": "Movimiento no válido"})
                            continue

                        # realizar movimiento
                        r = drop_piece(room.board, col, my_mark)
                        assert r is not None
                        win = check_winner(room.board, r, col)
                        if win != EMPTY:
                            room.ended = True
                            room.winner = win
                            room.broadcast({"type": "MOVE_OK", "by": username, "col": col})
                            room.broadcast(room.board_payload())
                            room.broadcast({"type": "GAME_OVER", "winner": win, "by": username})
                            continue

                        if is_full(room.board):
                            room.ended = True
                            room.winner = EMPTY
                            room.broadcast({"type": "MOVE_OK", "by": username, "col": col})
                            room.broadcast(room.board_payload())
                            room.broadcast({"type": "GAME_OVER", "winner": 0})
                            continue

                        room.turn = P1 if room.turn == P2 else P2
                        room.broadcast({"type": "MOVE_OK", "by": username, "col": col, "next": room.turn})
                        room.broadcast(room.board_payload())

                    self.maybe_ai_move(room)
                    continue

                if mtype == "QUIT":
                    send_json(conn, {"type": "BYE"})
                    break

                send_json(conn, {"type": "ERROR", "error": f"Tipo desconocido: {mtype}"})

        except Exception as e:
            pass
        finally:
            with self.clients_lock:
                if conn in self.clients:
                    username = self.clients.pop(conn)
            if username:
                for r in self.rooms.values():
                    with r.lock:
                        if username in r.players:
                            del r.players[username]
                            r.broadcast({"type": "INFO", "msg": f"{username} salió."})
                        if username in r.spectators:
                            del r.spectators[username]
                            r.broadcast({"type": "INFO", "msg": f"{username} dejó de espectar."})
                        r.broadcast(r.board_payload())
            try:
                conn.close()
            except Exception:
                pass

    def maybe_ai_move(self, room: Room):
        """
        Si la sala es vs servidor y el turno es de P2, la IA juega.
        """
        if not room.vs_server:
            return
        with room.lock:
            if room.ended or not room.started:
                return
            if room.turn != P2:
                return
            col = self.ai_choose_column(room)
            r = drop_piece(room.board, col, P2)
            if r is None:
                # si por alguna razón no pudo (col llena), intentar otra
                valids = valid_columns(room.board)
                if not valids:
                    room.ended = True
                    room.winner = EMPTY
                    room.broadcast({"type": "GAME_OVER", "winner": 0})
                    return
                col = random.choice(valids)
                r = drop_piece(room.board, col, P2)

            win = check_winner(room.board, r, col)
            if win != EMPTY:
                room.ended = True
                room.winner = win
                room.broadcast({"type": "MOVE_OK", "by": "SERVER_AI", "col": col})
                room.broadcast(room.board_payload())
                room.broadcast({"type": "GAME_OVER", "winner": win, "by": "SERVER_AI"})
                return

            if is_full(room.board):
                room.ended = True
                room.winner = EMPTY
                room.broadcast({"type": "MOVE_OK", "by": "SERVER_AI", "col": col})
                room.broadcast(room.board_payload())
                room.broadcast({"type": "GAME_OVER", "winner": 0})
                return

            room.turn = P1
            room.broadcast({"type": "MOVE_OK", "by": "SERVER_AI", "col": col, "next": room.turn})
            room.broadcast(room.board_payload())

    # ---------- Aceptador ----------
    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()
            print(f"Servidor Conecta-4 escuchando en {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                t.start()


if __name__ == "__main__":
    Connect4Server(HOST, PORT).serve_forever()
