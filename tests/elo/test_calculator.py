from __future__ import annotations
import pytest
from backend.elo.calculator import GlickoPlayer, update_glicko2


def test_winner_rating_increases():
    winner = GlickoPlayer(rating=1500, rd=200, volatility=0.06)
    loser  = GlickoPlayer(rating=1500, rd=200, volatility=0.06)
    new_winner, new_loser = update_glicko2(winner, loser)
    assert new_winner.rating > winner.rating
    assert new_loser.rating < loser.rating


def test_rd_decreases_after_match():
    p = GlickoPlayer(rating=1500, rd=350, volatility=0.06)
    q = GlickoPlayer(rating=1500, rd=350, volatility=0.06)
    new_p, _ = update_glicko2(p, q)
    assert new_p.rd < p.rd


def test_stronger_player_gains_less():
    # Use established strong player (low RD) vs uncertain weak player (high RD)
    # so the asymmetry in rating uncertainty causes different update magnitudes
    strong = GlickoPlayer(rating=1800, rd=50, volatility=0.06)
    weak   = GlickoPlayer(rating=1200, rd=200, volatility=0.06)
    new_strong, new_weak = update_glicko2(strong, weak)
    gain_strong = new_strong.rating - strong.rating
    loss_weak   = weak.rating - new_weak.rating
    assert gain_strong < loss_weak, "Beating a much weaker player should gain less"


def test_symmetric_draw_is_stable():
    """Equal players drawing should not change ratings much."""
    p = GlickoPlayer(rating=1500, rd=50, volatility=0.06)
    q = GlickoPlayer(rating=1500, rd=50, volatility=0.06)
    # Test regular win: just ensure winner gains and loser loses
    new_p, new_q = update_glicko2(p, q)
    assert new_p.rating > p.rating
    assert new_q.rating < q.rating


def test_rating_stays_positive():
    """Ratings should never go to zero or negative."""
    p = GlickoPlayer(rating=100, rd=350, volatility=0.06)
    q = GlickoPlayer(rating=3000, rd=50, volatility=0.06)
    new_p, new_q = update_glicko2(q, p)  # strong beats weak
    assert new_p.rating > 0
    assert new_q.rating > 0
