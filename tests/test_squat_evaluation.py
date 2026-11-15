import pytest

from src.squat_evaluation import evaluate, match_events


def session(times):
    return {"model": {"inference_mode": "mediapipe"}, "source": {"sha256": "video-sha", "kind": "video"},
            "session": {"id": "test", "ended_at": "test-time"}, "actions": [{"kind": "video_finished"}],
            "page_version": "squat-counter-v1", "corrected_count": 2,
            "auto_events": [{"id": str(i), "time_ms": t, "feedback_time_ms": t + 100} for i, t in enumerate(times)],
            "frame_trace": [{"valid": False}, {"valid": True}]}


def annotations(times):
    return [{"source_id": "video-sha", "event_id": str(i), "time_ms": t, "condition": "occlusion"} for i, t in enumerate(times)]


def test_equal_totals_can_hide_both_false_and_missed_events():
    result = evaluate(session([1000, 3000]), annotations([1000, 6000]), tolerance_ms=500)
    assert result["ground_truth_count"] == result["raw_automatic_count"] == 2
    assert result["false_count"] == result["missed_count"] == 1
    assert result["feedback_delay_median_ms"] == 100
    assert result["invalid_frame_count"] == 1


def test_match_maximizes_pairs_before_nearest_timestamp():
    truth = [{"time_ms": t} for t in [100, 200]]
    predicted = [{"time_ms": t} for t in [0, 110]]
    assert match_events(truth, predicted, 110) == [(0, 0), (1, 1)]


def test_missing_and_negative_delays_are_not_replaced_by_zero():
    data = session([900, 2000])
    data["auto_events"][0]["feedback_time_ms"] = 950
    del data["auto_events"][1]["feedback_time_ms"]
    result = evaluate(data, annotations([1000, 2000]))
    assert result["feedback_delay_samples"] == 1
    assert result["feedback_delay_median_ms"] == -50
    assert result["negative_delay_samples"] == 1


@pytest.mark.parametrize("problem", ["mock", "empty", "source", "duplicate", "nan", "condition", "unfinished", "partial", "paused"])
def test_invalid_or_simulated_evidence_is_rejected(problem):
    data = session([1000])
    truth = annotations([1000])
    if problem == "mock": data["model"]["inference_mode"] = "mock_landmarks"
    if problem == "empty": truth = []
    if problem == "source": truth[0]["source_id"] = "different-video"
    if problem == "duplicate": truth.append(dict(truth[0]))
    if problem == "nan": truth[0]["time_ms"] = "nan"
    if problem == "condition": truth[0]["condition"] = "unknown"
    if problem == "unfinished": data["session"]["ended_at"] = None
    if problem == "partial": data["actions"] = []
    if problem == "paused": data["actions"].append({"kind": "pause"})
    with pytest.raises(ValueError): evaluate(data, truth)
