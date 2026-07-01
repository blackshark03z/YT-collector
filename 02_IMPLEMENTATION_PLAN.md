# Mist of Ages Multi-Channel MVP — Implementation Plan

## 1. Model và vai trò

### Tech Lead

```text
GPT-5.5 Thinking
```

### Codex worker

```text
GPT-5.4
Reasoning effort: Medium
```

### High effort chỉ dùng khi

- migration thật;
- OAuth blocker;
- token isolation bug;
- cross-channel contamination;
- non-overwrite risk.

Không dùng GPT-5.4 mini làm worker chính.

## 2. Nguyên tắc thực thi

- Audit trước khi sửa.
- Mỗi lượt chỉ làm một phase.
- Không tự chạy sang phase sau.
- Reuse architecture hiện có.
- Không refactor rộng.
- Không thêm database.
- Không đổi frontend framework.
- Không sửa AI/video pipeline.
- Focused tests trước.
- Stop ngay khi có blocker.
- Không commit/push nếu chưa được yêu cầu.
- Không cài dependency mới nếu chưa được duyệt.

## 3. Phase 0 — Read-only architecture audit

### Reasoning

```text
Medium
```

### Worker làm

- xác nhận CWD, branch, HEAD, worktree;
- đọc README;
- đọc UI server;
- đọc routes/services;
- đọc OAuth/token helpers;
- đọc YouTube Data/Analytics/Reporting clients;
- đọc project creation/validation;
- đọc learnings/metrics handling;
- đọc tests;
- đọc `.gitignore`;
- đọc project schema;
- tìm mọi hard-code single-channel.

### Output

```text
1. STATUS
2. CWD / BRANCH / HEAD / WORKTREE
3. CURRENT SINGLE-CHANNEL DATA FLOW
4. REUSABLE COMPONENTS
5. HARD-CODED SINGLE-CHANNEL POINTS
6. PROPOSED FILES TO ADD/MODIFY
7. MIGRATION RISKS
8. TEST PLAN
9. NEXT EXACT ACTION
```

### Gate

Không sửa code.

Tech Lead duyệt trước Phase 1.

## 4. Phase 1 — Channel filesystem model

### Reasoning

```text
Medium
```

### Mục tiêu

Tạo nền tảng channel workspace không phụ thuộc UI.

### Implement

- channel path resolver;
- channel slug validator;
- `channel.json` schema;
- channel repository:
  - list;
  - get;
  - create;
  - update status;
  - detect duplicate channel ID;
- per-channel token reference resolver;
- channel learnings path;
- channel metrics path;
- channel projects path.

### Focused tests

- create/load/list two channels;
- duplicate slug;
- duplicate YouTube channel ID;
- invalid slug;
- path traversal;
- token paths riêng;
- no secret content in metadata.

### Gate

Hai channel workspace cùng tồn tại trên disk.

## 5. Phase 2 — Per-channel OAuth isolation

### Reasoning

```text
Medium
```

Tăng lên `High` nếu gặp blocker.

### Implement

- Connect/Add Channel theo channel context;
- identify authenticated YouTube channel trước persist;
- một token path cho mỗi channel;
- reconnect theo selected channel;
- Analytics client theo selected token;
- Reporting client/state theo selected token/channel;
- clear auth status errors.

### Focused tests

- mock A/B OAuth;
- A/B token path khác nhau;
- reconnect A không sửa B;
- A API không dùng B credential;
- duplicate channel ID chuyển thành reconnect/duplicate error;
- token refresh vẫn đúng channel.

### Live smoke

- connect Mist of Ages thật;
- không log token;
- nếu có channel thứ hai, connect và kiểm tra ID khác.

### Gate

OAuth isolation pass.

## 6. Phase 3 — Channel-scoped projects

### Reasoning

```text
Medium
```

### Implement

- project root dưới selected channel;
- create/list/get/open/save/validate nhận `channel_slug`;
- `project.json` schema version mới;
- snapshot learnings;
- snapshot metrics;
- same competitor URL allowed across channels;
- project status scoped theo channel;
- non-overwrite giữ nguyên.

### Focused tests

- create project A;
- create project B;
- same competitor URL ở A/B;
- correct path;
- correct channel identity;
- correct learnings snapshot;
- correct metrics snapshot;
- no cross-read;
- rerun không overwrite transcript;
- refresh không overwrite workflow;
- content/publishing package không bị chạm.

### Gate

Project isolation pass.

## 7. Phase 4 — UI multi-channel

### Reasoning

```text
Medium
```

### Implement

- channel selector;
- Add Channel;
- Connect/Reconnect;
- Sync Metrics;
- Open Channel Folder;
- channel summary;
- project list by selected channel;
- create project sends `channel_slug`;
- all project actions scoped by selected channel.

### Không làm

- SPA mới;
- frontend framework mới;
- dashboard phức tạp;
- charting;
- background sync.

### Focused tests

- GET/list channels;
- render selector;
- switch channel;
- project list changes;
- create request contains channel slug;
- auth error does not expose secret;
- open folder resolves correct channel.

### Gate

UI can operate two channels.

## 8. Phase 5 — Legacy migration

### Reasoning

```text
High
```

### Implement

- dry-run report;
- create `channels/mist_of_ages`;
- copy learnings;
- copy metrics;
- copy projects;
- patch project metadata;
- preserve manual files;
- verify hashes;
- retain backup;
- no delete.

### Required evidence

```text
LEGACY PROJECT COUNT
MIGRATED PROJECT COUNT
MANUAL FILE HASHES PRESERVED
CHANNEL ID
LEARNINGS COPIED
METRICS COPIED
LEGACY BACKUP PATH
STATUS
```

### Gate

Migration validation pass trước khi UI chuyển canonical layout.

## 9. Phase 6 — Final validation

### Reasoning

```text
Medium
```

### Run

- all new focused tests;
- related existing regression tests;
- `git diff --check`;
- UI startup;
- channel A daily-use smoke;
- channel B isolation smoke;
- transcript save;
- validate READY_FOR_WORKFLOW;
- refresh safety.

### Update README

- add/connect channel;
- switch channel;
- sync metrics;
- create project;
- paste transcript;
- validate;
- folder layout;
- token paths;
- migration note.

### Final report

```text
1. STATUS
2. BASELINE
3. FILES ADDED
4. FILES MODIFIED
5. FINAL DATA LAYOUT
6. OAUTH/TOKEN ISOLATION
7. MIGRATION EVIDENCE
8. FOCUSED TESTS
9. REGRESSION TESTS
10. LIVE SMOKE
11. NON-OVERWRITE EVIDENCE
12. RISKS / DEFERRED
13. GIT STATUS
14. EXACT DAILY-USE STEPS
15. NEXT EXACT ACTION
```

## 10. Acceptance matrix

| Tình huống | Kết quả bắt buộc |
|---|---|
| Add channel | Workspace, identity và token riêng |
| Duplicate channel | Không tạo duplicate |
| Switch channel | Projects, metrics, learnings đổi đúng |
| Create project | Nằm dưới selected channel |
| Same competitor | Cho phép ở hai channel |
| Snapshot | Đúng channel |
| Reconnect A | Không ảnh hưởng B |
| Sync A | Không ghi dữ liệu B |
| Refresh competitor | Không chạm transcript/workflow/content/package |
| Reach pending | Warning, không block nếu input khác đủ |
| Migration | Manual file hashes giữ nguyên |
| Content ready | `content.md` và `publishing_package.md` hợp lệ |
