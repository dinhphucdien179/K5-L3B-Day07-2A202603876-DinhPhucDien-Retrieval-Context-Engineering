# Kết quả thực nghiệm

Phân tích và các bảng tổng hợp nằm trong [báo cáo chung](../report/individual/2A202603876_DinhPhucDien.md). Thư mục này chứa bằng chứng chạy và nhãn để kiểm tra lại.

| Đường dẫn | Nội dung |
|---|---|
| `day07/retrieval-dev-01/` | Năm cấu hình retrieval chạy bằng câu hỏi dev gốc |
| `day07/agent-dev-01/` | Năm cấu hình agent, 17 câu dev mỗi cấu hình; trace và nhãn đầy đủ |
| `day07/agent-test-01/` | Baseline và hybrid ±1, cùng bảy câu test |
| `day07/selection.json` | Quyết định chọn cấu hình cơ bản bằng dev |
| `day07/benchmark-metrics.csv`, `day07/verification.json` | Chỉ số từng lượt và kiểm tra 99 kết quả agent cơ bản |
| `bonus/dev-gemini-05/layout_text/` | Nhánh text-only đã chạy đủ 18 dev, dùng cho phân tích giai đoạn phát triển |
| `bonus/dev-gemini-06/`, `bonus/test-gemini-01/` | Dev/test bản trước, giữ nguyên kết quả 17/18 và 26/30 |
| `bonus/selection.json`, `bonus/frozen-runtime-v1/` | Selection và bản mã nguồn tương ứng của kết quả cũ |
| `bonus/dev-gemini-07/`, `bonus/test-gemini-02/` | Dev/test hiện tại: 15/18 và 30/30 |
| `bonus/selection-v2.json` | Pipeline hiện tại được khóa trước khi chạy test mới |
| `bonus/v2-case-metrics.csv` | Chỉ số đủ 18 dev và 30 test hiện tại |
| `bonus/*source*.json`, `bonus/*absence*.json`, `bonus/corpus-audit.json` | Đối chiếu nguồn PDF, đính chính và kiểm tra câu thiếu bằng chứng |
| `bonus/dev07-resume-*.json` | Checksum chứng minh các câu dev đã lưu không bị thay khi chạy tiếp |
| `bonus/transport-review.json` | Làm rõ các lỗi HTTP 503 đã phục hồi ở lượt cũ |
| `bonus/docker/` | Bằng chứng build và kiểm tra container, tách với kiểm tra Conda |
| `submission/` | Kiểm tra offline cuối: unit test, checksum, nhãn, số liệu và link bài nộp |

Mỗi trial bonus có trace từng câu, `reviews.json` và `summary.json`. Mỗi trial cơ bản có `traces.json`, `evidence-metrics.json`, `reviews.json` và `review-summary.json`.

Một số file `run.json`, `execution.json`, phiếu chấm hoặc bản chấm dở trong các thư mục dev đã khóa vẫn được giữ: selection kiểm checksum của chúng khi tái lập test. Chúng là dữ liệu kiểm chứng, không phải các bản báo cáo bổ sung. Không chỉnh hoặc xóa những file đó. Nhánh crop chưa hoàn tất ở lượt phát triển `dev-gemini-05` đã được dọn; nhánh text-only hoàn tất và manifest gốc của lượt chạy vẫn được giữ.

Các bản báo cáo cũ, ghi chú tiến độ và lần thử kết nối đã được bỏ khỏi bài nộp. PDF, ảnh và model cache có thể tạo lại theo [hướng dẫn chạy](../docs/RUN.md).
