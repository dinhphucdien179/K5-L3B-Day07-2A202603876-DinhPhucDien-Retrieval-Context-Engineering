# Benchmark Day07

Đóng băng `dev.json` (15 có đáp án, 2 thiếu evidence) và `test.json` (5 có đáp án,
2 thiếu evidence) trước thử nghiệm. Checksum và lý do split ở `freeze.json`.
Dev kế thừa q01–q15 Day06, giữ evidence chính và thay thế. Test là câu mới về
giáo dục, lương doanh nghiệp FDI, lương hộ gia đình, pension và nghèo đô thị/nông
thôn; không dùng lại q16–q20 Day06 đã được xem và phân tích.

Nguồn của mọi evidence là corpus 39 trang Day06, không phải toàn bộ PDF 232
trang. `page` là trang PDF vật lý từ 1; `start`/`end` là offsets ký tự `[start,end)`
trên trang đã chuẩn hóa. Evidence thay thế trong `gold` là quan hệ OR. Benchmark
này không có câu bắt buộc kết hợp nhiều trang; câu nhiều con số cần trả lời đủ
mọi điều kiện. Gold và đáp án chỉ dùng ở evaluator, không truyền vào agent.

Câu thiếu bằng chứng có ghi lý do và phạm vi kiểm tra. Ví dụ nhắc năm tương lai
trong một phép chiếu không phải số liệu quan sát từ khảo sát năm đó. Nhãn thiếu
evidence phải đối chiếu lại khi chấm, không suy chỉ từ việc top-k không tìm được.

`scripts/prepare_day07_benchmark.py` ghi lại quá trình soạn benchmark và từ chối
ghi đè split đã tồn tại. Không cần chạy script khi clone bài vì dữ liệu đã kèm.
Câu hỏi và nhãn được soạn có AI hỗ trợ; offsets kiểm bằng code không thay thế
đối chiếu nội dung với nguồn và người học chịu trách nhiệm kiểm tra.
