# tests/test_ev_and_evaluator.py
import pytest
from src.parlay.generator import implied_prob, compute_ev
from src.parlay.evaluator import evaluate_leg

def test_implied_prob():
    assert abs(implied_prob(2.0) - 0.5) < 1e-9
    assert abs(implied_prob(1.5) - (1/1.5)) < 1e-9

def test_compute_ev_positive():
    # Suppose p_hat 0.6 and odds 2.0: EV = 0.6*(1) - 0.4 = 0.2
    ev = compute_ev(0.6, 2.0)
    assert pytest.approx(ev, 0.0001) == 0.2

def test_evaluator_moneyline_win():
    match_final = {"status":"finished","home":"A","away":"B","home_score":2,"away_score":1}
    leg = {"market":"Moneyline","selection":"Home"}
    res = evaluate_leg(leg, match_final)
    assert res is True

def test_evaluator_moneyline_draw_loss():
    match_final = {"status":"finished","home":"A","away":"B","home_score":1,"away_score":1}
    leg = {"market":"Moneyline","selection":"Home"}
    res = evaluate_leg(leg, match_final)
    assert res is False

def test_evaluator_over_under_over():
    match_final = {"status":"finished","home":"A","away":"B","home_score":3,"away_score":0}
    leg = {"market":"Over/Under 2.5","selection":"Over 2.5"}
    res = evaluate_leg(leg, match_final)
    assert res is True

def test_evaluator_btts_yes():
    match_final = {"status":"finished","home":"A","away":"B","home_score":2,"away_score":1}
    leg = {"market":"Both Teams To Score","selection":"Yes"}
    assert evaluate_leg(leg, match_final) is True

def test_evaluator_correct_score():
    match_final = {"status":"finished","home":"A","away":"B","home_score":2,"away_score":1}
    leg = {"market":"Correct Score","selection":"2-1"}
    assert evaluate_leg(leg, match_final) is True
