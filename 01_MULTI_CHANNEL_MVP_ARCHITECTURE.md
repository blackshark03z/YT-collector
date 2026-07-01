# Mist of Ages Multi-Channel MVP — Architecture

## 1. Hiện trạng

Tool hiện tại là local personal-use web UI cho Mist of Ages.

Nó đã có:

- `scripts/ui_server.py`;
- YouTube Data API;
- OAuth cho YouTube Analytics/Reporting;
- competitor metadata;
- thumbnail download;
- channel learnings snapshot;
- channel metrics snapshot;
- manual transcript template;
- workflow placeholders;
- input validation;
- `READY_FOR_WORKFLOW`.

Tool hiện không:

- gọi AI API;
- tải transcript;
- chạy workflow content;
- tạo `content.md`;
- tạo `publishing_package.md`;
- upload video.

Vấn đề hiện tại là toàn bộ hệ thống đang ngầm gắn với một channel.

## 2. Mục tiêu MVP

MVP phải hỗ trợ:

1. Thêm và kết nối nhiều channel YouTube.
2. Mỗi channel có workspace riêng.
3. Mỗi channel có:
   - identity;
   - OAuth token;
   - learnings master;
   - metrics;
   - projects.
4. Mỗi lần tạo nội dung là một project dưới channel đang chọn.
5. Project nhận snapshot đúng learnings và metrics của channel đó.
6. Không lẫn dữ liệu giữa các channel.
7. Không làm mất hoặc ghi đè dữ liệu thủ công.
8. UI hiện tại vẫn là điểm vận hành duy nhất.

## 3. Ngoài phạm vi MVP

Không triển khai:

- AI automation;
- transcript downloader;
- uploader;
- scheduler;
- background workers;
- database;
- cloud deployment;
- multi-user auth;
- dashboard analytics nâng cao;
- cross-channel benchmarking;
- automated channel learnings inference.

## 4. Quyết định kiến trúc

### 4.1 Storage

Dùng:

```text
Filesystem + JSON + Markdown + CSV
```

Không thêm database.

### 4.2 Channel registry

Channel registry được hình thành bằng cách quét:

```text
channels/*/channel.json
```

Không cần registry database riêng.

### 4.3 Project ownership

Project phải nằm vật lý dưới channel:

```text
channels/<channel_slug>/projects/<project_slug>/
```

Đây là guardrail chính chống cross-channel contamination.

### 4.4 Secrets

Dùng chung:

```text
youtube_api_key.txt
youtube_oauth_client.json
```

Riêng từng channel:

```text
secrets/youtube/<channel_slug>_oauth_token.json
```

Không lưu access token hoặc refresh token trong `channel.json`.

### 4.5 Snapshots

Mỗi project nhận snapshot tại thời điểm tạo:

```text
input/channel_learnings.md
input/channel_metrics.csv
```

Snapshot không tự cập nhật.

Muốn cập nhật project cũ phải có action rõ ràng:

```text
Refresh Channel Snapshot
```

## 5. Cấu trúc thư mục chuẩn

```text
channels/
  mist_of_ages/
    channel.json
    channel_profile.md
    channel_learnings_master.md
    metrics/
      channel_metrics.csv
      reporting_state.json
      _raw/
        analytics_20260701T083000Z.json
        reach_20260701T083000Z.json
    projects/
      20260701_why-rome-executed-jesus/
        project.json
        input/
          competitor_reference.md
          channel_learnings.md
          channel_metrics.csv
          assets/
            competitor_thumbnail.jpg
          _raw/
            competitor_video.json
            channel_analytics.json
        research/
          competitor_transcript.md
        workflow/
          transcript_analysis.md
          research_pack.md
          evidence_ledger.md
          locked_creative_package.md
          retention_outline.md
          narration_v1.md
          red_team_report.md
        content.md
        publishing_package.md

secrets/
  youtube/
    mist_of_ages_oauth_token.json
    second_channel_oauth_token.json

youtube_api_key.txt
youtube_oauth_client.json
```

`content.md` và `publishing_package.md` chỉ xuất hiện sau khi workflow AI hoàn thành.

## 6. Quy tắc đặt tên

### Channel slug

- lowercase;
- ASCII-safe;
- dấu gạch dưới;
- ổn định sau khi tạo;
- không tự đổi khi display name đổi.

Ví dụ:

```text
Mist of Ages → mist_of_ages
Tam Builds → tam_builds
```

### Project folder

```text
YYYYMMDD_<project-slug>
```

Nếu trùng:

```text
YYYYMMDD_<project-slug>_<video_id_6_chars>
```

### Token

```text
secrets/youtube/<channel_slug>_oauth_token.json
```

## 7. Channel model

### `channel.json`

```json
{
  "schema_version": 1,
  "channel_slug": "mist_of_ages",
  "display_name": "Mist of Ages",
  "youtube_channel_id": "UC...",
  "youtube_handle": "@MistOfAges",
  "oauth_token_ref": "secrets/youtube/mist_of_ages_oauth_token.json",
  "status": "CONNECTED",
  "created_at": "2026-07-01T08:30:00Z",
  "last_connected_at": "2026-07-01T08:30:00Z",
  "last_metrics_sync_at": "2026-07-01T08:35:00Z",
  "analytics_window_days": 90
}
```

### Yêu cầu

- `youtube_channel_id` là unique.
- `channel_slug` là unique.
- Không lưu token content.
- `oauth_token_ref` chỉ là path.
- Timestamps phải timezone-aware.
- Identity phải được xác nhận sau OAuth.

## 8. Project model

### `project.json`

```json
{
  "schema_version": 2,
  "project_slug": "20260701_why-rome-executed-jesus",
  "channel_slug": "mist_of_ages",
  "youtube_channel_id": "UC...",
  "competitor_video_id": "...",
  "competitor_url": "...",
  "created_at": "...",
  "status": "WAITING_FOR_TRANSCRIPT",
  "workflow_input_status": "NOT_READY",
  "channel_snapshot": {
    "learnings_path": "input/channel_learnings.md",
    "metrics_path": "input/channel_metrics.csv",
    "captured_at": "..."
  }
}
```

### Guardrails

Project phải chứa:

```text
channel_slug
youtube_channel_id
```

Mọi API operation liên quan project phải resolve qua channel trước.

Không được fallback ngầm về Mist of Ages khi đã có nhiều channel.

## 9. Learnings và metrics

### Channel-level

```text
channels/<slug>/channel_learnings_master.md
channels/<slug>/metrics/channel_metrics.csv
```

### Project-level snapshot

```text
projects/<project>/input/channel_learnings.md
projects/<project>/input/channel_metrics.csv
```

### Quy tắc

- Master thuộc đúng một channel.
- Project mới copy snapshot.
- Project cũ giữ snapshot cũ.
- Sync channel không tự sửa project.
- Refresh competitor không tự sửa channel snapshot.
- Raw API response chỉ dùng debug.

## 10. OAuth và API isolation

### Dùng chung

```text
youtube_api_key.txt
youtube_oauth_client.json
```

### Tách riêng

```text
secrets/youtube/<channel_slug>_oauth_token.json
```

### Flow Add Channel

```text
Add Channel
→ OAuth browser flow
→ call authenticated channel identity
→ show display name + channel ID
→ confirm
→ create workspace
→ save token to per-channel path
→ write channel.json
```

### Quy tắc

- Nếu channel ID đã tồn tại, không tạo duplicate.
- Reconnect A không chạm token B.
- Analytics client của A không được dùng token B.
- Reporting state thuộc riêng channel.
- Reach data `PENDING` không block project creation.
- Không log token, refresh token hoặc client secret.

## 11. UI MVP

Chỉ mở rộng UI hiện tại.

### Header channel controls

- Channel selector
- Add Channel
- Connect/Reconnect
- Sync Metrics
- Open Channel Folder

### Channel summary

- Display name
- Channel ID
- OAuth status
- Last connected
- Last sync
- Project count

### Project area

- Competitor URL
- Optional project name
- Create Research Project
- Project list của selected channel
- Open Project
- Open Transcript
- Save Transcript
- Validate Inputs

### Trạng thái channel

```text
NOT_CONNECTED
CONNECTING
CONNECTED
SYNCING
READY
ERROR_AUTH
ERROR_API
NEEDS_RECONNECT
```

### Trạng thái project

```text
CREATED
WAITING_FOR_TRANSCRIPT
READY_FOR_WORKFLOW
WORKFLOW_IN_PROGRESS
CONTENT_READY
```

## 12. Daily flow

```text
Mở UI
→ chọn channel
→ sync metrics nếu cần
→ paste competitor URL
→ tạo project
→ tool snapshot learnings + metrics
→ paste transcript
→ validate
→ chạy workflow AI thủ công
→ lưu content.md + publishing_package.md
```

## 13. Migration

Legacy hiện tại được xem là Mist of Ages.

Migration phải:

1. Dry-run trước.
2. Tạo:

```text
channels/mist_of_ages/
```

3. Copy:
   - learnings;
   - metrics;
   - projects.
4. Patch `project.json`.
5. Kiểm tra file thủ công giữ nguyên byte/hash.
6. Giữ legacy backup.
7. Không delete tự động.

### Không được làm

- move trực tiếp trước validation;
- rewrite transcript;
- rewrite workflow files;
- rewrite `content.md`;
- rewrite `publishing_package.md`;
- ghi đè token.

## 14. Definition of Done

MVP hoàn thành khi:

- kết nối được ít nhất hai channel;
- mỗi channel có token riêng;
- channel selector chuyển đúng project list;
- create project tạo đúng folder channel;
- same competitor URL tạo được project riêng ở hai channel;
- snapshot learnings/metrics đúng channel;
- refresh A không chạm B;
- transcript/workflow files không bị overwrite;
- migration legacy pass;
- UI daily-use smoke pass;
- launch command hiện tại vẫn hoạt động.
