# Cài đặt và chạy thí nghiệm

Project sử dụng Python 3.12. Các lệnh đầu tiên chạy từ thư mục gốc repository, nơi có `README.md`, `data/` và `starter/`. Những bước chạy trong `starter/` đều có lệnh `cd` đi kèm.

Cần kết nối Internet để cài thư viện, tải mô hình lần đầu và tải lại PDF nếu muốn đối chiếu nguồn. Mô hình chạy trên CPU, không cần GPU hoặc API key. Cấu hình mặc định dùng 4 native threads, batch embedding tối đa 16 và ngưỡng kiểm tra RSS 2.048 MiB; nên chuẩn bị ít nhất 4 GiB RAM khả dụng cho Python và PostgreSQL.

## Chọn cách chạy theo hệ điều hành

| Hệ điều hành | Môi trường chạy pipeline | Hướng dẫn |
|---|---|---|
| Linux | Python 3.12, venv hoặc Conda | Bước 1–9 bên dưới |
| Windows 10/11 có WSL2 | Python 3.12 trong bản phân phối Linux | [Windows: WSL2](#windows-wsl2), sau đó bước 1–9 |
| macOS, Intel hoặc Apple Silicon | Container Linux, Python 3.12 và venv trong image | [macOS: Docker Desktop](#macos-docker-desktop) |

Pipeline đọc `/proc` để đo RSS và sử dụng `fcntl` cho khóa tiến trình. Vì vậy, Python chạy trực tiếp trong PowerShell hoặc trên macOS chưa đáp ứng phần quản lý tài nguyên của phiên bản này. Windows sử dụng WSL2; macOS sử dụng container Linux. Cài Conda trực tiếp trên Windows/macOS không thay thế lớp Linux này.

### Windows: WSL2

**1. Cài WSL2.** Mở PowerShell với quyền Administrator:

```powershell
wsl --install -d Ubuntu-24.04
```

Khởi động lại nếu Windows yêu cầu, mở Ubuntu và tạo tài khoản Linux. Kiểm tra trong PowerShell:

```powershell
wsl --update
wsl --list --verbose
```

Cột `VERSION` của Ubuntu phải bằng `2`. Nếu bản phân phối đang dùng WSL1:

```powershell
wsl --set-version Ubuntu-24.04 2
```

**2. Chuẩn bị Python trong Ubuntu.** Các lệnh tiếp theo chạy trong terminal Ubuntu, không phải PowerShell:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv git
python3.12 --version
```

Đặt bản repository trong hệ thống file Linux của WSL để giảm chi phí truy cập file. Mở terminal tại thư mục gốc project. Nếu chọn venv, thực hiện lựa chọn 1 ở bước 1; nếu chọn Conda — khuyến khích — cài bản Miniconda/Miniforge **dành cho Linux trong WSL**, rồi thực hiện lựa chọn 2. Python và Conda đã cài trên Windows không được dùng thay cho môi trường trong Ubuntu.

**3. Cài Docker Desktop for Windows.** Bật backend WSL2 và bật Ubuntu trong **Settings → Resources → WSL Integration**. Giữ Docker Desktop đang chạy. Kiểm tra từ Ubuntu:

```bash
docker --version
docker compose version
```

Sau đó thực hiện bước 2–7 bên dưới trong terminal Ubuntu. Lệnh `cp`, `source` và cách đặt biến môi trường ở các bước đó dùng cú pháp Bash. PostgreSQL chạy trong Docker Desktop, Python chạy trong WSL và kết nối qua cổng `127.0.0.1:55433`.

### macOS: Docker Desktop

Trên macOS, cả Python và PostgreSQL chạy trong container Linux. Không cần cài Python hoặc Conda trên máy để dùng cách này. Image pipeline tạo **venv với Python 3.12** và cài cùng bộ requirements của project; Docker chọn kiến trúc phù hợp với Mac Intel hoặc Apple Silicon. Model vẫn chạy trên CPU, không dùng MPS.

**1. Cài Docker Desktop.** Chọn bản dành cho Intel hoặc Apple Silicon theo máy, mở ứng dụng và chờ Docker Engine hoạt động. Dành ít nhất 4 GiB RAM cho Docker. Mở Terminal tại thư mục gốc repository:

```bash
docker --version
docker compose version
```

**2. Build môi trường và khởi động database:**

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion build pipeline
docker compose -f starter/docker-compose.yml -p data-ingestion up -d --wait postgres
```

`starter/Dockerfile` cài Python 3.12, PyTorch CPU và các thư viện đã ghim phiên bản. Profile `tools` giữ service pipeline ở chế độ chạy từng lệnh; Compose tự bật service khi được gọi trực tiếp bằng `run`. Database dùng volume riêng. Nếu đã có volume cũ chưa có database test, xem lệnh bổ sung `day6_test` ở bước 3.

**3. Kiểm tra cài đặt, nguồn và model:**

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline scripts/check_setup.py
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run preflight
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run validate
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m scripts.smoke_embedding
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m scripts.smoke_embedding --database --offline
```

**4. Chạy thí nghiệm:**

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run ingest
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run evaluate --split dev
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run evaluate --split test
```

Corpus đã có trong repository. Khi cần tải lại PDF:

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run fetch
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm pipeline -m src.run validate
```

**5. Kiểm thử và kiểm tra bảng đánh giá:**

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm --workdir /workspace pipeline -m pytest -q
docker compose -f starter/docker-compose.yml -p data-ingestion run --rm --workdir /workspace pipeline results/manual-review/finalize_test_review.py --check
```

`/workspace` là thư mục trong container; các thư mục trên máy được gắn bằng đường dẫn tương đối trong Compose. Kết quả ghi trực tiếp vào `results/`, model và cache nằm trong `.cache/`, nên không mất khi container của một lệnh kết thúc. Các thư mục ngoài phạm vi mã nguồn và dữ liệu của bài không được đưa vào build context.

Kết nối bên trong container dùng tên service `postgres` và cổng `5432`; không dùng `127.0.0.1:55433` để gọi container khác. Compose đã đặt hai URL cho database chính và test, nên không cần tạo `.env` cho cách chạy này. Nếu đổi tài khoản hoặc mật khẩu PostgreSQL, cập nhật cả service `postgres` và hai URL của service `pipeline`.

**6. Dừng và mở lại:**

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion stop
docker compose -f starter/docker-compose.yml -p data-ingestion up -d --wait postgres
```

Các lệnh Python trực tiếp ở bước 1–9 dành cho Linux/WSL2. Trên macOS, dùng chuỗi lệnh container ở mục này. File package PostgreSQL `linux-64.explicit.txt` ở bước 8 chỉ dành cho Linux x86-64, không cài trực tiếp trên macOS hoặc Windows.

Pipeline đã được kiểm thử bằng venv và bằng Docker trên Ubuntu. Lượt Docker đạt 44 kiểm thử, không bỏ qua ca nào; kết quả top-3 và điểm số trùng với thí nghiệm gốc. [Bằng chứng tái lập Docker](../artifacts/docker-verification.json) ghi phiên bản, dữ liệu cache và đối chiếu kết quả. WSL2 và Docker Desktop chưa được chạy trực tiếp trên máy Windows/macOS; các số đo hiệu suất trong báo cáo vẫn thuộc môi trường Linux đã công bố.

## 1. Tạo môi trường Python 3.12

Chọn một trong hai cách dưới đây. Sau khi kích hoạt, các lệnh còn lại dùng `python` của môi trường vừa tạo.

### Lựa chọn 1: venv

Cài Python 3.12 cùng module `venv` bằng bộ cài hoặc trình quản lý gói của hệ điều hành, rồi chạy:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip
```

Kết quả `python --version` phải là `Python 3.12.x`. Mỗi phiên terminal mới cần chạy lại `source .venv/bin/activate` từ thư mục gốc repository.

### Lựa chọn 2: Conda — khuyến khích

Cài Miniconda hoặc Miniforge, mở terminal đã có lệnh `conda`, rồi chạy:

```bash
conda env create -f starter/environment.yml
conda activate data-ingestion
python --version
python -m pip install --upgrade pip
```

Tên `data-ingestion` là tên môi trường mẫu của project, có thể đổi trong `starter/environment.yml`. Các lệnh chạy không phụ thuộc tên môi trường. Mỗi phiên terminal mới cần kích hoạt lại bằng `conda activate data-ingestion`.

## 2. Cài thư viện

Trong môi trường đã kích hoạt, từ thư mục gốc repository:

```bash
python -m pip install -r starter/requirements.txt
python -m pip install 'torch==2.15.0+cpu' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r starter/requirements-embedding.txt
python -m pip install -r starter/requirements-dev.txt
python -m pip check
```

Các file requirements ghim phiên bản dùng cho thí nghiệm. Bản PyTorch CPU được cài trước thư viện embedding. `pip check` phải kết thúc mà không báo xung đột dependency.

Quy trình cài thư viện đã được kiểm tra trong một venv Python 3.12 mới, không dùng chung site-packages. Kết quả cài đặt, `pip check`, smoke test và kiểm thử với PostgreSQL được lưu tại [environment-verification.json](../artifacts/environment-verification.json).

## 3. Khởi động PostgreSQL và pgvector bằng Docker

Cài Docker Engine hoặc Docker Desktop cùng Compose v2. Với WSL2, bật tích hợp Docker cho bản phân phối đang sử dụng. Kiểm tra:

```bash
docker --version
docker compose version
```

Từ thư mục gốc repository:

```bash
cp starter/.env.example starter/.env
docker compose -f starter/docker-compose.yml -p data-ingestion up -d --wait
python starter/scripts/check_setup.py
```

File `starter/.env` chứa kết nối `DATABASE_URL` cho `day6_lab` và `DAY6_TEST_DATABASE_URL` cho database kiểm thử riêng `day6_test`. Mật khẩu mẫu chỉ dùng cho PostgreSQL local. Cổng mặc định là `127.0.0.1:55433`; nếu đổi cổng, sửa đồng thời `starter/docker-compose.yml` và hai URL trong `starter/.env`. Các biến môi trường đã được đặt trong terminal có ưu tiên cao hơn giá trị trong `.env`.

`check_setup.py` in tên database, phiên bản PostgreSQL và pgvector, sau đó `Setup OK` khi kết nối hợp lệ. Đây là bước kiểm tra database; kết quả truy xuất được tạo ở bước chạy benchmark.

Script `starter/init.sql` tạo extension và database test khi Docker khởi tạo volume mới. Nếu dùng lại volume cũ chưa có `day6_test`, tạo thêm một lần:

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion exec -T postgres createdb -U day6 day6_test
docker compose -f starter/docker-compose.yml -p data-ingestion exec -T postgres psql -U day6 -d day6_test -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

Chỉ chạy `createdb` khi database đó chưa tồn tại. Không cần xóa volume để bổ sung database test.

## 4. Kiểm tra cấu hình và mô hình

```bash
cd starter
python -m src.run preflight
python -m src.run validate
python -m scripts.smoke_embedding
python -m scripts.smoke_embedding --database --offline
cd ..
```

`preflight` ghi tài nguyên CPU/RAM hiệu dụng và phiên bản thư viện. `validate` kiểm tra corpus, số trang, metadata, evidence, offsets và checksum của benchmark. Hai lệnh này không cần mô hình hoặc kết nối database.

Lệnh `smoke_embedding` đầu tiên tải model đã ghim revision và thử embedding ba câu ngắn. Lệnh thứ hai dùng model có sẵn để kiểm tra cosine SQL, lọc metadata và dữ liệu qua kết nối mới trên database test. Khi model đã được tải, có thể dùng `--offline` cho các lần smoke tiếp theo.

## 5. Chạy pipeline và benchmark

Corpus chuẩn hóa và bộ câu hỏi đã có trong `data/` và `benchmark/`. Chạy thí nghiệm trên những file này:

```bash
cd starter
python -m src.run validate
python -m src.run ingest
python -m src.run evaluate --split dev
python -m src.run evaluate --split test
cd ..
```

`ingest` tạo embedding và nạp A/B vào PostgreSQL; C dùng chung dữ liệu của B. Nạp lại cùng phiên bản thay dữ liệu trong transaction, không cộng dồn chunk. Nếu lỗi giữa batch, chiến lược đang nạp được rollback.

Phải đánh giá dev trước test. Quy tắc chọn là Evidence Hit@3 cao nhất, sau đó Hit@1, số chunk ít hơn và cuối cùng thứ tự A/B/C khi vẫn bằng nhau. Kết quả lựa chọn nằm tại `results/dev-selection.json`. Lượt test kiểm tra corpus, model, cấu hình chunking và bộ câu hỏi khớp với lượt dev.

Mỗi lệnh in đường dẫn thư mục kết quả vừa tạo. Các file chính gồm:

| File | Nội dung |
|---|---|
| `run.json` | Cấu hình, phiên bản thư viện và tài nguyên hiệu dụng |
| `status.json` | Kết quả lệnh hoặc loại lỗi |
| `telemetry.jsonl` | Thời gian từng bước, RSS và thông tin cache |
| `ingestion.json` | Số chunk, tổng ký tự và thống kê cache |
| `dev-summary.json`, `test-summary.json` | Hit@1, Evidence Hit@3 và số tử/mẫu theo chiến lược |
| `dev-traces.json`, `test-traces.json` | Top-3 đầy đủ: ID, text, score và metadata |
| `dev-manual-audit.json`, `test-manual-audit.json` | Phiếu metadata và grounding của lượt chạy |

### Tải lại PDF từ nguồn

Để kiểm tra khả năng lấy nguồn và tái tạo `data/pages.jsonl`:

```bash
cd starter
python -m src.run fetch
python -m src.run validate
cd ..
```

`fetch` dùng URL, danh sách trang và SHA256 trong `data/sources.json`. PDF khác checksum bị từ chối trước khi thay corpus. Lệnh mặc định dùng cache hợp lệ; thêm `--refresh` để kiểm tra lại nguồn HTTP. PDF được giới hạn 32 MiB, một worker, tối đa một tác vụ đang chờ và pacing một request mỗi giây.

Corpus của thí nghiệm gồm 39 trang vật lý, 119.228 ký tự chuẩn hóa. `page` là số trang PDF tính từ 1; `printed_page` là số in trên trang. [Manifest](../data/manifest.json) ghi danh sách trang và checksum; [hướng dẫn dữ liệu](../data/README.md) giải thích giấy phép và quy tắc loại trang.

Script `scripts.prepare_worldbank` phục vụ giai đoạn chuẩn bị nguồn: kiểm tra API, giấy phép, mục lục và số trang rồi ghi metadata lựa chọn nguồn. `scripts.finalize_corpus` phục vụ giai đoạn chốt corpus và benchmark trước thí nghiệm. Hai script này không thuộc chuỗi lệnh chạy lại benchmark đã chốt. Muốn thử corpus hoặc bộ câu hỏi khác, cần tách thành thí nghiệm riêng thay vì sửa bộ test hiện tại.

## 6. Phiếu đánh giá nội dung

Coherence dùng cùng 10 vị trí nguồn đã ghi tại `benchmark/coherence_positions.json`. Tạo phiếu mới mà không ghi đè bảng đánh giá đi kèm:

```bash
cd starter
python -m scripts.prepare_manual_review --output results/reproduction/coherence.json
cd ..
```

Generator chỉ chọn chunk và ghi dữ liệu để đọc, không tự gán điểm. Chấm coherence theo thang 0–2 trong [GUIDE](../GUIDE.md). Với mỗi lượt test, đọc `test-traces.json`, đối chiếu metadata với nguồn và điền `test-manual-audit.json` cho 5 câu × 3 chiến lược. Grounding đánh giá độ đủ của top-3 để trả lời; Hit@3 được tính riêng theo định nghĩa evidence của benchmark.

Các bảng đánh giá của thí nghiệm trong báo cáo nằm tại [results/manual-review](../results/manual-review/README.md).

## 7. Chạy kiểm thử

Từ thư mục gốc repository, trong môi trường đã kích hoạt:

```bash
DAY6_TEST_DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_test python -m pytest -q
```

Lệnh trên dùng kết nối Docker mẫu. Các kiểm thử database đọc `DAY6_TEST_DATABASE_URL` từ môi trường terminal, không tự đọc `.env`; nếu đã đổi cổng hoặc mật khẩu, thay URL tương ứng. URL phải trỏ tới database test riêng. Nếu chỉ muốn chạy phần không cần PostgreSQL:

```bash
python -m pytest -q -m 'not integration'
```

Ca integration kiểm tra nạp lại, lọc metadata, thay corpus và rollback khi lỗi giữa batch. Các vector tổng hợp trong test chỉ là fixture kiểm tra SQL, không dùng trong pipeline embedding hay bảng benchmark.

## 8. PostgreSQL local không qua Docker

Phương án này dành cho Linux x86-64 có Conda, có thể dùng cùng môi trường Python venv hoặc Conda đã tạo ở bước 1. Binary PostgreSQL được cài vào cache của project, tách khỏi môi trường Python:

```bash
conda create --prefix ./.cache/day6/postgres-runtime --file artifacts/postgres-runtime-linux-64.explicit.txt --yes
cd starter
python -m scripts.local_postgres start
python -m scripts.local_postgres check
python -m scripts.smoke_embedding
python -m scripts.local_postgres smoke
python -m scripts.local_postgres pipeline validate
python -m scripts.local_postgres pipeline ingest
python -m scripts.local_postgres pipeline evaluate --split dev
python -m scripts.local_postgres pipeline evaluate --split test
python -m scripts.local_postgres test
python -m scripts.local_postgres status
python -m scripts.local_postgres stop
cd ..
```

Danh sách package trong `artifacts/postgres-runtime-linux-64.explicit.txt` ghim PostgreSQL 16.16 và pgvector 0.7.4, là phiên bản database dùng cho số liệu trong báo cáo. Docker là một cách cài riêng; phiên bản thực tế của mỗi lần chạy được in bởi `check_setup.py`. Khi so sánh A/B/C, dùng cùng một database và phiên bản cho cả ba chiến lược.

Manager tạo cluster riêng trong vùng dữ liệu người dùng, thư mục quyền 0700 và file kết nối quyền 0600. Vị trí được tính từ home và mã định danh đường dẫn repository; không cần sửa đường dẫn theo máy. Mỗi repository có cluster riêng. Manager chỉ bind `127.0.0.1:55433`, tự truyền kết nối cho pipeline/test và từ chối dùng cổng của cluster khác.

Docker và cluster local dùng cùng cổng mặc định nên chỉ khởi động một phương án tại một thời điểm. Khi dùng manager, chạy qua `scripts.local_postgres pipeline ...` để nhận đúng thông tin kết nối.

## 9. Dừng dịch vụ và mở lại

Với Docker, từ thư mục gốc repository:

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion stop
```

Dữ liệu vẫn nằm trong Docker volume. Để mở lại:

```bash
docker compose -f starter/docker-compose.yml -p data-ingestion up -d --wait
```

Với cluster local, dùng `scripts.local_postgres stop` và `start` như ở bước 8. Không đưa `.env`, `.venv/` hoặc `.cache/` vào bài nộp.

## Tài liệu cài đặt

- [Python 3.12 — venv](https://docs.python.org/3.12/library/venv.html).
- [Conda — quản lý môi trường](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html).
- [PyTorch — cài đặt local](https://pytorch.org/get-started/locally/).
- [Microsoft — cài WSL](https://learn.microsoft.com/en-us/windows/wsl/install).
- [Docker Desktop — tích hợp WSL2](https://docs.docker.com/desktop/features/wsl/).
- [Docker Desktop — cài trên macOS](https://docs.docker.com/desktop/setup/install/mac-install/).
- [Docker Compose — service profiles](https://docs.docker.com/compose/how-tos/profiles/).
