# Code

Code thực hành nằm trong `day07/`; `starter/` giữ bộ khung đề bài để đối chiếu.

| File | Vai trò |
|---|---|
| `day06.py` | Kiểm identity và đọc PostgreSQL/pgvector Day06; query embedding cùng model/revision |
| `retrieval.py` | BM25 và hybrid RRF, ranking có ID/nguồn/score |
| `context.py` | Mở rộng chunk lân cận trên cùng trang theo offsets, không dùng gold |
| `llm.py` | OpenRouter GPT-4o-mini, tool calling, thông báo lỗi có che key |
| `agent.py` | Model điều phối search/finish, context budget, citation validation và trace |
| `benchmark.py` | Chạy dev/test, đo evidence, lưu trace và phiếu chấm |
| `review.py` | Tổng hợp nhãn đã đối chiếu và đóng băng lựa chọn từ dev |
| `__main__.py` | CLI check/search/ask/bench/review/freeze-selection |

[Hướng dẫn chạy](../docs/RUN.md) · [Báo cáo và phân tích thực nghiệm](../report/individual/2A202603876_DinhPhucDien.md).

Phần nâng cao nằm riêng trong `bonus/`: index đủ 232 trang, crop ảnh PDF,
agent đọc text/ảnh, benchmark và chốt cấu hình từ dev. `bonus/llm.py` hỗ trợ
OpenRouter hoặc Gemini trực tiếp; lựa chọn này không đổi client Day07 cơ bản.
Xem phần bonus trong [hướng dẫn chạy chung](../docs/RUN.md).
