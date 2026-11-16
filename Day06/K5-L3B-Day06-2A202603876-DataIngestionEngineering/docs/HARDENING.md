# Tính toàn vẹn dữ liệu và kiểm soát tài nguyên

Pipeline được thiết kế để phát hiện dữ liệu sai trước khi công bố corpus hoặc index, đồng thời giới hạn lượng công việc trong mỗi giai đoạn. Cấu hình nằm trong [pipeline.json](../starter/config/pipeline.json); các đường dẫn dữ liệu được tính từ gốc repository. Python 3.12 có thể chạy trong venv hoặc Conda. Phần theo dõi bộ nhớ và khóa tiến trình sử dụng giao diện của Linux; hướng dẫn cài đặt nằm trong [README](../README.md).

## Giới hạn xử lý

Ngân sách CPU được thiết lập trước khi import NumPy, PyTorch và Sentence Transformers. Số thread thực dùng là giá trị nhỏ hơn giữa cấu hình và số CPU khả dụng, có xét CPU affinity cùng quota cgroup. Các biến OpenMP, MKL, OpenBLAS và NumExpr nhận cùng ngân sách; tokenizer không tạo pool song song riêng. PyTorch dùng tối đa 4 intra-op threads và một inter-op thread theo cấu hình thực nghiệm. Embedding được xử lý tuần tự theo batch tối đa 16 văn bản để tránh chồng nhiều pool tính toán.

| Thành phần | Giới hạn trong thực nghiệm | Ý nghĩa |
|---|---:|---|
| Native threads | 4 | Ngân sách cho backend tính toán |
| Fetch workers | 1 | Một session HTTP bền vững theo worker |
| Tác vụ fetch đồng thời | 1 | Giới hạn cả tác vụ đã gửi và kết quả chờ tiêu thụ |
| Tần suất theo origin | 1 request/giây | Pacing dùng chung giữa các worker và các lần retry |
| Response sau giải mã | 32 MiB | Dừng đọc khi số byte thực vượt giới hạn |
| Embedding batch | 16 văn bản | Giới hạn kích thước ma trận đầu ra mỗi batch |
| RSS tiến trình | 2.048 MiB | Kiểm tra tại ranh giới giai đoạn/batch |
| Bộ nhớ khả dụng | Tối thiểu 10% | Xét bộ nhớ máy và giới hạn cgroup |

RSS guard là phép kiểm tra ở ranh giới xử lý, không phải giới hạn cứng do hệ điều hành cưỡng chế. Một lời gọi tokenizer, parser hoặc backend native vẫn có thể cấp phát thêm bộ nhớ giữa hai lần kiểm. Byte cap của HTTP cũng không phải giới hạn tổng RAM khi parser PDF giải nén nội dung. Khi không đọc được số đo bộ nhớ, pipeline báo lỗi thay vì ghi nhận mức sử dụng bằng 0.

JSONL được đọc tuần tự với giới hạn số byte trên dòng. Văn bản được chia và encode theo batch; validator giữ metadata phục vụ kiểm tra nguồn, nên bộ nhớ của bước này vẫn tăng theo số đơn vị nguồn. Các phép toán vector sử dụng ndarray float32 và backend native. Ở biên COPY, adapter nhận row view rồi serialize vào PostgreSQL; tokenizer, cache và giao thức database vẫn có cấp phát bộ nhớ.

## Thu thập nguồn và HTTP cache

Fetcher kiểm URL, Content-Type và cấu trúc payload theo loại HTML, JSON, PDF hoặc TXT. API World Bank chỉ chấp nhận các query parameter công khai đã khai báo; redirect không được tự động theo. Timeout kết nối là 5 giây, timeout đọc là 30 giây và vòng đọc response có deadline 60 giây, được kiểm sau mỗi block. HTTP 429, 5xx và lỗi mạng có tối đa ba lần thử; `Retry-After` được xử lý cùng pacing theo origin. Những mã lỗi khác, gồm 403, kết thúc ngay. Đây là các giới hạn theo lần đọc/lần thử, không phải một deadline cứng cho toàn bộ lệnh fetch.

HTTP cache có định danh theo URL và loại nội dung, kèm số byte và SHA-256. Body được ghi hợp lệ trước khi checkpoint được công bố. Khi đọc lại, cache phải qua kiểm tra kích thước, checksum, loại và cấu trúc; file hỏng không được sử dụng. `--refresh` yêu cầu revalidation bằng ETag hoặc Last-Modified khi nguồn hỗ trợ.

PDF World Bank được ghim checksum trong [khai báo nguồn](../data/sources.json). Bản tải có 20.584.558 byte và 232 trang; chỉ 39 trang đã chọn được đưa vào corpus. Nếu PDF đổi, MIME sai, payload hỏng hoặc một trang không trích xuất được, bước fetch báo lỗi trước khi thay corpus đang dùng. [Kết quả kiểm tra nguồn](../results/worldbank-fetch-probe/result.json) ghi phản hồi API, PDF và TXT trong lần thực nghiệm.

## Truy vết và công bố file

Mỗi trang giữ `document_id`, URL, số trang PDF, trang in và chương. Mỗi chunk có `char_start`, `char_end`, text và ID xác định từ nội dung, vị trí cùng cách chia. Offsets dùng khoảng nửa mở `[start, end)` trong văn bản đã chuẩn hóa; việc đối chiếu thực hiện bằng lát cắt nguồn, không tìm một câu tương tự rồi gán vị trí.

Chuẩn hóa dùng NFC và quy tắc khoảng trắng có phiên bản. Với PDF hai cột, chế độ plain giữ được thứ tự đọc tốt hơn layout trên các trang mẫu, nhưng không khôi phục ranh giới đoạn theo hình học. Header, caption và khoảng trắng do giãn chữ có thể còn trong text. Manifest giữ quy tắc chọn trang và checksum để giới hạn này có thể được kiểm tra từ cùng một bản nguồn.

Các file được ghi vào file tạm cùng thư mục, flush, fsync rồi đổi tên nguyên tử; thư mục cũng được fsync sau khi đổi tên. Cơ chế này bảo vệ từng file. Corpus, manifest và freeze là nhiều file khác nhau, nên một lần dừng giữa các bước công bố vẫn có thể tạo ra tập file không đồng nhất. Validator đối chiếu checksum giữa chúng và từ chối chạy tiếp khi không khớp; không có transaction đa file trên filesystem.

Bước chốt corpus kiểm nguồn, metadata, trang, evidence và offsets trước khi công bố freeze cuối cùng. Chốt lại cùng nội dung giữ nguyên mốc ban đầu. Sửa corpus/benchmark sau khi có ingest hoặc retrieval bị chặn để tránh gắn kết quả cũ với một bộ dữ liệu mới. Khóa file ngăn hai CLI cùng sửa artifact; đường dẫn ra ngoài các thư mục của bài lab, kể cả qua symlink, bị từ chối.

## Embedding và cache vector

Model được ghim bằng commit SHA đầy đủ; thiết bị chạy phải được chọn rõ ràng. Mỗi đầu vào được kiểm số token trước encode. Vượt context limit, thiếu thư viện, lỗi tải model hoặc yêu cầu thiết bị không khả dụng đều tạo lỗi, không chuyển sang vector giả hoặc cắt văn bản âm thầm.

Cache vector có fingerprint gồm tên và revision model, phiên bản thư viện, chuẩn hóa, thiết bị, thread budget, batch size, vai trò query/document và nội dung. Khi lấy từ cache, pipeline kiểm SHA-256, shape, dtype float32, giá trị hữu hạn và vector khác 0. Vector hỏng được tính lại; dữ liệu trả về sai hợp đồng không được lưu. File NumPy được đọc với `allow_pickle=False`.

## Transaction và truy xuất PostgreSQL

Một lần thay index của A hoặc B chạy trong một transaction: lấy advisory lock theo chiến lược, xóa dữ liệu cũ, COPY các batch mới rồi ghi fingerprint và số chunk. Lỗi ở bất kỳ batch nào sẽ rollback toàn bộ lần thay đó, giữ dữ liệu đã commit trước đó. Khóa chính `(strategy, chunk_id)` cùng việc thay toàn bộ chiến lược ngăn nhân bản khi nạp lại và loại chunk cũ khi corpus thu nhỏ. Transaction áp dụng cho từng chiến lược; A và B không được thay bằng một transaction chung.

C ánh xạ về dữ liệu vật lý B. Query embedding được tạo một lần cho mỗi câu và tái sử dụng giữa A/B/C. Bộ lọc chỉ chấp nhận các trường metadata được phép cùng giá trị scalar; nguồn gold và trang gold không được làm filter. Tìm kiếm dùng JSONB containment, exact cosine và chunk ID làm khóa phụ khi bằng điểm.

Trước evaluate, fingerprint của index phải khớp corpus, model và cấu hình. Toàn bộ lượt đánh giá đọc trong transaction `REPEATABLE READ READ ONLY` để không trộn các phiên bản dữ liệu. Kết nối database có timeout; statement timeout là 60 giây, lock timeout là 5 giây. Chi tiết cài đặt nằm trong [store.py](../starter/src/store.py).

## Benchmark và phạm vi kiểm thử

Validator kiểm split, source/page, evidence text, offsets, các evidence thay thế và checksum của đầu vào đã chốt. Test chỉ chạy khi có quyết định chọn trên dev với cùng fingerprint. Các kiểm tra này phát hiện thay đổi dữ liệu/cấu hình, nhưng không chứng minh người thực hiện chưa từng đọc tập test. Quy tắc thiết kế benchmark và giới hạn của mẫu được trình bày trong [báo cáo](../report/individual/2A202603876_DinhPhucDien.md).

| Nhóm lỗi | Phạm vi kiểm thử | Mã kiểm thử |
|---|---|---|
| Công việc không có giới hạn, pacing/retry sai | Dừng consumer, giới hạn producer, chia sẻ cooldown, retry 429/5xx, không retry 403, response quá lớn được đóng | [test_pipeline.py](../starter/tests/test_pipeline.py) |
| HTTP cache và payload không hợp lệ | MIME sai, cache khác loại, checkpoint sai cấu trúc, checksum hỏng, PDF thay phiên bản | [test_worldbank_fetch.py](../starter/tests/test_worldbank_fetch.py) |
| Công bố file dang dở | Inject lỗi đổi tên, giữ file cũ; lỗi giữa các trang không thay corpus | [test_pipeline.py](../starter/tests/test_pipeline.py), [test_worldbank_fetch.py](../starter/tests/test_worldbank_fetch.py) |
| Mất nguồn hoặc sửa benchmark | Bao phủ ký tự ngoài whitespace, offsets và ID ổn định; từ chối evidence/inputs sai | [test_pipeline.py](../starter/tests/test_pipeline.py), [test_source_preparation.py](../starter/tests/test_source_preparation.py) |
| Chốt corpus không đồng nhất | Provenance nhiều nguồn, evidence mơ hồ, lỗi cuối quy trình, chặn sửa sau retrieval | [test_finalize_corpus.py](../starter/tests/test_finalize_corpus.py) |
| Cache embedding hỏng | Khởi động lại, thay role/revision, vector hỏng hoặc NaN không được dùng | [test_pipeline.py](../starter/tests/test_pipeline.py) |
| Index một phần hoặc còn dữ liệu cũ | Nạp lại, thay tập nhỏ hơn, filter C trên B, inject lỗi giữa các batch COPY và kiểm rollback | [test_store_integration.py](../starter/tests/test_store_integration.py) |
| Quản lý PostgreSQL local sai tham số | Chuyển tiếp lệnh, environment và exit status; invocation sai không tạo dữ liệu quản lý | [test_local_postgres.py](../starter/tests/test_local_postgres.py) |

Các unit test sử dụng tmpdir và fixture tổng hợp, không lấy corpus thực làm giá trị kỳ vọng. Integration test dùng database test riêng cùng schema tạm; vector 3 chiều trong test chỉ phục vụ kiểm tra hành vi lưu trữ. Model smoke dùng ba câu tự soạn và embedding thật để so cosine SQL với NumPy, kiểm filter, reconnect và lưu bền; đây là phép kiểm hạ tầng riêng với benchmark corpus.

[Kết quả JUnit](../results/engineering-tests.xml) ghi phạm vi của lần chạy kiểm thử. Khi không có `DAY6_TEST_DATABASE_URL`, ca PostgreSQL integration được skip và unit test không thay thế bằng chứng database thật. Các phép thử hiện có mô phỏng lỗi ở mức ứng dụng; chúng không mô phỏng mất điện, hỏng ổ đĩa hay OS crash. Kết quả CPU exact search cũng không cho phép suy ra hành vi GPU hoặc index approximate.

Telemetry ghi wall time, RSS, peak RSS, CPU hiệu dụng và cache hit/miss. RSS/peak RSS là của tiến trình Python, không bao gồm PostgreSQL server. So sánh thời gian cần giữ nguyên corpus, model và phần cứng, đồng thời phân biệt cache lạnh/ấm với thời gian tải model. Số liệu và phạm vi đo cụ thể nằm trong [báo cáo thực nghiệm](../report/individual/2A202603876_DinhPhucDien.md).
