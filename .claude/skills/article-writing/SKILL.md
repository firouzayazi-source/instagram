---
name: article-writing
description: >
  Structured co-writing of long Persian texts for Stock Land: website articles, buying guides, long captions,
  carousel scripts, FAQs and project docs. Gathers context first, builds the outline section by section with the
  owner, drafts, then tests the draft with a fresh reader (sub-agent) before handing it over. Use when the user
  says «مقاله بنویس»، «راهنمای خرید»، «متن بلند»، «کپشن طولانی»، «سند»، "write an article", "draft a guide".
---

# Article writing (Stock Land)

Project-specific workflow written for this repo. The idea of a three-stage co-writing loop with reader testing is
inspired by Anthropic's public `doc-coauthoring` example; no text is copied from it. The project's CLAUDE.md
always takes precedence.

## Rules that never bend
- Never invent a business fact: price, stock, installment terms, address, phone, warranty, hours, founder,
  statistics. Facts come from the owner, the panel knowledge base (`tgbot` sections, `ai_settings`) or a source
  the owner approves. When a fact is missing, ask; don't fill the gap.
- Contact number is always `09127488434` written without spaces. Installment wording follows the approved
  section text (the cash/installment difference is mentioned, never itemised).
- Customer messages are private: no names, numbers or usernames from DMs in any draft or file.
- Drafting never authorises publishing. Nothing goes to the site or the page without explicit approval and the
  time the owner chooses.
- Ask and report in Persian. Commands, if any, go in separate code blocks.

## Stage 1. Context (short)
Ask, in one message, only what is not already known:
1. نوع متن و جای انتشار (سایت، کپشن، کاروسل، سند داخلی)؟
2. خواننده کیست و بعد از خواندن باید چه کار کند (بپرسد، بخرد، ذخیره کند)؟
3. حقیقت‌ها و عددهایی که باید بیاید، و چیزهایی که نباید گفته شود؟
4. طول تقریبی و نمونه‌ی متنی که می‌پسندند؟
Read `docs/voice/voice.md` and `docs/voice/about.md` if they exist. Let the owner dump notes in any order.

## Stage 2. Outline, then sections
1. Propose an outline: title options plus 4 to 8 section headings, each with one line on what it answers.
2. Get approval or changes, then draft one section at a time. For each section list what it needs, draft it,
   take the owner's edits, move on. Keep a running list of open questions instead of guessing.
3. For Instagram: hook line first (visible before «…بیشتر»), one idea per carousel slide, one clear call to
   action at the end («اسم مدلت رو دایرکت کن»).

## Stage 3. Reader test (before handing over)
1. Write 5 to 8 questions a real reader would ask after reading (e.g. «پیش‌پرداخت چقدره؟»، «گارانتی داره؟»).
2. Give a fresh sub-agent only the draft and the questions, nothing from this conversation. Ask it to answer each
   question from the text alone and to list anything ambiguous, contradictory, or assumed.
3. Fix every gap it finds (or ask the owner for the missing fact) and repeat until the answers are correct.
4. Run the final text through the `humanizer` skill so it does not read as machine-written, without adding facts.

## Stage 4. Hand over
Give the final text, the reader-test result in one or two lines, and the list of facts the owner should
double-check. Save drafts the owner wants to keep under `docs/content/` (no customer data), and follow the
repo's daily STATUS/CHANGELOG rule when committing.
