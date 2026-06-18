from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass
class GlickoPlayer:
    rating:     float = 1500.0
    rd:         float = 350.0    # rating deviation
    volatility: float = 0.06


# Glicko-2 constants
_TAU  = 0.5      # system constant controlling volatility change speed


def _f(x: float, delta: float, v: float, phi: float, a: float, tau: float) -> float:
    ex   = math.exp(x)
    phi2 = phi ** 2
    num  = ex * (delta**2 - phi2 - v - ex)
    den  = 2 * (phi2 + v + ex) ** 2
    return num / den - (x - a) / tau**2


def update_glicko2(
    winner: GlickoPlayer, loser: GlickoPlayer
) -> tuple[GlickoPlayer, GlickoPlayer]:
    """Apply one match result using Glicko-2. Returns (new_winner, new_loser)."""
    new_winner = _update_one(winner, loser, score=1.0)
    new_loser  = _update_one(loser, winner, score=0.0)
    return new_winner, new_loser


def draw_glicko2(
    player_a: GlickoPlayer, player_b: GlickoPlayer
) -> tuple[GlickoPlayer, GlickoPlayer]:
    """Apply a draw result using score=0.5 for both players."""
    new_a = _update_one(player_a, player_b, score=0.5)
    new_b = _update_one(player_b, player_a, score=0.5)
    return new_a, new_b


def _update_one(player: GlickoPlayer, opponent: GlickoPlayer, score: float) -> GlickoPlayer:
    # Convert to Glicko-2 scale (μ, φ, σ)
    mu    = (player.rating - 1500) / 173.7178
    phi   = player.rd / 173.7178
    sigma = player.volatility

    mu_j    = (opponent.rating - 1500) / 173.7178
    phi_j   = opponent.rd / 173.7178

    g_j = 1.0 / math.sqrt(1 + 3 * phi_j**2 / math.pi**2)
    E_j = 1.0 / (1 + math.exp(-g_j * (mu - mu_j)))

    # Step 3: compute v
    v = 1.0 / (g_j**2 * E_j * (1 - E_j))

    # Step 4: compute delta
    delta = v * g_j * (score - E_j)

    # Step 5: determine new sigma via Illinois algorithm
    a  = math.log(sigma**2)
    A  = a
    if delta**2 > phi**2 + v:
        B = math.log(delta**2 - phi**2 - v)
    else:
        k = 1
        while _f(a - k * _TAU, delta, v, phi, a, _TAU) < 0:
            k += 1
        B = a - k * _TAU

    fA = _f(A, delta, v, phi, a, _TAU)
    fB = _f(B, delta, v, phi, a, _TAU)
    for _ in range(100):
        C  = A + (A - B) * fA / (fB - fA)
        fC = _f(C, delta, v, phi, a, _TAU)
        if fB * fC < 0:
            A, fA = B, fB
        else:
            fA /= 2
        B, fB = C, fC
        if abs(B - A) < 1e-6:
            break
    new_sigma = math.exp(A / 2)

    # Step 6: update phi*
    phi_star = math.sqrt(phi**2 + new_sigma**2)

    # Step 7: update mu, phi
    new_phi = 1.0 / math.sqrt(1 / phi_star**2 + 1 / v)
    new_mu  = mu + new_phi**2 * g_j * (score - E_j)

    # Convert back to Glicko-1 scale
    return GlickoPlayer(
        rating=173.7178 * new_mu + 1500,
        rd=173.7178 * new_phi,
        volatility=new_sigma,
    )
