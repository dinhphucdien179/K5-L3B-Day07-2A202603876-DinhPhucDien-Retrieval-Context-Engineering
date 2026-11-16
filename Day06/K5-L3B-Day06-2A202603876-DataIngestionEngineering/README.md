# Truy xuất tài liệu về nghèo và phúc lợi tại Việt Nam

Bài thực hành Data Ingestion Engineering xây dựng quy trình lấy tài liệu, chuẩn hóa văn bản, chia đoạn, tạo embedding và lưu vào PostgreSQL với pgvector. Thí nghiệm so sánh hai cách chia đoạn và ảnh hưởng của bộ lọc chương đối với khả năng tìm bằng chứng trả lời câu hỏi.

Nguồn dữ liệu là báo cáo *From the Last Mile to the Next Mile — 2022 Vietnam Poverty and Equity Assessment* của World Bank, giấy phép CC BY 3.0 IGO. Corpus gồm **39 trang nội dung**, **119.228 ký tự** thuộc chương 1 và 2. Bộ đánh giá có **20 câu hỏi**, chia thành 15 câu phát triển và 5 câu kiểm tra.

## Cài đặt

Project sử dụng **Python 3.12**. Linux chạy trực tiếp, Windows dùng WSL2 và macOS chạy pipeline trong container Linux. [Hướng dẫn theo hệ điều hành](docs/INSTALLATION.md#chọn-cách-chạy-theo-hệ-điều-hành) trình bày các bước tương ứng. Trên Linux/WSL2 có hai lựa chọn tạo môi trường:

1. **venv:** tạo môi trường `.venv` trong thư mục project.
2. **Conda — khuyến khích:** tạo môi trường từ `starter/environment.yml`.

[Hướng dẫn cài đặt và chạy](docs/INSTALLATION.md) trình bày cách tạo môi trường, cài thư viện, khởi tạo PostgreSQL, lấy dữ liệu và thực hiện thí nghiệm. Model embedding chạy trên CPU; không cần API key.

Sau khi cài môi trường và khởi động cơ sở dữ liệu theo hướng dẫn, chạy từ thư mục gốc:

```bash
cd starter
python -m src.run preflight
python -m src.run fetch
python -m src.run validate
python -m src.run ingest
python -m src.run evaluate --split dev
python -m src.run evaluate --split test
```

Các lệnh trên dùng kết nối `DATABASE_URL` trong `starter/.env`. Trường hợp cài PostgreSQL bằng công cụ quản lý local, sử dụng các lệnh tương ứng trong [hướng dẫn cài đặt](docs/INSTALLATION.md).

## Thiết kế thí nghiệm

| Cấu hình | Chia đoạn | Truy xuất |
|---|---|---|
| A | 300 ký tự, chồng lặp 30 ký tự | Không lọc |
| B | Ưu tiên ranh giới đoạn; đoạn dài được cắt tại ranh giới từ, tối đa 300 ký tự | Không lọc |
| C | Dùng chung đoạn, vector và index với B | Lọc chương khi câu hỏi có phạm vi được cung cấp trước |

Cả ba cấu hình dùng `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, vector 384 chiều và tìm kiếm cosine chính xác trong pgvector. Cấu hình A được chọn trên tập phát triển theo Evidence Hit@3, tiếp theo là Hit@1 và số đoạn lưu trữ.

## Kết quả

| Cấu hình | Số đoạn | Dev Evidence Hit@3 | Test Evidence Hit@3 | Coherence /2 | Grounding test /2 |
|---|---:|---:|---:|---:|---:|
| A | 459 | 4/15 | 2/5 | 1,00 | 1,20 |
| B | 421 | 2/15 | 1/5 | 1,10 | 1,60 |
| C | 421 | 3/15 | 1/5 | 1,10 | 1,60 |

Metadata đúng và đủ ở 45/45 bản ghi top-3 được kiểm tra; C tuân thủ bộ lọc ở 1/1 câu test có yêu cầu lọc. Chỉ số chứa đủ đoạn trích gold và mức đủ nghĩa để trả lời được phân tích riêng trong báo cáo. Kết quả trên năm câu test chỉ phản ánh corpus và cấu hình của thí nghiệm này.

## Tài liệu và dữ liệu

| Nội dung | Đường dẫn |
|---|---|
| Báo cáo cá nhân | [report/individual/2A202603876_DinhPhucDien.md](report/individual/2A202603876_DinhPhucDien.md) |
| Cài đặt và lệnh chạy | [docs/INSTALLATION.md](docs/INSTALLATION.md) |
| Thiết kế hệ thống | [docs/PROJECT_EXPLAINED.md](docs/PROJECT_EXPLAINED.md) |
| Nguồn dữ liệu, chọn trang và giấy phép | [data/README.md](data/README.md), [data/ATTRIBUTION.md](data/ATTRIBUTION.md) |
| Câu hỏi và cách đánh giá | [benchmark/README.md](benchmark/README.md) |
| Chỉ số và kết quả top-3 | [results/benchmark-summary.json](results/benchmark-summary.json) |
| Coherence, metadata và grounding | [results/manual-review/README.md](results/manual-review/README.md) |
| Thiết kế kiểm thử | [docs/HARDENING.md](docs/HARDENING.md) |
| Thông tin học viên và cấu trúc bài nộp | [STUDENT.md](STUDENT.md), [SUBMISSION.md](SUBMISSION.md) |
