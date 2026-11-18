# Báo cáo Day 09 — Nguyễn Văn Quang, 2A202603200

## 1. Kết luận trước
Pipeline kết luận **HOLD** (mã thoát 10). Lô có **224 ảnh**; 21 ảnh bị loại ở cửa vào; **203 ảnh** được QC và xuất ra `export/clean_v1` dưới dạng **bản nháp, chưa phát hành**.
Lý do: không còn lỗi bắt buộc nào (0), nhưng **38/203 ảnh (18,7%) còn cảnh báo** chưa qua người duyệt, vượt ngưỡng Hold 10%. Hàng đợi người duyệt có 125 ảnh, ngân sách chỉ 80 ảnh nên 45 ảnh không ai xem.
(Số liệu: `reports/08_summary.json`, `config_sha1` 5cee21d7…)

## 2. Lỗi và phân việc
Gom từ `02_error_list_v1` (210 dòng, 148 ảnh khác nhau). 21 ảnh bị loại ở cửa vào tính trên 224 ảnh; các mã còn lại tính trên 203 ảnh.

| Mã lỗi | Số lượng | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 / 3 ảnh | máy (xoá ảnh) | quy tắc rõ ràng, có calibration |
| LEAK_TEST | 5 ảnh | máy (xoá ảnh) | ảnh trùng kho test, không được vào train |
| CORRUPT_IMAGE / BAD_SIZE | 2 / 3 ảnh | máy (xoá ảnh) | ảnh hỏng hoặc quá nhỏ |
| BAD_FORMAT / BAD_CLASS_ID / BOX_ZERO / DUP_BOX | 3 / 6 / 4 / 7 dòng | máy (`drop_line`, 20 dòng) | lỗi cú pháp, xoá dòng an toàn |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (`clip_box`, 8 dòng) | cắt về trong ảnh, giữ lớp |
| BAD_CLASS_NAME | 2 | máy (`rename_classes`, 1 lần ghi) | ghi lại `names` đúng cấu hình |
| MISSING_LABEL_FILE | 6 ảnh | **người** | máy không được bịa nhãn (`needs_label`) |
| POSSIBLE_MISSING / WRONG_CLASS | 53 / 18 | **người** | ngữ nghĩa, model chỉ nghi ngờ |
| POSSIBLE_LOOSE_BOX / FALSE_POS | 28 / 29 | **người** | model lớn cũng có thể sai |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE, CLASS_RARE | 12, 6, 3, 4 | **người** | chỉ cảnh báo |

`05_review_queue.csv` xếp theo trọng số của từng mã (`review.weights`): ảnh dính mã nặng như `NEEDS_LABEL` (10), `WRONG_CLASS` (3), `MISSING`/`FALSE_POS` (2) lên đầu, ảnh chỉ có `BOX_TINY` (0,3) xuống cuối. Cả 6 ảnh `NEEDS_LABEL` nằm trong 80 ảnh được duyệt.
Trong 80 ảnh đó người duyệt xử lý chủ yếu lỗi ngữ nghĩa nặng: `WRONG_CLASS` 18 → 3, `MISSING` 53 → 13 (v2 → v3); còn `LOOSE_BOX` 28 → 20 và `FALSE_POS` 24 → 21 vì trọng số thấp. 45 ảnh chưa duyệt chứa chủ yếu `LOOSE_BOX` (16) và `FALSE_POS` (11).

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | DUP_IMAGE_NEAR: 1,00/0,50 → 1,00/0,67 | Xoá ảnh là hành động bắt buộc nên ưu tiên precision. Recall đứng yên ở 0,67 trong khoảng 4–14 trên calib, nên chọn mức giữa đã kiểm trên raw (xem dưới). |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING 0,50/1,00 → 0,57/1,00; WRONG_CLASS 0,56/0,83 → 0,62/0,83; LOOSE_BOX 0,29/0,40 → 0,20/0,20 | Là cảnh báo cho người nên ưu tiên recall. 0,6 là mức cao nhất mà recall của MISSING vẫn 1,00; từ 0,7 trở đi MISSING mất recall (0,88; 0,75 ở 0,8), tức lỗi lọt vào dataset. Đánh đổi: LOOSE_BOX kém đi (chỉ 5 lỗi chèn). |

**Chỗ calibration đánh lừa tôi:** precision của `DUP_IMAGE_NEAR` là 1,00 ở **mọi** ngưỡng, và `phash_dist=16` cho recall cao nhất (0,83), nên dễ chọn 16. Nhưng calib chỉ có 30 ảnh khác nhau. Trên raw, `phash_dist` 4 / 8 / 16 loại lần lượt 19 / 21 / 31 ảnh. Tôi ghép các cặp bị loại thêm ở 16 để xem (`work/viz_pairs/pairs.png`): trong **12** ảnh loại thêm so với mốc 4, chỉ **4** là bản sao thật (img_0084, img_0186, img_0223, img_0101); **8 ảnh còn lại là cảnh hoàn toàn khác** (ví dụ img_0011 sân tennis bị coi trùng img_0008 người trượt tuyết; img_0013 bàn laptop bị coi rò rỉ với test_087 là trận bóng chày). Vì vậy chọn 8: mốc này chỉ loại thêm 2 ảnh so với 4 và cả hai đều đúng (img_0223 phash 6; img_0101 rò rỉ test).

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) Chứng minh gate chặn: `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` → không có người duyệt nên 6 ảnh thiếu file nhãn còn nguyên, kết luận **REWORK — còn 6 lỗi bắt buộc chưa sửa**, **mã thoát 20**, log ghi "KHÔNG xuất", và thư mục `work/exp_nb` **không được tạo**.
(b) Điểm mù có bằng chứng:
1. **Ảnh gần trùng với phash 10**: img_0186 và img_0061 là cùng một ảnh (ghế đá) nhưng ở mốc `phash_dist=8` không bị bắt, nên vẫn nằm trong dataset. Hạ thấp hơn thì phải chấp nhận xoá nhầm (xem mục 3).
2. **Box lỏng nhẹ**: trên calib, `POSSIBLE_LOOSE_BOX` chỉ đạt recall 0,40 ở conf 0,25 và 0,20 ở conf 0,6, tức phần lớn box lỏng không bị cờ.
3. **Nhãn sai mà model lớn cũng nhận định giống**: `second_opinion` chỉ so với yolo26l, nên nếu cả nhãn máy lẫn model cùng nhầm (ví dụ car/truck) thì không có cờ nào (chưa đo được trên raw vì không có đáp án).

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Train trên Colab T4: `yolo26n`, 20 epoch, imgsz 640, 2 seed (0, 1), cùng val (`gold_val`, 40 ảnh) và test (100 ảnh). `clean` là **bản nháp Hold** (chưa phát hành). Nguồn: `submission/results/comparison.md`.

| biến thể | #ảnh train | seed | mAP50 (TB ± độ lệch) | mAP50-95 | precision | recall |
|---|---:|---:|---|---|---|---|
| raw | 224 | 2 | 0,726 ± 0,000 | 0,512 ± 0,004 | 0,764 ± 0,061 | 0,649 ± 0,028 |
| clean | 203 | 2 | 0,699 ± 0,025 | 0,486 ± 0,013 | 0,796 ± 0,050 | 0,596 ± 0,049 |

Chênh mAP50 (clean − raw) = **−0,027**, xấp xỉ **một độ lệch chuẩn giữa các seed của clean** (0,025; riêng 2 seed của clean cách nhau 0,035: 0,681 và 0,716). **Chưa kết luận được** rằng clean tốt hơn hay kém hơn raw: chênh nằm trong nhiễu của 2 seed, test chỉ 100 ảnh. Độ lệch 0,000 của raw chỉ là hai seed tình cờ trùng nhau (0,7256 và 0,7259), không chứng minh raw ổn định.
Theo lớp (AP50 trung bình 2 seed, raw → clean): car 0,738 → 0,741; person 0,823 → 0,824; bus 0,695 → 0,695; **truck 0,648 → 0,536**. Toàn bộ chênh lệch đến từ lớp truck, nhưng trên test truck chỉ có 24 box và hai seed của clean cho truck 0,484 và 0,588 (cách nhau 0,10, bằng cỡ chênh raw−clean 0,11), nên chênh này cũng nằm trong nhiễu.

Giả thuyết và cách kiểm:
1. **Nhiễu của lớp ít mẫu**: truck chỉ có 24 box test và 41 box train trong clean (32 trong raw). Kiểm bằng cách train thêm ≥ 3 seed và xem khoảng chồng lấn của AP truck.
2. **Rò rỉ test làm raw được lợi**: `raw` còn 5 ảnh `LEAK_TEST` trùng ảnh test (và các bản trùng gần). `clean` đã loại chúng, nên điểm `raw` có thể bị thổi phồng. Kiểm bằng cách train `raw` sau khi bỏ riêng 5 ảnh đó, so với `raw` gốc.
3. **Nhãn máy còn lại trong clean**: còn 38/203 ảnh có cảnh báo chưa duyệt (chủ yếu `LOOSE_BOX` và `FALSE_POS`), nên clean chưa phải "dữ liệu sạch" tuyệt đối. Kiểm bằng `oracle` (nhãn người, cùng ảnh): nếu oracle cao hơn clean rõ rệt thì nhãn còn sót đang kéo điểm xuống.
Việc tiếp theo: thêm seed, chạy `oracle`, và xem lại cảnh báo của Ultralytics ở bước train `raw` để biết số ảnh `raw` thật sự được dùng.

## 6. Quyết định và ghi chú AI
(a) **Quyết định cuối: Hold.** Để thành Release cần ≤ 20/203 ảnh còn cảnh báo (hiện 38), tức người duyệt thêm ít nhất 18 ảnh có cảnh báo (nếu mỗi ảnh được duyệt xong thì cảnh báo của nó coi như xử lý), nghĩa là mở rộng ngân sách duyệt vượt 80 ảnh hoặc giảm bớt cờ giả của `FALSE_POS` (precision 0,31 trên calib). Không hạ `conf` chỉ để hàng đợi vừa, vì như vậy là Release giả do checker bỏ sót.

(b) **Có dùng AI** (Claude Code) để viết 4 module theo docstring và test.
- Prompt chính: đưa đề, docstring và test của từng module, yêu cầu viết `label_format`, `gate`, `autofix`, `second_opinion` không viết cứng ngưỡng.
- Cách kiểm: chạy `pytest` (79 passed), tự chạy `autofix` trên file nhãn thử có dòng trống và dòng dính 2 lỗi, chạy pipeline và đối chiếu từng cặp ảnh bị loại bằng mắt.
- Một lần AI sai: khung `label_format` đầu tiên chỉ có chú thích bước 1–6 mà chưa có code, nên 12/14 test fail cho đến khi code được điền; ngoài ra AI từng đề xuất `phash_dist=4` rồi mới bị xem ảnh trên raw đổi thành 8.
