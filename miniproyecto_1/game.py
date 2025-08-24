#Estructura del juego Conecta4
from typing import List, Optional

ROWS, COLS = 6, 7
EMPTY, P1, P2 = 0, 1, 2

def create_board() -> List[List[int]]:
    """Crea un tablero vacío"""
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]

def clone_board(board: List[List[int]]) -> List[List[int]]:
    """Crea una copia del tablero"""
    return [row[:] for row in board]

def valid_columns(board: List[List[int]]) -> List[int]:
    """Devuelve las columnas donde se puede jugar"""
    return [c for c in range(COLS) if board[0][c] == EMPTY]

def drop_piece(board: List[List[int]], col: int, piece: int) -> Optional[int]:
    """Deja caer una ficha en la columna indicada. Devuelve la fila donde cayó o None si no se pudo."""
    for r in range(ROWS-1, -1, -1):
        if board[r][col] == EMPTY:
            board[r][col] = piece
            return r
    return None

def _count(board, r, c, dr, dc, mark) -> int:
    cnt = 0
    rr, cc = r, c
    while 0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == mark:
        cnt += 1
        rr += dr; cc += dc
    return cnt

def check_winner(board: List[List[int]], r: int, c: int) -> int:
    """Comprueba si hay un ganador tras la última jugada en (r, c). Devuelve EMPTY, P1 o P2."""
    mark = board[r][c]
    if mark == EMPTY:
        return EMPTY

    directions = [(1, 0), (0, 1), (1, 1), (1, -1)]  # vertical, horizontal, diagonal /
    for dr, dc in directions:
        count = _count(board, r, c, dr, dc, mark) + _count(board, r, c, -dr, -dc, mark) - 1
        if count >= 4:
            return mark
    return EMPTY

def is_full(board: List[List[int]]) -> bool:
    """Comprueba si el tablero está lleno"""
    return all(board[0][c] != EMPTY for c in range(COLS))

def print_board(board: List[List[int]]) -> None:
    """Imprime el tablero en la consola"""
    symbols = {EMPTY: '.', P1: 'X', P2: 'O'}
    for row in board:
        print(' '.join(symbols[cell] for cell in row))
    print(' '.join(str(c) for c in range(COLS)))
    print()

