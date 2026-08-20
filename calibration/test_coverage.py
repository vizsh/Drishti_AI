"""Correctness checks for calibration/coverage.py — run before trusting it
against a real seating chart.

Usage: python -m calibration.test_coverage
"""

from calibration.coverage import CameraCoverageInput, validate_coverage
from calibration.homography import SeatCalibration


def test_round_trip_project_inverse() -> None:
    cal = SeatCalibration(
        camera_id="synthetic",
        image_points=[(0, 100), (200, 100), (150, 0), (50, 0)],  # trapezoid, same as test_homography.py
        plane_points=[(0, 100), (200, 100), (200, 0), (0, 0)],
    )
    original = (75.0, 40.0)
    plane_point = cal.project(original)
    recovered = cal.project_inverse(plane_point)
    assert abs(recovered[0] - original[0]) < 1e-2 and abs(recovered[1] - original[1]) < 1e-2, (
        f"round-trip failed: {original} -> {plane_point} -> {recovered}"
    )
    print("PASS: project_inverse round-trips project() exactly")


def test_covered_seat() -> None:
    cal = SeatCalibration(
        camera_id="cam1",
        image_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
        plane_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    cal.seats["seat_1"] = cal.project((320, 240))  # dead center — clearly in-frame

    results = validate_coverage(["seat_1"], [CameraCoverageInput("cam1", cal, 640, 480)])
    assert results[0].covered and results[0].covering_cameras == ["cam1"]
    print("PASS: an in-frame calibrated seat is reported covered")


def test_missing_seat_is_blind_spot() -> None:
    cal = SeatCalibration(
        camera_id="cam1",
        image_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
        plane_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    cal.seats["seat_1"] = cal.project((320, 240))
    # seat_2 is on the institution's seating chart but was never calibrated —
    # exactly the "camera blind spot discovered mid-exam" failure this
    # validator exists to catch before the exam starts.
    results = validate_coverage(["seat_1", "seat_2"], [CameraCoverageInput("cam1", cal, 640, 480)])
    by_seat = {r.seat_id: r for r in results}
    assert by_seat["seat_1"].covered
    assert not by_seat["seat_2"].covered
    assert "not present in any camera's calibration" in by_seat["seat_2"].reason
    print("PASS: an uncalibrated seat is correctly flagged as a blind spot")


def test_calibrated_but_out_of_frame_is_flagged() -> None:
    cal = SeatCalibration(
        camera_id="cam1",
        image_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
        plane_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    # A stale/drifted calibration: the stored plane point maps back to a
    # pixel far outside the 640x480 frame — the seat is calibrated but the
    # calibration itself is no longer trustworthy.
    cal.seats["seat_1"] = (2000.0, 2000.0)

    results = validate_coverage(["seat_1"], [CameraCoverageInput("cam1", cal, 640, 480)])
    assert not results[0].covered
    assert "outside usable frame" in results[0].reason
    print("PASS: a calibrated seat that projects outside the frame is flagged, not silently trusted")


def test_multi_camera_redundant_coverage() -> None:
    cal_a = SeatCalibration(
        camera_id="cam_a",
        image_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
        plane_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    cal_a.seats["seat_1"] = cal_a.project((320, 240))
    cal_b = SeatCalibration(
        camera_id="cam_b",
        image_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
        plane_points=[(0, 0), (640, 0), (640, 480), (0, 480)],
    )
    cal_b.seats["seat_1"] = cal_b.project((100, 100))

    results = validate_coverage(
        ["seat_1"], [CameraCoverageInput("cam_a", cal_a, 640, 480), CameraCoverageInput("cam_b", cal_b, 640, 480)]
    )
    assert set(results[0].covering_cameras) == {"cam_a", "cam_b"}
    print("PASS: a seat covered by two cameras reports both (occlusion-fusion prerequisite)")


if __name__ == "__main__":
    test_round_trip_project_inverse()
    test_covered_seat()
    test_missing_seat_is_blind_spot()
    test_calibrated_but_out_of_frame_is_flagged()
    test_multi_camera_redundant_coverage()
    print("\nAll coverage-validator correctness checks passed.")
