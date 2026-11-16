# Benchmark bonus phiên bản 2

Bộ test cũ đã được dùng để phân tích và sửa lỗi agent. Kết quả 26/30 vẫn giữ
nguyên ở `results/bonus/test-gemini-01`; không dùng nó để đo độ đúng mới.
Mã nguồn chính xác của lượt cũ được lưu và kiểm tra checksum ở
`results/bonus/frozen-runtime-v1`.

Phiên bản này giữ 18 câu dev để tiếp tục phát triển và khóa **30 câu test mới**
trước khi chạy API với bản sửa. Phân bố test: 6 bảng, 5 sơ đồ khái niệm khác
nhau, 5 biểu đồ, 4 multi-hop từ ít nhất hai trang, 4 text và 6 thiếu bằng chứng.
Các câu mới hỏi những ô, nhánh hoặc thông tin khác; không đổi cách diễn đạt để
hỏi lại đáp án dev. Vẫn dùng cùng báo cáo World Bank và có tái sử dụng một số
hình/bảng: đây là kiểm tra theo tài liệu, chưa phải đánh giá tìm kiếm mở hoặc
kiểm tra mù do người ngoài tạo. Không suy độ khó hai phiên bản bằng nhau.

Không nhân bản corpus: `freeze.json` khóa checksum của toàn bộ index dùng chung
ở `data/bonus/corpus.jsonl` (232 trang, 437 bản ghi). `source-audit.json` lưu các
ảnh gốc đã đọc và checksum. Từng câu có vùng nguồn, đơn vị, đáp án và dung sai
đặt trước khi thử; câu thiếu bằng chứng có audit toàn bộ 232 trang và kiểm tra
trang nguồn gần chủ đề. Nhãn được AI hỗ trợ đọc từ PDF; người học chưa xác nhận
độc lập. Không đưa gold, nhóm câu hoặc vùng chuẩn vào agent.

Tạo dữ liệu bằng `scripts/prepare_bonus_holdout_v2.py`; script từ chối ghi đè.
Không chạy lại script khi thư mục đã tồn tại. Hash dev/test/corpus được kiểm tra
mỗi lần chạy. `--dataset data/bonus-v2` chọn đúng phiên bản. Khi test mới đã chạy,
nếu dùng lỗi của nó để sửa tiếp, cần test mới nữa trước khi báo điểm độc lập.
