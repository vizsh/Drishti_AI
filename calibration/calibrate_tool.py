"""Interactive per-camera seat calibration tool.

Only a human who can see the room can correctly identify desk corners and
seat positions — this tool doesn't guess, it walks you through it on a real
frame from your footage.

Usage:
    python -m calibration.calibrate_tool --source "data/test_videos/04.CCTV Candidate Talking.mkv" \
        --camera-id cam04 --output data/raw/cam04_calibration.json

Two phases, both driven by clicking on the displayed frame:

  Phase 1 — correspondence points (>=4). Click a point whose real-world
  position on the desk/seat plane you know (e.g. a desk corner), then type
  its plane coordinate in the console (any consistent unit — cm, or just a
  grid index like "1,0" if you don't want to measure). These solve the
  homography.

  Phase 2 — seat positions. Click the anchor point of each seat (where a
  seated student's lower-body/desk-contact point falls in the image), then
  type a seat_id in the console. Plane coordinates for seats are computed
  automatically from the homography built in phase 1 — no manual measuring
  needed for seats themselves.

Press 'n' to move from phase 1 to phase 2 once you have >=4 points.
Press 'q' to finish phase 2 and save.
"""

from __future__ import annotations

import argparse

import cv2

from calibration.homography import SeatCalibration


def grab_frame(source: str, frame_index: int):
    cap = cv2.VideoCapture(source)
    if frame_index > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Could not read frame {frame_index} from {source}")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--frame-index", type=int, default=0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-snap-distance", type=float, default=50.0)
    args = parser.parse_args()

    frame = grab_frame(args.source, args.frame_index)
    window = f"Calibrate {args.camera_id} — phase 1: correspondence points (need >=4)"
    cv2.namedWindow(window)

    image_points: list[tuple[float, float]] = []
    plane_points: list[tuple[float, float]] = []
    click_xy: list[tuple[int, int]] = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            click_xy.append((x, y))

    cv2.setMouseCallback(window, on_click)
    print("Phase 1: click a point with known real-world position, then answer the prompt.")
    print("Press 'n' once you have >=4 points to move to phase 2.\n")

    while True:
        vis = frame.copy()
        for i, (px, py) in enumerate(image_points):
            cv2.circle(vis, (int(px), int(py)), 5, (0, 255, 0), -1)
            cv2.putText(vis, str(i), (int(px) + 6, int(py)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imshow(window, vis)
        key = cv2.waitKey(30) & 0xFF

        if click_xy:
            x, y = click_xy.pop(0)
            wx = input(f"  clicked image point ({x},{y}) -> real-world plane X: ")
            wy = input(f"  clicked image point ({x},{y}) -> real-world plane Y: ")
            image_points.append((float(x), float(y)))
            plane_points.append((float(wx), float(wy)))
            print(f"  added correspondence #{len(image_points) - 1}\n")

        if key == ord("n"):
            if len(image_points) < 4:
                print(f"Need >=4 points, have {len(image_points)}. Keep clicking.")
                continue
            break
        if key == ord("q"):
            print("Aborted — no calibration saved.")
            cv2.destroyAllWindows()
            return

    cal = SeatCalibration(
        camera_id=args.camera_id,
        image_points=image_points,
        plane_points=plane_points,
        max_snap_distance=args.max_snap_distance,
    )

    cv2.destroyWindow(window)
    window2 = f"Calibrate {args.camera_id} — phase 2: click each seat, then 'q' to save"
    cv2.namedWindow(window2)
    cv2.setMouseCallback(window2, on_click)
    click_xy.clear()
    seat_image_points: dict[str, tuple[float, float]] = {}
    print("\nPhase 2: click each seat's anchor point, then type its seat_id.")
    print("Press 'q' when done to save.\n")

    while True:
        vis = frame.copy()
        for seat_id, img_pt in seat_image_points.items():
            x, y = img_pt
            cv2.circle(vis, (int(x), int(y)), 5, (0, 165, 255), -1)
            cv2.putText(vis, seat_id, (int(x) + 6, int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
        cv2.imshow(window2, vis)
        key = cv2.waitKey(30) & 0xFF

        if click_xy:
            x, y = click_xy.pop(0)
            seat_id = input(f"  clicked seat anchor ({x},{y}) -> seat_id: ")
            plane_pt = cal.project((x, y))
            cal.seats[seat_id] = plane_pt
            seat_image_points[seat_id] = (x, y)
            print(f"  seat '{seat_id}' -> plane {plane_pt}\n")

        if key == ord("q"):
            break

    cv2.destroyAllWindows()
    cal.to_json(args.output)
    print(f"\nSaved calibration ({len(cal.seats)} seats) to {args.output}")


if __name__ == "__main__":
    main()
