# Chessmaster
# Author: SHADOW

"""Channel chess for Red. Text board by default, optional image board."""

from __future__ import annotations

import asyncio
import io
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

WHITE, BLACK = 0, 1
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
EMPTY = 0
WK, WQ, BK, BQ = 1, 2, 4, 8
FILES = "abcdefgh"
RANKS = "12345678"
VALUES = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 0}
UNICODE = {
    (WHITE, PAWN): "♙", (WHITE, KNIGHT): "♘", (WHITE, BISHOP): "♗",
    (WHITE, ROOK): "♖", (WHITE, QUEEN): "♕", (WHITE, KING): "♔",
    (BLACK, PAWN): "♟", (BLACK, KNIGHT): "♞", (BLACK, BISHOP): "♝",
    (BLACK, ROOK): "♜", (BLACK, QUEEN): "♛", (BLACK, KING): "♚",
}
PST = {
    PAWN: [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, -20, -20, 10, 10, 5, 5, -5, -10, 0, 0, -10, -5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10, 50, 50, 50, 50, 50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0],
    KNIGHT: [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 5, 5, 0, -20, -40, -30, 5, 10, 15, 15, 10, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 10, 15, 15, 10, 0, -30, -40, -20, 0, 0, 0, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
    BISHOP: [-20, -10, -10, -10, -10, -10, -10, -20, -10, 5, 0, 0, 0, 0, 5, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 5, 10, 10, 5, 0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -10, -10, -10, -10, -20],
    ROOK: [0, 0, 0, 5, 5, 0, 0, 0, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
    QUEEN: [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 5, 0, 0, 0, 0, -10, -10, 5, 5, 5, 5, 5, 0, -10, 0, 0, 5, 5, 5, 5, 0, -5, -5, 0, 5, 5, 5, 5, 0, -5, -10, 0, 5, 5, 5, 5, 0, -10, -10, 0, 0, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
    KING: [20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20, -10, -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30],
}
KING_END = [-50, -30, -30, -30, -30, -30, -30, -50, -30, -30, 0, 0, 0, 0, -30, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -20, -10, 0, 0, -10, -20, -30, -50, -40, -30, -20, -20, -30, -40, -50]
CASTLE_ROOK_FROM = {WK: 7, WQ: 0, BK: 63, BQ: 56}
CASTLE_ROOK_TO = {WK: 5, WQ: 3, BK: 61, BQ: 59}
CASTLE_KING_TO = {WK: 6, WQ: 2, BK: 62, BQ: 58}
CASTLE_PATH = {WK: (5, 6), WQ: (1, 2, 3), BK: (61, 62), BQ: (57, 58, 59)}
CASTLE_SAFE = {WK: (4, 5, 6), WQ: (4, 3, 2), BK: (60, 61, 62), BQ: (60, 59, 58)}
STRENGTHS = {"casual": (0.6, 3), "club": (1.4, 4), "strong": (3.0, 5)}
IDLE_SECONDS = 45 * 60
RED = 0xE74C3C


def pack(color: int, kind: int) -> int:
    return (color << 3) | kind


def color_of(piece: int) -> int:
    return piece >> 3


def kind_of(piece: int) -> int:
    return piece & 7


def sq_name(sq: int) -> str:
    return FILES[sq & 7] + RANKS[sq >> 3]


@dataclass(slots=True)
class Move:
    frm: int
    to: int
    promo: int = 0
    castle: int = 0
    ep: bool = False

    def uci(self) -> str:
        suffix = "nbrq"[self.promo - KNIGHT] if self.promo else ""
        return sq_name(self.frm) + sq_name(self.to) + suffix


@dataclass
class Undo:
    captured: int
    castling: int
    ep: int
    halfmove: int
    moved: int
    rook_from: int = -1
    rook_to: int = -1
    rook_piece: int = 0


class Board:
    def __init__(self) -> None:
        self.sq = [EMPTY] * 64
        self.side = WHITE
        self.castling = WK | WQ | BK | BQ
        self.ep = -1
        self.halfmove = 0
        self.fullmove = 1
        self.king = [4, 60]
        self.set_start()

    def set_start(self) -> None:
        back = [ROOK, KNIGHT, BISHOP, QUEEN, KING, BISHOP, KNIGHT, ROOK]
        self.sq = [EMPTY] * 64
        for f, kind in enumerate(back):
            self.sq[f] = pack(WHITE, kind)
            self.sq[56 + f] = pack(BLACK, kind)
            self.sq[8 + f] = pack(WHITE, PAWN)
            self.sq[48 + f] = pack(BLACK, PAWN)
        self.side = WHITE
        self.castling = WK | WQ | BK | BQ
        self.ep = -1
        self.halfmove = 0
        self.fullmove = 1
        self.king = [4, 60]

    def key(self) -> tuple:
        return (tuple(self.sq), self.side, self.castling, self.ep)

    def make(self, move: Move) -> Undo:
        piece = self.sq[move.frm]
        undo = Undo(self.sq[move.to], self.castling, self.ep, self.halfmove, piece)
        kind = kind_of(piece)
        color = color_of(piece)
        self.sq[move.frm] = EMPTY
        self.halfmove = 0 if kind == PAWN or undo.captured else self.halfmove + 1
        self.ep = -1
        if move.ep:
            cap_sq = move.to - 8 if color == WHITE else move.to + 8
            undo.captured = self.sq[cap_sq]
            undo.rook_from = cap_sq
            self.sq[cap_sq] = EMPTY
        if move.castle:
            undo.rook_from = CASTLE_ROOK_FROM[move.castle]
            undo.rook_to = CASTLE_ROOK_TO[move.castle]
            undo.rook_piece = self.sq[undo.rook_from]
            self.sq[undo.rook_from] = EMPTY
            self.sq[undo.rook_to] = undo.rook_piece
        self.sq[move.to] = pack(color, move.promo) if move.promo else piece
        if kind == KING:
            self.king[color] = move.to
            self.castling &= ~(WK | WQ) if color == WHITE else ~(BK | BQ)
        if kind == PAWN and abs(move.to - move.frm) == 16:
            self.ep = (move.frm + move.to) // 2
        for sq, bit in ((0, WQ), (7, WK), (56, BQ), (63, BK)):
            if move.frm == sq or move.to == sq:
                self.castling &= ~bit
        if self.side == BLACK:
            self.fullmove += 1
        self.side ^= 1
        return undo

    def unmake(self, move: Move, undo: Undo) -> None:
        if self.side == WHITE:
            self.fullmove -= 1
        self.side ^= 1
        self.sq[move.frm] = undo.moved
        self.sq[move.to] = EMPTY if move.ep else undo.captured
        if move.ep:
            self.sq[undo.rook_from] = undo.captured
        if move.castle:
            self.sq[undo.rook_to] = EMPTY
            self.sq[undo.rook_from] = undo.rook_piece
        if kind_of(undo.moved) == KING:
            self.king[self.side] = move.frm
        self.castling = undo.castling
        self.ep = undo.ep
        self.halfmove = undo.halfmove

    def attacked(self, sq: int, by: int) -> bool:
        board = self.sq
        direction = -1 if by == WHITE else 1
        for df in (-1, 1):
            f, r = (sq & 7) + df, (sq >> 3) + direction
            if 0 <= f < 8 and 0 <= r < 8:
                piece = board[r * 8 + f]
                if piece and color_of(piece) == by and kind_of(piece) == PAWN:
                    return True
        kf, kr = sq & 7, sq >> 3
        for df, dr in ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)):
            f, r = kf + df, kr + dr
            if 0 <= f < 8 and 0 <= r < 8:
                piece = board[r * 8 + f]
                if piece and color_of(piece) == by and kind_of(piece) == KNIGHT:
                    return True
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if df == dr == 0:
                    continue
                f, r = kf + df, kr + dr
                if 0 <= f < 8 and 0 <= r < 8:
                    piece = board[r * 8 + f]
                    if piece and color_of(piece) == by and kind_of(piece) == KING:
                        return True
        for df, dr, sliders in (
            (-1, -1, (BISHOP, QUEEN)), (-1, 1, (BISHOP, QUEEN)),
            (1, -1, (BISHOP, QUEEN)), (1, 1, (BISHOP, QUEEN)),
            (-1, 0, (ROOK, QUEEN)), (1, 0, (ROOK, QUEEN)),
            (0, -1, (ROOK, QUEEN)), (0, 1, (ROOK, QUEEN)),
        ):
            f, r = kf + df, kr + dr
            while 0 <= f < 8 and 0 <= r < 8:
                piece = board[r * 8 + f]
                if piece:
                    if color_of(piece) == by and kind_of(piece) in sliders:
                        return True
                    break
                f += df
                r += dr
        return False

    def in_check(self, color: Optional[int] = None) -> bool:
        color = self.side if color is None else color
        return self.attacked(self.king[color], color ^ 1)

    def pseudo(self) -> list[Move]:
        moves: list[Move] = []
        side = self.side
        board = self.sq
        fwd = 8 if side == WHITE else -8
        start_rank = 1 if side == WHITE else 6
        promo_rank = 7 if side == WHITE else 0
        for sq, piece in enumerate(board):
            if not piece or color_of(piece) != side:
                continue
            kind = kind_of(piece)
            f, r = sq & 7, sq >> 3
            if kind == PAWN:
                one = sq + fwd
                if board[one] == EMPTY:
                    if (one >> 3) == promo_rank:
                        moves.extend(Move(sq, one, promo) for promo in (QUEEN, ROOK, BISHOP, KNIGHT))
                    else:
                        moves.append(Move(sq, one))
                        if r == start_rank and board[sq + 2 * fwd] == EMPTY:
                            moves.append(Move(sq, sq + 2 * fwd))
                for df in (-1, 1):
                    if not 0 <= f + df < 8:
                        continue
                    to = one + df
                    target = board[to]
                    if target and color_of(target) != side:
                        if (to >> 3) == promo_rank:
                            moves.extend(Move(sq, to, promo) for promo in (QUEEN, ROOK, BISHOP, KNIGHT))
                        else:
                            moves.append(Move(sq, to))
                    elif to == self.ep:
                        moves.append(Move(sq, to, ep=True))
            elif kind == KNIGHT:
                for df, dr in ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)):
                    tf, tr = f + df, r + dr
                    if 0 <= tf < 8 and 0 <= tr < 8:
                        to = tr * 8 + tf
                        if not board[to] or color_of(board[to]) != side:
                            moves.append(Move(sq, to))
            elif kind == KING:
                for df in (-1, 0, 1):
                    for dr in (-1, 0, 1):
                        if df == dr == 0:
                            continue
                        tf, tr = f + df, r + dr
                        if 0 <= tf < 8 and 0 <= tr < 8:
                            to = tr * 8 + tf
                            if not board[to] or color_of(board[to]) != side:
                                moves.append(Move(sq, to))
                for bit in ((WK, WQ) if side == WHITE else (BK, BQ)):
                    if self.castling & bit and not any(board[s] for s in CASTLE_PATH[bit]):
                        if not any(self.attacked(s, side ^ 1) for s in CASTLE_SAFE[bit]):
                            moves.append(Move(sq, CASTLE_KING_TO[bit], castle=bit))
            else:
                deltas = []
                if kind in (BISHOP, QUEEN):
                    deltas += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
                if kind in (ROOK, QUEEN):
                    deltas += [(-1, 0), (1, 0), (0, -1), (0, 1)]
                for df, dr in deltas:
                    tf, tr = f + df, r + dr
                    while 0 <= tf < 8 and 0 <= tr < 8:
                        to = tr * 8 + tf
                        if not board[to]:
                            moves.append(Move(sq, to))
                        else:
                            if color_of(board[to]) != side:
                                moves.append(Move(sq, to))
                            break
                        tf += df
                        tr += dr
        return moves

    def legal(self) -> list[Move]:
        side = self.side
        out = []
        for move in self.pseudo():
            undo = self.make(move)
            if not self.attacked(self.king[side], side ^ 1):
                out.append(move)
            self.unmake(move, undo)
        return out

    def insufficient(self) -> bool:
        minors = 0
        for piece in self.sq:
            if not piece:
                continue
            kind = kind_of(piece)
            if kind in (PAWN, ROOK, QUEEN):
                return False
            if kind in (KNIGHT, BISHOP):
                minors += 1
        return minors <= 1

    def pretty(self, flip: bool = False, last: Optional[Move] = None) -> str:
        marks = {last.frm, last.to} if last else set()
        ranks = range(8) if flip else range(7, -1, -1)
        files = range(7, -1, -1) if flip else range(8)
        lines = ["  " + " ".join(FILES[i] for i in files)]
        for rank in ranks:
            cells = []
            for file in files:
                sq = rank * 8 + file
                piece = self.sq[sq]
                cells.append(UNICODE[(color_of(piece), kind_of(piece))] if piece else ("•" if sq in marks else "·"))
            lines.append(RANKS[rank] + " " + " ".join(cells))
        lines.append("  " + " ".join(FILES[i] for i in files))
        return "```\n" + "\n".join(lines) + "\n```"

    def san(self, move: Move, siblings: Optional[list] = None) -> str:
        if move.castle in (WK, BK):
            text = "O-O"
        elif move.castle in (WQ, BQ):
            text = "O-O-O"
        else:
            kind = kind_of(self.sq[move.frm])
            capture = bool(self.sq[move.to]) or move.ep
            dest = sq_name(move.to)
            if kind == PAWN:
                text = (sq_name(move.frm)[0] + "x" + dest) if capture else dest
            else:
                pool = siblings if siblings is not None else self.legal()
                ambiguous = [m for m in pool if m.to == move.to and m.frm != move.frm and kind_of(self.sq[m.frm]) == kind and m.promo == move.promo]
                dis = ""
                if ambiguous:
                    if not any((m.frm & 7) == (move.frm & 7) for m in ambiguous):
                        dis = sq_name(move.frm)[0]
                    elif not any((m.frm >> 3) == (move.frm >> 3) for m in ambiguous):
                        dis = sq_name(move.frm)[1]
                    else:
                        dis = sq_name(move.frm)
                text = "NBRQK"[kind - KNIGHT] + dis + ("x" if capture else "") + dest
            if move.promo:
                text += "=" + "NBRQ"[move.promo - KNIGHT]
        undo = self.make(move)
        if self.attacked(self.king[self.side], self.side ^ 1):
            text += "#" if not self.legal() else "+"
        self.unmake(move, undo)
        return text


class Engine:
    def __init__(self, think_s: float = 1.4, max_depth: int = 4) -> None:
        self.think_s = think_s
        self.max_depth = max_depth
        self.nodes = 0
        self.deadline = 0.0
        self.best: Optional[Move] = None
        self.killers: list[list[Optional[Move]]] = []

    def search(self, board: Board) -> tuple[Move, int, int]:
        self.nodes = 0
        self.deadline = time.monotonic() + self.think_s
        self.killers = [[None, None] for _ in range(self.max_depth + 6)]
        moves = board.legal()
        if not moves:
            raise RuntimeError("no legal moves")
        self.best = moves[0]
        depth_reached = 1
        if len(moves) == 1:
            return moves[0], 0, 1
        try:
            for depth in range(1, self.max_depth + 1):
                self._negamax(board, depth, -30000, 30000, 0)
                depth_reached = depth
                if time.monotonic() > self.deadline:
                    break
        except TimeoutError:
            pass
        return self.best, 0, depth_reached

    def _timed_out(self) -> bool:
        return self.nodes % 64 == 0 and time.monotonic() > self.deadline

    def _negamax(self, board: Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if ply and self._timed_out():
            raise TimeoutError
        in_check = board.in_check()
        if in_check:
            depth += 1
        if depth <= 0:
            return self._quiesce(board, alpha, beta, ply)
        moves = board.legal()
        if not moves:
            return -29000 + ply if in_check else 0
        moves.sort(key=lambda m: self._score_move(board, m, ply), reverse=True)
        for move in moves:
            undo = board.make(move)
            score = -self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.unmake(move, undo)
            if score > alpha:
                alpha = score
                if ply == 0:
                    self.best = move
                if score >= beta:
                    return beta
        return alpha

    def _quiesce(self, board: Board, alpha: int, beta: int, ply: int) -> int:
        stand = self.evaluate(board) * (1 if board.side == WHITE else -1)
        if stand >= beta:
            return beta
        if stand > alpha:
            alpha = stand
        if ply > 8:
            return alpha
        for move in board.legal():
            if not board.sq[move.to] and not move.ep and not move.promo:
                continue
            undo = board.make(move)
            score = -self._quiesce(board, -beta, -alpha, ply + 1)
            board.unmake(move, undo)
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _score_move(self, board: Board, move: Move, ply: int) -> int:
        score = 0
        victim = board.sq[move.to]
        if victim:
            score += 10 * VALUES[kind_of(victim)] - VALUES[kind_of(board.sq[move.frm])]
        if move.promo:
            score += VALUES[move.promo]
        return score

    def evaluate(self, board: Board) -> int:
        endgame = not any(p and kind_of(p) == QUEEN for p in board.sq)
        score = 0
        for sq, piece in enumerate(board.sq):
            if not piece:
                continue
            kind = kind_of(piece)
            table = KING_END if kind == KING and endgame else PST[kind]
            mirrored = sq if color_of(piece) == WHITE else sq ^ 56
            delta = VALUES[kind] + table[mirrored]
            score += delta if color_of(piece) == WHITE else -delta
        return score


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_board(board: Board, flip: bool = False, last: Optional[Move] = None) -> io.BytesIO:
    """Draw a board. No network, no piece font required."""
    size, margin = 64, 28
    img = Image.new("RGB", (margin + size * 8 + 12, size * 8 + margin + 24), "#1C1C1E")
    draw = ImageDraw.Draw(img)
    font = _font(16)
    marks = {last.frm, last.to} if last else set()
    check_sq = board.king[board.side] if board.in_check() else -1
    ranks = range(8) if flip else range(7, -1, -1)
    files = range(7, -1, -1) if flip else range(8)
    for display_r, rank in enumerate(ranks):
        for display_f, file in enumerate(files):
            sq = rank * 8 + file
            x, y = margin + display_f * size, 8 + display_r * size
            dark = (file + rank) % 2 == 0
            color = "#B58863" if dark else "#F0D9B5"
            if sq in marks:
                color = "#C9A227" if dark else "#F6E58D"
            if sq == check_sq:
                color = "#C0392B"
            draw.rectangle((x, y, x + size - 1, y + size - 1), fill=color)
            piece = board.sq[sq]
            if piece:
                _piece(draw, x, y, size, color_of(piece), kind_of(piece))
        draw.text((8, 8 + display_r * size + 22), RANKS[rank], fill="#E74C3C", font=font)
    for display_f, file in enumerate(files):
        draw.text((margin + display_f * size + 26, 8 + size * 8 + 2), FILES[file], fill="#E74C3C", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _piece(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, color: int, kind: int) -> None:
    fill = "#F7F4EF" if color == WHITE else "#2B2B2B"
    edge = "#2B2B2B" if color == WHITE else "#F7F4EF"
    cx, cy = x + size // 2, y + size // 2 + 2
    if kind == PAWN:
        draw.ellipse((cx - 10, cy - 16, cx + 10, cy + 4), fill=fill, outline=edge)
        draw.ellipse((cx - 16, cy + 6, cx + 16, cy + 18), fill=fill, outline=edge)
    elif kind == ROOK:
        draw.rectangle((cx - 14, cy - 16, cx + 14, cy + 16), fill=fill, outline=edge)
        draw.rectangle((cx - 16, cy - 20, cx - 6, cy - 12), fill=fill, outline=edge)
        draw.rectangle((cx - 4, cy - 20, cx + 4, cy - 12), fill=fill, outline=edge)
        draw.rectangle((cx + 6, cy - 20, cx + 16, cy - 12), fill=fill, outline=edge)
    elif kind == KNIGHT:
        draw.polygon([(cx - 14, cy + 16), (cx - 8, cy - 8), (cx + 2, cy - 18), (cx + 14, cy - 4), (cx + 6, cy + 16)], fill=fill, outline=edge)
    elif kind == BISHOP:
        draw.polygon([(cx, cy - 20), (cx - 12, cy + 6), (cx + 12, cy + 6)], fill=fill, outline=edge)
        draw.ellipse((cx - 14, cy + 4, cx + 14, cy + 18), fill=fill, outline=edge)
    elif kind == QUEEN:
        draw.polygon([(cx - 16, cy + 14), (cx - 14, cy - 8), (cx - 6, cy + 2), (cx, cy - 18), (cx + 6, cy + 2), (cx + 14, cy - 8), (cx + 16, cy + 14)], fill=fill, outline=edge)
    else:
        draw.rectangle((cx - 12, cy - 8, cx + 12, cy + 16), fill=fill, outline=edge)
        draw.rectangle((cx - 3, cy - 20, cx + 3, cy - 4), fill=fill, outline=edge)
        draw.rectangle((cx - 8, cy - 16, cx + 8, cy - 10), fill=fill, outline=edge)


@dataclass
class Session:
    channel_id: int
    white_id: int
    black_id: int
    board: Board
    image: bool = False
    moves: list = field(default_factory=list)
    sans: list = field(default_factory=list)
    keys: list = field(default_factory=list)
    message: Optional[discord.Message] = None
    strength: str = "club"
    flip: bool = False
    draw_offer: int = -1
    last_touch: float = field(default_factory=time.time)
    thinking: bool = False
    pgn_white: str = "White"
    pgn_black: str = "Black"
    view: Optional[discord.ui.View] = None

    @property
    def vs_engine(self) -> bool:
        return self.white_id == 0 or self.black_id == 0

    def player_id(self, side: int) -> int:
        return self.white_id if side == WHITE else self.black_id

    def side_of(self, user_id: int) -> Optional[int]:
        if user_id == self.white_id:
            return WHITE
        if user_id == self.black_id:
            return BLACK
        return None

    def cache(self, legal: list) -> None:
        self._preview = {m.uci(): self.board.san(m, legal) for m in legal}

    def label(self, move: Move) -> str:
        return getattr(self, "_preview", {}).get(move.uci(), move.uci())


class MoveSelect(discord.ui.Select):
    def __init__(self, cog: "Chessmaster", session: Session, page: int, pages: list):
        seen = set()
        options = []
        for move in pages[page]:
            value = move.uci()
            if value in seen:
                continue
            seen.add(value)
            options.append(discord.SelectOption(label=session.label(move)[:100], value=value))
        super().__init__(placeholder=f"Legal moves ({page + 1}/{len(pages)})", options=options[:25], row=0)
        self.cog = cog
        self.session = session

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.play_uci(interaction, self.session, self.values[0])


class GameView(discord.ui.View):
    def __init__(self, cog: "Chessmaster", session: Session, page: int = 0):
        super().__init__(timeout=IDLE_SECONDS)
        self.cog = cog
        self.session = session
        legal = session.board.legal()
        session.cache(legal)
        pages = [legal[i:i + 25] for i in range(0, len(legal), 25)] or [[]]
        self.page = max(0, min(page, len(pages) - 1))
        self.pages = pages
        if legal:
            self.add_item(MoveSelect(cog, session, self.page, pages))
        if len(pages) > 1:
            prev = discord.ui.Button(label="Prev", style=discord.ButtonStyle.secondary, row=1)
            nxt = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev
            nxt.callback = self._next
            self.add_item(prev)
            self.add_item(nxt)
        style = discord.ui.Button(
            label="Text board" if session.image else "Image board",
            style=discord.ButtonStyle.secondary,
            row=3,
        )
        style.callback = self._style
        self.add_item(style)

    async def _prev(self, interaction: discord.Interaction) -> None:
        await self._page(interaction, -1)

    async def _next(self, interaction: discord.Interaction) -> None:
        await self._page(interaction, 1)

    async def _page(self, interaction: discord.Interaction, delta: int) -> None:
        if self.cog.games.get(self.session.channel_id) is not self.session:
            await interaction.response.send_message("That game is already over.", ephemeral=True)
            return
        view = self.cog.bind(self.session, GameView(self.cog, self.session, (self.page + delta) % len(self.pages)))
        await self.cog.edit_board(interaction, self.session, view)

    async def _style(self, interaction: discord.Interaction) -> None:
        if self.session.side_of(interaction.user.id) is None:
            await interaction.response.send_message("Only the players can switch the board.", ephemeral=True)
            return
        if not self.session.image and not HAS_PIL:
            await interaction.response.send_message("Image boards need Pillow.", ephemeral=True)
            return
        self.session.image = not self.session.image
        view = self.cog.bind(self.session, GameView(self.cog, self.session, self.page))
        await self.cog.edit_board(interaction, self.session, view)

    @discord.ui.button(label="Type move", style=discord.ButtonStyle.primary, row=2)
    async def type_move(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.cog.can_move(self.session, interaction.user.id):
            await interaction.response.send_message("It isn't your turn.", ephemeral=True)
            return
        await interaction.response.send_modal(MoveModal(self.cog, self.session))

    @discord.ui.button(label="Offer draw", style=discord.ButtonStyle.secondary, row=2)
    async def offer_draw(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.offer_draw(interaction, self.session)

    @discord.ui.button(label="Resign", style=discord.ButtonStyle.danger, row=2)
    async def resign(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.resign(interaction, self.session)

    @discord.ui.button(label="Flip", style=discord.ButtonStyle.secondary, row=3)
    async def flip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.session.side_of(interaction.user.id) is None:
            await interaction.response.send_message("Only the players can flip the board.", ephemeral=True)
            return
        self.session.flip = not self.session.flip
        view = self.cog.bind(self.session, GameView(self.cog, self.session, self.page))
        await self.cog.edit_board(interaction, self.session, view)


class MoveModal(discord.ui.Modal, title="Play a move"):
    notation = discord.ui.TextInput(label="SAN or UCI", placeholder="e4, Nf3, O-O, e7e8q", max_length=16)

    def __init__(self, cog: "Chessmaster", session: Session):
        super().__init__()
        self.cog = cog
        self.session = session

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.play_text(interaction, self.session, str(self.notation))


class AcceptView(discord.ui.View):
    def __init__(self, cog: "Chessmaster", channel_id: int, challenger_id: int, opponent_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.channel_id = channel_id
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.done = False

    def _close(self) -> None:
        self.done = True
        self.cog.pending.discard(self.channel_id)
        self.stop()

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Only the challenged player can accept.", ephemeral=True)
            return
        self._close()
        await self.cog.begin_human(interaction, self.challenger_id, self.opponent_id)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id not in (self.opponent_id, self.challenger_id):
            await interaction.response.send_message("You aren't part of this challenge.", ephemeral=True)
            return
        self._close()
        await interaction.response.edit_message(content="Challenge declined. Nothing was saved.", embed=None, view=None, attachments=[])

    async def on_timeout(self) -> None:
        if self.done:
            return
        self.cog.pending.discard(self.channel_id)
        if self.message is not None:
            try:
                await self.message.edit(content="Challenge expired. Nothing was saved.", view=None, attachments=[])
            except discord.HTTPException:
                pass


class Chessmaster(commands.Cog):
    """Play chess in this channel."""

    __author__ = "SHADOW"
    __version__ = "1.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.games: dict[int, Session] = {}
        self.pending: set[int] = set()
        self.config = Config.get_conf(self, identifier=264837192, force_registration=True)
        self.config.register_guild(image_mode=False)
        self._sweeper: Optional[asyncio.Task] = None

    async def cog_load(self) -> None:
        self._sweeper = asyncio.create_task(self._sweep())

    def cog_unload(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
        self.games.clear()
        self.pending.clear()

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre = super().format_help_for_context(ctx)
        return f"{pre}\nAuthor: {self.__author__}\nVersion: {self.__version__}"

    async def _sweep(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = time.time()
            for cid in [cid for cid, g in self.games.items() if now - g.last_touch > IDLE_SECONDS]:
                session = self.games.get(cid)
                if not session:
                    continue
                embed, file = self.payload(session, over="Game expired after 45 minutes idle. Session wiped.")
                message = session.message
                self._drop(session)
                if message:
                    try:
                        await message.edit(embed=embed, view=None, attachments=[file] if file else [])
                    except discord.HTTPException:
                        pass

    def bind(self, session: Session, view: discord.ui.View) -> discord.ui.View:
        if session.view is not None and session.view is not view:
            session.view.stop()
        session.view = view
        return view

    def _drop(self, session: Session) -> None:
        self.games.pop(session.channel_id, None)
        if session.view is not None:
            session.view.stop()
            session.view = None
        session.board.sq = []
        session.moves.clear()
        session.keys.clear()

    def can_move(self, session: Session, user_id: int) -> bool:
        return session.player_id(session.board.side) == user_id

    def clip(self, text: str, limit: int = 1024) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def payload(self, session: Session, over: str = "", footer: str = "") -> tuple[discord.Embed, Optional[discord.File]]:
        side = "White" if session.board.side == WHITE else "Black"
        embed = discord.Embed(title="Chessmaster" if not over else "Chessmaster — game over", color=RED)
        file = None
        if session.image and HAS_PIL and session.board.sq:
            buf = render_board(session.board, session.flip, session.moves[-1] if session.moves else None)
            file = discord.File(buf, filename="board.png")
            embed.set_image(url="attachment://board.png")
        elif session.board.sq:
            embed.description = session.board.pretty(session.flip, session.moves[-1] if session.moves else None)
        embed.add_field(name="Players", value=self.clip(f"{session.pgn_white} vs {session.pgn_black}"), inline=False)
        if session.sans:
            pairs = []
            for i in range(0, len(session.sans), 2):
                black = session.sans[i + 1] if i + 1 < len(session.sans) else ""
                pairs.append(f"{i // 2 + 1}. {session.sans[i]} {black}".rstrip())
            embed.add_field(name="Moves", value=self.clip(" ".join(pairs)), inline=False)
        if over:
            embed.add_field(name="Result", value=self.clip(over), inline=False)
            embed.set_footer(text="SHADOW · session cleared")
        else:
            who = "Cog-800" if session.player_id(session.board.side) == 0 else side
            offer = " · draw offered" if session.draw_offer > 0 else ""
            mode = "image" if session.image else "text"
            embed.set_footer(text=footer or f"{who} to move{offer} · {mode} board · SHADOW")
        return embed, file

    async def edit_board(self, interaction: discord.Interaction, session: Session, view: Optional[discord.ui.View], over: str = "", footer: str = "") -> None:
        embed, file = self.payload(session, over, footer)
        kwargs = {"embed": embed, "view": view, "attachments": [file] if file else []}
        if interaction.response.is_done():
            await interaction.edit_original_response(**kwargs)
        else:
            await interaction.response.edit_message(**kwargs)

    async def send_board(self, ctx: commands.Context, session: Session, view: Optional[discord.ui.View]) -> None:
        embed, file = self.payload(session)
        if ctx.interaction:
            await ctx.interaction.response.send_message(embed=embed, view=view, file=file)
            session.message = await ctx.interaction.original_response()
        else:
            session.message = await ctx.send(embed=embed, view=view, file=file)

    @commands.hybrid_group(name="chessmaster")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, send_messages=True)
    async def chessmaster(self, ctx: commands.Context) -> None:
        """Play chess in this channel."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @chessmaster.command(name="bot")
    async def vs_bot(self, ctx: commands.Context, strength: str = "club", color: str = "white") -> None:
        """Play Cog-800. Strength: casual, club, strong. Color: white, black, random."""
        if not await self._occupy(ctx):
            return
        strength = strength.lower()
        color = color.lower()
        if strength not in STRENGTHS or color not in {"white", "black", "random"}:
            await ctx.send("Use strength casual, club, or strong, and color white, black, or random.")
            return
        want = random.choice(("white", "black")) if color == "random" else color
        white_id = ctx.author.id if want == "white" else 0
        black_id = ctx.author.id if want == "black" else 0
        session = Session(
            channel_id=ctx.channel.id,
            white_id=white_id,
            black_id=black_id,
            board=Board(),
            image=await self.config.guild(ctx.guild).image_mode(),
            strength=strength,
            pgn_white=ctx.author.display_name if white_id else "Cog-800",
            pgn_black=ctx.author.display_name if black_id else "Cog-800",
            flip=want == "black",
        )
        session.keys.append(session.board.key())
        self.games[ctx.channel.id] = session
        view = self.bind(session, GameView(self, session)) if white_id else None
        await self.send_board(ctx, session, view)
        if not white_id and ctx.interaction:
            await self._engine_move(session, ctx.interaction)

    @chessmaster.command(name="challenge")
    async def challenge(self, ctx: commands.Context, opponent: discord.Member) -> None:
        """Challenge a member. They accept on the message. Nothing is stored if they decline."""
        if opponent.bot or opponent.id == ctx.author.id:
            await ctx.send("Pick a human who isn't you.")
            return
        if not await self._occupy(ctx):
            return
        self.pending.add(ctx.channel.id)
        view = AcceptView(self, ctx.channel.id, ctx.author.id, opponent.id)
        content = f"{opponent.mention}, {ctx.author.display_name} challenged you to chess."
        if ctx.interaction:
            await ctx.interaction.response.send_message(content, view=view, allowed_mentions=discord.AllowedMentions(users=[opponent]))
            view.message = await ctx.interaction.original_response()
        else:
            view.message = await ctx.send(content, view=view, allowed_mentions=discord.AllowedMentions(users=[opponent]))

    @chessmaster.command(name="resign")
    async def resign_cmd(self, ctx: commands.Context) -> None:
        """Resign the game in this channel and wipe it."""
        session = self.games.get(ctx.channel.id)
        if not session:
            await ctx.send("No game in this channel.")
            return
        if ctx.interaction:
            await self.resign(ctx.interaction, session)
        else:
            await self._prefix_resign(ctx, session)

    @chessmaster.command(name="draw")
    async def draw_cmd(self, ctx: commands.Context) -> None:
        """Offer a draw, or accept the current offer."""
        session = self.games.get(ctx.channel.id)
        if not session:
            await ctx.send("No game in this channel.")
            return
        if ctx.interaction:
            await self.offer_draw(ctx.interaction, session)
        else:
            await ctx.send("Use the Offer draw button on the board message.")

    @chessmaster.command(name="mode")
    @commands.admin_or_permissions(manage_guild=True)
    async def mode(self, ctx: commands.Context, style: str) -> None:
        """Set the default board for new games: text or image."""
        style = style.lower()
        if style not in {"text", "image"}:
            await ctx.send("Use text or image.")
            return
        if style == "image" and not HAS_PIL:
            await ctx.send("Image boards need Pillow installed.")
            return
        await self.config.guild(ctx.guild).image_mode.set(style == "image")
        await ctx.send(f"New games in this server will use a {style} board.")

    async def _occupy(self, ctx: commands.Context) -> bool:
        if ctx.channel.id in self.games or ctx.channel.id in self.pending:
            await ctx.send("This channel already has a game or a pending challenge.")
            return False
        return True

    async def begin_human(self, interaction: discord.Interaction, white_id: int, black_id: int) -> None:
        guild = interaction.guild
        white = guild.get_member(white_id) if guild else None
        black = guild.get_member(black_id) if guild else None
        image = await self.config.guild(guild).image_mode() if guild else False
        session = Session(
            channel_id=interaction.channel_id,
            white_id=white_id,
            black_id=black_id,
            board=Board(),
            image=image,
            pgn_white=white.display_name if white else "White",
            pgn_black=black.display_name if black else "Black",
        )
        session.keys.append(session.board.key())
        self.games[interaction.channel_id] = session
        view = self.bind(session, GameView(self, session))
        embed, file = self.payload(session)
        await interaction.response.edit_message(content=None, embed=embed, view=view, attachments=[file] if file else [])
        session.message = interaction.message

    async def resign(self, interaction: discord.Interaction, session: Session) -> None:
        if self.games.get(session.channel_id) is not session:
            await interaction.response.send_message("That game is already over.", ephemeral=True)
            return
        side = session.side_of(interaction.user.id)
        if side is None:
            await interaction.response.send_message("Only a player can resign.", ephemeral=True)
            return
        winner = "Black" if side == WHITE else "White"
        await self.finish(interaction, session, f"{interaction.user.display_name} resigned. {winner} wins.")

    async def _prefix_resign(self, ctx: commands.Context, session: Session) -> None:
        side = session.side_of(ctx.author.id)
        if side is None:
            await ctx.send("Only a player can resign.")
            return
        winner = "Black" if side == WHITE else "White"
        reason = f"{ctx.author.display_name} resigned. {winner} wins."
        embed, file = self.payload(session, over=reason + "\n" + self.pgn(session, reason))
        message = session.message
        self._drop(session)
        if message:
            await message.edit(embed=embed, view=None, attachments=[file] if file else [])
        await ctx.send("Game ended and wiped.")

    async def offer_draw(self, interaction: discord.Interaction, session: Session) -> None:
        if self.games.get(session.channel_id) is not session:
            await interaction.response.send_message("That game is already over.", ephemeral=True)
            return
        side = session.side_of(interaction.user.id)
        if side is None:
            await interaction.response.send_message("Only a player can offer a draw.", ephemeral=True)
            return
        if session.vs_engine:
            if session.board.insufficient() or abs(Engine().evaluate(session.board)) < 40:
                await self.finish(interaction, session, "Cog-800 accepts the draw.")
            else:
                await interaction.response.send_message("Cog-800 declines the draw.", ephemeral=True)
            return
        other = session.black_id if side == WHITE else session.white_id
        if session.draw_offer == other:
            await self.finish(interaction, session, "Draw agreed.")
            return
        session.draw_offer = interaction.user.id
        session.last_touch = time.time()
        view = self.bind(session, GameView(self, session))
        await self.edit_board(interaction, session, view, footer=f"{interaction.user.display_name} offers a draw. Opponent presses Offer draw.")

    async def play_text(self, interaction: discord.Interaction, session: Session, text: str) -> None:
        if not self.can_move(session, interaction.user.id):
            await interaction.response.send_message("It isn't your turn.", ephemeral=True)
            return
        move = self.parse(session, text.strip())
        if move is None:
            await interaction.response.send_message("Couldn't read that as a legal move.", ephemeral=True)
            return
        await self.play_uci(interaction, session, move.uci())

    async def play_uci(self, interaction: discord.Interaction, session: Session, uci: str) -> None:
        if self.games.get(session.channel_id) is not session:
            await interaction.response.send_message("That game is already over.", ephemeral=True)
            return
        if session.thinking:
            await interaction.response.send_message("The engine is still thinking.", ephemeral=True)
            return
        if not self.can_move(session, interaction.user.id):
            await interaction.response.send_message("It isn't your turn.", ephemeral=True)
            return
        move = next((m for m in session.board.legal() if m.uci() == uci), None)
        if move is None:
            await interaction.response.send_message("That move isn't legal.", ephemeral=True)
            return
        await self.commit(interaction, session, move)

    async def commit(self, interaction: discord.Interaction, session: Session, move: Move) -> None:
        session.sans.append(session.board.san(move))
        session.board.make(move)
        session.moves.append(move)
        session.keys.append(session.board.key())
        session.draw_offer = -1
        session.last_touch = time.time()
        reason = self.terminal(session)
        if reason:
            await self.finish(interaction, session, reason)
            return
        if session.player_id(session.board.side) == 0:
            session.thinking = True
            if session.view is not None:
                session.view.stop()
                session.view = None
            await self.edit_board(interaction, session, None, footer="Cog-800 is thinking.")
            await self._engine_move(session, interaction)
            return
        await self.edit_board(interaction, session, self.bind(session, GameView(self, session)))

    async def _engine_move(self, session: Session, interaction: discord.Interaction) -> None:
        think, depth = STRENGTHS[session.strength]
        engine = Engine(think, depth)
        try:
            move, _, reached = await asyncio.get_running_loop().run_in_executor(None, engine.search, session.board)
        except Exception:
            session.thinking = False
            await self.finish(interaction, session, "Engine failed. Game wiped.")
            return
        san = session.board.san(move)
        session.board.make(move)
        session.moves.append(move)
        session.sans.append(san)
        session.keys.append(session.board.key())
        session.thinking = False
        session.last_touch = time.time()
        reason = self.terminal(session)
        view = None if reason else self.bind(session, GameView(self, session))
        footer = "" if reason else f"Cog-800 played {san} · depth {reached} · {engine.nodes} nodes"
        await self.edit_board(interaction, session, view, reason + "\n" + self.pgn(session, reason) if reason else "", footer)
        if reason:
            self._drop(session)

    def terminal(self, session: Session) -> str:
        board = session.board
        if not board.legal():
            return ("Checkmate. " + ("Black" if board.side == WHITE else "White") + " wins.") if board.in_check() else "Stalemate. Draw."
        if board.halfmove >= 100:
            return "Draw by the 50-move rule."
        if session.keys.count(board.key()) >= 3:
            return "Draw by threefold repetition."
        if board.insufficient():
            return "Draw by insufficient material."
        return ""

    async def finish(self, interaction: discord.Interaction, session: Session, reason: str) -> None:
        embed, file = self.payload(session, over=reason + "\n" + self.pgn(session, reason))
        message = session.message
        same = interaction.message is not None and message is not None and interaction.message.id == message.id
        self._drop(session)
        kwargs = {"embed": embed, "view": None, "attachments": [file] if file else []}
        if same and not interaction.response.is_done():
            await interaction.response.edit_message(**kwargs)
            return
        if not interaction.response.is_done():
            await interaction.response.send_message("Game ended and wiped.", ephemeral=True)
        if message:
            try:
                await message.edit(**kwargs)
            except discord.HTTPException:
                pass

    def pgn(self, session: Session, reason: str) -> str:
        result = "0-1" if "Black wins" in reason else "1-0" if "wins" in reason else "1/2-1/2"
        body = []
        for i in range(0, len(session.sans), 2):
            black = session.sans[i + 1] if i + 1 < len(session.sans) else ""
            body.append(f"{i // 2 + 1}. {session.sans[i]} {black}".rstrip())
        return f'[White "{session.pgn_white}"] [Black "{session.pgn_black}"] [Result "{result}"] {" ".join(body)} {result}'

    def parse(self, session: Session, text: str) -> Optional[Move]:
        raw = text.replace("0-0-0", "O-O-O").replace("0-0", "O-O").replace("×", "x").strip()
        legal = session.board.legal()
        compact = raw.lower().replace("=", "")
        for move in legal:
            if move.uci() == compact:
                return move
        target = raw.replace("+", "").replace("#", "")
        matches = [m for m in legal if session.board.san(m, legal).replace("+", "").replace("#", "") == target]
        if len(matches) == 1:
            return matches[0]
        alias = {"o-o": "O-O", "o-o-o": "O-O-O"}
        want = alias.get(raw.lower())
        if want:
            matches = [m for m in legal if session.board.san(m, legal).startswith(want)]
            if len(matches) == 1:
                return matches[0]
        return None
