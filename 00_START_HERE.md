# Mist of Ages Multi-Channel MVP — Start Here

## Mục tiêu

Nâng cấp Input Collector hiện tại từ **một kênh** thành **nhiều kênh**, nhưng vẫn giữ đúng phạm vi:

- local;
- dùng cá nhân;
- tối giản;
- đủ dùng hằng ngày;
- không gọi AI API;
- không tải transcript;
- không upload video;
- không dùng database;
- không xây frontend mới.

Luồng cuối cùng:

```text
Chọn channel
→ dán link video đối thủ
→ tool tạo project trong đúng channel
→ lấy competitor metadata + thumbnail
→ snapshot channel learnings + metrics
→ người dùng dán transcript thủ công
→ validate READY_FOR_WORKFLOW
→ chạy workflow AI thủ công
→ content.md + publishing_package.md
```

## Bộ tài liệu

| File | Mục đích |
|---|---|
| `01_MULTI_CHANNEL_MVP_ARCHITECTURE.md` | Kiến trúc, folder layout, data model, OAuth, UI và migration |
| `02_IMPLEMENTATION_PLAN.md` | Kế hoạch triển khai theo phase, test gate và acceptance |
| `03_CODEX_WORKER_PROTOCOL.md` | Quy tắc làm việc cố định cho Codex worker |
| `04_PHASE_0_AUDIT_PROMPT.md` | Prompt đầu tiên gửi cho Codex để audit repo |
| `05_DAILY_USE_RUNBOOK.md` | Hướng dẫn vận hành sau khi MVP hoàn thành |

## Phân công model

### Tech Lead

```text
GPT-5.5 Thinking
```

Nhiệm vụ:

- khóa kiến trúc;
- chia phase;
- review báo cáo Codex;
- quyết định blocker;
- kiểm soát scope;
- viết prompt phase tiếp theo;
- không trực tiếp thay worker coding context.

### Codex worker duy nhất

```text
GPT-5.4
Reasoning effort: Medium
```

Dùng `Medium` cho:

- read-only audit;
- channel model;
- project scoping;
- UI;
- tests;
- documentation;
- final validation.

Chỉ đổi sang:

```text
GPT-5.4
Reasoning effort: High
```

khi:

- thực hiện migration dữ liệu thật;
- xử lý OAuth token isolation blocker;
- review/fix nguy cơ ghi đè hoặc cross-channel contamination;
- Tech Lead yêu cầu rõ.

### Không dùng

- Không dùng GPT-5.4 mini làm worker chính.
- Không dùng GPT-5.5 làm worker coding thường trực.
- Không đổi model giữa một phase.

## Cách làm việc

Mỗi lượt chỉ giao **một phase**:

```text
Tech Lead viết prompt phase
→ GPT-5.4 thực hiện
→ worker trả evidence
→ Tech Lead review
→ mới mở phase tiếp theo
```

Không gửi toàn bộ implementation plan rồi cho worker tự chạy hết.

## Bước bắt đầu ngay

1. Mở Codex.
2. Chọn:

```text
Model: GPT-5.4
Reasoning: Medium
```

3. Gửi nội dung file:

```text
04_PHASE_0_AUDIT_PROMPT.md
```

4. Không cho phép sửa code ở Phase 0.
5. Gửi báo cáo Phase 0 trở lại Tech Lead để duyệt.
