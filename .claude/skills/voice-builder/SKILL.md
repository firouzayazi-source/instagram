---
name: voice-builder
description: >
  Build the Stock Land voice profile (how the page and its owner write) from a short interview plus 3 to 5 real
  samples: past captions, stories, DM replies the owner liked. Use when the user wants Instagram posts, stories,
  captions or bot replies to sound like Stock Land instead of generic AI, or says «لحن پیج رو یاد بگیر»،
  «مثل خودم بنویس»، «صدای برند», "build my voice", "learn my voice". Produces docs/voice/about.md and
  docs/voice/voice.md, which every later content draft reads first.
---

# Voice Builder (Stock Land)

Adapted from charlie947/social-media-skills `voice-builder` (MIT, see LICENSE). Changes: Persian and Instagram
instead of LinkedIn, files under `docs/voice/` instead of the repo root, no borrowed starter samples, and the
project's CLAUDE.md rules take precedence over everything here.

## Rules that never bend
- Work only from what the owner says and the samples they give. Never invent a fact, price, offer, address,
  installment term, customer story or metric. Business facts come from the owner or the panel's knowledge base.
- Customer DM text is private: if a sample is a DM reply, remove names, phone numbers and usernames before
  quoting it in any file. Never commit raw customer messages.
- Drafting and saving never authorise publishing. Nothing goes to the page without the owner's explicit approval
  and the publish time they choose.
- Ask questions and report in Persian. Write the profile files in Persian.

## Step 1. Short interview (Persian, one batch of at most 4 questions, then a second batch)
Batch 1:
1. مخاطب اصلی پیج کیست؟ (مثلاً خریدار اولین آیفون، خریدار اقساطی، کسی که گوشی کارکرده‌ی سالم می‌خواهد)
2. سه تا پنج موضوعی که پیج باید با آن‌ها شناخته شود؟
3. لحن: خودمانی و گرم، رسمی و مطمئن، شوخ، یا ترکیبی؟
4. حرف متفاوت استوک‌لند چیست که بقیه نمی‌گویند؟
Batch 2:
5. مخاطب با دیدن پیج باید چه فکری کند؟ (قابل اعتماد، به‌صرفه، صادق…)
6. چه چیزی هرگز نوشته نمی‌شود؟ (مثلاً نام رقیب، قول قیمت بدون موجودی، اغراق)
If an answer is missing, ask that one question once more in chat, then continue.

## Step 2. Write docs/voice/about.md (under 300 words)
Sections: مخاطب، موضوع‌های اصلی، حرف متفاوت، قول برند، ممنوع‌ها. Every line must be something a later draft
would actually use.

## Step 3. Ask for samples
Ask for 3 to 5 pieces the owner considers "ours": captions or stories that did well, or replies they liked.
Minimum 3; ask for more if fewer. Do not use anyone else's writing as a stand-in.

## Step 4. Analyse
Look for patterns across all samples, not one-off quirks:
- sentence length, paragraph rhythm, line breaks
- how they open (question, number, story, direct offer) and how they close (call to DM, «اسم مدل رو بفرستید»…)
- tone, recurring words and phrases, emoji use and how much
- what is consistently absent (constructions, words, punctuation). Mark absences as provisional with counts
  ("in 0 of 4 samples"); only the owner's explicit rules are permanent bans.
If samples contradict each other, write the contradiction down instead of smoothing it over.

## Step 5. Write docs/voice/voice.md (under 500 words)
Sections: کلیِ لحن، ویژگی‌های همیشگی و هرگز، ریتم جمله، شروع‌ها (با یک نمونه)، پایان و دعوت به پیام،
واژه‌ها و عبارت‌های امضادار، ممنوع‌ها (صریح صاحب پیج)، نبودها (موقت، با شمارش).
Fill every section from the samples; if a pattern is not present, say so.

## Step 6. Hand off
Tell the owner in Persian that the two files are in `docs/voice/`, that they can edit them anytime, and that
every content draft from now on reads them first and then goes through the `humanizer` skill before it is shown.
Commit the two files (they hold no customer data) following the repo's daily STATUS/CHANGELOG rule.
