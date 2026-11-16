# Corpus World Bank

Nguồn: World Bank. 2022. *From the Last Mile to the Next Mile — 2022 Vietnam Poverty and Equity Assessment*. Washington, DC: World Bank. [Hồ sơ báo cáo](https://documents.worldbank.org/en/publication/documents-reports/documentdetail/099115004242216918). Giấy phép **CC BY 3.0 IGO**, xác minh tại trang PDF vật lý 3; xem [ATTRIBUTION](ATTRIBUTION.md) và [bản trích thông báo quyền](source-rights.txt).

API Documents & Reports trả metadata, URL tài liệu và số báo cáo `170511`. Bản PDF được tải trực tiếp bằng HTTPS; không cần tài khoản/API key. PDF có **232 trang vật lý, 20.584.558 byte**, SHA256 `6b2e5b40b08a3454f2265564e781bbf7bc0038ba37cb87ca32e1446b8f6b4e00`. Không đưa file PDF lớn vào bài nộp; lệnh dưới tải lại đúng bản đã ghim. `worldbank-api.json` giữ nguyên byte phản hồi API để đối chiếu checksum.

Corpus có **39 trang nội dung, 119.228 ký tự**:

| Chương | Trang PDF vật lý được chọn | Trang in | Số trang |
|---|---|---|---:|
| 1 — Taking stock of welfare trends over a dynamic decade | 45–65, bỏ 48 và 53 | 25–45, cùng loại trừ | 19 |
| 2 — A review of the drivers of poverty reduction | 75–97, bỏ 88, 90 và 97 | 55–77, cùng loại trừ | 20 |

Mỗi dòng `pages.jsonl` là một trang PDF thật; `page` là số nguyên 1-based, `metadata.printed_page` là trang in đã đối chiếu. Không tính bìa, mục lục, references/annex và các trang bị loại vì chủ yếu là bảng, biểu đồ hoặc công thức. Từng trang chọn vẫn có trên 1.500 ký tự sau chuẩn hóa; không nhân bản hoặc chèn thêm nội dung. [Danh sách và kiểm tra trang](source-selection.json), [khai báo nguồn](sources.json), [đặc tả corpus](corpus-spec.json), [manifest](manifest.json).

`year: 2022` lấy từ năm báo cáo/copyright. API ghi `docdt: 2023-04-10T04:00:00Z`; lưu riêng `api_document_date`, không coi hai trường là cùng ngày. `chapter` là chuỗi `"1"`/`"2"` xác minh từ mục lục; dùng làm filter phạm vi đọc cung cấp trước retrieval.

Trong môi trường Python 3.12 đã kích hoạt, chạy từ `starter/`:

```bash
python -m src.run fetch
python -m src.run validate
```

`fetch` kiểm checksum PDF rồi trích đúng các trang đã khai báo. Cache có checksum; dùng `--refresh` để kiểm tra lại nguồn HTTP khi cần. `validate` đối chiếu corpus với manifest và benchmark đã chốt. Cách cài venv, Conda và database được trình bày trong [hướng dẫn cài đặt](../docs/INSTALLATION.md).

Ở giai đoạn chuẩn bị dữ liệu, `scripts.prepare_worldbank` kiểm metadata API, giấy phép và mục lục trước khi ghi khai báo nguồn. Bộ dữ liệu đi kèm đã có đầy đủ những thông tin này. Thay corpus hoặc bộ câu hỏi cần thực hiện trong một thí nghiệm riêng.

Giới hạn trích xuất: pypdf plain giữ thứ tự đọc hai cột tốt hơn layout mode trong các mẫu đã xem, nhưng không khôi phục ranh giới đoạn theo hình học. Header, caption và một số chữ/số của bảng/biểu đồ còn trong text; không phân phối ảnh bitmap hoặc logo. Kerning có thể tạo khoảng trắng trong từ, còn xuống dòng/ngắt từ. Evidence chỉ lấy từ văn xuôi đã kiểm exact span; offsets trỏ vào văn bản chuẩn hóa này. Bản TXT của World Bank là OCR chưa hiệu đính, chỉ dùng kiểm khả thi độc lập.
