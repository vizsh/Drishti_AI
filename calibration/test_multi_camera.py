"""Correctness checks for calibration/multi_camera.py — run before trusting
occlusion fusion against real multi-camera data.

Usage: python -m calibration.test_multi_camera
"""

from calibration.multi_camera import SeatObservation, fuse_seat_observations


def test_single_observation_passes_through_unchanged() -> None:
    obs = SeatObservation(camera_id="cam_a", torso_yaw=0.3, motion_magnitude=0.1, pose_confidence=0.8)
    fused = fuse_seat_observations([obs])
    assert fused is obs, "single-camera case must not be altered by fusion"
    print("PASS: single observation passes through unchanged")


def test_occluded_camera_contributes_less() -> None:
    # cam_a is nearly blind to this seat (occluded by a neighbor);
    # cam_b has a clear view. The fused reading should sit close to
    # cam_b's value, not a plain 50/50 average of the two.
    occluded = SeatObservation(camera_id="cam_a", torso_yaw=2.0, motion_magnitude=0.5, pose_confidence=0.05)
    clear = SeatObservation(camera_id="cam_b", torso_yaw=0.1, motion_magnitude=0.05, pose_confidence=0.9)
    fused = fuse_seat_observations([occluded, clear])

    plain_average = (2.0 + 0.1) / 2  # 1.05 — what naive averaging would give
    assert abs(fused.torso_yaw - 0.1) < 0.15, f"expected close to clear camera's 0.1, got {fused.torso_yaw}"
    assert abs(fused.torso_yaw - plain_average) > 0.5, "fusion must not degrade to a plain average"
    print(f"PASS: occluded camera (conf=0.05) contributes little; fused yaw={fused.torso_yaw:.3f} vs plain avg {plain_average:.3f}")


def test_object_detection_is_logical_or() -> None:
    # A phone visible from one angle but hidden from another must still be
    # reported — a miss on one camera must not suppress a hit on another.
    blind_to_phone = SeatObservation(camera_id="cam_a", torso_yaw=0.0, motion_magnitude=0.0, pose_confidence=0.7)
    sees_phone = SeatObservation(
        camera_id="cam_b", torso_yaw=0.0, motion_magnitude=0.0, pose_confidence=0.6,
        object_label="phone", object_confidence=0.55,
    )
    fused = fuse_seat_observations([blind_to_phone, sees_phone])
    assert fused.object_label == "phone" and fused.object_confidence == 0.55
    print("PASS: object detection from either camera is preserved (logical OR)")


def test_fused_confidence_is_max_not_average() -> None:
    # This is the actual point of occlusion fusion: one blocked camera must
    # not drag down the seat's effective coverage when another camera has a
    # clear view. If this were an average, a 0.9/0.1 split would report the
    # seat as only ~50% covered, which misrepresents genuinely good coverage.
    blocked = SeatObservation(camera_id="cam_a", torso_yaw=0.0, motion_magnitude=0.0, pose_confidence=0.1)
    clear = SeatObservation(camera_id="cam_b", torso_yaw=0.0, motion_magnitude=0.0, pose_confidence=0.9)
    fused = fuse_seat_observations([blocked, clear])
    assert fused.pose_confidence == 0.9, f"expected max(0.1, 0.9)=0.9, got {fused.pose_confidence}"
    print("PASS: fused pose_confidence is the max across cameras, not an average")


def test_empty_observations_raises() -> None:
    try:
        fuse_seat_observations([])
        raise AssertionError("expected ValueError for empty observations")
    except ValueError:
        print("PASS: empty observation list raises rather than silently returning nothing")


if __name__ == "__main__":
    test_single_observation_passes_through_unchanged()
    test_occluded_camera_contributes_less()
    test_object_detection_is_logical_or()
    test_fused_confidence_is_max_not_average()
    test_empty_observations_raises()
    print("\nAll multi-camera fusion correctness checks passed.")
