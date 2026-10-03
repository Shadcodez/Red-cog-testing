"""Connect Four rules and Cog-800. No Discord imports."""

from __future__ import annotations

import random
from typing import List, Optional, Sequence, Tuple

WIDTH = 7
HEIGHT = 6
EMPTY = 0
RED = 1
YELLOW = 2
OTHER = {RED: YELLOW, YELLOW: RED}
ORDER = (3, 2, 4, 1, 5, 0, 6)
DIRS = ((1, 0), (0, 1), (1, 1), (1, -1))
Cell = Tuple[int, int]
Grid = List[List[int]]


def new_board() -> Grid:
    return [[EMPTY for _ in range(HEIGHT)] for _ in range(WIDTH)]


def clone(board: Grid) -> Grid:
    return [col[:] for col in board]


def stack(board: Grid, col: int) -> int:
    return sum(1 for cell in board[col] if cell)


def open_cols(board: Grid) -> List[int]:
    return [col for col in ORDER if stack(board, col) < HEIGHT]


def drop(board: Grid, col: int, side: int) -> Optional[int]:
    row = stack(board, col)
    if row >= HEIGHT:
        return None
    board[col][row] = side
    return row


def winning_cells(board: Grid, col: int, row: int) -> List[Cell]:
    side = board[col][row]
    if not side:
        return []
    for dc, dr in DIRS:
        cells = [(col, row)]
        for sign in (1, -1):
            c, r = col, row
            while True:
                c += dc * sign
                r += dr * sign
                if not (0 <= c < WIDTH and 0 <= r < HEIGHT) or board[c][r] != side:
                    break
                cells.append((c, r))
        if len(cells) >= 4:
            return cells
    return []


def is_draw(board: Grid) -> bool:
    return not open_cols(board)


def windows(board: Grid) -> List[Sequence[int]]:
    found: List[Sequence[int]] = []
    for c in range(WIDTH):
        for r in range(HEIGHT - 3):
            found.append([board[c][r + i] for i in range(4)])
    for r in range(HEIGHT):
        for c in range(WIDTH - 3):
            found.append([board[c + i][r] for i in range(4)])
    for c in range(WIDTH - 3):
        for r in range(HEIGHT - 3):
            found.append([board[c + i][r + i] for i in range(4)])
        for r in range(3, HEIGHT):
            found.append([board[c + i][r - i] for i in range(4)])
    return found


def score_window(window: Sequence[int], side: int) -> int:
    opp = OTHER[side]
    mine = window.count(side)
    theirs = window.count(opp)
    empty = window.count(EMPTY)
    if mine and theirs:
        return 0
    if mine == 4:
        return 100000
    if mine == 3 and empty == 1:
        return 120
    if mine == 2 and empty == 2:
        return 18
    if theirs == 3 and empty == 1:
        return -900
    if theirs == 2 and empty == 2:
        return -16
    return 0


def evaluate(board: Grid, side: int) -> int:
    score = 0
    center = WIDTH // 2
    for col in range(WIDTH):
        weight = 3 - abs(col - center)
        score += weight * board[col].count(side) * 6
        score -= weight * board[col].count(OTHER[side]) * 6
    for window in windows(board):
        score += score_window(window, side)
    return score


def immediate(board: Grid, side: int) -> Optional[int]:
    for col in open_cols(board):
        trial = clone(board)
        row = drop(trial, col, side)
        if row is not None and winning_cells(trial, col, row):
            return col
    return None


def _search(board: Grid, depth: int, alpha: int, beta: int, side: int, root: int) -> int:
    win = immediate(board, side)
    if win is not None:
        return 100000 + depth
    lose = immediate(board, OTHER[side])
    if lose is not None and depth == 0:
        return -100000
    moves = open_cols(board)
    if not moves:
        return 0
    if depth == 0:
        return evaluate(board, side)
    best = -10**9
    for col in moves:
        row = drop(board, col, side)
        value = -_search(board, depth - 1, -beta, -alpha, OTHER[side], root)
        board[col][row] = EMPTY
        if value > best:
            best = value
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def choose(board: Grid, side: int, strength: str, rng: random.Random) -> int:
    moves = open_cols(board)
    if not moves:
        raise ValueError("no legal column")
    win = immediate(board, side)
    if win is not None and (strength != "easy" or rng.random() < 0.45):
        return win
    block = immediate(board, OTHER[side])
    if strength == "easy":
        return rng.choice(moves)
    if strength == "normal":
        if block is not None:
            return block
        ranked = []
        for col in moves:
            trial = clone(board)
            drop(trial, col, side)
            if immediate(trial, OTHER[side]) is not None and len(moves) > 1:
                ranked.append((evaluate(trial, side) - 400, col))
            else:
                ranked.append((evaluate(trial, side), col))
        ranked.sort(reverse=True)
        top = ranked[0][0]
        best = [col for score, col in ranked if score >= top - 8]
        return rng.choice(best)
    depth = 5
    if block is not None:
        # Still search, but a missed block is almost never best.
        pass
    best_score = -10**9
    best_cols = [moves[0]]
    for col in moves:
        row = drop(board, col, side)
        if winning_cells(board, col, row):
            board[col][row] = EMPTY
            return col
        value = -_search(board, depth - 1, -10**9, 10**9, OTHER[side], side)
        board[col][row] = EMPTY
        if value > best_score:
            best_score = value
            best_cols = [col]
        elif value == best_score:
            best_cols.append(col)
    return best_cols[0]
