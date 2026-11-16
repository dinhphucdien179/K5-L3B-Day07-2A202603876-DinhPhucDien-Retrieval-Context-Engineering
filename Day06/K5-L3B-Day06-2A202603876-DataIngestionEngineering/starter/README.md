# Pipeline nhập liệu và tìm kiếm tài liệu

Mã nguồn thực hiện chuỗi xử lý PDF → văn bản theo trang → chunk → embedding → PostgreSQL + pgvector → đánh giá top-3. Corpus gồm 39 trang nội dung thuộc báo cáo *2022 Vietnam Poverty and Equity Assessment* của World Bank, sử dụng theo giấy phép CC BY 3.0 IGO.

## Cài đặt và chạy

Xem [hướng dẫn cài đặt](../docs/INSTALLATION.md) để tạo môi trường **Python 3.12**, cài thư viện và khởi động PostgreSQL. Hướng dẫn có hai lựa chọn: **venv** và **Conda (khuyến khích)**. Mô hình embedding chạy trên CPU; không cần API key.

Windows dùng [WSL2](../docs/INSTALLATION.md#windows-wsl2); macOS dùng [container Linux](../docs/INSTALLATION.md#macos-docker-desktop). Các lệnh Python trực tiếp dưới đây dành cho Linux/WSL2. Với macOS, dùng các lệnh `docker compose run` trong hướng dẫn riêng.

Sau khi cài đặt và kích hoạt môi trường, chạy từ thư mục gốc của repository:

```bash
python starter/scripts/check_setup.py
cd starter
python -m src.run preflight
python -m src.run validate
python -m src.run ingest
python -m src.run evaluate --split dev
python -m src.run evaluate --split test
cd ..
DAY6_TEST_DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_test python -m pytest -q
```

Lệnh kiểm thử dùng URL của database test trong cấu hình Docker mẫu; thay URL nếu cấu hình kết nối khác. Corpus và benchmark đã có trong repository. Lệnh `fetch` ở tài liệu cài đặt dùng để tải lại PDF và đối chiếu nguồn; không cần tải lại để chạy trên bản corpus kèm theo.

## Cấu trúc mã nguồn

| Đường dẫn | Nội dung |
|---|---|
| `config/pipeline.json` | Model, giới hạn tài nguyên, chunking và đường dẫn dữ liệu |
| `src/fetching.py` | HTTP session, pacing, retry, giới hạn dung lượng và cache có checksum |
| `src/ingestion.py` | Đọc PDF/JSONL và chuẩn hóa văn bản |
| `src/chunking.py` | Cắt chunk, tạo ID và giữ offsets trong trang nguồn |
| `src/embeddings.py` | Sentence Transformers, kiểm tra token và cache vector |
| `src/store.py` | Nạp dữ liệu theo transaction, lưu pgvector và lọc metadata |
| `src/evaluation.py` | Đối chiếu nguồn, trang và evidence; tính Hit@1/Hit@3 |
| `src/run.py` | CLI chạy pipeline |
| `scripts/` | Kiểm tra cài đặt, kiểm chứng nguồn và tạo phiếu đánh giá |
| `tests/` | Kiểm thử dữ liệu, cache, provenance và transaction |

Các đường dẫn trong cấu hình được tính từ thư mục gốc repository. Thay đổi thư mục đặt repository không yêu cầu sửa mã nguồn.

## Ba chiến lược

| Chiến lược | Chunking | Truy xuất |
|---|---|---|
| A | 300 ký tự, overlap 30 ký tự | Cosine, không lọc metadata |
| B | Ưu tiên đoạn, giới hạn 300 ký tự; đoạn dài được cắt ở ranh giới từ | Cosine, không lọc metadata |
| C | Dùng chung chunk và vector của B | Cosine, thêm filter do ngữ cảnh câu hỏi cung cấp |

PDF trích xuất ít giữ dòng trống giữa các đoạn. Vì vậy, nhiều chunk B được tạo bằng quy tắc cắt đoạn dài; đây là một giới hạn khi diễn giải kết quả. C không phát sinh thêm document embedding hay bản sao index.

Model dùng chung là `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều, vector float32 chuẩn hóa. Truy xuất dùng cosine exact search trong PostgreSQL. CLI đặt ngân sách native threads trước khi nạp thư viện tính toán và từ chối văn bản vượt giới hạn token.

## Dữ liệu và kết quả

- [Nguồn dữ liệu và cách chọn trang](../data/README.md).
- [Benchmark và quy tắc chia dev/test](../benchmark/README.md).
- [Báo cáo thí nghiệm](../report/individual/2A202603876_DinhPhucDien.md).
- [Bảng kết quả](../results/benchmark-summary.json).
- [Đánh giá metadata và grounding](../results/manual-review/test-review.md).
- [Kiểm soát lỗi và tài nguyên](../docs/HARDENING.md).

Mỗi lượt chạy tạo một thư mục trong `results/` với cấu hình, phiên bản thư viện, thời gian, tài nguyên và đầu ra. `evaluate` lưu toàn bộ top-3 và tạo phiếu đánh giá nội dung. Chọn chiến lược trên dev trước khi chạy test; lệnh test kiểm tra fingerprint của kết quả lựa chọn dev.
