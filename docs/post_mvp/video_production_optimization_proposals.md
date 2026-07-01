# Mist of Ages — Đề xuất tối ưu hóa sản xuất video sau MVP

## 1. Mục tiêu

Tài liệu này tổng hợp các đề xuất có thể nghiên cứu sau khi MVP Multi-Channel đã hoàn thành.

Mục tiêu chính:

- giảm thao tác thủ công giữa Gemini, GPT và Claude;
- giảm lỗi khi chuyển prompt, artifact và trạng thái giữa các bước;
- tự động hóa các phần lặp lại nhưng không làm mất quyền quyết định của người vận hành;
- tạo thêm đầu ra phục vụ TTS, timeline, image generation, subtitle, upload và performance review;
- giữ nguyên các human gate quan trọng về topic, evidence, package, narration và chiến lược kênh.

Không đề xuất thêm một AI stage mới nếu chưa có bằng chứng rõ rằng nó cải thiện chất lượng.

---

## 2. Điểm cần thống nhất trong workflow hiện tại

Hai nguyên tắc nên được hợp nhất thành một quy tắc chung:

> Khóa package contract trước khi viết prose; chỉ tinh chỉnh cách thực thi thumbnail sau khi narration hoặc rough cut hoàn tất.

Cụ thể:

- title direction, thumbnail contradiction, package promise và first-15-second proof phải được khóa trước prose;
- không được dựng xong video rồi nghĩ lại angle từ đầu;
- sau rough cut chỉ nên tinh chỉnh cách thể hiện hình ảnh, crop, text overlay hoặc mức độ rõ ràng;
- chỉ sửa title tối thiểu nếu final narration có thay đổi nhỏ về mức độ chắc chắn;
- description và hashtags được draft sớm nhưng chỉ final sau narration.

---

## 3. Các module đề xuất

## 3.1. Assisted AI Workflow Orchestrator

### Mục tiêu

Thay thế phần thao tác thủ công:

- nhớ đang ở bước nào;
- copy prompt;
- tìm đúng file đầu vào;
- chuyển artifact giữa các model;
- đặt tên output;
- kiểm tra thiếu section;
- theo dõi phiên bản prompt;
- kiểm soát retry.

### State machine đề xuất

```text
INPUT_READY
→ TRANSCRIPT_ANALYZED
→ RESEARCH_READY
→ PACKAGE_LOCKED
→ OUTLINE_READY
→ NARRATION_V1_READY
→ RED_TEAM_READY
→ FINAL_READY
→ PRODUCTION_READY
```

### Chế độ vận hành đề xuất

#### Assisted Mode

- Tool tạo đúng prompt bundle cho từng model.
- Hiển thị model phải dùng.
- Liệt kê đúng file cần đính kèm.
- Có nút copy prompt.
- Cho phép dán output trở lại tool.
- Tự validate output.
- Chỉ mở khóa bước tiếp theo khi gate pass.
- Không cần API trả phí ở giai đoạn đầu.

#### API Mode

Nghiên cứu sau, chỉ khi Assisted Mode ổn định:

- gọi model tự động;
- theo dõi cost;
- retry có kiểm soát;
- timeout;
- prompt caching;
- batch execution;
- provider adapter cho Gemini, OpenAI và Claude.

### Giá trị

Đây là module có ROI cao nhất vì thay thế phần tốn thời gian nhưng ít giá trị sáng tạo.

---

## 3.2. Artifact Validator + Structured Sidecar

### Mục tiêu

Giữ artifact Markdown cho con người, đồng thời tạo JSON sidecar cho tool.

Ví dụ:

```text
evidence_ledger.md
evidence_ledger.json

locked_creative_package.md
locked_creative_package.json

retention_outline.md
retention_outline.json
```

### Evidence Ledger dạng cấu trúc

Mỗi claim nên có:

```json
{
  "claim_id": "CLM-014",
  "claim": "The fleet departed in May 1941.",
  "status": "VERIFIED",
  "source_ids": ["SRC-003", "SRC-007"],
  "allowed_wording": "The fleet departed in May 1941.",
  "forbidden_upgrades": [
    "The fleet was forced to depart in May 1941."
  ]
}
```

### Kiểm tra tự động có thể thực hiện

- claim thiếu source;
- narration dùng claim `UNSUPPORTED`;
- attribution bị bỏ mất;
- title overclaim so với ledger;
- description có claim ngoài narration;
- thumbnail concept mô tả tình huống không được xác minh;
- required anchor fact chưa xuất hiện;
- output thiếu section bắt buộc;
- sai format của `content.md`;
- metadata bị lẫn vào `content.md`;
- image prompt yêu cầu render text;
- Prompt 6 rewrite narration thay vì red-team;
- Prompt 7 không xuất đúng hai file.

### Giá trị

Đây là module quan trọng nhất về độ tin cậy và giảm lỗi vận hành.

---

## 3.3. Production Pack Compiler

### Mục tiêu

Sau khi có `content.md` và `publishing_package.md`, tool nên tự tạo thêm các đầu ra sản xuất.

### Đầu ra đề xuất

```text
production_manifest.json
pronunciation_lexicon.csv
tts_segments.json
scene_manifest.json
subtitle_source.txt
thumbnail_manifest.json
upload_manifest.json
```

### Pronunciation Lexicon

Tự phát hiện:

- tên người;
- địa danh;
- quân hàm;
- tổ chức;
- chữ viết tắt;
- từ ngoại ngữ;
- năm và con số dễ đọc sai.

Người vận hành vẫn cần nghe thử và approve trước TTS.

### TTS Segments

Tool tự chia narration theo:

- câu;
- nhịp thở;
- giới hạn độ dài;
- khoảng nghỉ;
- emphasis;
- scene boundary;
- subtitle boundary.

### Scene Manifest

Mỗi scene nên có:

```json
{
  "scene_id": "SC-018",
  "narration_segment_ids": ["SEG-031", "SEG-032"],
  "estimated_start": 92.4,
  "estimated_duration": 8.5,
  "visual_purpose": "reveal",
  "subjects": ["fleet", "storm"],
  "historical_constraints": ["no modern ships"],
  "prompt": "...",
  "reuse_group": null
}
```

### Kiểm tra tự động có thể thực hiện

- scene quá dài;
- first 30 seconds thiếu thay đổi hình;
- đoạn narration abstract không có visual;
- quá nhiều proper nouns cùng lúc;
- scene vượt quá khả năng dựng người que;
- image prompt dùng chi tiết không có trong evidence;
- subtitle quá dài;
- câu TTS quá khó đọc;
- đoạn chết hình;
- hook chưa đủ nhịp.

### Giá trị

Đây là module có thể tiết kiệm thời gian dựng video nhiều nhất.

---

## 3.4. Topic Queue Scorer

### Mục tiêu

Xếp hạng topic trước khi đưa vào workflow nghiên cứu tốn thời gian.

### Tiêu chí đề xuất

- cluster fit;
- packageability;
- contradiction strength;
- human stakes;
- source availability;
- visual simplicity;
- originality opportunity;
- expected research cost;
- expected animation cost;
- similarity với video đã làm;
- phụ thuộc vào creator personality hay không;
- khả năng kể bằng causal chain.

### Output đề xuất

```text
PRODUCE_CANDIDATE
RESEARCH_FIRST
LOW_PACKAGEABILITY
OFF_CLUSTER
HIGH_PRODUCTION_COST
REJECT
```

### Quyền quyết định

Tool chỉ xếp hạng và giải thích. Người vận hành vẫn chọn topic cuối.

---

## 3.5. Research Source Manager

### Mục tiêu

Quản lý nguồn độc lập với phần prose.

### Mỗi source nên có

- `source_id`;
- URL;
- title;
- author hoặc institution;
- publish date;
- source tier;
- access date;
- source type;
- claims supported;
- confidence note;
- quote fragment giới hạn;
- source availability.

### Tool có thể tự động

- phát hiện URL trùng;
- phát hiện claim chỉ dựa trên nguồn yếu;
- phát hiện nguồn lỗi;
- map claim → source;
- tạo source packet;
- kiểm tra ledger thiếu source;
- khóa ledger sau khi approve.

### Human gate

Người vận hành vẫn duyệt:

- claim tranh cãi;
- claim tạo hook;
- số liệu casualty;
- attribution;
- myth vs documented fact.

---

## 3.6. Thumbnail Executor

### Mục tiêu

Tự động hóa phần kỹ thuật, không tự quyết định package thắng.

### Tool nên làm

- gửi prompt tới image provider;
- lưu asset theo package;
- crop 16:9;
- thêm text overlay ngoài image model;
- tạo preview 320 px và 160 px;
- kiểm tra safe zone;
- kiểm tra contrast;
- cảnh báo chủ thể quá nhỏ;
- cảnh báo quá nhiều chi tiết;
- tạo contact sheet;
- lưu primary và backup assets;
- giữ version package.

### Không nên tự động hoàn toàn

- chọn thumbnail thắng cuối;
- đổi title/thumbnail chỉ dựa trên AI score;
- kết luận CTR từ pre-test nhỏ.

---

## 3.7. Performance Scheduler + Learning Loop

### Mục tiêu

Tự động thu thập và chuẩn hóa dữ liệu sau khi đăng.

### Snapshot đề xuất

```text
24H
72H
7D
```

### Dữ liệu cần lấy

- views;
- impressions;
- CTR tổng;
- CTR theo traffic source;
- watch time;
- AVD;
- average percentage viewed;
- first 30-second retention;
- retention curve;
- primary traffic source;
- package version;
- package-change timestamp;
- before/after package change.

### Phân loại sơ bộ

```text
INSUFFICIENT_SIGNAL
POSSIBLE_PACKAGE_PROBLEM
POSSIBLE_OPENING_PROBLEM
POSSIBLE_MIDDLE_RETENTION_PROBLEM
TECHNICAL_OR_DISTRIBUTION_ANOMALY
```

### Quy tắc an toàn

Tool không tự đổi title hoặc thumbnail.

Tool chỉ đề xuất:

- giữ package;
- chờ thêm dữ liệu;
- xem xét Backup A;
- kiểm tra opening;
- đánh dấu technical anomaly;
- tạo learning candidate.

### Learning Loop

Sau mỗi ba video:

- tool tạo `learning_candidate.md`;
- operator review;
- chỉ sau khi approve mới merge vào `channel_learnings_master.md`;
- không tự động biến một tín hiệu yếu thành pattern chung.

---

## 3.8. Upload Manifest Builder

### Mục tiêu

Giảm lỗi ở bước upload mà không tự động đăng hàng loạt.

### Đầu ra đề xuất

```text
upload_manifest.json
upload_checklist.md
```

### Nội dung

- title primary;
- backup titles;
- description;
- hashtags;
- thumbnail path;
- subtitle path;
- playlist;
- audience setting;
- visibility;
- upload environment;
- end screen;
- package version;
- upload timestamp;
- package-change log;
- restriction check.

### Human gate

Người vận hành vẫn:

- kiểm tra final video;
- chọn package cuối;
- bấm upload;
- xác nhận visibility;
- xử lý restriction/copyright;
- duyệt package change.

---

## 4. Phần không nên giao hoàn toàn cho tool

Giữ human gate ở các điểm sau:

1. Chọn competitor.
2. Chọn topic cuối.
3. Quyết định `PRODUCE / REVISE / REJECT`.
4. Duyệt claim tranh cãi và anchor facts.
5. Chọn primary package.
6. Duyệt narration cuối.
7. Chọn thumbnail cuối.
8. Duyệt pronunciation quan trọng.
9. Quyết định đổi title/thumbnail.
10. Quyết định thay cluster hoặc chiến lược kênh.

Không nên tự động:

- thay package từ vài giờ dữ liệu;
- kết luận niche thất bại từ một video;
- nâng claim disputed thành fact;
- cho cùng một model viết và tự approve;
- tự đăng hàng loạt;
- tự xóa legacy hoặc evidence;
- tự merge learning khi signal còn yếu.

---

## 5. Thứ tự ưu tiên post-MVP

## Post-MVP 1 — Assisted Workflow Orchestrator

Phạm vi:

- state machine Prompt 1–7;
- prompt bundle;
- artifact input/output;
- approval gates;
- retry riêng từng bước;
- versioning;
- chưa cần gọi API tự động.

## Post-MVP 2 — Structured Evidence + Artifact Gate

Phạm vi:

- JSON sidecar;
- claim/source IDs;
- schema validation;
- fact/package/format checks;
- final delivery gate.

## Post-MVP 3 — Production Pack Compiler

Phạm vi:

- pronunciation lexicon;
- TTS segmentation;
- scene manifest;
- subtitle source;
- image prompt queue;
- visual-complexity checks.

## Post-MVP 4 — Performance Automation

Phạm vi:

- 24h/72h/7d snapshots;
- retention reports;
- package version log;
- learning candidates;
- three-video review dashboard.

## Post-MVP 5 — Thumbnail + Upload Assistance

Phạm vi:

- image execution;
- overlay composition;
- mobile preview;
- upload manifest;
- upload preflight checklist.

---

## 6. Đề xuất ưu tiên cuối cùng

Nếu chỉ làm một module tiếp theo:

> Assisted AI Workflow Orchestrator + Artifact Validator

Lý do:

- loại bỏ phần lớn thao tác copy/paste;
- giảm nhầm model, prompt và file;
- kiểm soát trạng thái từng project;
- giữ nguyên human approval;
- chưa cần API trả phí;
- dễ triển khai trên nền MVP hiện tại.

Nếu làm hai module:

> Thêm Production Pack Compiler

Khi đó pipeline sẽ tiến gần tới:

```text
Competitor input
→ AI workflow có kiểm soát
→ content.md + publishing_package.md
→ TTS/scene/subtitle/image production pack
→ final video
→ performance feedback
```

Người vận hành tập trung vào:

- chọn topic;
- duyệt evidence;
- khóa package;
- duyệt video;
- ra quyết định chiến lược.

---

## 7. Trạng thái đề xuất

```text
DOCUMENTED_FOR_LATER_RESEARCH
NO_IMPLEMENTATION_AUTHORIZED
```

Tài liệu này chỉ ghi nhận hướng tối ưu post-MVP.

Chưa có module nào được phê duyệt để triển khai.
