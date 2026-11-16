# Kiểm tra metadata và grounding trên tập test

Mẫu đánh giá gồm **45 bản ghi metadata** và **15 trường hợp grounding** trên cùng 5 câu test × A/B/C. Bảng này đánh giá bằng chứng truy xuất, không đo độ chính xác câu trả lời LLM. Corpus, câu hỏi, gold, model, metric và lựa chọn A trên dev được giữ nguyên.

| Cấu hình | Metadata đủ và đúng | Filter tuân thủ / số câu áp dụng | Grounding 0 / 1 / 2 | Trung bình /2 |
|---|---:|---:|---:|---:|
| A |15/15 |N/A |1 / 2 / 2 |1,20 |
| B |15/15 |N/A |0 / 2 / 3 |1,60 |
| C |15/15 |1/1 |0 / 2 / 3 |1,60 |

## Metadata: đối chiếu gì và với nguồn nào

Không phát hiện lỗi trong 45 bản ghi đã kiểm; mỗi bản ghi phải đủ và đúng tất cả trường được kiểm mới được tính đạt. Có **31 chunk khác nhau trên 13 trang nguồn**; 45 là số lần xuất hiện trong top-3, không phải 45 mẫu độc lập.

| Trường / thuộc tính | Bằng chứng đối chiếu |
|---|---|
| document_id, source, version |Corpus, manifest, khai báo nguồn, snapshot API và checksum PDF gốc. |
| page, printed_page |Trích lại PDF đúng trang vật lý; đối chiếu số trang trong header, không chỉ trừ 20 rồi mặc định đúng. |
| chapter, chapter_title |Khoảng chương từ mục lục PDF trang 9–10 và trang in đã xác minh. |
| year |Copyright trang PDF 3 ghi 2022; giữ riêng ngày API 2023-04-10. |
| language, document_type, country, report_number, api_document_date |Giá trị trong snapshot API đã ghim checksum. |
| char_start, char_end, text, chunk_id |Kiểu dữ liệu, ranh giới nguồn, vị trí text độc lập, exact source slice và ID theo method/offset/text. |

PDF được kiểm raw checksum trước khi trích lại; cả 39 trang corpus khớp văn bản chuẩn hóa. [Bằng chứng PDF](native-pdf-evidence.json) ghi header, checksum từng trang và văn bản mục lục/copyright. [Audit metadata](test-metadata-audit.json) có 45 dòng chi tiết, giá trị thực tế, kiểm tra và lỗi. Việc đối chiếu được thực hiện bằng chương trình.

`printed_page` giúp tìm đúng số trang in khi mở PDF, còn `chapter` thu hẹp phạm vi đọc. Ở q20, C nhận `chapter:"2"` từ ngữ cảnh đã cung cấp trước retrieval; cả 3 kết quả đều thuộc chương 2. A/B không áp dụng filter nên N/A, kể cả q20; q16–q19 của C không có filter cũng là N/A. Filter đúng chương vẫn chưa bảo đảm bằng chứng đủ để trả lời. URL/trang đúng cũng không khắc phục đoạn bị cắt.

## Grounding: điểm và lý do từng trường hợp

Rubric: **0** = không có bằng chứng trả lời; **1** = có bằng chứng liên quan nhưng thiếu điều kiện/ngữ cảnh cần thiết; **2** = top-3 đủ để trả lời và truy nguồn. Chỉ dùng văn bản thực sự được trả về; không lấy phần còn lại của trang nguồn hoặc expected answer để bù thông tin thiếu.

| Câu | Cấu hình | Điểm | Lý do |
|---|---|---:|---|
| q16 |A |2 |Top-1 PDF77 nêu đủ social insurance và unemployment insurance gắn với hợp đồng lao động. |
| q16 |B |2 |Top-1 PDF77 giữ đủ cùng quan hệ và cả hai loại bảo hiểm. |
| q16 |C |2 |Không có filter ở câu này; top-3 giống B, bằng chứng đủ. |
| q17 |A |1 |PDF83 giữ kỳ12 tháng của VHLSS nhưng cắt mất kỳ1 tháng của LFS; hai hit còn lại không bù được. |
| q17 |B |2 |Top-1 PDF83 giữ đủ phép so sánh12 tháng–1 tháng mà câu hỏi yêu cầu. |
| q17 |C |2 |Top-3 giống B, đủ cả hai kỳ hồi tưởng. |
| q18 |A |2 |Top-1 PDF89 nêu rõ trợ cấp mất giá vì không điều chỉnh theo lạm phát. |
| q18 |B |1 |PDF89 dừng ở hiện tượng mất giá; nguyên nhân về lạm phát không có trong top-3. |
| q18 |C |1 |Top-3 giống B, vẫn thiếu nguyên nhân được hỏi. |
| q19 |A |1 |Có ví dụ tăng lương là nguồn thu quan trọng ở PDF94 nhưng thiếu kết luận tăng trưởng chi phối phần lớn thập kỷ. |
| q19 |B |2 |Top-2 PDF65 nêu trực tiếp growth factors chi phối phần lớn thập kỷ; PDF92 hỗ trợ thêm thu nhập lao động. |
| q19 |C |2 |Top-3 giống B; không có filter, nên vẫn dùng được bằng chứng chương1 ở PDF65. |
| q20 |A |0 |PDF60/92 chỉ mô tả phân rã và đóng góp thu nhập; không có kết luận nhân quả hay giới hạn phương pháp. |
| q20 |B |1 |PDF96 giữ kết luận không có causal effect nhưng cắt mất lý do về general equilibrium và counterfactual distributions. |
| q20 |C |1 |Filter loại kết quả chương1, nhưng các chunk chương 2 vẫn không bổ sung mệnh đề phương pháp đã mất. |

[Phiếu đã chấm](../20261114T062008.998642Z-evaluate/test-manual-audit.json) giữ đúng15 cặp question/strategy và danh sách chunk gốc. [Grounding chi tiết](test-grounding.json) có lý do, phần thiếu, trích đoạn hỗ trợ kèm chunk ID, URL, trang và source offsets. [Tổng hợp](test-review-summary.json) tính lại phân bố và trung bình từ các phiếu.

q17 B/C và q19 B/C có grounding 2 dù strict Evidence Hit@3 là 0: q17 đã đủ hai kỳ hồi tưởng nhưng thiếu phần bổ sung của quote gold; q19 chỉ thiếu từ dẫn ‘The’. Đây là giới hạn của kiểm tra nguyên quote. Không thay gold, không ghi lại các miss thành hit hoặc chọn lại cấu hình theo đánh giá sau test. Trái lại, q18 B/C và q20 B/C thực sự thiếu nguyên nhân/điều kiện được hỏi, nên vẫn chỉ đạt 1.

## Phương pháp và giới hạn

Grounding được đánh giá bằng hai lượt đọc của mô hình với Codex. Lượt đối chiếu chỉ nhận [11 bộ top-3 có ID ẩn danh](test-grounding-input.json), câu hỏi, đáp án mục tiêu và metadata; không nhận tên A/B/C hoặc điểm retrieval. Lượt đọc chính đã biết kết quả benchmark. Nội dung ngoài top-3 không được dùng để bổ sung điều kiện bị thiếu, và đáp án mục tiêu không được coi là bằng chứng.

[Lượt đọc chính](test-grounding-primary.json) và [lượt đối chiếu](test-grounding-independent.json) có cùng điểm ở 11/11 bộ khác nhau. Việc đối chiếu này không đại diện cho độ đồng thuận giữa người chấm. B/C dùng chung index và trùng kết quả q16–q19, nên 15 phiếu chỉ gồm 11 bộ top-3 khác nhau. Cỡ mẫu năm câu test hạn chế khả năng suy rộng.

## Kiểm tra tính nhất quán

Từ thư mục gốc repository, trong môi trường Python 3.12 đã kích hoạt:

```bash
python results/manual-review/audit_test_metadata.py --help
python results/manual-review/finalize_test_review.py --check
```

Script metadata trích lại PDF đã kiểm checksum, đối chiếu trang/chương/thuộc tính nguồn và offsets. Finalizer kiểm tra điểm, 33 đoạn trong lượt đọc độc lập, trích dẫn hỗ trợ, bảng tổng hợp và checksum của dữ liệu thí nghiệm. Những kiểm tra này xác nhận tính nhất quán của file kết quả; phần đánh giá ý nghĩa được ghi trong điểm và lý do của từng phiếu.
