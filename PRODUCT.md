# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
One reader: Isaac, the owner of six public Giftful wish lists. He opens the email and the deals
page mostly on his iPhone, a few times a week, to see what on his lists — and what similar to
what he already has or wants — is on sale right now, then taps through to the store to buy.

## Product Purpose
A personal shopper built on Giftful. It reports price drops, promo codes and restocks on his
Giftful wishes, adds similar on-sale items that are not on his lists (grouped by category, as a
photo grid), and offers a search page that finds on-sale items similar to what he has gotten
and wants. Success: every item shown is a real, current deal he can buy in one tap, and new
finds match his taste closely enough that he acts on them. First full email by 2026-11-13,
ready for Black Friday (2026-11-27).

## Positioning
It knows his actual taste — the items he wishes for and the ones already claimed ("checked off")
on Giftful — and verifies every price at the store itself before showing it. Generic deal
sites can't do either.

## Operating Context
- Email via Resend, Monday and Thursday 7 AM UTC (daily 2026-11-23 to 2026-12-01).
- Static page on GitHub Pages (`docs/index.html`, built by `scraper/html_builder.py`).
- A scheduled Claude job finds new items; the GitHub Actions run price-checks them and sends the email.
- Live search (planned): SerpApi Google Shopping, Gemini ranking, a Vercel function behind a passcode.

## Capabilities and Constraints
- Deal types on wishes: price drop, promo code, back in stock (shown for 2 runs).
- New finds must show a crossed-out store price at **any** discount (no minimum percentage), be
  in stock, and not already be on his lists. They repeat each run until no longer on sale.
- Stores the checker can't read (ASOS behind Akamai) are skipped for new finds.
- **Like / dislike on suggested items** (confirmed requirement, design undecided): each new find
  gets like and dislike controls. Likes teach the finder his taste; dislikes remove that item
  and steer future finds away from it. Where the feedback is stored is open — the page is static
  and the email can't run scripts.
- Free tiers only, no credit card on any service; no single tool may exhaust its own limit
  (SerpApi counter stops at 230 of 250/month). Claude plan usage is fine where it works better.
- Code runs on Python 3.9 (local) and 3.11 (CI).

## Brand Commitments
- Name stays "giftful-deals"; the page link and repo don't change.
- Header uses the real Giftful wordmark (`docs/giftful_logo.png`) linking to his Giftful list,
  with the tagline "Today's deals".
- Wording is plain: "what's on sale, by category". No "you may like" or "because you got X".
- Items from his own lists carry a "Your list" tag.

## Evidence on Hand
- Live Giftful lists (public; claimed items marked `img alt="Claimed"`), current prices and
  inventory in `state/inventory.json`, per-run review log in `state/review_log.json`.
- No testimonials, users or metrics beyond the single owner — never invent any.

## Product Principles
1. Only show deals that are verified at the store right now: real price, in stock, working link.
2. Say what's on sale, by category — no recommendation-speak.
3. Taste comes from his own lists and his likes and dislikes, not from popularity.
4. Stay inside free limits; fail closed rather than run up a bill.
5. Phone first: one tap from the email to the store.
