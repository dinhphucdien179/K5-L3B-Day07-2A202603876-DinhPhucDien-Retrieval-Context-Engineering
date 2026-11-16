# Đánh giá chất lượng đoạn và bằng chứng

Mẫu đánh giá gồm 30 phiếu coherence tại cùng 10 vị trí nguồn, 45 bản ghi metadata trong top-3 của tập test và 15 trường hợp grounding. Nội dung đoạn, vị trí nguồn và lý do được lưu cùng điểm số để có thể đối chiếu.

## Coherence

Thang điểm 0–2 phản ánh khả năng hiểu riêng từng đoạn: 0 là thiếu ý hoặc chủ thể đến mức không hiểu được; 1 là hiểu được một phần nhưng thiếu ngữ cảnh; 2 là tự hiểu được và giữ trọn ý. Chọn cùng 10 vị trí từ các trang đầu đã sắp xếp; nếu nhiều đoạn phủ một vị trí, chọn đoạn có `char_start` nhỏ nhất, tiếp theo là `char_end` và ID. Offsets dùng khoảng nửa mở `[start, end)` trên văn bản chuẩn hóa.

| Cấu hình | Số phiếu | Mức 0 | Mức 1 | Mức 2 | Trung bình /2 |
|---|---:|---:|---:|---:|---:|
| A | 10 | 0 | 10 | 0 | 1,00 |
| B | 10 | 0 | 9 | 1 | 1,10 |
| C | 10 | 0 | 9 | 1 | 1,10 |

B và C dùng chung đoạn nên có tổng cộng 20 đoạn khác nhau. Một mẫu ở trang PDF 54 giữ đủ nội dung phương pháp small area estimation và đạt mức 2 ở B/C. Các mẫu khác còn thiếu chủ thể, điều kiện hoặc phần kết thúc nhận định. Mẫu chỉ thuộc chương 1; chênh lệch 0,10 điểm xuất phát từ một trường hợp, chưa đủ để suy rộng.

- [Điểm, lý do và vị trí nguồn](coherence.json).
- [Phân bố điểm](coherence-summary.json).
- [Mẫu đối chiếu ẩn danh](coherence-review-input.json) và [lượt đọc đối chiếu](coherence-independent-review.json).

## Metadata và grounding

Metadata được đối chiếu với PDF, snapshot API và corpus. Grounding xét cả ba đoạn trả về theo thang 0–2: không có bằng chứng, có nhưng thiếu điều kiện cần thiết, hoặc đủ để trả lời và truy nguồn.

| Cấu hình | Metadata đủ và đúng | Tuân thủ filter trên test | Grounding mức 0 / 1 / 2 | Trung bình /2 |
|---|---:|---:|---:|---:|
| A | 15/15 | N/A | 1 / 2 / 2 | 1,20 |
| B | 15/15 | N/A | 0 / 2 / 3 | 1,60 |
| C | 15/15 | 1/1 | 0 / 2 / 3 | 1,60 |

[Bảng từng câu và phân tích](test-review.md), [metadata chi tiết](test-metadata-audit.json) và [grounding chi tiết](test-grounding.json) cung cấp bằng chứng cho các kết quả trên. B/C trùng kết quả ở bốn câu test không có filter; 15 trường hợp tương ứng với 11 bộ top-3 khác nhau.

## Phương pháp đánh giá nội dung

Coherence và grounding được đánh giá bằng hai lượt đọc của mô hình với Codex theo cùng rubric. Lượt đối chiếu dùng ID ẩn danh, không nhận tên cấu hình hay điểm retrieval; lượt đọc chính đã biết kết quả tổng thể. Điểm và lý do được đối chiếu theo từng trường hợp. Metadata dùng kiểm tra bằng chương trình. Đây là giới hạn của phương pháp đánh giá; các lượt đọc không đại diện cho độ đồng thuận giữa những người chấm độc lập. Phương pháp được trình bày thêm trong [báo cáo](../../report/individual/2A202603876_DinhPhucDien.md).

Tạo bộ phiếu coherence khác theo [hướng dẫn cài đặt và chạy](../../docs/INSTALLATION.md). Generator chỉ chuẩn bị mẫu, không gán điểm. Kiểm tra tính nhất quán của bộ kết quả đi kèm bằng `python results/manual-review/finalize_test_review.py --check` từ thư mục gốc, trong môi trường Python 3.12 đã kích hoạt.
