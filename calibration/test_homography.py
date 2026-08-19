"""Correctness check for calibration/homography.py against known synthetic
geometry — run before trusting the module against real, hand-picked
calibration points where ground truth isn't independently known.

Usage: python calibration/test_homography.py
"""

from calibration.homography import SeatCalibration


def test_axis_aligned_square_projects_exactly() -> None:
    # A perfect square in the image maps to a perfect square on the plane —
    # a pure scale+offset transform, so projected points should be exact.
    cal = SeatCalibration(
        camera_id="synthetic",
        image_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        plane_points=[(0, 0), (200, 0), (200, 200), (0, 200)],  # 2x scale
    )
    x, y = cal.project((50, 50))
    assert abs(x - 100) < 1e-3 and abs(y - 100) < 1e-3, f"expected (100,100), got ({x},{y})"
    print("PASS: axis-aligned square projects exactly")


def test_perspective_correction() -> None:
    # A trapezoid in the image (near side wider than far side, as in a real
    # oblique CCTV view) maps to a rectangle on the plane — this is the
    # actual case the module exists for: correcting camera perspective.
    cal = SeatCalibration(
        camera_id="synthetic",
        image_points=[(0, 100), (200, 100), (150, 0), (50, 0)],  # trapezoid
        plane_points=[(0, 100), (200, 100), (200, 0), (0, 0)],   # rectangle
    )
    # the trapezoid's far-top-left corner should map to the rectangle's near-top-left
    x, y = cal.project((50, 0))
    assert abs(x - 0) < 1e-2 and abs(y - 0) < 1e-2, f"expected ~(0,0), got ({x},{y})"
    print("PASS: perspective correction maps trapezoid to rectangle")


def test_nearest_seat_snapping() -> None:
    cal = SeatCalibration(
        camera_id="synthetic",
        image_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        plane_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        seats={"seat_1": (10, 10), "seat_2": (90, 90)},
        max_snap_distance=30,
    )
    seat_id, dist = cal.nearest_seat((12, 12))
    assert seat_id == "seat_1", f"expected seat_1, got {seat_id}"

    seat_id, dist = cal.nearest_seat((50, 50))  # equidistant-ish, but outside snap range
    assert seat_id is None, f"expected None (too far from any seat), got {seat_id}"
    print("PASS: nearest-seat snapping respects max_snap_distance")


def test_roundtrip_json() -> None:
    cal = SeatCalibration(
        camera_id="cam1",
        image_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        plane_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
        seats={"seat_1": (10, 10)},
    )
    cal.to_json("data/raw/_test_calibration.json")
    loaded = SeatCalibration.from_json("data/raw/_test_calibration.json")
    assert loaded.camera_id == "cam1"
    assert loaded.nearest_seat((12, 12))[0] == "seat_1"
    print("PASS: calibration round-trips through JSON")


if __name__ == "__main__":
    test_axis_aligned_square_projects_exactly()
    test_perspective_correction()
    test_nearest_seat_snapping()
    test_roundtrip_json()
    print("\nAll homography correctness checks passed.")
