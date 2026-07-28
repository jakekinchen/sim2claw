from sim2claw.bidirectional_registration_v4_evaluator import evaluate


def test_single_open_heldout_rejects_v4_and_triggers_f1() -> None:
    receipt = evaluate()
    assert receipt["held_out_open_count"] == 1
    assert receipt["fit"]["passed"] is True
    assert abs(receipt["fit"]["residual_mm"] - 24.63150540351977) <= 1e-12
    assert receipt["held_out"]["passed"] is False
    assert abs(receipt["held_out"]["residual_mm"] - 164.35312826210378) <= 1e-9
    assert receipt["known_safe_geometry"]["no_new_external_contact"] is True
    assert receipt["known_safe_geometry"]["perfect_tracking_external_contact_pairs"] == []
    assert receipt["admitted"] is False
    assert receipt["fallback"] == "F1"
    assert receipt["status"] == "terminal_negative_f1_triggered"
