---
name: answer-quality
description: Improves how well the Stockland support bot understands and answers customers, from real unanswered messages. Use whenever the user asks to make the bot's answers smarter or stronger, to cover questions it didn't understand, to review unanswered questions (سؤال‌های بی‌پاسخ), to add words or phrasings, or says things like «ربات نفهمید»، «پاسخ‌گویی رو قوی کن»، «دیکشنری رو بیشتر کن» — even if they don't name this skill.
---

# Answer quality loop

The bot understands messages with its own engine (`brain.py` + intents in `faq.json` + the product search in
`catalog.py`), no external AI. Improving it is a loop over **real customer messages**: measure, fix the
cause of each miss, lock the fix in with a regression phrase, measure again. The checker runs the bot's
real `assistant_reply` path offline, so a green run means the live bot behaves the same way.

CLAUDE.md rules win over this skill (Persian reports, commands in their own code box, daily status file).

## Tools

- `python3 tools/answer_check.py` — the fixed regression set `tests/phrases.tsv` (line: `جمله<TAB>مسیر`,
  alternatives with `|`, a leading `!` marks a known failure). Exit code 1 on any new failure.
- `python3 tools/answer_check.py scan FILE [--faq faq.json] [--catalog catalog.json]` — coverage of real
  messages (`unmatched.json`, `[[text,count],…]`, or one message per line), grouped by route.
- Routes: an intent id (`i_hours`…), `catalog`, `smalltalk`, `dym` (asked "did you mean…?"),
  `human` (handed to a colleague on purpose, e.g. complaint), `unknown`, `timeout`/`error:*` (a bug — fix first).

## 1. Baseline

Run the regression set. It must be green before you change anything; otherwise fix that first.

## 2. Collect real data from the server

Customer text is private: keep it in `/tmp/aq/`, never commit it. Ask the user to run these on the server
(each in its own code box, nothing else inside) and paste the output; save each to `/tmp/aq/`:

```
python3 -c "import json;d=json.load(open('/opt/telegram-bot/unmatched.json'));print(json.dumps([[u['text'],u.get('count',1)] for u in d],ensure_ascii=False))"
```

```
cat /opt/telegram-bot/faq.json
```

`faq.json` holds the live intents, including the admin's own edits in the panel, so scanning against it
matches production. The bot's `/demand` report (in Telegram) adds product searches that found nothing.

## 3. Scan and classify every miss

`scan /tmp/aq/unmatched.json --faq /tmp/aq/faq.json` → note the coverage % (the "before" number).
For each `unknown`/`dym` message, decide the cause, because each has a different fix:

| Cause | Example | Fix |
|---|---|---|
| Vocabulary: a variant, misspelling, colloquial form | «ادرستون کجاس» | `brain.SYNONYMS`; for products `catalog.py` (`COLORS`, `ACCESSORY`, `VARIANTS`, `FILLER`) |
| Phrasing: the topic exists, the sentence is new | «کی بازید» | add to that intent's `examples`/`keys` in `DEFAULT_INTENTS` (bot.py) |
| Missing topic | «تعمیر هم دارید؟» | new intent in `DEFAULT_INTENTS` — see below |
| Wrong intent wins | «ممنون از راهنماییتون» → help | narrow the stealing key or fix the smalltalk/route rule |
| Not answerable by a bot | order status, a specific person | leave to a colleague; that is a correct outcome |

**Shipping intent changes to the server.** Intents live in the server's `faq.json`, not in code. Edits to
`DEFAULT_INTENTS` reach it only when you **increase `SEED_VERSION`**: on start, `seed_intents` adds new
intents and `_upgrade_intent` merges new keys/examples into existing ones while keeping anything the
admin changed. Forgetting the bump means the fix works in the checker but never goes live.

**New intents carry business facts.** Draft the answer text, but never invent prices, policies, warranty
terms or hours — show the drafted answers to the user and get their approval before committing.

Prefer the narrowest fix: one specific example sentence beats a short generic key, because short keys
(«هست»، «دارید») collide with other intents and regress unrelated phrases.

## 4. Lock fixes in

For every message you fixed, add a line to `tests/phrases.tsv` with the expected route (rewrite it
without names, phone numbers or other personal details). For a miss you deliberately leave, add it with
`!` so it stays visible. When the checker prints «درست شد (! را بردارید)», remove the `!`.

## 5. Verify

Run the regression set (must be green), then rescan the real messages for the "after" number.

## 6. Report, record, ship

Report to the user in Persian:

```
پوشش پیام‌های واقعی: قبل X٪ → بعد Y٪ (N پیام)
درست شد: … (به تفکیک: دیکشنری / جمله‌ی تازه / نیت تازه / تداخل)
منتظر تأیید شما: متن جواب نیت‌های تازه
عمداً به همکار: …
هنوز نفهمیده: … و چرا
```

Then update `وضعیت-پروژه.md`, commit and push, and give the deploy command in its own code box.
