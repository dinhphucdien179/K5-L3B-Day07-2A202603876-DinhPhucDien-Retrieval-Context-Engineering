# Nội dung bài nộp

Bài làm của Đinh Phúc Diên, MSSV **2A202603876**, lớp **L3B**. Báo cáo chính nằm tại [report/individual/2A202603876_DinhPhucDien.md](report/individual/2A202603876_DinhPhucDien.md).

## Đối chiếu yêu cầu

| Yêu cầu | Nội dung bài làm | Tài liệu |
|---|---|---|
| Tối thiểu 30 trang nội dung hợp lệ | 39 trang PDF, 119.228 ký tự; chương 1 có 19 trang, chương 2 có 20 trang | [Manifest](data/manifest.json), [giấy phép và chọn trang](data/README.md) |
| Tối thiểu 20 câu hỏi, chia dev/test | 15 câu dev, 5 câu test; 4 câu có phạm vi lọc | [Benchmark](benchmark/README.md) |
| Embedding thật và vector store | MiniLM đa ngữ, 384 chiều; PostgreSQL 16.16 và pgvector 0.7.4 trong thí nghiệm | [Cấu hình](starter/config/pipeline.json), [phiên bản](artifacts/environment.json) |
| Ba cấu hình có so sánh kiểm soát | A thay quy tắc chia đoạn; B/C dùng chung index và chỉ khác bộ lọc | [Nhật ký thí nghiệm](artifacts/experiment_log.csv) |
| Kết quả dev/test và top-3 | 60 trường hợp câu hỏi/cấu hình, có nội dung đoạn, điểm và metadata | [Tổng hợp kết quả](results/benchmark-summary.json) |
| Năm khía cạnh đánh giá | Hit@1/Hit@3; 30 phiếu coherence; 45 bản ghi metadata; 15 phiếu grounding; phân tích tài nguyên và đánh đổi | [Báo cáo](report/individual/2A202603876_DinhPhucDien.md) |
| Khả năng tái lập | Python 3.12; cài bằng venv hoặc Conda; có lệnh lấy dữ liệu, ingest, đánh giá và kiểm thử | [Cài đặt](docs/INSTALLATION.md) |

## Thành phần lưu trong repository

`starter/` chứa mã nguồn, cấu hình và kiểm thử. `data/` lưu văn bản chuẩn hóa, manifest, metadata nguồn và attribution. `benchmark/` lưu câu hỏi, đáp án, evidence và checksum. `results/` lưu chỉ số, kết quả truy xuất, đánh giá nội dung và bằng chứng kiểm tra. `artifacts/` lưu phiên bản thư viện và nhật ký thí nghiệm.

Môi trường Python, cache model, binary và dữ liệu PostgreSQL không nằm trong bộ bài nộp. PDF gốc được tải lại theo URL và checksum trong khai báo nguồn; corpus văn bản và trích đoạn được ghi nguồn theo CC BY 3.0 IGO. Cấu hình kết nối thực được lưu trong `.env`, không đưa vào Git.

Repository: [K5-L3B-Day06-2A202603876-DataIngestionEngineering](https://github.com/dinhphucdien179/K5-L3B-Day06-2A202603876-DataIngestionEngineering). Nộp đường dẫn repository qua kênh do giảng viên quy định.
