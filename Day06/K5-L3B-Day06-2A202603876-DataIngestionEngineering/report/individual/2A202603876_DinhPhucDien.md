# So sánh chiến lược chia đoạn và lọc metadata trong truy xuất tài liệu

**Học viên:** Đinh Phúc Diên — **MSSV:** 2A202603876 — **Lớp:** L3B  
**Bài thực hành:** Data Ingestion Engineering — **Ngày thực nghiệm:** 14/11/2026

## 1. Mục tiêu và dữ liệu

Bài thực nghiệm xây dựng pipeline lấy tài liệu, chuẩn hóa văn bản, chia đoạn, tạo embedding và lưu vào PostgreSQL với pgvector. Trên cùng một bộ dữ liệu, ba cấu hình được so sánh để xác định ảnh hưởng của cách chia đoạn và bộ lọc metadata đến chất lượng truy xuất. Phạm vi đánh giá dừng ở bằng chứng lấy về từ tài liệu; bài làm không xây dựng mô hình sinh câu trả lời.

Dữ liệu được lấy từ báo cáo *From the Last Mile to the Next Mile — 2022 Vietnam Poverty & Equity Assessment* của World Bank, số báo cáo 170511. Chủ đề được giới hạn ở diễn biến phúc lợi và các động lực giảm nghèo tại Việt Nam trong giai đoạn 2010–2020. Báo cáo sử dụng giấy phép **CC BY 3.0 IGO**, được ghi tại trang PDF vật lý 3. Thông tin trích dẫn và các thay đổi khi xử lý tài liệu được lưu trong [ATTRIBUTION.md](../../data/ATTRIBUTION.md).

API Documents & Reports cung cấp metadata và liên kết tải tài liệu. Lần kiểm tra nguồn nhận HTTP 200 cho API, PDF và TXT, không cần tài khoản hoặc API key. PDF có 232 trang, dung lượng 20.584.558 byte; checksum SHA-256 được ghim để bảo đảm các lần chạy dùng cùng một phiên bản. Corpus được trích từ PDF. Bản TXT là OCR chưa hiệu đính và chỉ được dùng để đối chiếu khả năng lấy dữ liệu.

Corpus gồm **39 trang nội dung với 119.228 ký tự sau chuẩn hóa**:

| Phạm vi | Trang PDF vật lý được chọn | Trang in tương ứng | Số trang |
|---|---|---|---:|
| Chương 1 — Diễn biến phúc lợi trong thập kỷ | 45–65, trừ 48 và 53 | 25–45, cùng các vị trí loại trừ | 19 |
| Chương 2 — Các động lực giảm nghèo | 75–97, trừ 88, 90 và 97 | 55–77, cùng các vị trí loại trừ | 20 |

Không tính bìa, mục lục, tài liệu tham khảo, phụ lục và năm trang chủ yếu là bảng, biểu đồ hoặc công thức. Mỗi trang được chọn có hơn 1.500 ký tự; không lặp trang để tăng quy mô corpus. Danh sách trang, số ký tự, thời điểm truy cập và checksum nằm trong [manifest](../../data/manifest.json) và [hồ sơ chọn nguồn](../../data/source-selection.json).

## 2. Pipeline và môi trường thực nghiệm

Văn bản được trích bằng pypdf ở chế độ plain, chuẩn hóa Unicode NFC và khoảng trắng theo phiên bản `NFC-paragraphs-code-v2`. Mỗi bản ghi giữ số trang PDF vật lý theo thứ tự từ 1, số trang in, URL nguồn và metadata của chương. Sau khi chia đoạn, `char_start` và `char_end` trỏ về khoảng ký tự `[start, end)` trong văn bản trang đã chuẩn hóa. Vì vậy, mỗi kết quả có thể được kiểm lại bằng đúng lát cắt văn bản nguồn.

PDF hai cột gây một số hạn chế: còn header, caption, xuống dòng và khoảng trắng do giãn chữ; 38/39 trang không giữ ranh giới đoạn dưới dạng dòng trống. Chế độ layout đã được thử trên các trang mẫu nhưng làm trộn thứ tự hai cột, nên không được dùng cho corpus. Các đoạn gold evidence đều lấy từ văn xuôi và được kiểm tra vị trí sau chuẩn hóa.

Embedding sử dụng `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, chạy trên CPU. Query và tài liệu dùng cùng model, vector 384 chiều, kiểu float32 và chuẩn hóa độ dài. Batch tối đa 16 đoạn; giới hạn đầu vào là 128 token. Pipeline kiểm tra độ dài trước khi encode và báo lỗi khi vượt giới hạn, thay vì tự cắt phần cuối văn bản.

Vector được lưu bền vững trong **PostgreSQL 16.16 với pgvector 0.7.4**, truy xuất exact search bằng khoảng cách cosine. A và B được nạp riêng; C dùng nguyên chunk, vector và dữ liệu vật lý của B. Việc nạp dữ liệu dùng một writer và transaction: thay corpus sẽ thay toàn bộ dữ liệu của chiến lược, lỗi batch sẽ rollback. Cache embedding có fingerprint theo model, revision, vai trò query/document, nội dung và cấu hình thực thi; checksum được kiểm trước khi sử dụng lại.

Môi trường đo dùng Python 3.12.13 trên Linux x86-64, CPU AMD Ryzen 7 4800H, với 16 CPU logic khả dụng và ngân sách 4 native threads. Các phiên bản chính gồm NumPy 2.5.4, PyTorch 2.15.0+cpu, Sentence Transformers 5.7.0, Transformers 5.23.0, pypdf 6.21.4 và psycopg 3.3.8. Danh sách phiên bản được lưu trong [environment.json](../../artifacts/environment.json). Hướng dẫn tạo môi trường Python 3.12 bằng venv hoặc Conda nằm tại [README](../../README.md).

Metadata được lưu cùng mỗi chunk:

| Trường | Kiểu dữ liệu | Nguồn giá trị và mục đích |
|---|---|---|
| `document_id`, `source` | Chuỗi | Định danh tài liệu và URL PDF; truy về tài liệu gốc |
| `page`, `printed_page` | Số nguyên | Số trang PDF và số in trên trang; mở đúng vị trí trích dẫn |
| `chapter`, `chapter_title` | Chuỗi | Mục lục báo cáo; lọc phạm vi chương 1 hoặc 2 |
| `year` | Số nguyên | Năm báo cáo 2022, theo thông tin xuất bản/copyright |
| `language`, `document_type`, `report_number` | Chuỗi | Ngôn ngữ English, loại Poverty Assessment và số báo cáo 170511 từ tài liệu/API |
| `api_document_date` | Chuỗi thời gian | Ngày `2023-04-10T04:00:00Z` từ API, lưu riêng với năm báo cáo |
| `version` | Chuỗi SHA-256 | Nhận diện đúng phiên bản PDF |
| `char_start`, `char_end` | Số nguyên | Đối chiếu nguyên văn chunk với trang đã chuẩn hóa |

## 3. Thiết kế thí nghiệm

### Cấu hình A, B và C

| Cấu hình | Quy tắc chia đoạn | Truy xuất |
|---|---|---|
| A | Độ dài cố định 300 ký tự, overlap 30 ký tự | Không lọc metadata |
| B | Ưu tiên ranh giới đoạn; đoạn quá dài được cắt tại ranh giới từ, tối đa 300 ký tự; không overlap | Không lọc metadata |
| C | Dùng chung chunk và vector của B | Thêm bộ lọc `chapter` khi câu hỏi có phạm vi đọc được cung cấp trước |

So sánh A–B thể hiện tác động của hai quy tắc chia đoạn, bao gồm khác biệt về overlap. So sánh B–C chỉ thay đổi bộ lọc. Do phần lớn ranh giới đoạn bị mất khi trích PDF, B chủ yếu sử dụng cách cắt tại ranh giới từ; kết quả không được diễn giải như một phép đánh giá hoàn chỉnh về chia đoạn theo cấu trúc tài liệu.

### Bộ câu hỏi và tiêu chí lựa chọn

Benchmark gồm **20 câu tiếng Anh**, chia trước thành 15 câu dev thuộc chương 1 và 5 câu test thuộc chương 2. Có bốn câu dùng metadata filter: q08, q14, q15 ở dev và q20 ở test. Với các câu này, phạm vi chương là đầu vào giả định do người đọc chọn trước khi truy xuất. Giá trị lọc không được suy ra từ nguồn gold hoặc đáp án.

Mỗi câu có đáp án kỳ vọng, nguồn, trang, đoạn trích và offsets. Ngoài 20 evidence chính, bốn evidence thay thế hợp lệ được khai báo để chấp nhận các trang có cùng nội dung hỗ trợ. Bộ câu hỏi, evidence, corpus và 10 vị trí đánh giá coherence được chốt bằng checksum trước ingest và retrieval. Hai chương vẫn có khái niệm trùng nhau, nên phép chia này không tạo thành một bộ test độc lập hoàn toàn về chủ đề. [Bộ câu hỏi](../../benchmark/questions.json), [kiểm tra evidence](../../benchmark/evidence_audit.json) và [thông tin chốt benchmark](../../benchmark/freeze.json) được nộp kèm.

Tiêu chí chọn chiến lược được xác định trước khi đọc test: ưu tiên **dev Evidence Hit@3**, sau đó đến **dev Hit@1**, rồi số chunk ít hơn; nếu vẫn bằng nhau, chọn theo thứ tự A, B, C. A được chọn trên dev trước khi chạy test. Corpus, model, câu hỏi, evidence và tham số chia đoạn được giữ nguyên sau đó.

### Cách đánh giá

Hit@1 là số câu có kết quả đầu tiên đạt yêu cầu chia cho tổng số câu. Evidence Hit@3 là số câu có ít nhất một kết quả đạt yêu cầu trong ba vị trí đầu chia cho tổng số câu. Trong phép đo tự động, một chunk phải đúng nguồn, đúng trang và chứa đầy đủ một evidence được chấp nhận sau khi chuẩn hóa khoảng trắng. Evidence nằm rải rác qua nhiều chunk không được tính là hit theo định nghĩa này. Hai evidence q08 và q20 dài lần lượt 314 và 321 ký tự, vượt giới hạn chunk 300; đặc điểm này được ghi nhận trước khi chạy và giữ lại để quan sát lỗi phân mảnh.

Coherence được đánh giá tại cùng 10 vị trí nguồn theo thang 0–2: 0 là không hiểu được do thiếu ý hoặc chủ thể; 1 là hiểu được một phần nhưng thiếu ngữ cảnh; 2 là tự hiểu được và giữ trọn ý. Mười vị trí được lấy từ 10 trang đầu đã sắp xếp; chọn chunk có điểm bắt đầu sớm nhất bao phủ vị trí đó. Mẫu này gồm toàn bộ các vị trí thuộc chương 1. B và C dùng cùng chunk, nên 30 phiếu tương ứng với 20 chunk khác nhau.

Metadata được đối chiếu trên 5 câu test × 3 kết quả × 3 cấu hình, tổng cộng 45 bản ghi. Grounding được đánh giá riêng cho 15 trường hợp test theo thang 0–2: 0 là không có bằng chứng; 1 là có bằng chứng nhưng thiếu điều kiện hoặc ngữ cảnh cần thiết; 2 là đủ bằng chứng để trả lời và truy nguồn. Điểm grounding xét cả bộ top-3, không suy từ Hit@3 và không đo độ chính xác câu trả lời của LLM.

## 4. Kết quả

### Độ chính xác truy xuất

Thời gian trong bảng là tổng thời gian SQL search của từng cấu hình, chưa gồm tải model và embedding câu hỏi. Chi phí API của pipeline bằng 0 do model chạy local; chi phí phần cứng và điện không được hạch toán.

| Cấu hình | Tập | Hit@1 | Evidence Hit@3 | Số chunk | Tổng SQL search (giây) | Chi phí API (USD) |
|---|---|---|---|---:|---:|---:|
| A | Dev | 3/15 (20,0%) | 4/15 (26,7%) | 459 | 0,0736 | 0 |
| B | Dev | 2/15 (13,3%) | 2/15 (13,3%) | 421 | 0,0747 | 0 |
| C | Dev | 3/15 (20,0%) | 3/15 (20,0%) | 421 | 0,0680 | 0 |
| A | Test | 2/5 (40,0%) | 2/5 (40,0%) | 459 | 0,0260 | 0 |
| B | Test | 1/5 (20,0%) | 1/5 (20,0%) | 421 | 0,0239 | 0 |
| C | Test | 1/5 (20,0%) | 1/5 (20,0%) | 421 | 0,0220 | 0 |

Kết quả từng câu, điểm cosine, nội dung và metadata của top-3 nằm trong [dev trace](../../results/20261114T061838.368412Z-evaluate/dev-traces.json) và [test trace](../../results/20261114T062008.998642Z-evaluate/test-traces.json). Bảng tổng hợp có ở [benchmark-metrics.csv](../../results/benchmark-metrics.csv); quyết định chọn A trước test được lưu tại [dev-selection.json](../../results/dev-selection.json).

### Quy mô dữ liệu và tài nguyên

| Cấu hình lưu trữ | Số chunk | Tổng ký tự chunk | Độ dài nhỏ nhất | Trung vị | P95 | Độ dài trung bình | Thời gian ingest (giây) |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 459 | 131.670 | 31 | 300 | 300 | 286,86 | 12,388 |
| B; C dùng chung | 421 | 118.845 | 16 | 296 | 300 | 282,29 | 10,507 |

Độ dài tính bằng ký tự; P95 dùng hạng gần nhất. Tổng ký tự của A lớn hơn corpus do overlap. B loại khoảng trắng ở rìa chunk nên tổng nhỏ hơn 119.228 ký tự của corpus. B giảm 38 chunk, tương đương 8,3% so với A; C không phát sinh thêm document embedding hoặc bản sao dữ liệu.

Toàn bộ giai đoạn ingest mất **30,511 giây**, bao gồm khởi tạo model và kết nối database. Cache embedding ghi nhận 871 miss và 9 hit trên 880 chunk A/B; file model đã được tải trước. A chạy trước B trong cùng tiến trình, vì vậy hai thời gian ingest không phải các phép đo cold/warm độc lập. Thời gian evaluate từ đầu đến cuối là 7,860 giây cho dev và 7,523 giây cho test.

Peak RSS của tiến trình Python theo `ru_maxrss` là **1.065,87 MiB**, khoảng 1,04 GiB; số đo không bao gồm PostgreSQL server. Ngân sách RAM cấu hình là 2.048 MiB, được kiểm ở ranh giới batch và không phải giới hạn cứng của hệ điều hành. Fetch dùng một worker, tối đa một tác vụ đồng thời, pacing một request/giây và giới hạn response 32 MiB. Các phép đo chi tiết được lưu trong [kết quả ingest](../../results/20261114T061734.896134Z-ingest/ingestion.json) và [telemetry](../../results/20261114T061734.896134Z-ingest/telemetry.jsonl).

### Coherence, metadata và grounding

| Cấu hình | Coherence trung bình /2 (n = 10) | Metadata đủ và đúng | Tuân thủ filter trên test | Grounding: số câu mức 0 / 1 / 2 | Grounding trung bình /2 |
|---|---|---|---|---|---:|
| A | 1,00 | 15/15 | N/A | 1 / 2 / 2 | 1,20 |
| B | 1,10 | 15/15 | N/A | 0 / 2 / 3 | 1,60 |
| C | 1,10 | 15/15 | 1/1 | 0 / 2 / 3 | 1,60 |

Ở coherence, A có 10 mẫu mức 1; B và C mỗi cấu hình có 9 mẫu mức 1 và một mẫu mức 2. Mẫu mức 2 nằm trên trang PDF 54, giữ được ý về phương pháp small area estimation dù phần dẫn và trích dẫn bị cắt. Những mẫu còn lại vẫn có thông tin đọc được nhưng thiếu chủ thể, điều kiện hoặc phần kết thúc nhận định. Toàn bộ nội dung, điểm, lý do và offsets nằm trong [30 phiếu coherence](../../results/manual-review/coherence.json).

Trong mẫu metadata, **45/45 bản ghi đủ và đúng**, gồm 31 chunk khác nhau thuộc 13 trang nguồn. Các trường URL, định danh, trang vật lý, trang in, chương, thuộc tính xuất bản, version và offsets được đối chiếu với corpus, PDF đã ghim checksum và snapshot API. Không phát hiện lỗi trong các trường đã kiểm. Chi tiết nằm trong [bảng kiểm metadata](../../results/manual-review/test-metadata-audit.json).

`printed_page` hỗ trợ đối chiếu số trang mà báo cáo sử dụng khi trích dẫn. `chapter` có tác dụng trực tiếp ở q20: C loại kết quả chương 1 ra khỏi phạm vi tìm kiếm và cả ba kết quả đều thuộc chương 2. Vì A và B không áp dụng filter, tỷ lệ tuân thủ của hai cấu hình được ghi N/A. Hạn chế của `chapter` là chỉ thu hẹp phạm vi, không bảo đảm kết quả liên quan hoặc đủ bằng chứng. Tương tự, năm báo cáo 2022 và ngày API năm 2023 phục vụ hai mục đích khác nhau và không thể dùng thay nhau.

| Câu test | A | B | C | Cơ sở chấm grounding |
|---|---:|---:|---:|---|
| q16 — Bảo hiểm gắn với hợp đồng lao động | 2 | 2 | 2 | Cả ba cấu hình giữ đủ social insurance và unemployment insurance. |
| q17 — Kỳ hồi cứu của VHLSS và LFS | 1 | 2 | 2 | A thiếu kỳ một tháng của LFS; B/C giữ đủ so sánh 12 tháng với một tháng. |
| q18 — Vì sao trợ cấp tiền mặt mất giá trị | 2 | 1 | 1 | A giữ được nguyên nhân không điều chỉnh theo lạm phát; B/C bị cắt trước nguyên nhân. |
| q19 — Kênh giảm nghèo chi phối phần lớn thập kỷ | 1 | 2 | 2 | A có thông tin liên quan nhưng thiếu kết luận chính; B/C nêu rõ vai trò chi phối của tăng trưởng. |
| q20 — Ý nghĩa nhân quả của phân rã thu nhập | 0 | 1 | 1 | A thiếu bằng chứng về nhân quả; B/C giữ kết luận nhưng thiếu giải thích về cân bằng tổng thể. |

[Phiếu grounding](../../results/manual-review/test-grounding.json) ghi lý do và phần bằng chứng cho từng trường hợp. B/C trả cùng top-3 ở q16–q19, nên 15 trường hợp trong bảng tương ứng với 11 bộ top-3 khác nhau.

## 5. Phân tích và lựa chọn chiến lược

A đạt dev Evidence Hit@3 = 4/15, cao hơn B = 2/15 và C = 3/15, nên được chọn theo tiêu chí đã định. Trên test, A đạt 2/5, còn B và C đạt 1/5. Lợi thế của A về chỉ số này đi kèm số chunk và tổng ký tự lưu trữ lớn hơn do overlap.

B giảm 8,3% số chunk nhưng chưa tận dụng được nhiều cấu trúc đoạn vì giới hạn trích PDF. Coherence tăng từ 1,00 lên 1,10 chỉ nhờ một mẫu trong 10 vị trí. Tại q14, B/C giữ được điều kiện dự báo trên trang PDF 63 trong một chunk, trong khi A không có chunk chứa trọn evidence. Ngược lại, q18 cho thấy bỏ overlap có thể làm mất mệnh đề quan trọng ở biên chunk. Các trường hợp này giải thích vì sao giảm số chunk không đồng nghĩa với tăng độ chính xác.

C tăng dev Hit@3 từ 2/15 lên 3/15 so với B. Cải thiện đến từ q15: bộ lọc chương 1 đưa bằng chứng ở trang PDF 65 lên vị trí đầu. Trên test, filter q20 đúng phạm vi nhưng không tăng số hit hoặc grounding, vì phần giải thích cần thiết vẫn bị chia cắt. Kết quả cho thấy lọc metadata giải quyết phạm vi tìm kiếm, còn việc bảo toàn bằng chứng phụ thuộc cách chia đoạn.

Grounding của B/C đạt 1,60/2, cao hơn A là 1,20/2. Sự khác biệt với Hit@3 đến từ cách đo: grounding xét đủ ý để trả lời trong cả top-3, còn metric tự động yêu cầu một chunk chứa trọn quote gold. Hai lỗi điển hình thể hiện rõ điều này:

1. **q17, trang PDF 83, trang in 63.** A trả cả ba chunk đúng trang nhưng thiếu kỳ hồi cứu một tháng của LFS, nên grounding bằng 1. B/C giữ đủ cặp 12 tháng–một tháng, đạt grounding 2. Cả ba cấu hình vẫn miss theo metric chính vì không chunk nào chứa trọn quote gold, trong đó còn có mệnh đề bổ sung về các loại thu nhập LFS không thu thập.
2. **q19, trang PDF 91 và các evidence thay thế ở trang 65/92.** A có hai chunk trong kho chứa đủ evidence hợp lệ nhưng chúng không vào top-3, thể hiện lỗi xếp hạng. B/C truy được đoạn trang 65 nêu rõ vai trò chi phối của tăng trưởng; đoạn này mất từ mở đầu “The” so với quote đã chốt, nên grounding đạt 2 nhưng strict Hit@3 vẫn bằng 0. Đây là giới hạn của phép khớp quote tự động đối với bằng chứng tương đương về nghĩa.

q20 còn cho thấy một lỗi có ảnh hưởng trực tiếp đến lập luận. Quote dài 321 ký tự không thể nằm trọn trong chunk tối đa 300 ký tự. B/C lấy được kết luận rằng phân rã không biểu thị hiệu ứng nhân quả, nhưng mất lý do các phân phối phản thực không phải kết quả của cân bằng kinh tế. Bộ lọc không khôi phục được phần giải thích đã bị cắt. [Phân tích phân mảnh evidence](../../results/evidence-fragmentation.json) cho phép đối chiếu sự khác nhau giữa lỗi chia đoạn và lỗi xếp hạng trên toàn bộ kho chunk.

Với tiêu chí lựa chọn đã chốt, A là cấu hình được giữ lại cho bộ thực nghiệm này. Kết quả chưa đủ để kết luận A tốt hơn tổng quát: test chỉ có năm câu, mẫu coherence tập trung ở chương 1 và thời gian đo chưa có nhiều lần lặp độc lập. Điểm truy xuất còn thấp; giới hạn 300 ký tự cùng lỗi cấu trúc PDF là hai nguyên nhân cần xử lý trước khi đưa pipeline vào ứng dụng. Hướng mở rộng là chia theo câu/token, bảo toàn mệnh đề điều kiện qua biên chunk và đánh giá trên dev cùng một holdout mới. Những thay đổi đó chưa được áp dụng vào số liệu trong báo cáo.

## 6. Tái lập và kiểm tra

Tạo môi trường **Python 3.12**, cài dependencies và khởi tạo PostgreSQL theo [hướng dẫn cài đặt](../../docs/INSTALLATION.md): lựa chọn 1 dùng venv; lựa chọn 2 dùng Conda, được khuyến khích để quản lý phiên bản Python. Sau khi kích hoạt môi trường và cấu hình kết nối database, chạy từ thư mục gốc repository:

```bash
cd starter
python -m src.run preflight
python -m src.run fetch
python -m src.run validate
python -m src.run ingest
python -m src.run evaluate --split dev
python -m src.run evaluate --split test
```

`fetch` tải đúng PDF theo checksum và danh sách trang đã khai báo; `validate` kiểm corpus, provenance, evidence và benchmark trước khi chạy model. Tham số nằm trong [pipeline.json](../../starter/config/pipeline.json); các đường dẫn cấu hình được tính từ gốc repository. Từng lần chạy lưu cấu hình, phiên bản, telemetry, kết quả và lỗi trong `results/`.

Bộ kiểm thử kỹ thuật có **44 test đạt, không có test bị bỏ qua**, bao gồm kiểm tra với PostgreSQL thật. Các ca kiểm thử bao phủ rollback khi COPY lỗi, nạp lại không nhân đôi, loại chunk cũ khi thay corpus, lọc metadata, cache hỏng và kiểm tra provenance/evidence. Kết quả được lưu trong [JUnit XML](../../results/engineering-tests.xml). Quy trình cài thư viện cũng được kiểm tra trong một venv Python 3.12 mới, tách biệt site-packages; `pip check`, model smoke test và bộ kiểm thử PostgreSQL đều chạy thành công. [Thông tin kiểm tra môi trường](../../artifacts/environment-verification.json) ghi phiên bản và lệnh cài đặt.

Lượt tái lập bằng Docker trên Ubuntu sử dụng Python 3.12.16, PostgreSQL 16.16 và pgvector 0.8.7, đạt **44/44 kiểm thử**, không bỏ qua ca nào. Cả 45 trường hợp dev và 15 trường hợp test có nội dung top-3, thứ tự và điểm số trùng với thí nghiệm gốc. Ingest tạo 459 chunk A và 421 chunk B; C dùng chung B. Lượt này có 880 cache hit và không có cache miss, nên không dùng thời gian ingest để so sánh tốc độ với lượt đầu. [Đối chiếu tái lập Docker](../../artifacts/docker-verification.json) và [JUnit Docker](../../results/docker-tests.xml) lưu bằng chứng riêng; số liệu của thí nghiệm gốc trong các bảng trên được giữ nguyên.

Codex được sử dụng để hỗ trợ lập trình, đối chiếu nguồn, xây dựng câu hỏi và phân tích kết quả. Nhãn coherence và grounding được tạo bằng hai lượt đọc của mô hình theo thang điểm đã nêu; lượt đối chiếu nhận mẫu ẩn danh, không nhận tên cấu hình hoặc điểm retrieval. Lượt đọc chính đã biết kết quả tổng thể, nên đánh giá không hoàn toàn mù. Metadata được kiểm bằng chương trình đối chiếu từng bản ghi với nguồn. Các nhãn định tính có lý do và trích dẫn để kiểm tra lại, nhưng không đại diện cho độ đồng thuận giữa những người chấm độc lập.
