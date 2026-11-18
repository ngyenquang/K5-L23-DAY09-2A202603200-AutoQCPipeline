"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    c = cfg["label_format"]
    issues = []
    for lp in ds.label_files():
        stem = lp.stem
        size = ds.image_size(stem)          # (W,H) hoặc None
        kept = []                           # các box hợp lệ ở dòng trước, để so DUP_BOX
        for ln, text in ds.read_label_lines(stem) or []:
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    "dòng không đúng 5 cột số", line=ln))
                continue
            # 1) id lớp ngoài 0..len(classes)-1
            if not 0 <= cls < len(ds.classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài 0..{len(ds.classes) - 1}", line=ln))
                continue
            # 2) box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    f"box có w={w}, h={h}", line=ln))
                continue
            # 3) box tràn ảnh: mức tràn lớn nhất trong 4 mép
            overflow = max(-(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > c["overflow_tol"]:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.4f}", line=ln,
                                    extra={"overflow": round(overflow, 4)}))
            # 4) box lặp: cùng lớp với dòng trước đó, IoU cao -> báo ở dòng sau
            if any(k[0] == cls and iou_xywh(k[1:], (x, y, w, h)) > c["dup_box_iou"] for k in kept):
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                    "box lặp với một dòng trước đó", line=ln))
            # 5) box quá nhỏ (cảnh báo): cạnh ngắn tính bằng px
            if size is not None and min(w * size[0], h * size[1]) < c["min_box_px"]:
                issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                    f"cạnh ngắn < {c['min_box_px']}px", line=ln))
            # 6) box quá to (cảnh báo)
            if w * h > c["max_box_frac"]:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"box chiếm {w * h:.0%} ảnh", line=ln))
            kept.append((cls, x, y, w, h))
    return issues
