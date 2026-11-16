# Day 7 — Agentic RAG

**Đinh Phúc Diên — 2A202603876 — L3B.** Bài thực hành dùng PostgreSQL/pgvector
và embedding Day06 cho phần cơ bản, mở rộng toàn bộ báo cáo World Bank 232 trang
cho phần bonus.

- [Báo cáo hoàn chỉnh](report/individual/2A202603876_DinhPhucDien.md): dữ liệu, thí nghiệm retrieval, đánh giá agent và bonus theo mẫu đề.
- [Cài đặt và lệnh chạy trên Windows, macOS, Linux](docs/RUN.md): lựa chọn 1 — venv; lựa chọn 2 — Conda (khuyến khích). [Chuẩn bị Day06](docs/DAY06_SETUP.md).
- [Code](src/README.md), [benchmark cơ bản](data/day07/README.md), [benchmark bonus hiện tại](data/bonus-v2/README.md).
- [Kiểm tra bài nộp](results/submission/verification.json): unit test, checksum, nhãn, số liệu và đường dẫn tài liệu.

Phần cơ bản chọn hybrid mở rộng một chunk mỗi phía trên dev; test có context đủ
evidence 5/5, điểm trả lời 2,000/2, citation hợp lệ 6/8. Bonus đạt 30/30 trên bộ
test mới, không có câu lỗi hệ thống; kết quả cũ 26/30 được giữ để đối chiếu.
Nhãn có AI hỗ trợ đọc nguồn, chưa có xác nhận độc lập của người học.

```bash
python scripts/verify_submission.py
```

Chạy lệnh trên sau khi tạo và kích hoạt môi trường Python theo hướng dẫn.
Lệnh kiểm tra offline, không gọi API. Các lệnh dùng model thật nằm trong
hướng dẫn chạy. Phần đề bài gốc được giữ bên dưới.

**Bài cá nhân · Python 3.11+ · tiếp nối Day 6**

Dùng embedding và vector store từ Day 6 để xây một agent biết tìm bằng chứng, trả lời có nguồn và nhận biết khi không đủ thông tin. Bạn tự chọn kiến trúc, số tool và cách tổ chức retrieval.

> **Tùy chọn:** [Gợi ý dùng AI để lập trình](AGENT_SETUP.md) giúp bạn làm lab; phần này không bắt buộc và không tính điểm.

## Bài cần làm

![Agent tìm tài liệu trong kho Day 6 và trả lời có nguồn](assets/retrieval-pipeline.svg)

1. Kết nối dữ liệu, embedding và vector store Day 6.
2. Xây agent dùng model thật và ít nhất một khả năng truy xuất dữ liệu. Agent có thể dùng nhiều tool và nhiều lượt gọi.
3. Thử **ít nhất 3 phương pháp retrieval khác nhau**, trong đó có dense retrieval dùng vector store Day 6. Tự chọn các phương pháp còn lại; xem [gợi ý](GUIDE.md#2-thử-các-phương-pháp-retrieval).
4. Thử nhiều cấu hình, benchmark, phân tích lỗi và chọn cấu hình tốt trên **dev**; sau đó đánh giá trên **test**.

Benchmark tối thiểu có **24 câu**: dev gồm 15 câu có đáp án và 2 câu thiếu bằng chứng; test gồm 5 câu có đáp án và 2 câu thiếu bằng chứng. Xem [benchmark](BENCHMARK.md) và [rubric](RUBRIC.md).

## Thử thách nâng cao · +15 điểm

Index một tài liệu thực tế từ **100 trang** có bảng, ảnh và biểu đồ; xây agent truy xuất và trả lời các câu hỏi về nội dung đó. Hoàn thành [thử thách nâng cao](ADVANCED.md) và đạt **ít nhất 90% benchmark test** để nhận 15 điểm bonus. Phần cơ bản tối đa 85 điểm; toàn bài tối đa 100 điểm.

## Bắt đầu

1. Đọc [hướng dẫn](GUIDE.md), [rubric](RUBRIC.md) và [quy tắc](RULES.md).
2. Tạo repo cá nhân theo [cách nộp bài](SUBMISSION.md), chuẩn bị đầu ra Day 6 và model hỗ trợ tool calling.
3. Dùng hoặc thay thế [starter](starter/README.md); bạn cần kết nối model và vector store thật.
4. Chạy `python -m unittest discover -s tests -v`. Test mock chỉ kiểm tra code, không phải benchmark agent thật.

![Các bước thử nghiệm trên dev và đánh giá trên test](assets/experiment-loop.svg)

Nộp code, cách chạy, cấu hình, benchmark, trace và [báo cáo](report/individual/2A202603876_DinhPhucDien.md). Thời gian ở [checkpoints](CHECKPOINTS.md) là gợi ý, có thể điều chỉnh theo lớp và phạm vi thử nghiệm.
