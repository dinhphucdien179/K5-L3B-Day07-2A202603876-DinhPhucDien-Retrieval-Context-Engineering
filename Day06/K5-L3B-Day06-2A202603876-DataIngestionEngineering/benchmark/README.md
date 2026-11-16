# Benchmark World Bank: nghèo và phúc lợi tại Việt Nam

Corpus dùng các trang nội dung của chương 1–2 trong *From the Last Mile to the Next Mile — 2022 Vietnam Poverty and Equity Assessment*. Bộ câu hỏi được soạn bằng cách đọc nguồn trước khi chạy embedding hoặc truy xuất; không chỉnh câu hỏi, evidence hay filter theo kết quả retrieval.

- `questions.authored.json`: 20 câu hỏi tiếng Anh, đáp án và đoạn evidence nguyên văn đã đối chiếu với corpus chuẩn hóa. Đây là bản soạn, chưa phải kết quả thí nghiệm.
- `questions.json`: finalizer bổ sung document ID, URL, offsets và checksum của trang nguồn; các nguồn bằng chứng thay thế được giữ riêng.
- `evidence_audit.json`: xác nhận vị trí đoạn trích bằng chương trình. Kiểm tra chuỗi không thay thế đánh giá đủ nghĩa của người học.
- `coherence_positions.json`: 10 vị trí nội dung cố định trước retrieval để chấm coherence thủ công.
- `freeze.json`: checksum dữ liệu, bộ câu hỏi, manifest, corpus specification và các đầu vào đánh giá; thay đổi trước retrieval phải có lịch sử amendment.

**Split đã định trước:** q01–q15 là 15 câu dev về chương 1; q16–q20 là 5 câu test về chương 2. Cả 39 trang của corpus vẫn được truy xuất trong A/B/C. Các khái niệm trong cùng báo cáo có thể lặp lại giữa chương; đây là hạn chế của split theo chủ đề, không phải holdout tài liệu hoàn toàn độc lập.

`unit` và `gold_page` là **số trang vật lý của PDF, bắt đầu từ 1**. Metadata `printed_page` lưu số trang in để đối chiếu khi đọc báo cáo. Evidence lấy từ văn xuôi giải thích, không suy đáp án từ hình, trục biểu đồ hay bảng trích xuất lệch cột. Xuống dòng và lỗi khoảng trắng do PDF được giữ nguyên trong đoạn trích; offsets tính trên văn bản chuẩn hóa đang lưu.

**Filter:** q08, q14, q15 dùng `chapter="1"`; q20 dùng `chapter="2"`. `filter_context` giả định người đọc đã chọn chương trong trình xem tài liệu trước khi đặt câu hỏi. A/B không lọc; C dùng đúng scope đầu vào này, không suy chương từ gold và không lọc theo source/page. Với câu khác, C không áp dụng filter và dùng chung index với B.

**Evidence thay thế:** q05 chấp nhận lý do khảo sát không đủ chi tiết địa lý tại trang vật lý 51 và 54; q15 ghi nhận mô tả thu nhập nông nghiệp tăng ít ở trang 65 và 85; q19 ghi nhận nhận định tăng trưởng là động lực chính ở các trang 91, 65 và 92. Các đoạn trích khác nhau được đọc đối chiếu về nghĩa; finalizer còn phát hiện đoạn evidence giống nguyên văn tại những trang khác nếu có. Không ép một câu trả lời đúng phải dẫn duy nhất một trang.

Tiêu chí chọn cấu hình vẫn là Evidence Hit@3 trên dev, tiếp theo Hit@1, rồi số chunk ít hơn; hòa thì A, B, C. Chỉ đọc kết quả test sau khi lựa chọn đã cố định. Hit yêu cầu một chunk thuộc nguồn/trang được chấp nhận và chứa đủ đoạn evidence; evidence bị chia giữa nhiều chunk vẫn là lỗi theo metric chính. Không rút ngắn evidence theo cửa sổ chunk để tăng điểm.

**Ghi nhận trước khi có điểm:** evidence q08 dài 314 ký tự và q20 dài 321 ký tự, lớn hơn giới hạn chunk hiện tại 300 ký tự. Vì metric chính yêu cầu một chunk chứa đủ evidence, hai câu này không thể đạt full-quote hit với giới hạn đó; chúng được giữ làm trường hợp kiểm tra evidence bị phân mảnh. Không rút ngắn đoạn trích hoặc sửa câu test để vừa cửa sổ chunk.

Kết quả được trình bày trong [bảng chỉ số](../results/benchmark-summary.json) và [báo cáo](../report/individual/2A202603876_DinhPhucDien.md). Mẫu đánh giá bổ sung gồm 30 phiếu coherence, 45 bản ghi metadata và 15 trường hợp grounding; [phương pháp và phiếu đánh giá](../results/manual-review/README.md) được lưu cùng nội dung đoạn và vị trí nguồn. Cách sử dụng công cụ hỗ trợ được mô tả trong phần phương pháp của báo cáo. Năm câu test là mẫu nhỏ của corpus này, không xác lập cấu hình tốt nhất tổng quát.
