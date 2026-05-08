# Article Cadence

Founder testimony on 2026-05-07 identified the generated publications cadence
as too frequent: essays and memos were appearing three or four times per day.
The regular publication generator is therefore capped at one public article per
rolling seven-day window.

The default cap is `DEFAULT_WEEKLY_ARTICLE_CAP = 1`. Operators can override it
with `NOOSPHERE_ARTICLES_WEEKLY_CAP`, which must be an integer greater than or
equal to zero. `NOOSPHERE_ARTICLES_WEEKLY_CAP=0` disables article generation
entirely. Negative values are ignored and fall back to the default.

Correction articles are an exception to weekly exhaustion: when a cited source
is revoked or corrected inside the 24-hour correction window, the correction can
publish even if the regular weekly article slot has already been used. This
exception does not override `NOOSPHERE_ARTICLES_WEEKLY_CAP=0`; that setting
turns all article generation off.
