# Tái lập Day06 trong project Day07

Bản Day06 được nộp trong `Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering/`.
Quy trình này dùng code, corpus, benchmark và cấu hình trong bản copy đó, không
phụ thuộc project gốc ở `buoi6/`, cache cũ hoặc đường dẫn home của tác giả.

## Điều kiện ban đầu

- Windows: chạy các lệnh trong Ubuntu WSL2, bật WSL Integration của Docker Desktop.
- macOS: chạy trong Terminal và mở Docker Desktop.
- Linux: chạy trong Bash, dùng Docker Engine hoặc Docker Desktop.
- Docker Engine hoặc Docker Desktop đang chạy, kèm Compose; tài khoản chạy lệnh
  có quyền truy cập Docker.
- Internet để tải image, thư viện Python và model embedding lần đầu.
- Ít nhất 4 GiB RAM khả dụng và dung lượng đĩa cho image, model và database.
- Cổng `127.0.0.1:55433` chưa bị dịch vụ khác chiếm.

Python 3.12 và thư viện được cài trong image. Không cần Python, Conda, PostgreSQL
hoặc API key trên máy chủ để tái lập riêng Day06.

Nếu muốn chạy bonus hoặc kiểm tra offline bằng Python trên máy chủ, tạo venv
hoặc Conda theo [hướng dẫn môi trường cho từng hệ điều hành](RUN.md). Tên môi
trường và đường dẫn cài Python do người chạy chọn.

## Chạy từ thư mục gốc Day07

```bash
bash scripts/reproduce_day06.sh
```

Script build môi trường, khởi động PostgreSQL + pgvector, kiểm tra dữ liệu/model,
ingest, đánh giá dev rồi test, và chạy kiểm thử kỹ thuật. Script dừng nếu một bước
lỗi. Lượt đầu không cần cache có sẵn; các lượt sau tái sử dụng cache hợp lệ.
Script không xóa database hay cache để ép chạy lạnh.

Các ví dụ dùng Docker không kèm `sudo` để dùng chung giữa các hệ điều hành.
Nếu Linux yêu cầu quyền quản trị, chạy `sudo bash scripts/reproduce_day06.sh`
và thêm `sudo` trước các lệnh `docker` tương ứng. Trên Windows/macOS với
Docker Desktop, giữ lệnh như ví dụ.

Image được kiểm thử trên Linux x86-64. Nếu Mac Apple Silicon gặp lỗi không có
wheel CPU đã ghim, chọn chạy image x86-64 qua Docker Desktop:

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
bash scripts/reproduce_day06.sh
```

Giữ biến này trong terminal khi tiếp tục chạy container Day07. Đây là lựa chọn
kiến trúc image theo máy, không phải đường dẫn Python hoặc môi trường cá nhân.
Biến được mô tả trong [tài liệu Docker CLI](https://docs.docker.com/reference/cli/docker/).

Muốn tải lại PDF đã ghim checksum và tái tạo corpus trước khi ingest:

```bash
bash scripts/reproduce_day06.sh --fetch
```

Mặc định dùng corpus đã kèm trong bài nộp. `--fetch` tải nguồn nhưng vẫn có thể
tận dụng cache hợp lệ nếu đã chạy trước đó. Không chỉnh đáp án hoặc benchmark
khi tái lập. Kết quả mỗi lần chạy được lưu trong thư mục `results/` của Day06;
quyết định chọn cấu hình tại `results/dev-selection.json` được cập nhật bằng dev.
Chạy lại benchmark Day06 không thay thế benchmark agent của Day07.

Các đường dẫn được tính từ vị trí script và Compose, nên có thể di chuyển hoặc
đổi tên thư mục ngoài của project mà không sửa mã nguồn. Compose tự cấp kết nối
database local mẫu; không cần tạo `.env`.

## Vị trí lưu dữ liệu và dừng dịch vụ

Model/cache được ghi vào `.cache/` của bản Day06. PostgreSQL nằm trong Docker
named volume `day07-day06_pg_data`, do Docker Engine hoặc Docker Desktop quản lý.
Không cần gắn một thư mục dữ liệu PostgreSQL tại đường dẫn riêng trên máy tác giả.

Dừng dịch vụ, giữ dữ liệu:

```bash
docker compose -f Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering/starter/docker-compose.yml -p day07-day06 stop
```

Khởi động lại database đã có:

```bash
docker compose -f Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering/starter/docker-compose.yml -p day07-day06 up -d --wait postgres
```

Cache, môi trường cài đặt và Docker volume không cần nộp. Nộp code, cấu hình,
corpus được phép chia sẻ, benchmark, kết quả và hướng dẫn. Đây là bước chuẩn bị
dữ liệu Day06; tiếp tục chạy agent và đánh giá theo [RUN.md](RUN.md).
