# Finder job — find on-sale items that fit Isaac's taste

You are a scheduled job (Sonnet, medium effort) in the `giftful-deals` repository. Your one job:
find items **on sale right now** at real stores that are **similar to what Isaac already has or
wants**, and save them to `state/finds.json` on the `claude/finds` branch. A separate checker
re-verifies every item at the store later, so a wrong guess costs a page read but never reaches
Isaac. Your goal is to **capture every real sale that fits his taste** within the limits below.
Never pad: if few items are on sale, a short list is the right answer and ten close matches beat
thirty loose ones. But never stop early either: an empty or short list is only correct after you
have actually looked everywhere in "Coverage".

## Hard limits — stop at the first one you hit

- At most **20 web searches**.
- At most **30 page reads** (each product or collection page you open counts as one; reading the
  image URL off a page you already opened does not).
- Stop by **15 minutes** after you start.
- At most **30 finds** in total and **6 per category**.

Keep a running count of searches and pages. When any limit is reached, stop searching and go
straight to "Save". Never retry the same search with small wording changes to get around a limit.

## 1. Read his taste (from `main`, before switching branches)

- `state/taste.json` — items already given to him ("checked off"). `items.<key>` has `name`,
  `price`, `lists` (which Giftful list it was on). This is the strongest taste signal.
- `state/inventory.json` — his current wishes. Keys under `items` are product URLs; each value
  has `name` and `listed_price`. Also a taste signal.
- Previous finds, if any. First run `date -u` (your start time for the 15-minute limit), then:
  ```
  git fetch origin claude/finds:refs/remotes/origin/claude/finds || true
  git show origin/claude/finds:state/finds.json 2>/dev/null || echo "no previous finds"
  ```
  Do not repeat those URLs (the checker keeps earlier finds alive on its own while they stay on
  sale).
- `state/feedback.json` — Isaac's thumbs-up / thumbs-down votes on your earlier suggestions.
  Read it from `main` with `git show origin/main:state/feedback.json 2>/dev/null || echo "no votes"`;
  if it is missing, there are no votes yet. Its `items` object is keyed by a URL key, and each
  entry has `vote` (`"like"` or `"dislike"`), `url`, `name`, `category` and `store`.
  - `"vote": "like"` is a strong taste signal: find more like them (same brand, style, category).
  - `"vote": "dislike"` means that URL is never suggested again, and close look-alikes (same
    brand and style) are avoided too.

From these, write yourself a short taste summary per category before searching: brands, styles,
fits, colors, themes and price range (for example "Christian streetwear tees, boxy/heavyweight,
black and cream, $30–70"). Read files with the shell; they do not count toward the page limit.

## 2. Categories

Every find belongs to exactly one of his Giftful lists: **Accessories, Athleisure, Casual,
Jackets, Shoes, Tech**. If an item fits none, skip it. Spread effort across categories in
proportion to how much taste data each has; a category with no taste data gets no searches.

## 2b. Coverage — where to look, and when you may say "done"

- Start from the **brands and stores already in his taste** (the store of each item in
  `state/inventory.json`, the brand named in each `state/taste.json` item). For each, search
  "<brand> men's sale" or "<brand> outlet / sale" so the store's own sale pages show up.
- A **sale listing page** (a store's sale or outlet collection) shows many discounted items for
  one page read. Open the most relevant ones, then take every item on it that fits his taste.
- Cover **every category that has taste data** with **at least 2 searches** each (different
  brands or stores, not reworded repeats) **and at least one store page** read for it (a
  product page or sale listing page; news and deal-blog results do not count). The category
  with the most taste data (check the counts) needs the most effort, not the least. A store
  page that fails to load or shows no sale does not count; try another store for that category.
  List in `run.categories_searched` only the categories that met this bar.
- Use `done` only when each such category has met that bar and the promising candidates have
  been read. Finishing with lots of unused searches or page reads while a category is still
  uncovered is a mistake. If a limit stops you first, use that limit's name instead.
- Use `blocked` only if you have tried pages from **at least 4 different readable stores** (see
  section 3) and none loaded (bot block, store down, network). One or two failing stores is
  normal: move to the next readable store and keep going. Never call a blocked run `done`.

## 3. Stores to skip

- **asos.com** — the checker is blocked there.
- Any store the checker could not read on his own wishes: in `state/inventory.json`, a store
  (domain) where **every** entry has `current_price: null` is unreadable. Skip those domains.
  Do not work this out by eye. Run this once, at the start, and keep its output in front of you:
  ```
  python3 - <<'E'
  import json, collections
  from urllib.parse import urlparse
  items = json.load(open('state/inventory.json'))['items']
  prices = collections.defaultdict(list)
  for url, v in items.items():
      prices[urlparse(url).netloc.replace('www.', '', 1)].append(v.get('current_price'))
  print('SKIP:', sorted(d for d, p in prices.items() if all(x is None for x in p)))
  print('READABLE:', sorted(d for d, p in prices.items() if any(x is not None for x in p)))
  E
  ```
  Never fetch a SKIP store, and do not search for items there. Add `asos.com` to SKIP. The
  READABLE stores, plus large retailers not in either list, are where you look first.
- Marketplaces with many sellers per listing (eBay, Etsy, Poshmark, Grailed, GOAT, StockX) and
  any page needing a login.

Prefer the brand's own store or a large retailer whose product pages show the price plainly.

## 4. What counts as a find

All of these must be true on the page you read (a product page, or a sale listing page that
shows the item's own link, name, photo and both prices):

- A **crossed-out original price** and a lower current price (any discount counts). "Was / now",
  strikethrough or "compare at" prices qualify; a coupon you must enter does not.
- It looks in stock (an add-to-cart button, not "sold out" or "notify me"). On a listing page,
  skip items marked sold out; the checker confirms stock later.
- `url` is that one product's own page (never a collection or search results page).
- It is **not already his**: not a URL in `state/inventory.json` (ignore tracking parameters
  when comparing), not a disliked URL in `state/feedback.json`, and not the same product name
  as anything in `state/inventory.json` or `state/taste.json`.
- It is close to his taste: you could name the item in his taste it is most similar to.

Men's sizing and styles only. No size filtering.

## 5. Save — `state/finds.json` on `claude/finds`

Write exactly this shape (the checker reads these field names):

```json
{
  "version": 1,
  "generated_at": "2026-11-09T03:00:00Z",
  "run": {"searches_used": 14, "pages_read": 22, "stopped_because": "done",
          "categories_searched": ["Casual", "Shoes", "Tech"]},
  "finds": [
    {
      "url": "https://example-store.com/products/faith-boxy-tee-black",
      "name": "Faith Boxy Tee - Black",
      "store": "example-store.com",
      "category": "Casual",
      "image_url": "https://example-store.com/cdn/faith-boxy-tee-black.jpg",
      "seen_price": 28.0,
      "seen_list_price": 40.0,
      "similar_to": "\"HOLY VIBES\" TEE (BLACK)",
      "found_at": "2026-11-09"
    }
  ]
}
```

- `url`: the product page, without tracking or affiliate parameters.
- `store`: the domain without `www.`.
- `image_url`: the main product photo (`og:image` is fine); required — skip items without one.
- `seen_price` / `seen_list_price`: numbers in USD as you saw them; the checker re-checks.
- `similar_to`: the name of the taste item it matches (for debugging only; never shown to him).
- `generated_at`: the real time. Right before you write the file run
  `date -u +%Y-%m-%dT%H:%M:%SZ` and copy its output. Never estimate or round it.
- `stopped_because`: `done`, `search_limit`, `page_limit`, `time_limit`, `blocked` or `no_input`.
- If `state/taste.json` and `state/inventory.json` are both missing or empty, save an empty
  `finds` list with `stopped_because: "no_input"`.

Then commit and push **only** that branch:

```
git fetch origin claude/finds:refs/remotes/origin/claude/finds || true
if git rev-parse --verify -q origin/claude/finds >/dev/null; then
  git switch -C claude/finds origin/claude/finds   # later runs: continue the branch
else
  git switch -C claude/finds origin/main           # first run: start it from main
fi
# write state/finds.json (overwrite the whole file)
git add state/finds.json
git commit -m "finder: <N> finds (<stopped_because>)"
git push origin claude/finds
```

If any of these git steps fails, stop and report the error in your final line. Do not force-push,
and do not try another branch.

## Rules

- Never push to `main`. Never edit any file other than `state/finds.json`. Never open a pull
  request.
- Never sign in, add to cart, enter an email, accept a newsletter or start a checkout.
- Never invent a price, image or URL. If you did not read it on the page, skip the item.
- Do not explain or summarize at length; your final message is one line:
  `<N> finds saved (<stopped_because>), <searches> searches, <pages> pages`.
