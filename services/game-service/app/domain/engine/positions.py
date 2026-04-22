from __future__ import annotations

def assign_positions(active_seats: list[int], starting_dealer: int) -> tuple[int, int, int]:
    if len(active_seats) == 2:
        dealer_idx = active_seats.index(starting_dealer) if starting_dealer in active_seats else 0
        sb_idx = dealer_idx
        bb_idx = (dealer_idx + 1) % len(active_seats)
        return active_seats[dealer_idx], active_seats[sb_idx], active_seats[bb_idx]

    dealer_idx = active_seats.index(starting_dealer) if starting_dealer in active_seats else 0
    sb_idx = (dealer_idx + 1) % len(active_seats)
    bb_idx = (dealer_idx + 2) % len(active_seats)
    return active_seats[dealer_idx], active_seats[sb_idx], active_seats[bb_idx]

def rotate_positions(active_seats: list[int], current_dealer: int) -> tuple[int, int, int]:
    if current_dealer in active_seats:
        current_idx = active_seats.index(current_dealer)
        new_dealer_idx = (current_idx + 1) % len(active_seats)
    else:
        new_dealer_idx = 0

    if len(active_seats) == 2:
        sb_idx = new_dealer_idx
        bb_idx = (new_dealer_idx + 1) % len(active_seats)
    else:
        sb_idx = (new_dealer_idx + 1) % len(active_seats)
        bb_idx = (new_dealer_idx + 2) % len(active_seats)

    return active_seats[new_dealer_idx], active_seats[sb_idx], active_seats[bb_idx]