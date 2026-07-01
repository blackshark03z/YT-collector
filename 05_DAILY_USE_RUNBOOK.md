# Multi-Channel Input Collector — Daily Use Runbook

## 1. Khởi động

```powershell
python scripts/ui_server.py
```

Mở local UI, dự kiến:

```text
http://127.0.0.1:8765
```

## 2. Thêm channel lần đầu

1. Bấm `Add Channel`.
2. Đăng nhập đúng Google Account hoặc Brand Account.
3. Kiểm tra:
   - channel name;
   - YouTube channel ID.
4. Xác nhận.
5. Tool tạo channel workspace.
6. Bấm `Sync Metrics`.

## 3. Trước khi tạo project

Kiểm tra:

```text
Selected Channel
OAuth Status
Last Metrics Sync
Channel ID
```

Không tạo project nếu đang chọn nhầm channel.

## 4. Tạo project

1. Chọn channel.
2. Paste competitor URL.
3. Nhập project name nếu cần.
4. Bấm `Create Research Project`.

Project phải nằm tại:

```text
channels/<selected_channel>/projects/<project>/
```

## 5. Tool tự tạo

```text
project.json
input/competitor_reference.md
input/channel_learnings.md
input/channel_metrics.csv
input/assets/competitor_thumbnail.*
research/competitor_transcript.md
workflow/transcript_analysis.md
workflow/research_pack.md
workflow/evidence_ledger.md
workflow/locked_creative_package.md
workflow/retention_outline.md
workflow/narration_v1.md
workflow/red_team_report.md
```

Tool không tạo:

```text
content.md
publishing_package.md
```

## 6. Dán transcript

1. Mở `research/competitor_transcript.md`.
2. Dán transcript thủ công.
3. Giữ timestamp ở các đoạn quan trọng.
4. Lưu UTF-8.
5. Bấm `Validate Inputs`.

Kết quả mong đợi:

```text
COMPETITOR REFERENCE: PASS
CHANNEL LEARNINGS: PASS
CHANNEL METRICS: PASS
MANUAL TRANSCRIPT: PASS
WORKFLOW INPUT STATUS: READY_FOR_WORKFLOW
```

## 7. Chạy workflow AI

Prompt 1 nhận:

```text
input/competitor_reference.md
research/competitor_transcript.md
input/channel_learnings.md
```

Các output được lưu vào `workflow/`.

Output cuối:

```text
content.md
publishing_package.md
```

## 8. Chuyển channel

Trước mỗi project mới:

1. Switch channel.
2. Kiểm tra channel ID.
3. Kiểm tra project list đổi đúng.
4. Kiểm tra metrics/learnings thuộc channel đó.

Không di chuyển project thủ công giữa channel folders.

## 9. Khi nào sync metrics

Sync khi:

- project đầu tiên trong ngày;
- vừa reconnect;
- có video mới đủ dữ liệu;
- chuẩn bị cập nhật learnings.

Không cần sync khi chỉ mở project cũ.

## 10. Channel learnings

Master:

```text
channels/<slug>/channel_learnings_master.md
```

Chỉ thêm:

- pattern đã được duyệt;
- kết luận không quá mạnh;
- instruction có thể hành động.

Project mới nhận snapshot mới.

Project cũ giữ snapshot cũ.

## 11. Refresh safety

Refresh competitor chỉ được cập nhật:

- competitor reference;
- public statistics;
- thumbnail nếu yêu cầu;
- generated metadata.

Không được chạm:

```text
competitor_transcript.md
workflow/*.md
content.md
publishing_package.md
channel snapshots
```

## 12. Backup

Backup:

```text
channels/
secrets/youtube/
youtube_api_key.txt
youtube_oauth_client.json
```

Không commit secrets.

Trước migration hoặc update lớn:

- copy legacy folders;
- copy `channels/`;
- verify backup path.

## 13. Lỗi thường gặp

### Wrong channel identity

- dừng;
- reconnect đúng account/Brand Account;
- kiểm tra channel ID.

### Token expired

- reconnect đúng channel;
- không xóa token channel khác.

### Metrics empty

- kiểm tra OAuth scopes;
- kiểm tra date range;
- kiểm tra selected channel.

### Reach pending

- không xem là blocker nếu input khác đủ.

### Project sai channel

- không sửa tay một phần;
- dùng migration/move có patch `project.json`.

### Transcript overwrite warning

- cancel;
- mở file hiện tại;
- tool không được tự overwrite.

## 14. Checklist

```text
[ ] Đúng selected channel
[ ] OAuth CONNECTED
[ ] Metrics đủ mới hoặc chấp nhận snapshot hiện tại
[ ] Competitor URL đúng
[ ] Project path đúng channel
[ ] Transcript có nội dung thật
[ ] Validate READY_FOR_WORKFLOW
[ ] content.md lưu đúng project
[ ] publishing_package.md lưu đúng project
```
