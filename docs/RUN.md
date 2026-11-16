# Cài đặt và chạy bài Day07

Hướng dẫn dành cho người nhận bài từ repository hoặc file nén. Các lệnh chạy từ thư mục gốc project, nơi có `README.md`, `requirements.txt` và `environment.yml`. Dùng thư mục làm việc của bạn; không cần môi trường Python, tên tài khoản hoặc đường dẫn trên máy tác giả.

[Báo cáo](../report/individual/2A202603876_DinhPhucDien.md) trình bày chung phần cơ bản và bonus. Chọn **một** trong hai cách tạo môi trường: **lựa chọn 1 — venv**, hoặc **lựa chọn 2 — Conda (khuyến khích)**. Cả hai dùng Python 3.12. Conda thuận tiện hơn vì cài được cả Python và Poppler trong cùng môi trường.

## 1. Chuẩn bị theo hệ điều hành

| Hệ điều hành | Terminal dùng cho các lệnh bên dưới | Python và phần chạy trực tiếp | Day06 và agent cơ bản |
|---|---|---|---|
| Windows 10/11 | Ubuntu trong WSL2 | Tạo venv hoặc Conda **bên trong WSL2**; chạy bonus và kiểm tra offline ở đây | Docker Desktop tích hợp WSL2 |
| macOS, Intel hoặc Apple Silicon | Terminal, Bash hoặc Zsh | Tạo venv hoặc Conda trên macOS; chạy bonus và kiểm tra offline | Container Linux qua Docker Desktop |
| Linux | Terminal Bash | Tạo venv hoặc Conda; chạy bonus và kiểm tra offline | Docker Engine; có thêm cách chạy Python trực tiếp ở mục 7 |

Phạm vi trên dựa vào code: bonus sử dụng `fcntl` cho khóa file, còn Day06 dùng `/proc` để kiểm soát bộ nhớ. `fcntl` là [module Unix](https://docs.python.org/3.12/library/fcntl.html). Vì vậy, Windows dùng WSL2 thay cho Python trong PowerShell; trên macOS, phần Day06 chạy trong container Linux. Tạo được môi trường Python không đồng nghĩa mọi phần của pipeline chạy trực tiếp trên mọi hệ điều hành.

### Windows: cài WSL2

Mở PowerShell với quyền Administrator và cài Ubuntu 24.04:

```powershell
wsl --install -d Ubuntu-24.04
```

Khởi động lại nếu được yêu cầu, mở Ubuntu và hoàn tất bước tạo tài khoản Linux. Trong PowerShell, kiểm tra:

```powershell
wsl --list --verbose
```

Cột `VERSION` của Ubuntu phải là `2`; nếu đang là `1`, dùng `wsl --set-version Ubuntu-24.04 2`. Các bước này theo [hướng dẫn WSL của Microsoft](https://learn.microsoft.com/en-us/windows/wsl/install).

Từ đây, mở **terminal Ubuntu**, tải hoặc giải nén project vào thư mục làm việc trong WSL, rồi mở terminal tại gốc project. Tất cả lệnh Bash trong tài liệu chạy tại đây. Cài Git và curl nếu chưa có:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
```

Nếu chọn Conda, cài bản **Linux bên trong WSL**, không dùng bản Conda Windows. Nếu chạy Docker, cài Docker Desktop for Windows, bật backend WSL2 và bật Ubuntu tại **Settings → Resources → WSL Integration** theo [tài liệu Docker](https://docs.docker.com/desktop/features/wsl/).

### macOS

Mở Terminal tại gốc project. Lựa chọn venv bên dưới sử dụng [Homebrew](https://brew.sh/) để cài Python và Poppler; hãy cài Homebrew theo hướng dẫn trên trang đó nếu chưa có. Lựa chọn Conda không cần Homebrew. Cài và mở [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) khi chạy Day06 và phần cơ bản, chọn bộ cài đúng Intel hoặc Apple Silicon.

### Linux

Các lệnh `apt` trong hướng dẫn áp dụng cho Ubuntu 24.04 và WSL Ubuntu 24.04. Với bản phân phối khác, dùng trình quản lý gói tương ứng để cài Python 3.12 và Poppler, hoặc chọn Conda để cài chúng trong môi trường riêng. Cần Docker Engine và Compose khi chạy database và phần cơ bản.

Các ví dụ Docker dùng `docker` trực tiếp. Nếu Linux yêu cầu quyền quản trị, thêm `sudo` trước lệnh Docker, hoặc chạy script Docker bằng `sudo bash ...` theo cấu hình máy. Windows với Docker Desktop và macOS không dùng `sudo` cho các lệnh này.

## 2. Lựa chọn 1 — venv

### Windows trong WSL2 và Linux Ubuntu 24.04

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv poppler-utils
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS

```bash
brew install python@3.12 poppler
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`python3.12` là executable của [gói Homebrew Python 3.12](https://formulae.brew.sh/formula/python@3.12). Nếu đã cài Python 3.12 và Poppler bằng cách khác, bỏ qua lệnh `brew install`.

Mỗi khi mở terminal mới, vào gốc project và chạy lại `source .venv/bin/activate`. Thoát môi trường bằng `deactivate`. Không sao chép thư mục `.venv` sang máy khác; tạo lại bằng `requirements.txt`. Cách tạo và kích hoạt tuân theo [tài liệu venv](https://docs.python.org/3.12/library/venv.html).

## 3. Lựa chọn 2 — Conda (khuyến khích)

Nếu đã có Conda trong đúng hệ điều hành chạy project, chuyển đến bước tạo môi trường. Nếu chưa có, cài [Miniforge](https://github.com/conda-forge/miniforge). Bộ cài dưới đây tự chọn kiến trúc CPU qua `uname -m`; không giả định đường dẫn cài trên máy.

**Windows trong WSL2 và Linux:**

```bash
curl -fsSL -o /tmp/day07-miniforge.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$(uname -m).sh"
bash /tmp/day07-miniforge.sh
```

**macOS:**

```bash
curl -fsSL -o /tmp/day07-miniforge.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-$(uname -m).sh"
bash /tmp/day07-miniforge.sh
```

Làm theo bộ cài, đồng ý khởi tạo Conda cho shell khi được hỏi, rồi đóng và mở lại terminal. Kiểm tra bằng `conda --version`. Sau đó vào lại gốc project và tạo môi trường:

```bash
conda env create --name day07 --file environment.yml
conda activate day07
python -m pip check
```

`day07` chỉ là **tên ví dụ**, có thể thay bằng tên bạn chọn ở cả hai lệnh. File `environment.yml` không chứa tên môi trường cố định hay đường dẫn máy cá nhân; nó cài Python 3.12, pip, [Poppler từ conda-forge](https://anaconda.org/conda-forge/poppler) và dependency Python từ `requirements.txt`. Không tạo thêm venv bên trong Conda.

Mỗi khi mở terminal mới, kích hoạt lại môi trường bằng `conda activate day07` hoặc tên bạn đã chọn. Thoát bằng `conda deactivate`. Cách tạo và quản lý môi trường theo [tài liệu Conda](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html).

## 4. Kiểm tra môi trường và cấu hình API

Sau khi kích hoạt **venv hoặc Conda**, các lệnh Python còn lại dùng cùng cú pháp trên macOS, Linux và Ubuntu trong WSL2:

```bash
python -c "import sys; print(sys.version); print(sys.executable); assert sys.version_info[:2] == (3, 12)"
python -m pip check
pdftotext -v
pdftoppm -v
export PYTHONPATH="$PWD/src"
python scripts/verify_submission.py
```

Python phải là 3.12 và nằm trong môi trường vừa tạo; hai lệnh Poppler phải tìm thấy executable. `export PYTHONPATH` giúp chạy `python -m day07` và `python -m bonus` từ source trong project; đặt lại khi mở terminal mới. Script kiểm tra bài nộp tự tìm source nên không phụ thuộc biến này. Nó không gọi API hoặc database.

`requirements.txt` đủ cho bonus và kiểm tra offline. Nó không cài Torch/embedding Day06. Phần cơ bản trong Docker có bộ dependency riêng, được cài từ các file requirements Day06; nếu chạy trực tiếp trên Linux, xem mục 7.

Tạo cấu hình local một lần rồi mở `.env` bằng trình soạn thảo bạn dùng:

```bash
cp -n .env.example .env
```

Phần cơ bản cần `OPENROUTER_API_KEY`, giữ `OPENROUTER_MODEL=openai/gpt-4o-mini` để tái lập thí nghiệm. Bonus dùng key Google AI Studio qua `GEMINI_API_KEY`, với thiết lập đã chốt:

```dotenv
BONUS_LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_TIMEOUT_SECONDS=120
GEMINI_MAX_OUTPUT_TOKENS=8192
GEMINI_REASONING_EFFORT=low
GEMINI_MAX_RETRIES=2
GEMINI_MIN_INTERVAL_SECONDS=6
GEMINI_MAX_INFLIGHT=2
```

`.env.example` là cấu hình mẫu, không chứa key. Các model và tham số trên thuộc thí nghiệm đã công bố; người chạy dùng tài khoản API của mình. Chỉ nộp file mẫu, không nộp `.env`. Các lệnh `llm-check`, `ask` và benchmark agent gọi API thật, có thể tính phí và chịu quota tài khoản. Agent gửi câu hỏi, context và ảnh đã chọn tới provider; không gửi đáp án chuẩn.

## 5. Chuẩn bị dữ liệu Day06

Phần cơ bản dùng database và embedding Day06; bonus không cần PostgreSQL. Cài và mở Docker trước, sau đó kiểm tra:

```bash
docker info
docker compose version
```

Nếu chưa có dữ liệu, chạy tại gốc Day07:

```bash
bash scripts/reproduce_day06.sh
```

Script build môi trường Linux, khởi động PostgreSQL, tải embedding lần đầu, ingest và kiểm tra Day06. Chi tiết và cách khởi động lại database đã có nằm trong [DAY06_SETUP.md](DAY06_SETUP.md). Cách này dùng được từ Bash trên Linux, WSL2 và Terminal macOS; không phụ thuộc môi trường Python trên máy chủ.

## 6. Thử phần cơ bản

Kiểm database, model và ba cách retrieval; các lệnh này không gọi LLM:

```bash
docker compose -f compose.day07.yml run --rm day07 check
docker compose -f compose.day07.yml run --rm day07 search --method dense --query 'What does the Shared Prosperity indicator measure?'
docker compose -f compose.day07.yml run --rm day07 search --method bm25 --query 'What does the Shared Prosperity indicator measure?'
docker compose -f compose.day07.yml run --rm day07 search --method hybrid --query 'What does the Shared Prosperity indicator measure?'
```

Kiểm tool calling rồi chạy một câu bằng cấu hình được chọn:

```bash
docker compose -f compose.day07.yml run --rm day07 llm-check
docker compose -f compose.day07.yml run --rm day07 ask --method hybrid --neighbors 1 --query 'What does the Shared Prosperity indicator measure?' --top-k 5 --budget 6000 --max-searches 3 --output results/day07/my-answer.json
```

## 7. Chạy phần cơ bản bằng Python trực tiếp — Linux/WSL2

Cách này dành cho Linux hoặc Ubuntu trong WSL2 vì Day06 cần `/proc`. Trên macOS, dùng lệnh Docker ở mục 6. Giữ nguyên venv hoặc Conda đã tạo; cài thêm bộ dependency Day06 trong môi trường đó:

```bash
python -m pip install -r Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering/starter/requirements.txt
python -m pip install 'torch==2.15.0+cpu' --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering/starter/requirements-embedding.txt
python -m pip check
```

Dùng cùng phiên bản Torch/embedding với image Day06; không thay bằng bản CUDA hay bản khác khi truy vấn index đã tạo trong image. Nguồn wheel CPU theo [hướng dẫn PyTorch](https://pytorch.org/get-started/locally/). Nếu nền tảng không có wheel đã ghim, dùng cách Docker để giữ đúng bộ thư viện.

Database và cache model vẫn phải được chuẩn bị ở mục 5. `.env` đặt `DATABASE_URL` trỏ tới `127.0.0.1:55433`; Docker Compose tự dùng hostname `postgres` bên trong mạng container. Sau khi đặt `PYTHONPATH` như mục 4:

```bash
python -m day07 check
python -m day07 ask --method hybrid --neighbors 1 --query 'What does the Shared Prosperity indicator measure?' --top-k 5 --budget 6000 --max-searches 3 --output results/day07/my-local-answer.json
```

Có thể thay phần `docker compose -f compose.day07.yml run --rm day07` trong các lệnh benchmark bằng `python -m day07`. `--filter '{"chapter":"1"}'` là ví dụ giới hạn do người chạy chọn; benchmark đã nộp không đặt filter.

## 8. Chạy lại benchmark cơ bản

Để đo lại đúng baseline và cấu hình đã nộp trên test:

```bash
docker compose -f compose.day07.yml run --rm day07 bench --suite agent --split test --selection results/day07/selection.json --output results/day07/my-test --workers 3
```

Để thực hiện thí nghiệm dev mới:

```bash
docker compose -f compose.day07.yml run --rm day07 bench --suite retrieval --split dev --output results/day07/my-retrieval-dev
docker compose -f compose.day07.yml run --rm day07 bench --suite agent --split dev --output results/day07/my-agent-dev
```

Trong từng trial, sao chép `reviews.template.json` thành `reviews.json`, đọc câu trả lời/context/PDF và điền điểm context, điểm trả lời, mức hỗ trợ của **từng citation**, nhãn từ chối, người chấm và lý do. Chấm đủ cả câu lỗi, giữ đúng trạng thái thực thi. Sau đó tổng hợp nhãn, chọn bằng dev rồi mới test:

```bash
docker compose -f compose.day07.yml run --rm day07 review --dev-run results/day07/my-agent-dev/dense_baseline
# Lặp lệnh review cho bm25, hybrid, hybrid_neighbors1 và hybrid_neighbors2.
docker compose -f compose.day07.yml run --rm day07 freeze-selection --dev-run results/day07/my-agent-dev --trial hybrid_neighbors1 --reason 'Điền lý do dựa trên các nhãn dev đã chấm' --output results/day07/my-selection.json
docker compose -f compose.day07.yml run --rm day07 bench --suite agent --split test --selection results/day07/my-selection.json --output results/day07/my-new-test --workers 3
# Điền reviews.json trong hai trial test và dùng lệnh review để tổng hợp.
```

Tên trial trong ví dụ phải được thay bằng cấu hình thực sự chọn từ dev. CLI kiểm model, corpus, config và checksum mã nguồn trước khi cho chạy test. Mỗi lượt dùng output mới. Nếu bị ngắt, thêm `--resume` với đúng output và cùng thiết lập để giữ các câu đã lưu, kể cả câu lỗi. Không ghi đè kết quả đã nộp.

## 9. Thử phần bonus

Build và thử retrieval/render PDF bằng Docker, không gọi LLM:

```bash
docker compose -f compose.bonus.yml build bonus
docker compose -f compose.bonus.yml run --rm bonus prepare
docker compose -f compose.bonus.yml run --rm bonus search --query 'Table 4.1 expected years of school'
docker compose -f compose.bonus.yml run --rm bonus page --page 135
```

Kiểm tra build, index, toàn bộ unit test và render ảnh bằng một script:

```bash
bash scripts/check_bonus_docker.sh
```

Kết quả container ghi ở `results/bonus/docker/`. Image bind mount source từ project. Script không gọi API. Bằng chứng được nộp ghi nhận 46 test ở thời điểm kiểm tra container trước đó; bộ test của code hiện tại có 65 ca.

Kiểm API và chạy một câu bằng cấu hình đã chốt:

```bash
docker compose -f compose.bonus.yml run --rm bonus llm-check --provider gemini
docker compose -f compose.bonus.yml run --rm bonus ask --provider gemini --trial layout_vision_image --query 'In Table 4.1, what are the expected years of school for Vietnam?' --output results/bonus/my-answer.json
```

Chạy trực tiếp bằng venv hoặc Conda đã kích hoạt, sau khi đặt `PYTHONPATH` ở mục 4:

```bash
python -m bonus prepare
python -m bonus search --query 'Table 4.1 expected years of school'
python -m bonus page --page 135
python -m bonus llm-check --provider gemini
python -m bonus ask --provider gemini --trial layout_vision_image --query 'In Table 4.1, what are the expected years of school for Vietnam?' --output results/bonus/my-local-answer.json
```

`prepare` dùng corpus đã nộp, kiểm checksum và tải PDF gốc nếu chưa có. Ảnh được tạo lại trong `.cache/bonus/`; lệnh `page` in đường dẫn để mở ảnh. `prepare --reextract` chỉ dùng khi cần kiểm tra lại extraction: kết quả khác corpus đã khóa sẽ báo lỗi, không âm thầm thay dữ liệu.

## 10. Chạy lại benchmark bonus

Dùng **`data/bonus-v2`** cho bộ test hiện tại. `data/bonus` giữ corpus dùng chung và benchmark cũ để kiểm tra lịch sử; mặc định CLI trỏ về bộ cũ nên cần ghi rõ `--dataset`.

Đo lại test hiện tại trong môi trường Python đã kích hoạt:

```bash
python -m bonus bench --provider gemini --dataset data/bonus-v2 --split test --selection results/bonus/selection-v2.json --output results/bonus/my-test --workers 2
```

Hoặc dùng Docker:

```bash
docker compose -f compose.bonus.yml run --rm bonus bench --provider gemini --dataset data/bonus-v2 --split test --selection results/bonus/selection-v2.json --output results/bonus/my-docker-test --workers 2
```

Lệnh chỉ chạy khi mã nguồn, cấu hình, model, workers, benchmark và các artifact dev khớp selection. Dùng key đủ quyền/quota, giữ thiết lập đã chốt. Mức hai worker giãn sáu giây chỉ áp dụng trong tiến trình này; các tiến trình khác dùng chung dự án vẫn có thể làm vượt quota.

Để làm thí nghiệm dev mới và chốt một selection mới:

```bash
python -m bonus bench --provider gemini --dataset data/bonus-v2 --split dev --trials layout_vision_image --output results/bonus/my-dev --workers 2
# Điền reviews.json từ reviews.template.json sau khi đọc trace và PDF gốc từng câu.
python -m bonus review --split dev --run results/bonus/my-dev/layout_vision_image
python -m bonus select --run results/bonus/my-dev --trial layout_vision_image --reason 'Điền lý do từ review dev thực tế' --output results/bonus/my-selection.json
python -m bonus bench --provider gemini --dataset data/bonus-v2 --split test --selection results/bonus/my-selection.json --output results/bonus/my-new-test --workers 2
# Điền reviews.json cho đủ 30 câu, kể cả lỗi, rồi tổng hợp:
python -m bonus review --split test --run results/bonus/my-new-test/layout_vision_image
```

Review đọc dataset từ `run.json`. Không chạy `review` hay `select` lên thư mục dev đã được selection khóa: các thao tác này có thể viết lại artifact. Có thể dùng `--resume` cho lượt chưa hoàn tất khi identity không đổi; không dùng để thay một câu lỗi bằng kết quả mới. Nếu sửa code dựa trên lỗi test đã đọc, cần bộ test mới trước khi báo điểm độc lập.

## 11. Kiểm tra bài nộp mà không gọi API

```bash
python scripts/verify_submission.py
```

Script chạy unit test, đối chiếu checksum, benchmark, nhãn, số liệu và link tài liệu; kết quả ở `results/submission/verification.json`. Script không kết nối database hay gọi API và không sửa artifact đã khóa. Muốn chỉ chạy unit test:

```bash
python -m unittest discover -s tests -v
```

Các thư mục cần nộp gồm code, cấu hình, benchmark, kết quả và báo cáo. `.env`, model cache, PDF/ảnh cache, Python cache và Docker volume không thuộc bài nộp. Dữ liệu Day06 cần thiết đã nằm trong bản copy của project; xem phần dữ liệu và lệnh tái tạo ở [DAY06_SETUP.md](DAY06_SETUP.md).
