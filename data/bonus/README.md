# Dữ liệu cho bonus

Tách biệt với `data/day07`; không sửa benchmark/kết quả cơ bản.

- `corpus.jsonl`: 437 bản ghi: 232 trang, 171 hình có số, 34 bảng có số.
  Mọi trang vật lý đều được giữ. Bản ghi bảng/hình có mã riêng, số trang,
  caption, tọa độ caption và khung toàn trang. Khung toàn trang
  được ghi rõ; không giả định đó là crop chính xác của từng hình.
- `manifest.json`: nguồn, SHA-256, giấy phép, phiên bản Poppler, thống kê
  từng trang và giới hạn. Có 205/205 đối tượng xác định được hộp caption.
  Mục lục gốc có 6 sai lệch mã bảng/số trang; danh mục dùng caption trên trang
  thực và giữ cả locator mục lục để kiểm tra (`source_catalog_corrections`).
- `catalog-amendment.json`: ghi bản sửa danh mục nguồn trước benchmark,
  checksum trước/sau; câu hỏi và gold dev/test không thay đổi. Bản ghi này
  giải thích việc sửa mục lục nguồn, không dùng các lần thử kết nối làm benchmark.
- `dev.json`: 15 câu có đáp án (3 câu mỗi nhóm) và 3 câu thiếu bằng chứng.
  Nhóm ảnh/sơ đồ trên dev dùng bản đồ mang thông tin, không dùng ảnh trang trí.
- `test.json`: 24 câu có đáp án: 6 bảng, 5 sơ đồ, 5 biểu đồ, 4 multi-hop,
  4 văn bản; cộng 6 câu thiếu bằng chứng. Nhóm sơ đồ test là 5 sơ đồ khái niệm
  khác nhau, không lấy biểu đồ để bù vào số lượng.
- `freeze.json`: thời điểm và checksum hai tập, corpus; tạo trước khi thử agent.
- `dev-label-correction-01.json`: lịch sử sửa nhãn `bd09` sau khi đọc lại
  ảnh gốc: Việt Nam khoảng 37% (2010) lên 45% (2018). Sửa trước dev-02;
  lưu nhãn trước/sau và thời điểm để người chấm kiểm tra.
- `test-label-correction-01.json`: sửa nhãn `bt22` trước mọi lần chạy test,
  khi kiểm chứng trang 178 cho câu dev trên cùng trang: mực nước biển dự báo
  tăng 30 cm năm 2050 và 70 cm năm 2100 trong kịch bản xấu nhất. Có checksum
  ảnh nguồn, giá trị trước/sau và lý do. Không có đầu ra agent trên test để
  dùng vào sửa nhãn/chọn cấu hình. Freeze lưu lịch sử các bản sửa này.

Gold ghi trang vật lý, vùng bằng lời, tọa độ, các ý phải có và phép tính/đơn vị.
Các câu đọc biểu đồ có khoảng dung sai đã định trước. Nhãn được AI hỗ trợ soạn
bằng cách đọc ảnh PDF gốc và text bố cục; người học cần kiểm chứng. Gold chỉ
dùng phía đánh giá. Agent chỉ nhận câu hỏi và nội dung lấy từ corpus.

Đây là benchmark theo một tài liệu, nhiều câu nêu trực tiếp mã bảng/hình.
Kết quả không đại diện cho tìm kiếm tự do trên các tài liệu chưa biết.

PDF gốc được tải và kiểm tra SHA-256 khi cần. Ảnh trang được tạo lại bằng
`pdftoppm` trong `.cache/bonus/`, không cần đưa PDF hoặc hàng trăm ảnh vào Git.
Trial crop dùng tọa độ caption/cột và dòng Source để cắt pixel từ PDF, giữ
chú giải khi tìm được; vùng cắt là heuristic và có thể còn chữ lân cận. Trace
ghi bbox, phương pháp và checksum; model có thể inspect toàn trang khi cần.
Index text được nộp cùng repo để tránh sai khác trích xuất giữa các bản Poppler.
Lệnh `prepare --reextract` kiểm tra lại extraction; khác bản đã chốt sẽ báo lỗi
thay vì âm thầm thay đổi corpus. Môi trường tạo index: Poppler 24.02.0.

Nguồn: World Bank. 2022. *From the Last Mile to the Next Mile — 2022 Vietnam
Poverty & Equity Assessment*. Washington, DC: World Bank. CC BY 3.0 IGO.
[Bản gốc](https://documents1.worldbank.org/curated/en/099115004242216918/pdf/P176261155e1805e1bd6e14287197d61965ce02eb562.pdf),
quyền sử dụng ở trang vật lý 3. Nội dung bên thứ ba có thể có điều kiện riêng;
giữ ghi nguồn của từng hình. Câu hỏi, mô tả và bản dịch trong bài là phần biên
soạn phục vụ học tập, không phải bản dịch chính thức, không được World Bank
xác nhận hoặc bảo trợ.

Đính chính phía kiểm chứng test: `bt14` có nhãn mẫu sai năm giá (2018).
Hình 5.4 trang 157 ghi **2010 USD**. [Bằng chứng và thời điểm phát hiện](../../results/bonus/test-source-errata.json)
được lưu trước khi có đầu ra câu này. Giữ nguyên file test/freeze/selection,
chấm theo PDF gốc như quy tắc đã công bố; không sửa agent dựa trên test.
