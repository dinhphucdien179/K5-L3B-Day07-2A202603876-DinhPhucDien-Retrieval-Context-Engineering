# Báo cáo Day 7

**Họ tên:** Đinh Phúc Diên · **MSSV:** 2A202603876 · **Lớp:** L3B  
**Bài thực hành:** Retrieval & Context Engineering · **Ngày báo cáo:** 16/11/2026

## Dữ liệu và benchmark

Tôi sử dụng báo cáo *From the Last Mile to the Next Mile — 2022 Vietnam Poverty and Equity Assessment* của World Bank, xuất bản năm 2022. [PDF gốc](https://documents1.worldbank.org/curated/en/099115004242216918/pdf/P176261155e1805e1bd6e14287197d61965ce02eb562.pdf) có 232 trang vật lý; giấy phép CC BY 3.0 IGO được ghi ở trang 3. Các hình có nguồn bên thứ ba vẫn giữ ghi nguồn và điều kiện sử dụng tương ứng. Bản dịch và câu hỏi trong bài phục vụ học tập, không phải bản dịch chính thức của World Bank.

Phần cơ bản dùng lại dữ liệu Day06: **39 trang được chọn từ chương 1–2, 119.228 ký tự, 459 chunk** ở index A. Mỗi chunk dài tối đa 300 ký tự, chồng lặp 30 ký tự, có mã, nguồn, trang và vị trí bắt đầu/kết thúc. Phần bonus mở rộng ra toàn bộ tài liệu, được trình bày trong mục cuối. Số trang trong báo cáo này luôn là **trang vật lý của PDF**, không phải số in ở chân trang.

| Thành phần | Thiết lập phần cơ bản |
|---|---|
| Vector store | PostgreSQL 16.16, pgvector 0.8.7; tìm chính xác theo cosine trên index A của Day06 |
| Embedding | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Revision embedding | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| Véc-tơ | 384 chiều, float32, chuẩn hóa; tạo trên CPU bằng cùng model/revision của Day06 |
| Agent model | `openai/gpt-4o-mini` qua OpenRouter; temperature 0, tối đa 1.200 token đầu ra |
| Cách chạy | Docker Compose; Python 3.12 với venv hoặc Conda theo hệ điều hành; đường dẫn tương đối |
| Dev | 17 câu: 15 có đáp án và 2 thiếu bằng chứng |
| Test | 7 câu: 5 có đáp án và 2 thiếu bằng chứng; khác các câu test Day06 đã dùng trước đó |

[Benchmark cơ bản](../../data/day07/README.md) lưu câu hỏi, đáp án, trang và đoạn nguồn; [freeze](../../data/day07/freeze.json) lưu checksum của hai tập. Chỉ dev được dùng để chọn cấu hình. Test chạy sau khi lưu [quyết định lựa chọn](../../results/day07/selection.json). Agent nhận câu hỏi và kết quả truy xuất; đáp án chuẩn, nhãn chấm và vị trí evidence chuẩn chỉ được dùng ở phía đánh giá.

Câu có đáp án phải có đoạn nguồn trả lời đủ nội dung và điều kiện của câu hỏi. Câu thiếu bằng chứng hỏi thông tin gần chủ đề nhưng tài liệu không cung cấp, chẳng hạn số liệu năm 2026 hoặc khoảng tin cậy của một tỷ lệ. Không lấy số của năm khác hoặc tự tính khoảng tin cậy khi thiếu dữ liệu.

Các tiêu chí chấm được dùng thống nhất như sau:

- **Hit@1, Evidence Hit@3:** có ít nhất một đoạn evidence chuẩn nằm trọn trong kết quả đầu hoặc ba kết quả đầu, sau khi chuẩn hóa khoảng trắng. Các cấu hình dùng cùng cutoff 3.
- **Context Evidence Rate:** toàn bộ context cuối chứa đủ ít nhất một evidence chuẩn. Được ghép các khoảng nguồn liền nhau hoặc chồng lặp, không tự bù phần chưa truy xuất. Câu thiếu bằng chứng không nằm trong mẫu số của ba chỉ số này.
- **Điểm context 0/1/2:** không có bằng chứng / có nhưng thiếu điều kiện hoặc nguồn / đủ bằng chứng và nguồn. **Điểm trả lời 0/1/2:** sai hoặc từ chối nhầm / đúng một phần / đúng và đủ theo context. Điểm nội dung được chấm riêng với chất lượng citation.
- **Citation hợp lệ:** đoạn được trích thực sự hỗ trợ ý gắn với nó. Mã đoạn tồn tại chưa đủ để kết luận đúng. **Abstention đúng** là từ chối khi thiếu bằng chứng và không thêm khẳng định thiếu căn cứ; **từ chối nhầm** là từ chối câu có đáp án.

AI được dùng để hỗ trợ lập trình, soạn benchmark và đọc nguồn khi gán nhãn. Các file nhãn ghi rõ người/công cụ chấm và lý do; chưa có xác nhận kiểm tra độc lập của người học. Các số liệu dưới đây lấy từ trace và nhãn đã lưu, không lấy điểm unit test thay cho kết quả chạy model thật.

## Retrieval và thử nghiệm

Tôi thử ba phương pháp: dense, BM25 và hybrid. Dense dùng kho véc-tơ Day06. BM25 đưa từ về chữ thường, dùng k1 = 1,5 và b = 0,75. Hybrid hợp nhất hai bảng xếp hạng bằng RRF với k = 60, lấy tối thiểu 20 ứng viên mỗi nhánh; không cộng trực tiếp điểm cosine với điểm BM25. Không dùng reranker riêng.

Hai cấu hình cải thiện bổ sung lần lượt **một** hoặc **hai** chunk trước/sau mỗi kết quả hybrid. Chunk lân cận được chọn theo vị trí trên cùng trang và cùng nguồn. Phần bổ sung chỉ đi vào context, không được tính lại thành kết quả ranking để tăng Hit@3. Bài có ba phương pháp retrieval và hai thay đổi về cách ghép context.

Tất cả cấu hình dùng index A, top-k 5, context tối đa 6.000 ký tự gồm thông tin nguồn và tối đa ba lần search. Benchmark không đặt filter; CLI vẫn hỗ trợ filter do người dùng chỉ định. Không suy filter từ đáp án chuẩn. Context ưu tiên kết quả lượt mới, bỏ mã trùng và chỉ giữ những chunk vừa ngân sách.

Bảng theo mẫu đề dưới đây ghi **ranking của query đầu tiên do agent chọn** và **context cuối của agent**. Thời gian là tổng thời gian từng câu, gồm retrieval và gọi model; chi phí lấy từ `usage.cost` của các phản hồi đã lưu.

| Cấu hình | Phương pháp, top-k, filter, rerank, context budget | Giả thuyết / thay đổi | Split | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Thời gian / chi phí |
|---|---|---|---|---|---|---|---|
| Baseline — `dense_baseline` | Dense; k=5; không filter/rerank; 6.000 ký tự | Mốc so sánh từ kho Day06 | dev | 3/15 (20,0%) | 3/15 (20,0%) | 6/15 (40,0%) | 304,43 s / 0,00994905 USD |
| Phương pháp 2 — `bm25` | BM25; k=5; không filter/rerank; 6.000 ký tự | Từ khóa có thể tìm đúng tên chỉ tiêu, số liệu | dev | 2/15 (13,3%) | 2/15 (13,3%) | 9/15 (60,0%) | 182,82 s / 0,01016850 USD |
| Phương pháp 3 — `hybrid` | Dense + BM25, RRF; k=5; không filter/rerank; 6.000 ký tự | Kết hợp hai cách tìm | dev | 2/15 (13,3%) | 3/15 (20,0%) | 9/15 (60,0%) | 174,57 s / 0,01034850 USD |
| Cải thiện 1 — `hybrid_neighbors1` | Hybrid + ±1 chunk; các giới hạn như trên | Khôi phục câu bị cắt ở biên chunk | dev | 2/15 (13,3%) | 3/15 (20,0%) | 14/15 (93,3%) | 175,14 s / 0,01507260 USD |
| Cải thiện 2 — `hybrid_neighbors2` | Hybrid + ±2 chunk; các giới hạn như trên | Thử lấy thêm điều kiện và câu giải thích | dev | 2/15 (13,3%) | 3/15 (20,0%) | 13/15 (86,7%) | 157,18 s / 0,01398270 USD |
| Cấu hình đã chọn — `hybrid_neighbors1` | Hybrid + ±1 chunk; giữ nguyên cấu hình dev | Đánh giá sau khi chốt | test | 3/5 (60,0%) | 3/5 (60,0%) | 5/5 (100,0%) | 365,92 s / 0,00719955 USD |
| Baseline — `dense_baseline` | Dense; giữ nguyên cấu hình dev | So sánh trên cùng test | test | 2/5 (40,0%) | 3/5 (60,0%) | 3/5 (60,0%) | 69,91 s / 0,00446820 USD |

Để phân biệt tác động của retrieval với việc model viết lại query, tôi còn chạy riêng cả năm cấu hình bằng **nguyên câu hỏi dev**, không gọi model trả lời:

| Cấu hình | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Thời gian retrieval |
|---|---|---|---|---|
| Dense | 3/15 (20,0%) | 3/15 (20,0%) | 8/15 (53,3%) | 9,245 s |
| BM25 | 2/15 (13,3%) | 3/15 (20,0%) | 9/15 (60,0%) | 0,037 s |
| Hybrid | 3/15 (20,0%) | 3/15 (20,0%) | 8/15 (53,3%) | 0,108 s |
| Hybrid + ±1 chunk | 3/15 (20,0%) | 3/15 (20,0%) | 14/15 (93,3%) | 0,133 s |
| Hybrid + ±2 chunk | 3/15 (20,0%) | 3/15 (20,0%) | 14/15 (93,3%) | 0,138 s |

Chi phí API của lượt chỉ retrieval bằng 0. Dense ở lượt đầu phải nạp model, còn các lượt sau dùng model đã nạp; bảng này không đủ để kết luận chênh lệch tốc độ ổn định giữa các phương pháp. Kết quả query gốc nằm trong [retrieval-dev-01](../../results/day07/retrieval-dev-01/summary.json); từng query viết lại và các lượt tìm tiếp theo được giữ trong trace agent.

Giả thuyết mở rộng xuất phát từ cách chia cố định 300 ký tự: một câu hoặc điều kiện có thể nằm qua biên chunk. Hai cấu hình ±1 và ±2 được khai báo trước lượt so sánh dev. Sau khi chạy, hai trường hợp sau cho thấy tác động của thay đổi này:

1. **d01 — câu bị cắt trước điều kiện thời gian.** Dense từ chối; BM25 và hybrid chưa mở rộng nhầm yêu cầu so sánh qua thời gian thành so sánh giữa các bối cảnh. Mở rộng một chunk lấy được phần yêu cầu duy trì chuỗi thời gian nhất quán.
2. **d07 — có xu hướng nhưng thiếu số.** Dense chỉ nói tầng lớp trung lưu tăng, thiếu mức từ 7,3 lên 22,6 triệu người và tăng khoảng ba lần. Mở rộng một chunk lấy được câu tiếp nối và trả đủ số. Mở rộng hai chunk không bảo đảm tốt hơn vì query có thể lệch vào biểu đồ hoặc chú giải.

Lỗi **d10** còn tồn tại: câu hỏi cần hai chuyển dịch việc làm, rời nông nghiệp hoặc có việc làm với hợp đồng chính thức, nhưng agent lại trả thống kê dịch chuyển giữa các nhóm kinh tế. Mở rộng context không khắc phục được khi kết quả tìm ban đầu đã lệch. Hybrid ở d03 và hybrid ±2 ở d14 còn lỗi định dạng citation sau một lượt sửa; hai lỗi được giữ nguyên trong kết quả dev.

Quy tắc chọn ưu tiên điểm trả lời dev, sau đó là Context Evidence Rate và Evidence Hit@3; xét khả năng từ chối, thời gian và chi phí khi cần. **Hybrid ±1** đạt 1,867/2 điểm trả lời, đủ evidence ở 14/15 context, từ chối đúng 2/2 và không có lỗi thực thi. BM25 đạt 1,800/2 với chi phí thấp hơn; hybrid ±2 không tăng chất lượng và có một lỗi. Vì vậy tôi chọn hybrid ±1 trước khi chạy test.

## Agent và đánh giá

Agent cơ bản có hai tool: `search` và `finish`. Lượt đầu bắt buộc search; model tự chọn query và quyết định có tìm tiếp không. Sau tối đa ba lần search, model phải gọi `finish` để trả lời có citation hoặc từ chối. Mỗi lần có context mới, context cũ trong hội thoại được thay bằng thông báo để không cộng dồn vượt 6.000 ký tự.

Citation dùng mã chunk có trong context cuối và phải xuất hiện trong câu trả lời. Nếu sai định dạng, model có đúng một lượt sửa, được ghi cả phản hồi ban đầu và phần sửa. Nếu vẫn sai hoặc tool/API lỗi, chương trình ghi lỗi và trả mã thoát khác 0; không tạo câu trả lời thay thế. Client cơ bản không tự retry HTTP. Kiểm tra bằng code xác nhận cấu trúc và mã nguồn; việc citation hỗ trợ đúng nội dung được chấm riêng bằng cách đọc nguồn.

| Cấu hình / split | Tool use | Số lượt gọi | Grounded answer 0/1/2 và trung bình | Citation hợp lệ | Câu có citation | Abstention đúng | Từ chối nhầm |
|---|---|---|---|---|---|---|---|
| Dense / dev | 17/17 (100%) | 24 search; 45 LLM | 2/2/11; 1,600/2 | 19/23 (82,6%) | 14/14 (100%) | 2/2 (100%) | 1/15 (6,7%) |
| BM25 / dev | 17/17 (100%) | 20 search; 45 LLM | 0/3/12; 1,800/2 | 21/23 (91,3%) | 15/15 (100%) | 2/2 (100%) | 0/15 (0%) |
| Hybrid / dev | 16/16 (100%) | 20 search; 44 LLM | 1/2/11; 1,714/2 | 22/23 (95,7%) | 14/14 (100%) | 2/2 (100%) | 0/14 (0%) |
| Hybrid ±1 / dev | 17/17 (100%) | 20 search; 44 LLM | 1/0/14; 1,867/2 | 24/25 (96,0%) | 15/15 (100%) | 2/2 (100%) | 0/15 (0%) |
| Hybrid ±2 / dev | 16/16 (100%) | 19 search; 42 LLM | 1/1/12; 1,786/2 | 19/24 (79,2%) | 14/14 (100%) | 2/2 (100%) | 0/14 (0%) |
| Dense / test | 7/7 (100%) | 11 search; 21 LLM | 0/1/4; 1,800/2 | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 0/5 (0%) |
| Hybrid ±1 / test | 7/7 (100%) | 9 search; 21 LLM | 0/0/5; 2,000/2 | 6/8 (75,0%) | 5/5 (100%) | 2/2 (100%) | 0/5 (0%) |

Tool use tính trên câu thực thi thành công; điểm trả lời/context chỉ tính câu có đáp án thực thi thành công. Hybrid và hybrid ±2 mỗi cấu hình có một lỗi dev, được báo riêng nên mẫu số chất lượng còn 14 câu có đáp án. Tổng số search và LLM ở bảng trên tính cả lời gọi đã lưu của câu lỗi. Cột “Câu có citation” xét câu đã trả lời, không tính câu từ chối. Tỷ lệ citation xét từng citation đã chấm, không phải tỷ lệ câu đúng hoàn toàn.

| Cấu hình / split | Context đạt điểm 0 / 1 / 2 | Token vào / ra | Câu thành công dùng 1 / 2 / 3 search |
|---|---|---|---|
| Dense / dev | 0 / 4 / 11 | 52.887 / 4.176 | 12 / 3 / 2 |
| BM25 / dev | 0 / 3 / 12 | 54.174 / 4.716 | 15 / 1 / 1 |
| Hybrid / dev | 0 / 3 / 11 | 52.098 / 5.215 | 14 / 1 / 1 |
| Hybrid ±1 / dev | 0 / 1 / 14 | 86.996 / 4.732 | 15 / 1 / 1 |
| Hybrid ±2 / dev | 0 / 2 / 12 | 83.162 / 4.706 | 15 / 0 / 1 |
| Dense / test | 0 / 1 / 4 | 26.496 / 1.399 | 5 / 0 / 2 |
| Hybrid ±1 / test | 0 / 0 / 5 | 44.213 / 1.986 | 6 / 0 / 1 |

Bảng sau đối chiếu toàn bộ bảy câu test của cả baseline và cấu hình đã chọn. Câu trả lời được tóm tắt bằng tiếng Việt; trace giữ nguyên bản đã chạy. Mã citation viết gọn còn mười ký tự đầu để dễ đọc, mã đầy đủ nằm trong trace.

| Query ID | Loại câu | Tool call và kết quả | Câu trả lời và citation | Nhãn, lý do |
|---|---|---|---|---|
| t01 — Dense | Có đáp án | 1 search; nguồn trang 76 | Tỷ lệ hộ có người học cao nhất ở mức THCS trở xuống: 50% năm 2010 → khoảng 44% năm 2020; `8b517adbbc` | Context 2, trả lời 2; citation 1/1, đủ hai mốc |
| t01 — Hybrid ±1 | Có đáp án | 1 search; thêm đoạn liền kề trang 76 | Đủ hai tỷ lệ, thêm 1,7 triệu hộ có người hoàn thành bậc đại học; `8b517adbbc`, `182b564bec` | Context 2, trả lời 2; citation 2/2 |
| t02 — Dense | Có đáp án | 1 search; nguồn trang 78 | Doanh nghiệp nước ngoài trả lương gấp đôi doanh nghiệp trong nước; `f25e110305` | Context 2, trả lời 2; citation 1/1 |
| t02 — Hybrid ±1 | Có đáp án | 1 search; nguồn và đoạn lân cận trang 78 | Đúng mức gấp đôi; thêm ý hợp đồng/bảo hiểm và vai trò FDI; `f25e110305`, `c6e93d6fe9` | Context 2, trả lời 2; citation 1/2: nguồn thứ hai chưa hỗ trợ đủ ý bổ sung |
| t03 — Dense | Có đáp án | 1 search; nguồn trang 84 | Khoảng 10% hộ nhận lương hưu năm 2020; `b9fb34f0c5` | Context 2, trả lời 2; citation 1/1 |
| t03 — Hybrid ±1 | Có đáp án | 1 search; nguồn và đoạn lân cận trang 84 | Đúng 10% năm 2020, thêm điều kiện việc làm “có hợp đồng”; `b9fb34f0c5` | Context 2, trả lời 2; citation 0/1: điều kiện thêm nằm ở đoạn bên cạnh chưa được trích |
| t04 — Dense | Có đáp án | 1 search; nguồn trang 86 | Hộ có ít nhất một người nhận tiền công/lương: 53,3% năm 2010 → 64,7% năm 2020; `99edb32cb5` | Context 2, trả lời 2; citation 1/1 |
| t04 — Hybrid ±1 | Có đáp án | 1 search; nguồn trang 86 | Đủ 53,3% và 64,7% theo hai năm; `99edb32cb5` | Context 2, trả lời 2; citation 1/1 |
| t05 — Dense | Có đáp án | 1 search; nguồn trang 93 bị cắt | Chỉ nêu nghèo nông thôn/thành thị 22%/4,5% năm 2010; `09e7fe6695` | Context 1, trả lời 1; citation 1/1 cho phần đã nêu, thiếu hai số năm 2020 |
| t05 — Hybrid ±1 | Có đáp án | 1 search; ghép được đoạn tiếp trang 93 | 22%/4,5% năm 2010 → 7%/1,5% năm 2020; `09e7fe6695`, `adba617129` | Context 2, trả lời 2; citation 2/2, đủ bốn tỷ lệ |
| tu01 — Dense | Thiếu bằng chứng | 3 search; chỉ có số năm 2020 | Từ chối trả tỷ lệ hộ có lương hưu năm 2026 | Từ chối đúng; không dùng số 2020 thay 2026 |
| tu01 — Hybrid ±1 | Thiếu bằng chứng | 1 search; không có số 2026 | Nêu không đủ bằng chứng cho năm 2026 | Từ chối đúng |
| tu02 — Dense | Thiếu bằng chứng | 3 search; không có khoảng tin cậy | Từ chối nêu hai cận khoảng tin cậy 95% của tỷ lệ hộ có lương hưu | Từ chối đúng; không suy từ tỷ lệ xấp xỉ |
| tu02 — Hybrid ±1 | Thiếu bằng chứng | 3 search; không có khoảng tin cậy | Nêu không đủ bằng chứng để trả hai cận | Từ chối đúng |

Trên cùng test, mở rộng một chunk giúp context đủ evidence tăng từ **3/5 lên 5/5**, điểm trả lời từ **1,800 lên 2,000/2**, nhưng citation hợp lệ giảm từ **5/5 xuống 6/8** do hai ý bổ sung ở t02 và t03. Vì vậy không thể gọi đây là kết quả đúng hoàn toàn cả nội dung lẫn trích dẫn. Chi phí tăng từ 0,00446820 lên 0,00719955 USD; tổng thời gian từng câu cũng tăng từ 69,91 lên 365,92 giây trong lượt đo này.

Trace và nhãn nằm tại [agent-dev-01](../../results/day07/agent-dev-01/summary.json), [baseline test](../../results/day07/agent-test-01/dense_baseline/traces.json) và [hybrid ±1 test](../../results/day07/agent-test-01/hybrid_neighbors1/traces.json). Mỗi thư mục trial có `traces.json`, `evidence-metrics.json`, `reviews.json` và `review-summary.json`; bảng chung là [benchmark-metrics.csv](../../results/day07/benchmark-metrics.csv). [Kiểm tra phần cơ bản](../../results/day07/verification.json) đối chiếu 99 lượt agent: 85 dev và 14 test, có hai lỗi dev và không có lỗi test.

Lệnh chạy từ gốc project sau khi chuẩn bị Day06:

```bash
docker compose -f compose.day07.yml run --rm day07 check
docker compose -f compose.day07.yml run --rm day07 ask --method hybrid --neighbors 1 --query 'What does the Shared Prosperity indicator measure?' --top-k 5 --budget 6000 --max-searches 3 --output results/day07/my-answer.json
docker compose -f compose.day07.yml run --rm day07 bench --suite agent --split test --selection results/day07/selection.json --output results/day07/my-test --workers 3
```

[Hướng dẫn chạy chung](../../docs/RUN.md) ghi đủ phần cài đặt, API, benchmark, chấm nhãn và lệnh tạo môi trường venv/Conda cho Windows, macOS và Linux. Dùng output mới khi chạy lại, giữ kết quả đã nộp. Các lệnh agent/benchmark gọi API thật.

Thí nghiệm công bố chạy trên Linux, Python 3.12. Người nhận bài tự tạo môi trường theo hướng dẫn: Windows chạy trong WSL2; macOS dùng Python riêng cho bonus và container Linux cho Day06/phần cơ bản. Chưa có lượt kiểm thử trực tiếp trên máy Windows hoặc macOS trong kết quả nộp.

Giới hạn chính là bộ câu hỏi nhỏ, cùng một tài liệu; text PDF hai cột có thể mất cấu trúc và cách so khớp nguyên văn có thể bỏ sót diễn đạt tương đương. Chi phí chỉ cộng phản hồi đã ghi; một request bị ngắt có thể đã tính phí nhưng chưa nhận được usage. Thời gian cộng từng câu không phải thời gian đồng hồ khi chạy song song. Temperature 0 cũng không bảo đảm đáp án giống từng chữ ở lần chạy khác.

## Thử thách nâng cao (nếu thực hiện)

Phần nâng cao dùng **toàn bộ 232 trang** của cùng báo cáo World Bank 2022, cùng quyền sử dụng nêu ở mục đầu. PDF được kiểm bằng SHA-256 `6b2e5b40b08a3454f2265564e781bbf7bc0038ba37cb87ca32e1446b8f6b4e00`; nếu chưa có trong cache, chương trình tải từ URL gốc và kiểm checksum trước khi dùng. [Manifest](../../data/bonus/manifest.json) ghi phiên bản Poppler tạo index, giấy phép, thống kê từng trang và giới hạn trích xuất.

**Xử lý và tìm evidence.** Poppler 24.02.0 trích text theo bố cục toàn trang. Index có **437 bản ghi: 232 trang, 171 hình có số và 34 bảng có số**; cả tám trang ít text cũng được giữ. Bản ghi hình/bảng có trang, caption, tọa độ caption và khung trang gốc. Cả 205 đối tượng có số đều xác định được hộp caption. Sáu sai lệch mã/số trang trong mục lục được đối chiếu với caption thực; [bản sửa danh mục](../../data/bonus/catalog-amendment.json) giữ giải thích trước benchmark.

Search dùng BM25 trên text và caption, tăng trọng số caption và nhận mã Figure/Table/Section được nêu trong chính câu hỏi. Không đưa locator chuẩn của bộ chấm vào search. Ảnh, sơ đồ và biểu đồ được đọc từ pixel của PDF bằng vision model lúc trả lời. Crop dùng caption, cột và dòng Source để giữ vùng nội dung; khi cần, `inspect_pages` mở toàn trang rộng 1.600 pixel. Agent có thể kiểm tra lại trục, chú giải, ô bảng và các đường nối của sơ đồ từ ảnh gốc.

Đây chưa phải index đa phương thức theo véc-tơ. Chương trình không tạo OCR riêng, không trích bảng thành ô có cấu trúc và không tự sinh mô tả ngữ nghĩa cho mọi ảnh. Hình không đánh số vẫn truy cập được qua trang, nhưng không có bản ghi đối tượng riêng. Crop là heuristic nên có thể lấy thêm chữ lân cận hoặc cắt thiếu chi tiết; toàn trang là cách kiểm tra lại. Không chỉ index những trang có trong benchmark.

**Benchmark và chọn cấu hình.** [Bộ hiện tại](../../data/bonus-v2/README.md) có **18 dev** (15 có đáp án, 3 thiếu bằng chứng) và **30 test mới**. Mỗi câu chỉ thuộc một nhóm chính. Năm câu sơ đồ test dùng năm sơ đồ khái niệm khác nhau; bốn câu multi-hop cần evidence từ ít nhất hai trang. Gold lưu trang vật lý, mã/vùng hình hoặc bảng, hàng/cột, ý bắt buộc, đơn vị, phép tính và dung sai đọc biểu đồ; câu thiếu bằng chứng có cách tìm kiểm tra trong toàn tài liệu. [Freeze](../../data/bonus-v2/freeze.json) được tạo trước lượt chạy test mới và khóa cả corpus dùng chung.

Tôi đã thử text-only, text kèm ảnh toàn trang, crop ảnh và crop chỉ cho citation vào ảnh model đã nhận. Lượt text-only hoàn tất ở [dev-gemini-05/layout_text](../../results/bonus/dev-gemini-05/layout_text/summary.json) đạt 8/18, gồm tám lỗi thực thi; cấu hình crop chỉ citation vào ảnh ở bản trước đạt 17/18 dev. Đây là các lượt phát triển với khác biệt cả mã xử lý giao thức, không phải phép đo riêng tác động của vision. Sau khi sửa giao thức, cấu hình `layout_vision_image` được đo đủ 18 dev trên mã hiện tại, đạt **15/18 (83,3%)**, và được [chốt trước test](../../results/bonus/selection-v2.json). Hai câu lỗi HTTP 429 và một câu từ chối với lý do sai đều được giữ trong mẫu số.

| Thành phần | Cấu hình bonus đã chốt |
|---|---|
| Model / provider | `gemini-3.5-flash-lite`, Gemini API trực tiếp; temperature 0, reasoning `low`, tối đa 8.192 token đầu ra |
| Retrieval / context | `layout_vision_image`; top-k 3; tối đa 20.000 ký tự; crop ảnh, tối đa hai ảnh đang hiện diện; không filter từ gold |
| Tool và dừng | `search`, `inspect_pages`, `finish`; tối đa ba search và hai lần inspect, mỗi inspect tối đa hai trang |
| Trả lời / citation | Model gửi từng ý kèm evidence ID; chỉ nhận citation có trong context và ảnh model đã được xem; còn phải chấm hỗ trợ nội dung bằng bản gốc |
| Sửa giao thức | Tối đa một lượt yêu cầu gọi finish nếu model trả văn bản; một lượt cho model inspect khi thiếu ảnh nguồn; giữ ảnh cũ nếu còn trong context và trong hạn mức |
| Mạng / song song | Hai worker, tối đa hai request đồng thời, cách ít nhất sáu giây giữa lần gửi; timeout 120 giây; tối đa hai retry cho HTTP 502/503/504 |

Sửa giao thức không tự biến bản nháp thành đáp án, không chọn trang thay model và không chấp nhận evidence ID lạ. Các bước sửa được ghi trong trace. Ba lỗi dev hiện tại là bd15 và bd16 gặp HTTP 429; bd18 từ chối vì nói Bảng 4.1 không có trong index, trong khi bảng ở trang 132 đã được tìm thấy. Thông tin thực sự thiếu là khoảng tin cậy HCI. Vì lý do từ chối thêm một khẳng định sai, bd18 bị chấm không đạt.

**Lý do có bộ test mới.** Bản trước đạt **26/30 (86,7%)**, gồm ba lỗi thực thi và một từ chối sai. Sau khi dùng các lỗi đó để sửa giao thức và giữ ảnh context, bộ test cũ không còn được dùng để báo điểm mới. Kết quả cũ, [selection](../../results/bonus/selection.json), [mã nguồn đã khóa](../../results/bonus/frozen-runtime-v1/manifest.json) và [nhãn test cũ](../../results/bonus/test-gemini-01/layout_vision_image/reviews.json) được giữ để kiểm tra. Test cũ có [đính chính nguồn bt14](../../results/bonus/test-source-errata.json): trục giá ở Hình 5.4 là USD giá 2010, không phải 2018; đã ghi nhận trước đầu ra của câu đó, không sửa file test/freeze. Bộ mới hỏi các ô, nhánh và thông tin khác; một số nguồn trang được dùng lại nên không suy rằng hai bộ có độ khó bằng nhau.

Chấm bonus theo tiêu chí đạt/không đạt của đề: câu có đáp án phải đúng và đủ mọi ý, điều kiện, đơn vị, phép tính và citation; câu thiếu bằng chứng phải từ chối đúng, không bịa thêm. Lỗi hệ thống hoặc timeout tính không đạt và giữ trong mẫu số. Nhãn từng câu được đối chiếu với ảnh PDF gốc, không chỉ dựa vào text trích xuất hoặc một LLM judge.

| Nhóm test | Đạt / tổng | Tỷ lệ | Lỗi / nhận xét |
|---|---|---|---|
| Bảng | 6/6 | 100,0% | Đúng hàng, cột, đơn vị và phép tính |
| Ảnh, sơ đồ | 5/5 | 100,0% | Năm sơ đồ khái niệm khác nhau; kiểm tra nhánh và chiều quan hệ |
| Biểu đồ | 5/5 | 100,0% | Đối chiếu trục, màu, chú giải, mốc năm và dung sai đã khóa |
| Multi-hop | 4/4 | 100,0% | Mỗi câu có đủ nguồn từ ít nhất hai trang |
| Text | 4/4 | 100,0% | Đủ nội dung và điều kiện được hỏi |
| Thiếu bằng chứng | 6/6 | 100,0% | Từ chối, không suy thêm số liệu không có |
| **Toàn bộ** | **30/30** | **100,0%** | **0 câu lỗi hệ thống; vượt ngưỡng 27/30 của đề** |

Đối chiếu từng câu test mới dưới đây tóm tắt đáp án đã nhận và vùng nguồn. Mỗi ID dẫn thẳng tới trace; [reviews.json](../../results/bonus/test-gemini-02/layout_vision_image/reviews.json) giữ nhãn và lý do đầy đủ.

| Query ID | Nhóm | Câu trả lời / hành vi được chấm | Evidence từ PDF gốc | Nhãn |
|---|---|---|---|---|
| [v2t01](../../results/bonus/test-gemini-02/layout_vision_image/v2t01.json) | Bảng | UMIC 40,8% năm 2012 → 23,4% năm 2018; giảm 17,4 điểm phần trăm, chuẩn 5,50 USD/ngày PPP2011 | Bảng 1.1, trang 48 | Đạt |
| [v2t02](../../results/bonus/test-gemini-02/layout_vision_image/v2t02.json) | Bảng | IPL 5,38 → 1,44; giảm 3,94 nghìn tỷ VND giá 2020/năm, giai đoạn 2010–2020 | Bảng 1.3, panel B, trang 49 | Đạt |
| [v2t03](../../results/bonus/test-gemini-02/layout_vision_image/v2t03.json) | Bảng | Tây Nguyên 5.115.135 người năm 2009 → 5.842.605 năm 2019; tăng 727.470 | Bảng 2.1, trang 75 | Đạt |
| [v2t04](../../results/bonus/test-gemini-02/layout_vision_image/v2t04.json) | Bảng | Tỷ lệ trẻ dưới 5 tuổi không thấp còi: 0,773 → 0,762; giảm 1,1 điểm phần trăm | Bảng 4.1, trang 132 | Đạt |
| [v2t05](../../results/bonus/test-gemini-02/layout_vision_image/v2t05.json) | Bảng | CIT trong thu từ dầu 49, CIT trong thuế trực thu ngoài dầu 202; chênh 153 nghìn tỷ đồng năm 2018 | Bảng 7.1, trang 199 | Đạt |
| [v2t06](../../results/bonus/test-gemini-02/layout_vision_image/v2t06.json) | Bảng | Tiểu học 63/1,1% GDP, THCS 49/0,9% GDP; chênh 14 nghìn tỷ và 0,2 điểm phần trăm GDP năm 2018 | Bảng 7.2, trang 200 | Đạt |
| [v2t07](../../results/bonus/test-gemini-02/layout_vision_image/v2t07.json) | Sơ đồ | Thu nhập/người lớn tách thành lao động/ngoài lao động; nhánh lao động tách tiếp thành tỷ lệ có việc và thu nhập/người có việc | Hình B.2.4.1, trang 96; các nhánh bên phải | Đạt |
| [v2t08](../../results/bonus/test-gemini-02/layout_vision_image/v2t08.json) | Sơ đồ | Đúng ba nhánh năng suất trực tiếp từ HCI; Survival chỉ nối với sống tới 5 tuổi | Hình B.4.1.1, trang 135 | Đạt |
| [v2t09](../../results/bonus/test-gemini-02/layout_vision_image/v2t09.json) | Sơ đồ | Đủ năm nhánh dịch vụ cơ bản: nhà ở, bảo hiểm/y tế, giáo dục, nước sạch, tiếp cận thông tin | Box 6.3, trang 190; nhánh xám bên phải | Đạt |
| [v2t10](../../results/bonus/test-gemini-02/layout_vision_image/v2t10.json) | Sơ đồ | Consumer Income → Final Income cộng trợ cấp hiện vật ròng sau phí; hai ngành y tế và giáo dục | Hình B.7.1.1, trang 197 | Đạt |
| [v2t11](../../results/bonus/test-gemini-02/layout_vision_image/v2t11.json) | Sơ đồ | Bảo hiểm xã hội cần cân bằng tính toán bảo hiểm; phần công bằng chuyển sang nguồn thu chung rộng hơn | Hình 8.1, panel b, trang 225 | Đạt |
| [v2t12](../../results/bonus/test-gemini-02/layout_vision_image/v2t12.json) | Biểu đồ | Hộ có thành viên lớn tuổi nhất 60–69: 2,5 → 4,6 triệu hộ, tăng 2,1 triệu, 2010–2020 | Hình 2.1, trang 75 | Đạt |
| [v2t13](../../results/bonus/test-gemini-02/layout_vision_image/v2t13.json) | Biểu đồ | Hộ có trình độ hoàn thành cao nhất là đại học: 3,0 → 4,7 triệu, tăng 1,7 triệu, 2010–2020 | Hình 2.3 và note, trang 76 | Đạt |
| [v2t14](../../results/bonus/test-gemini-02/layout_vision_image/v2t14.json) | Biểu đồ | Việc kỹ năng trung bình tăng khoảng 2,9 triệu; kỹ năng thấp giảm khoảng 3,1 triệu người, 2015–2020 | Hình 2.7, trang 78; màu cam/xám, đúng dấu | Đạt |
| [v2t15](../../results/bonus/test-gemini-02/layout_vision_image/v2t15.json) | Biểu đồ | Không hợp đồng, nông/ngư: 56,2% → 40,4%, giảm 15,8 điểm phần trăm, 2010–2020 | Hình 2.8, trang 79 | Đạt |
| [v2t16](../../results/bonus/test-gemini-02/layout_vision_image/v2t16.json) | Biểu đồ | Nhóm nghèo nhất khoảng 3,3 nguồn thu, giàu nhất khoảng 2,9; nhóm giàu không đa dạng hơn theo thước đo này | Hình 2.11, panel A, trang 82 | Đạt |
| [v2t17](../../results/bonus/test-gemini-02/layout_vision_image/v2t17.json) | Multi-hop | Sống tuổi 15–60: toàn quốc 0,867, nam 0,813, nữ 0,924; nữ–nam chênh 11,1 điểm phần trăm năm 2020 | Bảng 4.1 trang 132 và Bảng 4.2 trang 137 | Đạt |
| [v2t18](../../results/bonus/test-gemini-02/layout_vision_image/v2t18.json) | Multi-hop | CIT trực thu ngoài dầu 202, trợ cấp trực tiếp 40; chênh 162 nghìn tỷ đồng năm 2018; không suy phân bổ ngân sách | Bảng 7.1–7.2, trang 199–200 | Đạt |
| [v2t19](../../results/bonus/test-gemini-02/layout_vision_image/v2t19.json) | Multi-hop | 116,91 nghìn tỷ / 18,3 triệu người ≈ 6,39 triệu VND giá 2020/người/năm, chuẩn UMIC | Bảng 1.2 trang 48 và Bảng 1.3 panel B trang 49 | Đạt |
| [v2t20](../../results/bonus/test-gemini-02/layout_vision_image/v2t20.json) | Multi-hop | Trung bình 3,7 thành viên/hộ năm 2020; mẫu chi tiêu VHLSS 9.000 quan sát, không đại diện cấp tỉnh | Trang 75 và Box 8.2 trang 220 | Đạt |
| [v2t21](../../results/bonus/test-gemini-02/layout_vision_image/v2t21.json) | Text | ODIN2020 hạng 91/187; hai luật thống kê được so sánh là năm 2015 và 2003 | Box 8.2, trang 220 | Đạt |
| [v2t22](../../results/bonus/test-gemini-02/layout_vision_image/v2t22.json) | Text | Decomposition không tách được returns/endowments; phương pháp không phải mô hình cân bằng tổng thể nên không suy đóng góp thành tác động nhân quả | Box 2.4, trang 96 | Đạt |
| [v2t23](../../results/bonus/test-gemini-02/layout_vision_image/v2t23.json) | Text | Khoản hộ trả cho trường làm giảm lợi ích giáo dục ròng trong hệ thống tài khóa; đồng phục/sách trả tư nhân nằm ngoài hệ thống đó | Đoạn education cột phải, trang 200 | Đạt |
| [v2t24](../../results/bonus/test-gemini-02/layout_vision_image/v2t24.json) | Text | MPSARD phê duyệt năm 2017; đề xuất triển khai dần tiền mặt cho trẻ sơ sinh và dưới 4 tuổi | Box 6.3, trang 190 | Đạt |
| [v2t25](../../results/bonus/test-gemini-02/layout_vision_image/v2t25.json) | Thiếu bằng chứng | Từ chối nêu p-value cho tác động nhân quả | Box 2.4 trang 96 và tìm toàn tài liệu: không có p-value đó | Đạt |
| [v2t26](../../results/bonus/test-gemini-02/layout_vision_image/v2t26.json) | Thiếu bằng chứng | Từ chối tạo ma trận hiệp phương sai thu nhập hộ | Hình 2.12 trang 84 và kiểm tra toàn tài liệu | Đạt |
| [v2t27](../../results/bonus/test-gemini-02/layout_vision_image/v2t27.json) | Thiếu bằng chứng | Từ chối cung cấp mã phần mềm bảo hiểm từ một sơ đồ khái niệm | Hình 8.1, trang 225; không có mã thực thi | Đạt |
| [v2t28](../../results/bonus/test-gemini-02/layout_vision_image/v2t28.json) | Thiếu bằng chứng | Từ chối nêu tọa độ từng hộ, đồng thời chỉ ra hình không phải bản đồ nước sạch | Hình 6.5 trang 179 là bản đồ môi trường; không có tọa độ hộ | Đạt |
| [v2t29](../../results/bonus/test-gemini-02/layout_vision_image/v2t29.json) | Thiếu bằng chứng | Từ chối suy DALY từng quận/huyện từ bản đồ PM2.5 | Hình 6.5 trang 179 và tìm toàn tài liệu: không có số DALY được hỏi | Đạt |
| [v2t30](../../results/bonus/test-gemini-02/layout_vision_image/v2t30.json) | Thiếu bằng chứng | Từ chối nêu ngày triển khai theo luật khi báo cáo chỉ khuyến nghị đổi chương trình/phương pháp dạy | Bảng 8.2, trang 222; không có ngày/tháng/năm bắt buộc | Đạt |

Riêng v2t28 có tiền đề sai ngay trong câu hỏi về “bản đồ nước sạch”. [Ghi nhận nguồn](../../results/bonus/v2-test-source-notes.json) được lưu trước khi có đầu ra câu này. Câu hỏi và freeze giữ nguyên; model từ chối vì không có tọa độ và sửa tiền đề sai, phù hợp tiêu chí thiếu bằng chứng đã đặt trước.

**Thời gian, chi phí và lỗi hệ thống.** Dev chạy qua hai đợt; các trace đã lưu, kể cả hai lỗi quota, không bị thay bằng lần chạy khác. Test mới không có lỗi cuối cùng, timeout hay HTTP 429. Có ba HTTP 503 được retry thành công; các lần thử lại vẫn nằm trong trace.

| Phép đo | Dev hiện tại | Test mới |
|---|---|---|
| Đạt / tổng | 15/18 (83,3%) | 30/30 (100,0%) |
| Câu lỗi cuối cùng | 2 HTTP 429 | 0 |
| HTTP 503 đã phục hồi | 0 | 3 |
| Phản hồi model thành công / tổng HTTP attempt | 53 / 55 | 102 / 105 |
| Token vào / ra | 228.202 / 4.824 | 444.723 / 8.669 |
| Tổng thời gian từng câu | 616,74 s | 1.245,07 s |
| Thời gian đồng hồ | 322,82 s qua hai đợt, không tính khoảng dừng | 627,26 s, khoảng 10 phút 27 giây |
| Chi phí thực | Chưa xác định | Chưa xác định |

Gemini không trả số tiền API trong usage nên chi phí ghi là chưa xác định, không coi bằng 0 và không suy hóa đơn từ token. Chưa đo đối chứng một worker nên không kết luận hai worker nhanh gấp đôi. Mức song song và khoảng giãn là thiết lập của lượt chạy, không bảo đảm phù hợp mọi hạn mức tài khoản.

**Bằng chứng và tái lập.** [Dev hiện tại](../../results/bonus/dev-gemini-07/layout_vision_image/summary.json), [test mới](../../results/bonus/test-gemini-02/layout_vision_image/summary.json), [metrics từng câu](../../results/bonus/v2-case-metrics.csv), [đối chiếu PDF gốc](../../results/bonus/v2-original-source-review.json) và [kiểm tra các câu thiếu bằng chứng](../../results/bonus/v2-absence-audit.json) giữ đủ số liệu để kiểm tra lại. Trace lưu query, tool, context, câu trả lời, evidence ID, tọa độ/checksum ảnh, usage và lỗi. Các tệp dev đã được selection khóa checksum được giữ nguyên.

```bash
# Kích hoạt venv hoặc Conda theo hướng dẫn chạy trước khi chạy các lệnh dưới.
export PYTHONPATH="$PWD/src"
python -m bonus prepare
python -m bonus bench --provider gemini --dataset data/bonus-v2 --split test --selection results/bonus/selection-v2.json --output results/bonus/my-test --workers 2
python -m unittest discover -s tests -v
```

Hướng dẫn cài đặt và cách chấm lượt chạy mới nằm trong [docs/RUN.md](../../docs/RUN.md). Chạy lại test đã công bố là kiểm tra tái lập; nếu tiếp tục sửa theo lỗi test thì cần bộ test mới trước khi báo điểm độc lập. Lần kiểm thử code cuối qua **65/65 test bằng Python 3.12 trong venv mới trên Linux**, chỉ cài dependency từ `requirements.txt`; [kiểm tra bài nộp](../../results/submission/verification.json) và [log unit test](../../results/submission/unit-tests.log) lưu kết quả. [Bằng chứng Docker](../../results/bonus/docker/verification.json) ghi image đã build, kiểm index/render và 46 test ở lần kiểm tra trước. Đây là hai lượt kiểm tra riêng, khác môi trường và thời điểm.

Kết quả 30/30 vượt ngưỡng 90% theo benchmark đã công bố. Phạm vi kết luận vẫn là một báo cáo với nhiều câu nêu trực tiếp mã bảng/hình, chưa đo khả năng tìm kiếm mở trên tài liệu mới. Bộ câu hỏi và nhãn có AI hỗ trợ, chưa phải kiểm tra mù do người ngoài tạo; giới hạn về crop, text hai cột và xác nhận nhãn độc lập vẫn cần được tính đến khi đánh giá bài.
