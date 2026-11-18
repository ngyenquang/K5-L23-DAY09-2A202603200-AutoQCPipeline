"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}      # cộng thêm mọi mã DUP_IMAGE_*


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE")


def _clip(x, y, w, h):
    """Cắt box (cx,cy,w,h) về trong [0,1]; None nếu sau khi cắt không còn diện tích."""
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]          # cảnh báo là việc của người

    # 1) data.yaml: ghi lại tên lớp đúng cfg["classes"]
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        before = d.get("names")
        d["names"] = {k: n for k, n in enumerate(cfg["classes"])}
        ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        fixes.append({"image": "data.yaml", "line": None, "action": "rename_classes",
                      "before": str(before), "after": str(d["names"])})

    # 2) xoá ảnh (kèm nhãn); từ đây bỏ qua mọi issue của ảnh đã xoá
    removed = set()
    for stem in sorted({i.image for i in errors if _is_remove(i.code)}):
        img = ds.image_path(stem)
        lab = ds.label_path(stem)
        if img is None and not lab.exists():
            continue                                             # đã xoá từ lần trước
        before = img.name if img else "(không có ảnh)"
        if img:
            img.unlink()
        if lab.exists():
            lab.unlink()
        removed.add(stem)
        fixes.append({"image": stem, "line": None, "action": "remove_image",
                      "before": before, "after": "(đã xoá)"})
    removed |= {i.image for i in errors if _is_remove(i.code)}

    # 3) sửa dòng nhãn: gom theo file, ghi lại MỘT lần, dùng số dòng gốc
    by_line = defaultdict(lambda: defaultdict(set))              # stem -> số dòng -> tập mã lỗi
    for i in errors:
        if i.image not in removed and i.line is not None and (i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE"):
            by_line[i.image][i.line].add(i.code)

    for stem in sorted(by_line):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        out = list(raw)
        drop = set()
        for ln in sorted(by_line[stem]):
            if not 1 <= ln <= len(raw):
                continue
            codes, text = by_line[stem][ln], raw[ln - 1]
            if codes & DROP_CODES:                               # xoá thắng clip
                drop.add(ln)
                fixes.append({"image": stem, "line": ln, "action": "drop_line",
                              "before": text, "after": "(đã xoá dòng)"})
                continue
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            box = _clip(x, y, w, h)
            if box is None:                                      # nằm hẳn ngoài ảnh
                drop.add(ln)
                fixes.append({"image": stem, "line": ln, "action": "drop_line",
                              "before": text, "after": "(đã xoá dòng)"})
            else:
                new = f"{c} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}"
                out[ln - 1] = new
                fixes.append({"image": stem, "line": ln, "action": "clip_box",
                              "before": text, "after": new})
        if out != raw or drop:
            kept = [t for k, t in enumerate(out, 1) if k not in drop]
            path.write_text("".join(t + "\n" for t in kept), encoding="utf-8")

    # 4) thiếu file nhãn: không bịa nhãn, chuyển người gán (ghi lại mỗi lần)
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        fixes.append({"image": stem, "line": None, "action": "needs_label",
                      "before": "(không có file)", "after": "chuyển người gán"})
    return fixes
