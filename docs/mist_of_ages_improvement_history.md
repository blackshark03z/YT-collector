# MIST OF AGES — IMPROVEMENT HISTORY

**Loại tài liệu:** Lịch sử cải tiến vận hành, append-only  
**Kênh:** Mist of Ages  
**Thị trường:** Khán giả nói tiếng Anh, ưu tiên Hoa Kỳ  
**Định dạng chính:** Long-form lịch sử minh họa người que 2D  
**Ngày khởi tạo:** 2026-07-14  
**Mục tiêu hiện tại:** CTR Home/Suggested trên 5% và video long-form đầu tiên đạt 1.000 lượt xem

---

## 1. Mục đích của tài liệu

Tài liệu này là nguồn lịch sử duy nhất cho các đợt cải tiến của Mist of Ages.

Mỗi đợt cải thiện phải ghi lại:

1. Baseline trước khi thay đổi.
2. Vấn đề được xác định.
3. Giả thuyết cải thiện.
4. Thay đổi đã áp dụng.
5. Chỉ số mục tiêu.
6. Kết quả thực tế.
7. Điều được giữ lại.
8. Điều bị loại bỏ.
9. Bước tiếp theo.

### Quy tắc quản trị

- Không xóa hoặc viết lại các entry cũ.
- Khi kết luận thay đổi, thêm entry mới để đính chính.
- Tách rõ dữ liệu quan sát, suy luận và quyết định.
- Không tuyên bố một pattern thành công chỉ từ một video.
- Mỗi thay đổi lớn phải có tên đợt, ngày bắt đầu và tiêu chí kết thúc.
- Không đổi nhiều biến cùng lúc nếu mục tiêu là xác định nguyên nhân.
- Chỉ xem một đợt là hoàn tất khi đã có kết quả 24 giờ, 72 giờ hoặc 7 ngày phù hợp với loại thử nghiệm.

---

## 2. Mục tiêu và ngưỡng đánh giá hiện hành

| Chỉ số | Mục tiêu |
|---|---:|
| CTR Home/Suggested trong 24 giờ | >= 5% |
| Retention khoảng 30 giây | >= 70% |
| Average percentage viewed | >= 40% |
| Impressions trong 72 giờ | >= 20.000 |
| Views mục tiêu | >= 1.000 |
| Video length ưu tiên | 7–9 phút |
| Narration | Khoảng 1.000–1.300 từ |

Các ngưỡng trên là mục tiêu vận hành nội bộ, không phải benchmark chung cho mọi kênh YouTube.

---

## 3. Baseline hệ thống hiện có

### 3.1 Mist of Ages Input Collector

Collector hiện hỗ trợ:

- workspace theo channel và project;
- lấy metadata video đối thủ;
- lưu thumbnail đối thủ;
- nhập transcript thủ công;
- snapshot channel learnings;
- workflow Prompt 1–7;
- parse, preview, candidate, approve/reject;
- production handoff gồm `content.md` và `publishing_package.md`;
- Analytics Collector và Analytics ZIP;
- vận hành local, filesystem-based.

Collector là lớp điều phối nghiên cứu, workflow và dữ liệu kênh. Nó không trực tiếp tạo video.

### 3.2 Workflow Content Package-First V2

Luồng hiện hành:

```text
Competitor
→ Transcript Diagnosis
→ Historical Research
→ Evidence Ledger
→ Locked Creative Package
→ Retention Outline
→ Narration V1
→ Independent Red-Team
→ content.md + publishing_package.md
```

Nguyên tắc đã khóa:

- competitor transcript chỉ là idea lead;
- research phải có trước angle;
- Evidence Ledger là nguồn quyền lực về fact;
- title và thumbnail được khóa trước prose;
- opening phải trả package promise trong 15 giây đầu;
- central question phải rõ trước khoảng 35 giây;
- Claude sở hữu prose;
- GPT sở hữu strategy, packaging, outline và red-team;
- metadata không được đặt trong `content.md`.

### 3.3 Công cụ tìm kiếm nội dung hiện tại

#### `youtube_topic_opportunity_scan.py`

Chức năng hiện có:

- tìm video bằng nhiều YouTube search query;
- lọc video long-form theo thời lượng;
- lấy các video gần đây của cùng channel;
- so sánh target với median video cùng định dạng;
- tính:
  - outlier score;
  - views per day;
  - views per subscriber;
  - opportunity score;
- xuất CSV, JSON và danh sách top opportunities.

#### `youtube_competitor_probe.py`

Chức năng hiện có:

- nhận video ID, URL hoặc search query;
- lấy metadata video;
- lấy thông tin channel;
- lấy các video gần đây;
- tính median baseline và target outlier score;
- xuất dữ liệu phục vụ đánh giá một đối thủ cụ thể.

### 3.4 YouTube Auto

Pipeline hiện có:

```text
content.md
→ ElevenLabs / Typecast / Story Audio input
→ audio + alignment
→ timeline
→ character consistency
→ image prompts
→ Google Flow images
→ subtitles
→ FFmpeg final video
→ metadata
→ thumbnail
```

Khả năng đáng chú ý:

- từng stage có artifact riêng;
- resume theo dependency fingerprint;
- project lock chống chạy trùng;
- Gemini timeline với OpenAI fallback opt-in;
- character/style bible;
- nhiều visual style;
- Google Flow automation;
- subtitle SRT/ASS;
- FFmpeg compose;
- metadata và thumbnail generation;
- Story Audio Handoff V1;
- ElevenLabs key pool và Typecast support.

---

## 4. Lịch sử các đợt cải thiện

# IMPROVEMENT ROUND 0 — BASELINE WORKFLOW

**Thời gian:** Trước 2026-07-09  
**Trạng thái:** Đã thay thế một phần

### Baseline

Quy trình có thể tạo video hoàn chỉnh, nhưng việc chọn chủ đề, package và content chưa được khóa thành một hệ thống phản hồi dữ liệu chặt chẽ.

### Vấn đề

- package thường được xử lý quá muộn;
- metadata có thể được nghĩ lại sau khi video đã dựng;
- scoring thiên về tính đúng logic, chưa phản ánh đủ khả năng click của casual audience;
- topic discovery phụ thuộc nhiều vào search query do người vận hành tự nghĩ;
- chưa có lịch sử thử nghiệm thống nhất.

### Bài học giữ lại

Pipeline artifact-based và khả năng chạy độc lập từng stage là nền tảng đúng.

---

# IMPROVEMENT ROUND 1 — PACKAGE-FIRST V2

**Ngày bắt đầu:** 2026-07-09  
**Trạng thái:** Đã triển khai vào workflow

### Thay đổi

- khóa package trước prose;
- tạo một primary package và hai backup package;
- thêm package contract;
- thêm first-15-second proof;
- thêm Evidence Ledger;
- thêm retention architecture;
- thêm red-team độc lập;
- đầu ra cuối tách thành:
  - `content.md`;
  - `publishing_package.md`.

### Mục tiêu

- giảm lệch title–thumbnail–opening;
- tránh clickbait sai nội dung;
- tăng khả năng package được thực hiện đúng trong video;
- tăng độ chính xác lịch sử.

### Kết quả sơ bộ

Workflow tạo được video có nội dung và retention tốt hơn, nhưng package score nội bộ vẫn có thể đánh giá quá cao một topic hoặc thumbnail khó cạnh tranh trên Home feed.

### Bài học

Package integrity và package appeal là hai tiêu chí khác nhau.

Một package có thể:

- đúng nội dung;
- evidence-supported;
- khớp opening;

nhưng vẫn không đủ hấp dẫn với người chưa biết chủ thể lịch sử.

---

# IMPROVEMENT ROUND 2 — SULLA PACKAGE EXPERIMENT

**Video:** `Why Roman Soldiers Marched on Their Own Capital`  
**Video ID:** `oKs9qnzuHMg`  
**Ngày đăng:** 2026-07-11  
**Trạng thái:** Đóng thử nghiệm, không tiếp tục cứu video cũ

### Baseline checkpoint

Checkpoint Studio ngay sau khi đổi package:

| Chỉ số | Giá trị |
|---|---:|
| Impressions | Khoảng 5.100 |
| CTR | 2,9% |
| Views | 188 |
| Traffic chính | Browse |
| Video length | 8:04 |

Analytics export ngày 2026-07-14 ghi nhận:

| Chỉ số | Giá trị |
|---|---:|
| Views catalog | 227 |
| Likes | 2 |
| Comments | 1 |
| Retention rows toàn export | 900 |
| Reach normalized rows | 0 |

### Quan sát

- YouTube đã thử video trên Browse.
- Nội dung giữ người tương đối tốt so với catalog.
- Việc thay title từ tên riêng `Sulla` sang hành động dễ hiểu hơn là đúng hướng.
- Thumbnail vẫn có xu hướng giống một cảnh minh họa lịch sử hơn là một xung đột đọc được trong một giây.
- Tốc độ view sau thay package không đủ để tạo đợt mở rộng mới.
- Reach data trong Analytics ZIP chưa được materialize thành `reach_daily.csv`, dù Studio có impressions và CTR.

### Kết luận

Bottleneck chính không còn là khả năng hoàn thành video.

Bottleneck là:

1. Chọn topic có trần audience đủ lớn.
2. Tạo package có appeal với người không biết lịch sử.
3. Tạo thumbnail như một quảng cáo cho xung đột, không phải một frame minh họa.
4. Dùng dữ liệu thật để phản hồi về bước tìm topic.

### Quyết định ngày 2026-07-14

**Không tiếp tục cứu vớt hoặc đổi package video Sulla.**

Video được giữ làm dữ liệu học:

- content/retention reference;
- ví dụ về package integrity khá tốt nhưng broad-audience appeal chưa đủ;
- ví dụ về rủi ro dùng nhân vật niche làm cửa vào;
- baseline để so sánh video kế tiếp.

---

# IMPROVEMENT ROUND 3 — NEXT-VIDEO-FIRST UPGRADE

**Ngày bắt đầu:** 2026-07-14  
**Trạng thái:** Đang khởi động  
**Phạm vi:** Tìm chủ đề → đánh giá packageability → workflow content → sản xuất video  
**Không thuộc phạm vi:** Tiếp tục cứu video cũ

## 4.1 Mục tiêu của đợt

- chọn chủ đề có khả năng đạt ít nhất 20.000 impressions;
- target CTR Home/Suggested trên 5%;
- tạo video long-form đầu tiên vượt 1.000 views;
- giảm proper-noun overload trong 90 giây đầu;
- tích hợp packageability vào topic selection, không đợi đến Prompt 3;
- rút ngắn thời gian từ tìm topic đến production-ready package;
- đưa dữ liệu performance quay lại công cụ tìm chủ đề.

## 4.2 Giả thuyết chính

Video tiếp theo có xác suất breakout cao hơn nếu thỏa đồng thời:

1. Chủ thể hoặc biểu tượng được casual audience nhận ra.
2. Có một hành động, lựa chọn hoặc hậu quả hiểu được không cần kiến thức nền.
3. Thumbnail có một chủ thể, một đối trọng và một câu hỏi trực quan.
4. Opening trả đúng promise trong 15 giây.
5. Setup không chồng nhiều tên riêng.
6. Causal chain rõ hơn chronology.
7. Topic đã chứng minh khả năng tạo outlier ở nhiều channel, không chỉ một video lớn.

---

## 5. Kế hoạch nâng cấp công cụ tìm kiếm nội dung

# TASK 11A — TOPIC OPPORTUNITY ENGINE V2

**Ưu tiên:** Cao nhất  
**Mục tiêu:** Biến script scan hiện tại thành một hệ thống tạo shortlist có thể đưa thẳng vào Collector.

### 5.1 Những gì công cụ hiện tại làm tốt

- lấy dữ liệu thật từ YouTube Data API;
- tính outlier trong baseline cùng channel;
- tính velocity;
- phân biệt long-form và short-form;
- xuất dữ liệu có thể audit.

### 5.2 Khoảng trống hiện tại

- search query vẫn phụ thuộc nhiều vào người vận hành;
- chưa có query expansion theo cluster;
- chưa đánh giá độ quen thuộc của chủ thể;
- chưa đánh giá visual packageability;
- chưa đánh giá saturation;
- chưa phân biệt gateway topic và expert-only topic;
- chưa gom cùng một historical event qua nhiều cách gọi;
- chưa chấm độ mạnh của premise/title;
- chưa đưa channel learnings vào score;
- chưa tạo sẵn competitor candidate cho Collector.

### 5.3 Thiết kế Opportunity Engine V2

Luồng mới:

```text
Channel Learnings
+ Seed Cluster
+ Query Expansion
→ YouTube Candidate Collection
→ Event/Entity Normalization
→ Outlier and Velocity Analysis
→ Cross-Channel Validation
→ Packageability Gate
→ Researchability Gate
→ Ranked Topic Shortlist
→ Collector Project Candidate
```

### 5.4 Query expansion

Từ một seed như `Roman Republic collapse`, công cụ phải sinh các nhóm query:

- known figure:
  - Caesar;
  - Augustus;
  - Spartacus;
  - Hannibal;
- forbidden act:
  - crossed the Rubicon;
  - marched on Rome;
  - killed a consul;
- hidden cause:
  - army loyalty;
  - land crisis;
  - political violence;
- human consequence:
  - citizens lost farms;
  - veterans demanded land;
  - street gangs controlled elections;
- myth correction:
  - Caesar did not end the Republic alone;
  - Rome's victories weakened the Republic;
- object/place gateway:
  - Rubicon;
  - Senate;
  - Roman eagle;
  - triumph;
  - grain dole.

Query expansion phải deterministic và lưu lại seed/query lineage.

### 5.5 Candidate metrics mới

Ngoài chỉ số hiện tại, thêm:

| Nhóm | Metric |
|---|---|
| Demand | views, views/day, outlier score |
| Channel normalization | views/subscriber, baseline median |
| Freshness | age-adjusted velocity |
| Cross-channel proof | số channel độc lập có video outlier cùng topic |
| Saturation | số video gần đây cạnh tranh trực tiếp |
| Gateway familiarity | độ nhận diện nhân vật/sự kiện/vật thể |
| Packageability | one-sentence contradiction, one-image conflict |
| Researchability | nguồn đáng tin có thể truy cập |
| Production fit | dựng được bằng stick figure, không cần spectacle quá phức tạp |
| Channel fit | phù hợp cluster đang có tín hiệu |
| Originality room | còn khoảng trống cho angle mới |

### 5.6 Hard gates

Một topic bị loại trước workflow nếu:

- cần hơn một câu để giải thích vì sao nó đáng quan tâm;
- title bắt buộc phải bắt đầu bằng tên riêng ít người biết;
- không có hình ảnh mâu thuẫn đơn giản;
- chỉ có một video lớn nhưng không có cross-channel proof;
- competitor thành công chủ yếu nhờ creator personality;
- research không đủ để bảo vệ hook;
- hình ảnh cần battle spectacle quá phức tạp so với pipeline;
- angle mới chỉ là paraphrase của competitor.

### 5.7 Output mới

Mỗi candidate phải có một `topic_candidate.md`:

```markdown
# Topic Candidate

## Event Identity
## Cluster
## Why Now
## Cross-Channel Evidence
## Outlier Evidence
## Audience Gateway
## One-Sentence Contradiction
## Three Package Hypotheses
## Thumbnail Objects
## Research Questions
## Production Complexity
## Risks
## Score Breakdown
## Verdict
SHORTLIST / HOLD / REJECT
```

Đồng thời xuất:

- `topic_candidates.csv`;
- `topic_candidates.json`;
- `top_opportunities.md`;
- `collector_import.json`.

### 5.8 Scoring nguyên tắc

Không dùng một điểm tổng duy nhất làm quyền quyết định.

Hiển thị riêng ít nhất năm sub-score:

1. Demand score.
2. Cross-channel score.
3. Packageability score.
4. Researchability score.
5. Channel-fit score.

`opportunity_score` chỉ dùng để xếp hàng, không thay thế human gate.

---

## 6. Kế hoạch nâng cấp workflow nội dung

# TASK 11B — BROAD-AUDIENCE PACKAGE GATE

### Thay đổi

Thêm một gate trước khi tạo project hoặc trước Prompt 1:

- Người không biết lịch sử có hiểu stakes không?
- Có thể diễn đạt contradiction trong một câu ngắn không?
- Có một dominant object/action cho thumbnail không?
- Title có hoạt động khi bỏ proper noun không?
- Topic có gateway name hoặc gateway object không?
- Có tối thiểu ba package hypotheses khác nhau không?

### Scorecard mới

| Tiêu chí | Điểm |
|---|---:|
| Casual-audience comprehension | 0–2 |
| Recognizable gateway | 0–2 |
| One-image conflict | 0–2 |
| Specific information gap | 0–2 |
| Evidence-supported hook | 0–2 |
| Production simplicity | 0–2 |
| Cross-channel demand | 0–2 |
| Original angle room | 0–2 |

**Gate tối thiểu:** 13/16 và không có hard-fail.

Package score cũ vẫn được dùng ở Prompt 3, nhưng không còn là gate duy nhất.

---

## 7. Kế hoạch nâng cấp sản xuất video

# TASK 11C — PRODUCTION QUALITY V3

### 7.1 Package authority

- `publishing_package.md` là nguồn authority cho title/thumbnail.
- Stage metadata không được tự tạo primary title mới khi package đã khóa.
- Metadata generator chỉ:
  - validate;
  - format;
  - tạo upload fields;
  - cảnh báo mismatch.

### 7.2 First-90-Seconds QA

Tạo QA artifact tự động:

`output/first_90_seconds_qa.json`

Kiểm tra:

- package proof xuất hiện trước 15 giây;
- central question rõ trước 35 giây;
- inciting decision trước 45–60 giây;
- số proper nouns mới;
- context block dài;
- câu quá dài cho TTS;
- cảnh đầu có thực hiện thumbnail promise;
- visual change frequency;
- subtitle density;
- thời gian giữ một ảnh.

### 7.3 Timeline và hình ảnh

- scene target linh hoạt theo chức năng narrative;
- tension beat: cảnh ngắn hơn;
- explanation beat: cảnh dài hơn nhưng phải có visual change;
- recurring character phải lấy từ `characters.json`;
- first 30 seconds dùng hình có contrast và action cao nhất;
- không dùng cảnh establishing rộng làm thumbnail hoặc opening mặc định;
- cảnh phải phân biệt được protagonist, opposing force và consequence.

### 7.4 Thumbnail production

Tạo ba concept thực sự khác nhau:

1. Decision.
2. Conflict.
3. Consequence.

Không coi thay font, crop hoặc màu là concept mới.

Mỗi thumbnail phải có:

- dominant subject;
- opposing element;
- mobile crop preview;
- grayscale/readability preview;
- text-safe region;
- 160 px preview;
- package promise label.

### 7.5 Pre-render QA

Trước khi chạy toàn bộ ảnh:

- render thumbnail candidates;
- render 3–5 keyframes đầu;
- render keyframe reframe/climax;
- duyệt visual identity;
- chỉ sau đó mới batch toàn video.

Mục tiêu là phát hiện sớm:

- poster drift;
- parchment drift;
- nhân vật không nhất quán;
- composition quá rộng;
- silhouette không rõ;
- opening visuals thiếu tension.

### 7.6 Final QA artifact

Tạo:

`output/production_readiness.json`

Trạng thái:

- `READY_TO_RENDER`
- `READY_TO_UPLOAD`
- `BLOCKED_PACKAGE_MISMATCH`
- `BLOCKED_OPENING_MISMATCH`
- `BLOCKED_AUDIO_QA`
- `BLOCKED_VISUAL_QA`
- `BLOCKED_SUBTITLE_QA`

---

## 8. Kế hoạch vòng phản hồi dữ liệu

# TASK 11D — PERFORMANCE FEEDBACK LOOP

Mỗi video phải có một package experiment identity:

```text
video_id
project_slug
topic_candidate_id
package_version
title_hash
thumbnail_hash
activated_at
```

Dữ liệu cần lưu:

- impressions 24h / 72h / 7d;
- CTR tổng;
- CTR Browse;
- CTR Suggested;
- views;
- views/hour;
- AVD;
- APV;
- 30-second retention;
- topic score lúc chọn;
- packageability score;
- source cluster;
- kết quả thực tế.

Mục tiêu:

- so sánh score dự đoán với performance thật;
- điều chỉnh weight của Opportunity Engine;
- tìm gateway topic hiệu quả;
- tìm title pattern;
- tìm thumbnail language;
- tìm giới hạn production style.

### Collector issue cần xử lý

Analytics export ngày 2026-07-14 có:

- 13 video trong catalog;
- 57 dòng `video_daily.csv`;
- 900 dòng `retention.csv`;
- 69 dòng `traffic_source_daily.csv`;
- nhưng `reach_daily.csv` vẫn có 0 dòng.

Task kỹ thuật sau Opportunity Engine V2:

- đọc các reach reports đã tải;
- materialize impressions và CTR vào normalized output;
- ghi rõ unavailable do API, chưa có report hay parser chưa hỗ trợ;
- không để trạng thái generic che mất nguyên nhân.

---

## 9. Thứ tự triển khai được khóa

### Phase 1 — Topic discovery

1. Audit hai script hiện tại.
2. Thiết kế schema `topic_candidate`.
3. Thêm query expansion.
4. Thêm dedup/event normalization.
5. Thêm cross-channel proof.
6. Thêm packageability/researchability gates.
7. Xuất shortlist và Collector import.
8. Chạy real scan cho cluster Rome.
9. Chọn topic video kế tiếp.

### Phase 2 — Content workflow

1. Thêm Broad-Audience Package Gate.
2. Cập nhật Prompt 3 scorecard.
3. Thêm first-90-seconds constraints.
4. Giữ Evidence Ledger và red-team hiện tại.
5. Tạo production-ready package.

### Phase 3 — Production

1. Khóa package authority.
2. Thumbnail/keyframe preflight.
3. First-90-seconds QA.
4. Render video.
5. Final production readiness.
6. Upload với package đã khóa.

### Phase 4 — Measurement

1. Ghi T0.
2. Ghi 24h.
3. Ghi 72h.
4. Ghi 7 ngày.
5. Cập nhật file lịch sử này.
6. Cập nhật channel learnings.
7. Điều chỉnh Opportunity Engine.

---

## 10. Tiêu chí hoàn tất Improvement Round 3

Đợt này chỉ được đóng khi đạt một trong hai điều kiện:

### SUCCESS

- CTR Home/Suggested >= 5%;
- ít nhất 1.000 views;
- retention 30 giây >= 70%;
- APV >= 40%;
- có dữ liệu đủ để xác nhận topic/package pattern.

### LEARNING-COMPLETE

Không đạt 1.000 views, nhưng:

- có dữ liệu 72h/7d;
- xác định rõ bottleneck thuộc topic, package, opening, content hoặc distribution;
- score dự đoán và performance thật đã được lưu;
- có thay đổi cụ thể cho đợt tiếp theo;
- không lặp lại cùng một lỗi chưa được xử lý.

---

## 11. Entry template cho các lần cập nhật sau

```markdown
# IMPROVEMENT ROUND N — [TÊN]

**Ngày bắt đầu:**  
**Ngày kết thúc:**  
**Video/project:**  
**Trạng thái:**  

## Baseline

## Vấn đề

## Giả thuyết

## Thay đổi đã áp dụng

## Package

## Content changes

## Production changes

## Metrics target

## T0

## 24h result

## 72h result

## 7-day result

## What worked

## What failed

## Decision

## Changes retained

## Changes rejected

## Next round
```

---

## 12. Trạng thái hiện tại

**Ngày:** 2026-07-14  
**Current round:** Improvement Round 3 — Next-Video-First Upgrade  
**Current priority:** Task 11A — Topic Opportunity Engine V2  
**Old-video rescue:** Closed  
**Next deliverable:** Một shortlist chủ đề được chấm theo demand, cross-channel proof, packageability, researchability và channel fit  
**Production target:** Video kế tiếp được lựa chọn và khóa package trước khi viết narration  
**Performance target:** CTR trên 5% và 1.000 views đầu tiên

---

# IMPROVEMENT ROUND 3A - TASK 11A.1 TOPIC SCAN CORRECTNESS + STRUCTURED TOPIC GROUPS

**Ngay bat dau:** 2026-07-14  
**Ngay ket thuc:** 2026-07-14  
**Video/project:** Next-video selection only  
**Trang thai:** Implemented, awaiting Tech Lead review

## Baseline

- Topic scan and competitor probe already pulled useful YouTube Data API metadata.
- The old scan compared videos with only a coarse `SHORT` / `LONG` split.
- Baseline age was not protected strongly enough.
- Search results were useful but stayed query-centric instead of topic-group-centric.
- Old-video rescue for Sulla was already closed and stayed out of scope.

## Van de

- Unsafe baseline comparisons could mix unlike long-form formats.
- Total views alone could overstate an older video's advantage.
- The scan lacked deterministic group-level cross-channel evidence.
- There was no structured `--plan` handoff for repeatable topic clusters.
- The canonical tracked implementation did not yet live under `scripts/`.

## Gia thuyet

If the engine uses same-band baselines, minimum baseline age, lifetime views/day, explicit confidence labels, and structured topic groups, then topic selection will become more honest, more repeatable, and easier to review before creating the next Collector project.

## Thay doi da ap dung

- Added tracked shared core: `scripts/youtube_research_core.py`.
- Added tracked canonical scan CLI: `scripts/youtube_topic_opportunity_scan.py`.
- Added tracked canonical competitor probe CLI: `scripts/youtube_competitor_probe.py`.
- Added structured plan example: `config/topic_scan_plan.example.json`.
- Added operator documentation: `docs/topic_opportunity_engine.md`.
- Added offline regression coverage: `tests/test_youtube_research_core.py`.

## Package

No package, thumbnail, narration, transcript, or workflow-runtime generation was changed in this task.

## Content changes

No content-generation workflow prompt, candidate, approval, or production artifact was modified.

## Production changes

No YouTube Auto, rendering, subtitle, audio, or upload-stage behavior was modified.

## Metrics target

- Compare only against the same duration band.
- Exclude baseline videos younger than `48` hours by default.
- Report both:
  - descriptive `views_outlier_score`
  - primary `velocity_outlier_score` using `lifetime_views_per_day`
- Emit topic-group verdicts with explicit confidence and cross-channel evidence.

## T0

Implementation and offline verification only. No production topic was created in this step.

## 24h result

Not applicable yet. This task prepares deterministic topic selection, not live YouTube distribution.

## 72h result

Not applicable yet.

## 7-day result

Not applicable yet.

## What worked

- Shared core now owns API key loading, retry/backoff, sanitized cache fingerprints, ISO-8601 parsing, duration bands, datetime parsing, baseline eligibility, medians, confidence, and deterministic serialization.
- Structured `--plan` mode now validates schema version, unique group IDs, non-empty queries, duplicate normalized queries, and positive baseline settings.
- Direct repeated `--query` mode remains supported through a synthesized deterministic topic group.
- Candidate outputs now preserve multi-query hits while deduplicating video-detail requests globally.
- Topic groups now report candidate counts, unique-channel counts, qualifying outlier counts, median/max velocity evidence, confidence, quality label, verdict, and reasons.
- Competitor probe now uses the shared core and reports same-band baseline, minimum age, baseline confidence, `views_outlier_score`, and `velocity_outlier_score`.

## What failed

- No live Rome scan evidence was collected yet in this entry.
- This task does not yet solve broader packageability scoring or workflow import automation.

## Decision

- Keep Sulla rescue closed.
- Use Task 11A.1 outputs only for next-topic review, not automatic project creation.
- Move next decision gate to Tech Lead review of Task 11A.1 evidence.

## Changes retained

- Canonical duration bands:
  - `SHORT`
  - `LONG_3_10`
  - `LONG_10_30`
  - `LONG_30_PLUS`
- Baseline confidence labels:
  - `LOW`
  - `MEDIUM`
  - `HIGH`
- Group quality labels:
  - `WEAK`
  - `DIRECTIONAL`
  - `SUPPORTED`
  - `STRONG`
- Group verdicts:
  - `SHORTLIST`
  - `HOLD`
  - `REJECT`

## Changes rejected

- No AI scoring or recommendation layer was added.
- No transcript download or Collector import action was added.
- No runtime write into channel/project workflow state was added.

## Next round

Tech Lead review of Task 11A.1 evidence only. Task 11B remains unauthorized.

## Task 11A.1 verification addendum

- Disposable live Rome scan status: PASS.
- Candidate videos collected: `9`.
- Topic groups collected: `2`.
- Shortlist groups: `1`.
- `caesar_rubicon` => `SHORTLIST`.
- `marius_sulla` => `HOLD`.
- This addendum updates the live-evidence status without reopening old-video rescue work.
