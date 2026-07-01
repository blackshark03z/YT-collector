from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_SOURCE_FILENAME = "Mist_of_Ages_Prompt_Content_AI_Toi_Uu_V2.docx"
EXPECTED_SOURCE_SHA256 = "3D63D7049BA69CFF7B87537429D145B742394138864BB06F41E0B21FEA0EC772"
WORDPROCESSINGML_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
PROMPT_TITLE_TO_STEP_ID = {
    "Prompt 1 — Transcript Analyst": "prompt_1_transcript_analysis",
    "Prompt 2 — Historical Researcher + Evidence Ledger": "prompt_2_historical_research",
    "Prompt 3 — Creative Strategist + Publishing Package Designer": "prompt_3_creative_package",
    "Prompt 4 — Retention Architect": "prompt_4_retention_outline",
    "Prompt 5 — Main Writer": "prompt_5_narration_v1",
    "Prompt 6 — Independent Red-Team — Script + Package": "prompt_6_red_team",
    "Prompt 7 — Finalizer — Hai file bàn giao": "prompt_7_final_content",
}


class PromptSourceIngestError(Exception):
    pass


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def verify_source_document(path: Path | str) -> str:
    source_path = Path(path)
    digest = sha256_file(source_path)
    if digest != EXPECTED_SOURCE_SHA256:
        raise PromptSourceIngestError("Source DOCX SHA-256 does not match the approved value.")
    return digest


def _docx_paragraphs(path: Path | str) -> list[str]:
    source_path = Path(path)
    with zipfile.ZipFile(source_path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", WORDPROCESSINGML_NS):
        line = "".join((node.text or "") for node in paragraph.findall(".//w:t", WORDPROCESSINGML_NS)).strip()
        if line:
            paragraphs.append(line)
    return paragraphs


def extract_raw_prompt_bodies(path: Path | str) -> dict[str, str]:
    paragraphs = _docx_paragraphs(path)
    bodies: dict[str, str] = {}
    for index, line in enumerate(paragraphs):
        step_id = PROMPT_TITLE_TO_STEP_ID.get(line)
        if step_id is None:
            continue
        body_index = index + 9
        if body_index >= len(paragraphs):
            raise PromptSourceIngestError(f"Prompt body is missing for {line}.")
        bodies[step_id] = paragraphs[body_index]
    if set(bodies) != set(PROMPT_TITLE_TO_STEP_ID.values()):
        raise PromptSourceIngestError("Could not extract all seven prompt bodies from the source DOCX.")
    return bodies


def _replace_markers(text: str, markers: list[tuple[str, str]]) -> str:
    value = text
    for source, replacement in markers:
        value = value.replace(source, replacement)
    return value


def _normalize_common(text: str) -> str:
    value = text
    value = value.replace("\n-  ", "\n- ")
    cleanup_replacements = {
        "memory.The transcript": "memory.\nThe transcript",
        "moments;- curiosity beats.5. WEAK OR REMOVABLE ELEMENTSIdentify": "moments;\n- curiosity beats.\n5. WEAK OR REMOVABLE ELEMENTS\nIdentify",
        "claims;- later memoir claims.7. ORIGINALITY RISKSIdentify": "claims;\n- later memoir claims.\n7. ORIGINALITY RISKS\nIdentify",
        "questions;- 3 one-sentence core angles.Each core angle must:-": "questions;\n- 3 one-sentence core angles.\n\nEach core angle must:\n-",
        "framing.PART 2 — TITLE LABGenerate": "framing.\n\nPART 2 — TITLE LAB\nGenerate",
        "alternatives.Each concept must include:": "alternatives.\nEach concept must include:",
        "PART 4 — PACKAGE CONTRACTFor each title–thumbnail package, define:": "PART 4 — PACKAGE CONTRACT\nFor each title–thumbnail package, define:",
        "PART 5 — EARLY METADATA DRAFTCreate:": "PART 5 — EARLY METADATA DRAFT\nCreate:",
        "PART 6 — LOCK ONE PACKAGEChoose": "PART 6 — LOCK ONE PACKAGE\nChoose",
        "system.Do not rewrite the narration and do not create a new package.": "system.\nDo not rewrite the narration and do not create a new package.",
        "certainty?- Is it supported by the Evidence Ledger?": "certainty?\n- Is it supported by the Evidence Ledger?",
        "or locations.Qualify interpretations": "or locations.\nQualify interpretations",
        "words.The outline must fulfill the Primary Title, Primary Thumbnail Promise, and First-15-Second Proof.": "words.\nThe outline must fulfill the Primary Title, Primary Thumbnail Promise, and First-15-Second Proof.",
    }
    for source, replacement in cleanup_replacements.items():
        value = value.replace(source, replacement)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip() + "\n"


def _format_prompt_1(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("audience.INPUTS-", "audience.\n\nINPUTS\n- "),
                (" metadata- Full", " metadata\n- Full"),
                (" Transcript- Optional", " Transcript\n- Optional"),
                (" LearningsMISSION", " Learnings\n\nMISSION\n"),
                (" memory.The transcript", " memory.\nThe transcript"),
                ("source.DELIVER1. SUBJECT", "source.\n\nDELIVER\n1. SUBJECT\n"),
                (".2. COMPETITOR PROMISE", ".\n2. COMPETITOR PROMISE\n"),
                ("quickly.3. NARRATIVE MAP", "quickly.\n3. NARRATIVE MAP\n"),
                ("ending.4. STRONG IDEA-LEVEL ELEMENTS", "ending.\n4. STRONG IDEA-LEVEL ELEMENTS\n"),
                ("researching:- contradiction;", "researching:\n- contradiction;"),
                ("; human stakes;", "\n- human stakes;"),
                ("; emotional tension;", "\n- emotional tension;"),
                ("; visually strong moments;", "\n- visually strong moments;"),
                ("moments;- curiosity beats.5. WEAK OR REMOVABLE ELEMENTSIdentify", "moments;\n- curiosity beats.\n5. WEAK OR REMOVABLE ELEMENTS\nIdentify"),
                ("; curiosity beats.5. WEAK OR REMOVABLE ELEMENTSIdentify", "\n- curiosity beats.\n5. WEAK OR REMOVABLE ELEMENTS\nIdentify"),
                ("; curiosity beats.5. WEAK OR REMOVABLE ELEMENTS", "\n- curiosity beats.\n5. WEAK OR REMOVABLE ELEMENTS\n"),
                ("chronology.6. CLAIM MAP", "chronology.\n6. CLAIM MAP\n"),
                ("verification:- names", "verification:\n- names"),
                ("; dates and locations;", "\n- dates and locations;"),
                ("; casualty counts and numbers;", "\n- casualty counts and numbers;"),
                ("; motives and internal states;", "\n- motives and internal states;"),
                ("; quotations and dialogue;", "\n- quotations and dialogue;"),
                ("; “common belief” claims;", "\n- “common belief” claims;"),
                ("; dramatic details;", "\n- dramatic details;"),
                ("; later memoir claims.7. ORIGINALITY RISKSIdentify", "\n- later memoir claims.\n7. ORIGINALITY RISKS\nIdentify"),
                ("; later memoir claims.7. ORIGINALITY RISKS", "\n- later memoir claims.\n7. ORIGINALITY RISKS\n"),
                ("copy.8. NEUTRAL RESEARCH QUESTIONS", "copy.\n8. NEUTRAL RESEARCH QUESTIONS\n"),
                ("correct.RULES-", "correct.\n\nRULES\n- "),
                (" narration.- Do not", " narration.\n- Do not"),
                (" angle.- Do not", " angle.\n- Do not"),
                (" phrases.- Mark", " phrases.\n- Mark"),
                ("[UNCLEAR].OUTPUT ONLY", "[UNCLEAR].\n\nOUTPUT ONLY\n"),
                ("## Subject## Competitor Promise", "## Subject\n## Competitor Promise"),
                ("Promise## Narrative Map", "Promise\n## Narrative Map"),
                ("Map## Strong Idea-Level Elements", "Map\n## Strong Idea-Level Elements"),
                ("Elements## Weak or Removable Elements", "Elements\n## Weak or Removable Elements"),
                ("Elements## Claims Requiring Verification", "Elements\n## Claims Requiring Verification"),
                ("Verification## Originality Risks", "Verification\n## Originality Risks"),
                ("Risks## Neutral Research Questions", "Risks\n## Neutral Research Questions"),
            ],
        )
    )


def _format_prompt_2(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("Ages.INPUTS-", "Ages.\n\nINPUTS\n- "),
                (" Analysis- Competitor", " Analysis\n- Competitor"),
                (" Transcript- TopicMISSION", " Transcript\n- Topic\n\nMISSION\n"),
                ("hypothesis.SOURCE PRIORITY1. Primary", "hypothesis.\n\nSOURCE PRIORITY\n1. Primary"),
                (" records2. Museums", " records\n2. Museums"),
                (" societies3. Reputable", " societies\n3. Reputable"),
                (" research4. High-quality", " research\n4. High-quality"),
                (" journalism5. General", " journalism\n5. General"),
                (" leadsRESEARCH TASKS1. Establish", " leads\n\nRESEARCH TASKS\n1. Establish"),
                ("timeline.2. Identify", "timeline.\n2. Identify"),
                (" roles.3. Verify", " roles.\n3. Verify"),
                (" quotations.4. Find", " quotations.\n4. Find"),
                (" story.5. Find", " story.\n5. Find"),
                (" cost.6. Separate", " cost.\n6. Separate"),
                (" details.7. Investigate", " details.\n7. Investigate"),
                (" Analyst.8. Find", " Analyst.\n8. Find"),
                (" framing.9. Identify", " framing.\n9. Identify"),
                (" angle.10. Identify", " angle.\n10. Identify"),
                (" animation.OUTPUT A — RESEARCH PACK", " animation.\n\nOUTPUT A — RESEARCH PACK\n"),
                ("## Topic Overview## Reliable Timeline", "## Topic Overview\n## Reliable Timeline"),
                ("Timeline## Key People and Roles", "Timeline\n## Key People and Roles"),
                ("Roles## Anchor Facts", "Roles\n## Anchor Facts"),
                ("Facts## Human Details and Human Cost", "Facts\n## Human Details and Human Cost"),
                ("Cost## Myths, Disputes, and Later Accounts", "Cost\n## Myths, Disputes, and Later Accounts"),
                ("Accounts## Facts That Contradict the Competitor", "Accounts\n## Facts That Contradict the Competitor"),
                ("Competitor## Possible Evidence-Based Contradictions", "Competitor\n## Possible Evidence-Based Contradictions"),
                ("Contradictions## Documented Visual Details", "Contradictions\n## Documented Visual Details"),
                ("Details## Source NotesOUTPUT B — EVIDENCE LEDGER", "Details\n## Source Notes\n\nOUTPUT B — EVIDENCE LEDGER\n"),
                ("claim:CLAIM:SOURCE:STATUS:ALLOWED WORDING:NOTES:STATUS RULES-", "claim:\nCLAIM:\nSOURCE:\nSTATUS:\nALLOWED WORDING:\nNOTES:\n\nSTATUS RULES\n- "),
                (" fact.- ATTRIBUTED:", " fact.\n- ATTRIBUTED:"),
                (" claimant.- DISPUTED:", " claimant.\n- DISPUTED:"),
                (" omitted.- UNSUPPORTED:", " omitted.\n- UNSUPPORTED:"),
                (" forbidden.- FALSE:", " forbidden.\n- FALSE:"),
                (" forbidden.Never silently", " forbidden.\n\nNever silently"),
                ("source.If reliable", "source.\n\nIf reliable"),
                ("output:RESEARCH_REQUIREDMissing verification:- [claim]- [claim]", "output:\nRESEARCH_REQUIRED\nMissing verification:\n- [claim]\n- [claim]"),
            ],
        )
    )


def _format_prompt_3(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("Ages.INPUTS-", "Ages.\n\nINPUTS\n- "),
                (" Reference- Transcript", " Reference\n- Transcript"),
                (" Analysis- Research", " Analysis\n- Research"),
                (" Pack- Evidence", " Pack\n- Evidence"),
                (" Ledger- Optional", " Ledger\n- Optional"),
                (" LearningsMISSION", " Learnings\n\nMISSION\n"),
                ("written.Create", "written.\nCreate"),
                (" fulfill.Do not", " fulfill.\nDo not"),
                (" narration.PART 1 — CREATE STRATEGIC OPTIONS", " narration.\n\nPART 1 — CREATE STRATEGIC OPTIONS\n"),
                ("Generate:- 3 central questions;", "Generate:\n- 3 central questions;"),
                ("questions;- 3 one-sentence core angles.Each core angle must:-", "questions;\n- 3 one-sentence core angles.\n\nEach core angle must:\n-"),
                ("; 3 one-sentence core angles.Each core angle must:- be specific to this event;", "\n- 3 one-sentence core angles.\n\nEach core angle must:\n- be specific to this event;"),
                ("; 3 one-sentence core angles.Each core angle must:-", "\n- 3 one-sentence core angles.\n\nEach core angle must:\n-"),
                ("; explain more than the timeline;", "\n- explain more than the timeline;"),
                ("; be supported by the Evidence Ledger;", "\n- be supported by the Evidence Ledger;"),
                ("; avoid generic lessons;", "\n- avoid generic lessons;"),
                ("; differ from the competitor’s signature framing.PART 2 — TITLE LAB", "\n- differ from the competitor’s signature framing.\n\nPART 2 — TITLE LAB\n"),
                ("English.Title requirements:- immediately understandable to a non-specialist;", "English.\n\nTitle requirements:\n- immediately understandable to a non-specialist;"),
                ("; strongest idea near the beginning;", "\n- strongest idea near the beginning;"),
                ("; one specific information gap;", "\n- one specific information gap;"),
                ("; accurate and evidence-supported;", "\n- accurate and evidence-supported;"),
                ("; no keyword stuffing;", "\n- no keyword stuffing;"),
                ("; no empty “untold truth” wording;", "\n- no empty “untold truth” wording;"),
                ("; no title that merely copies the competitor;", "\n- no title that merely copies the competitor;"),
                ("mobile.Eliminate weak candidates, then select:", "mobile.\n\nEliminate weak candidates, then select:"),
                ("; preferably concise enough to scan quickly on mobile.Eliminate", "\n- preferably concise enough to scan quickly on mobile.\n\nEliminate"),
                ("select:- 1 Primary Title;", "select:\n- 1 Primary Title;"),
                ("; 1 Backup Title A;", "\n- 1 Backup Title A;"),
                ("; 1 Backup Title B.For each finalist,", "\n- 1 Backup Title B.\n\nFor each finalist,"),
                (" carries.PART 3 — THUMBNAIL LAB", " carries.\n\nPART 3 — THUMBNAIL LAB\n"),
                ("include:- dominant subject;", "include:\n- dominant subject;"),
                ("; expression or emotion;", "\n- expression or emotion;"),
                ("; opposing element;", "\n- opposing element;"),
                ("; minimal background context;", "\n- minimal background context;"),
                ("; exact text overlay, 0–4 words;", "\n- exact text overlay, 0–4 words;"),
                ("; one visual accent;", "\n- one visual accent;"),
                ("; the unanswered question created;", "\n- the unanswered question created;"),
                ("; a complete image-generation prompt.Thumbnail requirements:- 16:9 YouTube composition;", "\n- a complete image-generation prompt.\n\nThumbnail requirements:\n- 16:9 YouTube composition;"),
                ("; one dominant subject;", "\n- one dominant subject;"),
                ("; one emotion;", "\n- one emotion;"),
                ("; one contradiction;", "\n- one contradiction;"),
                ("; high contrast and readable at mobile size;", "\n- high contrast and readable at mobile size;"),
                ("; simple 2D stick-figure style consistent with Mist of Ages;", "\n- simple 2D stick-figure style consistent with Mist of Ages;"),
                ("; no collage;", "\n- no collage;"),
                ("; no gore;", "\n- no gore;"),
                ("; no tiny historical details;", "\n- no tiny historical details;"),
                ("; no unsupported visual claim;", "\n- no unsupported visual claim;"),
                ("; leave clean negative space for the text overlay;", "\n- leave clean negative space for the text overlay;"),
                ("; do not ask the image model to render text inside the image.The generation prompt must describe only the image. Put the overlay text separately.PART 4 — PACKAGE CONTRACT", "\n- do not ask the image model to render text inside the image.\n\nThe generation prompt must describe only the image. Put the overlay text separately.\n\nPART 4 — PACKAGE CONTRACT\n"),
                ("define:- Package Promise;", "define:\n- Package Promise;"),
                ("; First-15-Second Proof;", "\n- First-15-Second Proof;"),
                ("; Deeper Unresolved Question.Score each package from 0–2 on:1. Instant comprehension2. Specific curiosity3. Visual simplicity4. Title–thumbnail complement5. Evidence support6. First-15-second deliverabilityReject packages below 10/12.PART 5 — EARLY METADATA DRAFT", "\n- Deeper Unresolved Question.\n\nScore each package from 0–2 on:\n1. Instant comprehension\n2. Specific curiosity\n3. Visual simplicity\n4. Title–thumbnail complement\n5. Evidence support\n6. First-15-second deliverability\n\nReject packages below 10/12.\n\nPART 5 — EARLY METADATA DRAFT\n"),
                ("Create:- one Description Draft of approximately 120–180 words;", "Create:\n- one Description Draft of approximately 120–180 words;"),
                ("; one Hashtag Draft containing 5–8 directly relevant hashtags;", "\n- one Hashtag Draft containing 5–8 directly relevant hashtags;"),
                ("; one Primary Keyword;", "\n- one Primary Keyword;"),
                ("; 3–6 Supporting Keywords.Description rules:- first two lines clearly state the premise;", "\n- 3–6 Supporting Keywords.\n\nDescription rules:\n- first two lines clearly state the premise;"),
                ("; natural keywords, no stuffing;", "\n- natural keywords, no stuffing;"),
                ("; no claim outside the Evidence Ledger;", "\n- no claim outside the Evidence Ledger;"),
                ("; no spoiler that destroys the central question;", "\n- no spoiler that destroys the central question;"),
                ("; one concise viewer question or soft CTA at the end.Hashtag rules:- relevant to the exact subject and history niche;", "\n- one concise viewer question or soft CTA at the end.\n\nHashtag rules:\n- relevant to the exact subject and history niche;"),
                ("; most important three first;", "\n- most important three first;"),
                ("; no unrelated viral tags.PART 6 — LOCK ONE PACKAGE", "\n- no unrelated viral tags.\n\nPART 6 — LOCK ONE PACKAGE\n"),
                ("potential.Do not", "potential.\nDo not"),
                (" dramatic.OUTPUT ONLY", " dramatic.\n\nOUTPUT ONLY\n"),
                ("# Locked Creative Package## Topic Verdict", "# Locked Creative Package\n## Topic Verdict"),
                ("VerdictPRODUCE / REVISE / TOPIC_REJECTED", "Verdict\nPRODUCE / REVISE / TOPIC_REJECTED"),
                ("TOPIC_REJECTED## Locked Central Question", "TOPIC_REJECTED\n## Locked Central Question"),
                ("Question## Locked Core Angle", "Question\n## Locked Core Angle"),
                ("Angle## Viewer Takeaway", "Angle\n## Viewer Takeaway"),
                ("moral.## Primary Package", "moral.\n## Primary Package"),
                ("Package### Primary Title", "Package\n### Primary Title"),
                ("Title### Why It Wins", "Title\n### Why It Wins"),
                ("Wins### Risk to Watch", "Wins\n### Risk to Watch"),
                ("Watch### Thumbnail Concept", "Watch\n### Thumbnail Concept"),
                ("Concept### Thumbnail Text Overlay", "Concept\n### Thumbnail Text Overlay"),
                ("Overlay### Thumbnail Generation Prompt", "Overlay\n### Thumbnail Generation Prompt"),
                ("Prompt### Package Promise", "Prompt\n### Package Promise"),
                ("Promise### First-15-Second Proof", "Promise\n### First-15-Second Proof"),
                ("Proof### Deeper Unresolved Question", "Proof\n### Deeper Unresolved Question"),
                ("Question### Package Score", "Question\n### Package Score"),
                ("Score## Backup Package A", "Score\n## Backup Package A"),
                ("A### Backup Title", "A\n### Backup Title"),
                ("Title### Why It Works", "Title\n### Why It Works"),
                ("Works### Thumbnail Concept", "Works\n### Thumbnail Concept"),
                ("Score## Backup Package B", "Score\n## Backup Package B"),
                ("B### Backup Title", "B\n### Backup Title"),
                ("Score## Additional Title Candidates", "Score\n## Additional Title Candidates"),
                ("CandidatesList the seven non-finalist titles.## Description Draft", "Candidates\nList the seven non-finalist titles.\n## Description Draft"),
                ("Draft## Hashtag Draft", "Draft\n## Hashtag Draft"),
                ("Draft## Keyword SetPrimary Keyword:Supporting Keywords:## Required Anchor Facts", "Draft\n## Keyword Set\nPrimary Keyword:\nSupporting Keywords:\n## Required Anchor Facts"),
                ("Facts## Required Human-Cost Detail", "Facts\n## Required Human-Cost Detail"),
                ("Detail## Forbidden Claims", "Detail\n## Forbidden Claims"),
                ("ClaimsInclude every UNSUPPORTED or FALSE claim likely to tempt the writer.## Originality Guardrails", "Claims\nInclude every UNSUPPORTED or FALSE claim likely to tempt the writer.\n## Originality Guardrails"),
                ("GuardrailsIf no package is strong and defensible, return:TOPIC_REJECTEDReason: [concise reason]", "Guardrails\nIf no package is strong and defensible, return:\nTOPIC_REJECTED\nReason: [concise reason]"),
            ],
        )
    )


def _format_prompt_4(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("Ages.INPUTS-", "Ages.\n\nINPUTS\n- "),
                (" Package- Research", " Package\n- Research"),
                (" Pack- Evidence", " Pack\n- Evidence"),
                (" LedgerMISSION", " Ledger\n\nMISSION\n"),
                (" words.The outline must fulfill the Primary Title, Primary Thumbnail Promise, and First-15-Second Proof.", " words.\nThe outline must fulfill the Primary Title, Primary Thumbnail Promise, and First-15-Second Proof."),
                ("Proof.STRUCTURE0:00–0:15 — PACKAGE PROOF", "Proof.\n\nSTRUCTURE\n0:00–0:15 — PACKAGE PROOF\n"),
                ("cost.Confirm the click without revealing the complete answer.0:15–0:35 — CENTRAL QUESTION", "cost.\nConfirm the click without revealing the complete answer.\n0:15–0:35 — CENTRAL QUESTION\n"),
                ("gap.0:35–1:30 — MINIMUM SETUP", "gap.\n0:35–1:30 — MINIMUM SETUP\n"),
                ("story.1:30–MIDDLE — CAUSAL ESCALATION", "story.\n1:30–MIDDLE — CAUSAL ESCALATION\n"),
                (" D.MIDDLE/LATE — EVIDENCE-BASED REFRAME", " D.\nMIDDLE/LATE — EVIDENCE-BASED REFRAME\n"),
                (" cost.LATE — HUMAN COST + AFTERMATH", " cost.\nLATE — HUMAN COST + AFTERMATH\n"),
                (" changed.ENDING — PRECISE MEANING + DEBATE", " changed.\nENDING — PRECISE MEANING + DEBATE\n"),
                (" answers.FOR EACH BEAT INCLUDE-", " answers.\n\nFOR EACH BEAT INCLUDE\n- "),
                (" position- Narrative purpose", " position\n- Narrative purpose"),
                (" purpose- Verified facts used", " purpose\n- Verified facts used"),
                (" used- Package element fulfilled", " used\n- Package element fulfilled"),
                (" fulfilled- Curiosity loop opened", " fulfilled\n- Curiosity loop opened"),
                (" opened- Curiosity loop closed", " opened\n- Curiosity loop closed"),
                (" closed- Emotional state", " closed\n- Emotional state"),
                (" state- Visual scene potential", " state\n- Visual scene potential"),
                (" potential- TransitionRETENTION RULES-", " potential\n- Transition\n\nRETENTION RULES\n- "),
                (" Package.- Meaningful", " Package.\n- Meaningful"),
                (" seconds.- No more", " seconds.\n- No more"),
                (" once.- Close", " once.\n- Close"),
                (" another.- No context", " another.\n- No context"),
                (" words.- Avoid", " words.\n- Avoid"),
                (" names.- Every beat", " names.\n- Every beat"),
                (" off.- Every beat", " off.\n- Every beat"),
                (" figures.Do not write finished prose.OUTPUT ONLY", " figures.\n\nDo not write finished prose.\n\nOUTPUT ONLY\n"),
                ("# Retention Outline## Package Fulfillment Map", "# Retention Outline\n## Package Fulfillment Map"),
                ("Map## 0:00–0:15 — Package Proof", "Map\n## 0:00–0:15 — Package Proof"),
                ("Proof## 0:15–0:35 — Central Question", "Proof\n## 0:15–0:35 — Central Question"),
                ("Question## 0:35–1:30 — Minimum Setup", "Question\n## 0:35–1:30 — Minimum Setup"),
                ("Setup## Causal Escalation", "Setup\n## Causal Escalation"),
                ("Escalation## Evidence-Based Reframe", "Escalation\n## Evidence-Based Reframe"),
                ("Reframe## Human Cost and Aftermath", "Reframe\n## Human Cost and Aftermath"),
                ("Aftermath## Ending and Debate Question", "Aftermath\n## Ending and Debate Question"),
                ("Question## Open-Loop Audit", "Question\n## Open-Loop Audit"),
                ("Audit## Visuality Audit", "Audit\n## Visuality Audit"),
            ],
        )
    )


def _format_prompt_5(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("audience.INPUTS-", "audience.\n\nINPUTS\n- "),
                (" Transcript- Locked", " Transcript\n- Locked"),
                (" Package- Research", " Package\n- Research"),
                (" Pack- Evidence", " Pack\n- Evidence"),
                (" Ledger- Retention", " Ledger\n- Retention"),
                (" Outline- Optional", " Outline\n- Optional"),
                (" NotesMISSION", " Notes\n\nMISSION\n"),
                (" rewrite.AUTHORITY ORDER1. Evidence Ledger = factual authority2. Locked Creative Package = strategic and packaging authority3. Retention Outline = structural authority4. Competitor Transcript = idea lead onlySOURCE RULES-", " rewrite.\n\nAUTHORITY ORDER\n1. Evidence Ledger = factual authority\n2. Locked Creative Package = strategic and packaging authority\n3. Retention Outline = structural authority\n4. Competitor Transcript = idea lead only\n\nSOURCE RULES\n- "),
                (" fact.- ATTRIBUTED:", " fact.\n- ATTRIBUTED:"),
                (" claimant.- DISPUTED:", " claimant.\n- DISPUTED:"),
                (" omit.- UNSUPPORTED/FALSE:", " omit.\n- UNSUPPORTED/FALSE:"),
                (" use.Never invent", " use.\n\nNever invent"),
                (" or locations.Qualify interpretations", " or locations.\nQualify interpretations"),
                (" have.”PACKAGE CONTRACT-", " have.”\n\nPACKAGE CONTRACT\n- "),
                (" promise.- The central", " promise.\n- The central"),
                (" seconds.- Do not", " seconds.\n- Do not"),
                (" promise.- Preserve", " promise.\n- Preserve"),
                (" answer.NARRATIVE REQUIREMENTS-", " answer.\n\nNARRATIVE REQUIREMENTS\n- "),
                (" angle.- 65–75% story/evidence; 15–25% analysis; 5–15% reflection.- Meaningful", " angle.\n- 65–75% story/evidence; 15–25% analysis; 5–15% reflection.\n- Meaningful"),
                (" seconds.- Causal", " seconds.\n- Causal"),
                (" listing.- Human", " listing.\n- Human"),
                (" supported.- No more", " supported.\n- No more"),
                (" loops.- Ending", " loops.\n- Ending"),
                (" debate.US AUDIENCEAssume little prior knowledge. Explain unfamiliar institutions and locations briefly. Avoid stacking names. Use concrete stakes and natural American English.STYLEThoughtful but clear. Cinematic but restrained. Emotional but not sentimental. Deep but not academic. Shorter sentences as tension rises. Light dry humor only when appropriate. Natural for AI voice. Visually adaptable to simple stick-figure scenes.AVOID-", " debate.\n\nUS AUDIENCE\nAssume little prior knowledge. Explain unfamiliar institutions and locations briefly. Avoid stacking names. Use concrete stakes and natural American English.\n\nSTYLE\nThoughtful but clear. Cinematic but restrained. Emotional but not sentimental. Deep but not academic. Shorter sentences as tension rises. Light dry humor only when appropriate. Natural for AI voice. Visually adaptable to simple stick-figure scenes.\n\nAVOID\n- "),
                (" openings;- “Imagine…”", " openings;\n- “Imagine…”"),
                (" history…”;- unverified", " history…”;\n- unverified"),
                (" framing;- generic", " framing;\n- generic"),
                (" lessons;- sermon tone;- fake quotes;- purple prose;- repeated thesis;- copied jokes, scene order, wording, or signature framing.Prefer not to use:“The real story…”“Nobody talks about…”“History remembers…”“Everything we know is wrong…”“This changes everything…”“That question is the whole story…”LENGTHApproximately 1,000–1,300 words. Do not add filler.OUTPUT ONLY## Narration[English narration]", " lessons;\n- sermon tone;\n- fake quotes;\n- purple prose;\n- repeated thesis;\n- copied jokes, scene order, wording, or signature framing.\n\nPrefer not to use:\n“The real story…”\n“Nobody talks about…”\n“History remembers…”\n“Everything we know is wrong…”\n“This changes everything…”\n“That question is the whole story…”\n\nLENGTH\nApproximately 1,000–1,300 words. Do not add filler.\n\nOUTPUT ONLY\n## Narration\n[English narration]"),
            ],
        )
    )


def _format_prompt_6(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("Ages.INPUTS-", "Ages.\n\nINPUTS\n- "),
                (" V1- Locked", " V1\n- Locked"),
                (" Package- Evidence", " Package\n- Evidence"),
                (" Ledger- Retention", " Ledger\n- Retention"),
                (" Outline- Competitor", " Outline\n- Competitor"),
                (" TranscriptMISSION", " Transcript\n\nMISSION\n"),
                (" system.Do not rewrite the narration and do not create a new package.", " system.\nDo not rewrite the narration and do not create a new package."),
                ("package.AUDIT DIMENSIONS1. FACT INTEGRITY", "package.\n\nAUDIT DIMENSIONS\n1. FACT INTEGRITY\n"),
                ("casualties.2. TITLE INTEGRITY- Does", "casualties.\n2. TITLE INTEGRITY\n- Does"),
                (" certainty?- Is it supported by the Evidence Ledger?", " certainty?\n- Is it supported by the Evidence Ledger?"),
                (" Ledger?- Does", " Ledger?\n- Does"),
                (" gap?3. THUMBNAIL INTEGRITY- Does", " gap?\n3. THUMBNAIL INTEGRITY\n- Does"),
                (" situation?- Does", " situation?\n- Does"),
                (" question?- Is", " question?\n- Is"),
                (" repetitive?- Does", " repetitive?\n- Does"),
                (" promise?4. DESCRIPTION AND HASHTAG INTEGRITY- Does", " promise?\n4. DESCRIPTION AND HASHTAG INTEGRITY\n- Does"),
                (" narration?- Does", " narration?\n- Does"),
                (" misleading?- Are", " misleading?\n- Are"),
                (" non-spammy?5. PACKAGE–OPENING ALIGNMENT- Does", " non-spammy?\n5. PACKAGE–OPENING ALIGNMENT\n- Does"),
                (" package?- Is", " package?\n- Is"),
                (" seconds?- Does", " seconds?\n- Does"),
                (" story?6. RETENTIONSlow", " story?\n6. RETENTION\nSlow"),
                (" blocks.7. CAUSALITYDoes", " blocks.\n7. CAUSALITY\nDoes"),
                (" movement.8. US CLARITYUnexplained", " movement.\n8. US CLARITY\nUnexplained"),
                (" stakes.9. AI LANGUAGEGeneric", " stakes.\n9. AI LANGUAGE\nGeneric"),
                (" metaphors.10. ORIGINALITYCopied", " metaphors.\n10. ORIGINALITY\nCopied"),
                (" framing.11. TTS AND VISUALITYNested/breathless", " framing.\n11. TTS AND VISUALITY\nNested/breathless"),
                (" execute.OUTPUT ONLY", " execute.\n\nOUTPUT ONLY\n"),
                ("## Overall VerdictPASS / REVISE / REJECT", "## Overall Verdict\nPASS / REVISE / REJECT"),
                ("REJECT## Must Fix — Narration", "REJECT\n## Must Fix — Narration"),
                ("NarrationFor each item:- Exact location- Problem- Why it matters- Surgical instruction", "Narration\nFor each item:\n- Exact location\n- Problem\n- Why it matters\n- Surgical instruction"),
                ("instruction## Must Fix — Publishing Package", "instruction\n## Must Fix — Publishing Package"),
                ("PackageFor each item:- Package field- Problem- Why it matters- Surgical instruction", "Package\nFor each item:\n- Package field\n- Problem\n- Why it matters\n- Surgical instruction"),
                ("instruction## Optional Improvements## Passed ChecksDo not produce a rewritten script.Do not generate replacement titles or prompts unless a Must Fix item requires a narrowly scoped correction.", "instruction\n## Optional Improvements\n## Passed Checks\n\nDo not produce a rewritten script.\nDo not generate replacement titles or prompts unless a Must Fix item requires a narrowly scoped correction."),
            ],
        )
    )


def _format_prompt_7(raw: str) -> str:
    return _normalize_common(
        _replace_markers(
            raw,
            [
                ("package.INPUTS-", "package.\n\nINPUTS\n- "),
                (" V1- Red-Team", " V1\n- Red-Team"),
                (" Report- Locked", " Report\n- Locked"),
                (" Package- Evidence", " Package\n- Evidence"),
                (" LedgerMISSION", " Ledger\n\nMISSION\n"),
                (" files:1. content.md2. publishing_package.mdAPPLY-", " files:\n1. content.md\n2. publishing_package.md\n\nAPPLY\n- "),
                (" item.- OPTIONAL", " item.\n- OPTIONAL"),
                (" alignment.PRESERVE-", " alignment.\n\nPRESERVE\n- "),
                (" question.- Locked", " question.\n- Locked"),
                (" angle.- Primary", " angle.\n- Primary"),
                (" contract.- Strongest", " contract.\n- Strongest"),
                (" lines.- Causal", " lines.\n- Causal"),
                (" progression.- Sourced", " progression.\n- Sourced"),
                (" cost.DO NOT-", " cost.\n\nDO NOT\n- "),
                (" necessity.- Introduce", " necessity.\n- Introduce"),
                (" claim.- Add", " claim.\n- Add"),
                (" Ledger.- Change", " Ledger.\n- Change"),
                (" angle.- Add", " angle.\n- Add"),
                (" filler.- Invent", " filler.\n- Invent"),
                (" package.FINAL PACKAGE RULES-", " package.\n\nFINAL PACKAGE RULES\n- "),
                (" narration.- If", " narration.\n- If"),
                (" Check.- Final", " Check.\n- Final"),
                (" words.- Final", " words.\n- Final"),
                (" first.- Thumbnail", " first.\n- Thumbnail"),
                ("supported.- Keep", "supported.\n- Keep"),
                (" text.FINAL SILENT CHECKFACT-", " text.\n\nFINAL SILENT CHECK\nFACT\n- "),
                (" allowed.- Attributed", " allowed.\n- Attributed"),
                (" attributed.- No", " attributed.\n- No"),
                (" scene.PACKAGE-", " scene.\n\nPACKAGE\n- "),
                (" specific.- Primary", " specific.\n- Primary"),
                (" question.- Title", " question.\n- Title"),
                (" repeat each other.- First", " repeat each other.\n- First"),
                (" package.- Central", " package.\n- Central"),
                (" seconds.METADATA-", " seconds.\n\nMETADATA\n- "),
                (" claim.- Hashtags", " claim.\n- Hashtags"),
                (" relevant.- Backup", " relevant.\n- Backup"),
                (" alternatives.RETENTION-", " alternatives.\n\nRETENTION\n- "),
                (" immediately.- Meaningful", " immediately.\n- Meaningful"),
                (" seconds.- No more", " seconds.\n- No more"),
                (" loops.- Middle", " loops.\n- Middle"),
                (" escalation.- Ending", " escalation.\n- Ending"),
                (" opening.VOICE-", " opening.\n\nVOICE\n- "),
                (" English.- Clear", " English.\n- Clear"),
                (" non-specialist.- Easy", " non-specialist.\n- Easy"),
                (" voice.- Visually", " voice.\n- Visually"),
                (" adaptable.- No sermon tone.- At least one precise, memorable observation.ORIGINALITY-", " adaptable.\n- No sermon tone.\n- At least one precise, memorable observation.\n\nORIGINALITY\n- "),
                (" rewrite.- No copied joke, sequence, or signature framing.OUTPUT EXACTLY TWO SECTIONS", " rewrite.\n- No copied joke, sequence, or signature framing.\n\nOUTPUT EXACTLY TWO SECTIONS\n"),
                ("=== FILE 1: content.md ===## Narration[Final English narration]=== FILE 2: publishing_package.md ===# Publishing Package## Primary Title[title]## Backup Title A[title]## Backup Title B[title]## Final Description[description]## Hashtags[hashtags on one line or one per line]## Keyword SetPrimary Keyword:Supporting Keywords:## Primary Thumbnail### Concept[concept]### Text Overlay[0–4 words]### Generation Prompt[image-only prompt; reserve negative space; do not render text]## Backup Thumbnail A### Concept[concept]### Text Overlay[0–4 words]### Generation Prompt[prompt]## Backup Thumbnail B### Concept[concept]### Text Overlay[0–4 words]### Generation Prompt[prompt]## Package–Opening Alignment Check- Package Promise:- First-15-Second Proof:- Central Question by 35 Seconds:- Any Minimal Final Correction:Nothing before the first file marker and nothing after the second file.", "=== FILE 1: content.md ===\n## Narration\n[Final English narration]\n=== FILE 2: publishing_package.md ===\n# Publishing Package\n## Primary Title\n[title]\n## Backup Title A\n[title]\n## Backup Title B\n[title]\n## Final Description\n[description]\n## Hashtags\n[hashtags on one line or one per line]\n## Keyword Set\nPrimary Keyword:\nSupporting Keywords:\n## Primary Thumbnail\n### Concept\n[concept]\n### Text Overlay\n[0–4 words]\n### Generation Prompt\n[image-only prompt; reserve negative space; do not render text]\n## Backup Thumbnail A\n### Concept\n[concept]\n### Text Overlay\n[0–4 words]\n### Generation Prompt\n[prompt]\n## Backup Thumbnail B\n### Concept\n[concept]\n### Text Overlay\n[0–4 words]\n### Generation Prompt\n[prompt]\n## Package–Opening Alignment Check\n- Package Promise:\n- First-15-Second Proof:\n- Central Question by 35 Seconds:\n- Any Minimal Final Correction:\nNothing before the first file marker and nothing after the second file."),
            ],
        )
    )


FORMATTERS = {
    "prompt_1_transcript_analysis": _format_prompt_1,
    "prompt_2_historical_research": _format_prompt_2,
    "prompt_3_creative_package": _format_prompt_3,
    "prompt_4_retention_outline": _format_prompt_4,
    "prompt_5_narration_v1": _format_prompt_5,
    "prompt_6_red_team": _format_prompt_6,
    "prompt_7_final_content": _format_prompt_7,
}


def extract_formatted_prompts(path: Path | str) -> dict[str, str]:
    verify_source_document(path)
    raw_prompts = extract_raw_prompt_bodies(path)
    return {step_id: FORMATTERS[step_id](raw_prompts[step_id]) for step_id in FORMATTERS}
