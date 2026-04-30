from validator import (
    check_identity,
    check_link_integrity,
    check_sold_out,
)


# ---------- check_link_integrity ----------


def test_link_integrity_passes_on_normal_product_page():
    html = """
    <html><head><title>Awesome Widget</title></head>
    <body><h1>Awesome Widget</h1><div class="price">$29.99</div></body>
    </html>
    """
    is_dead, reason = check_link_integrity(html)
    assert is_dead is False
    assert reason is None


def test_link_integrity_flags_page_not_found():
    html = """
    <html><body>
      <h1>Page Not Found</h1>
      <p>The page you are looking for does not exist.</p>
    </body></html>
    """
    is_dead, reason = check_link_integrity(html)
    assert is_dead is True
    assert "page not found" in reason.lower()


def test_link_integrity_flags_no_longer_available():
    html = """
    <html><body>
      <p>The product you are looking for is no longer available.</p>
    </body></html>
    """
    is_dead, reason = check_link_integrity(html)
    assert is_dead is True
    assert "no longer available" in reason.lower()


def test_link_integrity_flags_item_removed():
    html = "<html><body><p>This item has been removed.</p></body></html>"
    is_dead, reason = check_link_integrity(html)
    assert is_dead is True


def test_link_integrity_flags_404():
    html = "<html><body><h1>404 - Not Found</h1></body></html>"
    is_dead, reason = check_link_integrity(html)
    assert is_dead is True


def test_link_integrity_ignores_dead_phrases_inside_normal_content():
    # If a real product page happens to contain "out of stock" in nav
    # (e.g. a sub-link to an OOS variant), don't false-positive on it.
    html = """
    <html><head><title>Cool Sneaker - Brand</title></head>
    <body>
      <h1>Cool Sneaker</h1>
      <div class="price">$120</div>
      <p>Available in 5 colors. Size 10 is currently out of stock; other sizes available.</p>
      <button>Add to Cart</button>
    </body></html>
    """
    is_dead, reason = check_link_integrity(html)
    # Has a clear product name, h1, price, and "Add to Cart" — not a dead page.
    assert is_dead is False


def test_link_integrity_empty_html_is_dead():
    is_dead, reason = check_link_integrity("")
    assert is_dead is True


# ---------- check_identity ----------


def test_identity_matches_when_title_contains_name():
    html = """
    <html><head><title>Cool Sneaker - Big Brand Store</title></head>
    <body><h1>Cool Sneaker</h1></body></html>
    """
    matches, score = check_identity("Cool Sneaker", html)
    assert matches is True
    assert score > 0.5


def test_identity_matches_using_og_title_when_title_missing():
    html = """
    <html><head>
      <meta property="og:title" content="Awesome Widget Pro Edition" />
    </head><body></body></html>
    """
    matches, score = check_identity("Awesome Widget", html)
    assert matches is True


def test_identity_matches_using_h1_when_title_and_og_missing():
    html = "<html><body><h1>Vintage Brown Loafers</h1></body></html>"
    matches, score = check_identity("Vintage Brown Loafers", html)
    assert matches is True


def test_identity_matches_with_minor_word_overlap_threshold():
    # Giftful: "Nike Club Washed Shorts in Brown"
    # Page title: "Nike Club Washed Shorts | Brown | Nike.com"
    html = """
    <html><head><title>Nike Club Washed Shorts | Brown | Nike.com</title></head>
    </html>
    """
    matches, score = check_identity("Nike Club Washed Shorts in Brown", html)
    assert matches is True


def test_identity_rejects_completely_different_product():
    html = """
    <html><head><title>Apple iPhone 15 Pro Max - Apple Store</title></head>
    </html>
    """
    matches, score = check_identity("Vintage Brown Loafers", html)
    assert matches is False
    assert score < 0.5


def test_identity_passes_when_page_has_no_title_or_h1():
    # No title/h1/og means the page didn't really render anything — give
    # benefit of doubt instead of asserting "wrong product."
    html = "<html><body><p>some text</p></body></html>"
    matches, score = check_identity("Cool Sneaker", html)
    assert matches is True


def test_identity_passes_on_empty_html():
    # Empty HTML can't be a "wrong product" claim. Treat as unknown.
    matches, score = check_identity("Cool Sneaker", "")
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_empty_giftful_name():
    # No Giftful name to compare against — can't make a claim either way.
    html = "<html><head><title>x</title></head></html>"
    matches, score = check_identity("", html)
    assert matches is True


def test_identity_passes_on_cloudflare_challenge_page():
    html = """
    <html><head><title>Just a moment...</title></head>
    <body><h1>Checking your browser before accessing</h1>
    <p>Please wait while we verify you are human.</p></body></html>
    """
    matches, score = check_identity("Beats Powerbeats Pro 2 Wireless Earbuds", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_captcha_page():
    html = """
    <html><head><title>Verify</title></head>
    <body>Please complete this captcha to continue.</body></html>
    """
    matches, score = check_identity("Some Real Product Name Here", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_amazon_robot_check_page():
    # Amazon's automated-traffic challenge — common cause of 0.00 score
    # false positives in review_log.json.
    html = """
    <html><head><title>Amazon.com</title></head>
    <body><h1>Robot Check</h1>
    <p>Enter the characters you see below</p>
    <p>Sorry, we just need to make sure you're not a robot.</p>
    <p>To discuss automated access to Amazon data please contact api-services-support@amazon.com.</p>
    </body></html>
    """
    matches, score = check_identity("Beats Powerbeats Pro 2 Wireless Earbuds", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_amazon_type_characters_challenge():
    html = """
    <html><head><title>Amazon.com</title></head>
    <body><p>Type the characters you see in this image.</p></body></html>
    """
    matches, score = check_identity("Real Product Name", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_unusual_traffic_page():
    html = """
    <html><head><title>Sorry...</title></head>
    <body><p>Our systems have detected unusual traffic from your computer network.</p></body></html>
    """
    matches, score = check_identity("Real Product Name", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_amazon_continue_shopping_interstitial():
    # Amazon's soft block: title is "Amazon.com" exactly, no h1, body has
    # "Click the button below to continue shopping". This is what currently
    # leaks past _CHALLENGE_PHRASES because the wording is generic.
    html = """
    <html><head><title>Amazon.com</title></head>
    <body>
      <p>Click the button below to continue shopping</p>
      <a>Continue shopping</a>
      <p>Conditions of Use Privacy Policy © 1996-2025, Amazon.com, Inc.</p>
    </body></html>
    """
    matches, score = check_identity("Ring Battery Doorbell newest model", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_finishline_access_has_been_denied():
    # Finish Line (and other JD properties) shows "Your Access Has Been
    # Denied..." rather than the literal "Access Denied" we already catch.
    html = """
    <html><head><title></title></head>
    <body>
      <h1>Your Access Has Been Denied...</h1>
      <p>Please check back in 15 minutes as this may be temporary.</p>
    </body></html>
    """
    matches, score = check_identity("Men's Birkenstock Essentials Arizona", html)
    assert matches is True
    assert score == 0.0


def test_identity_uses_jsonld_product_name_as_candidate():
    # Some retailers (Shopify) emit a stripped <title> in the requests-based
    # response but a reliable <script type="application/ld+json"> Product.
    # Identity must use that Product.name to match.
    html = """
    <html><head><title>Shop</title></head>
    <body>
      <script type="application/ld+json">
      {"@type":"Product","name":"Second Skin Boxer Brief 8\\" (3-Pack)","offers":{"price":108}}
      </script>
    </body></html>
    """
    matches, score = check_identity('Second Skin Boxer Brief 8" (3-Pack)', html)
    assert matches is True
    assert score >= 0.5


def test_identity_uses_meta_description_as_candidate():
    # Title is > 10 chars and unrelated; only the meta description carries
    # the product name. Without meta-as-candidate, this would fail with
    # score 0.0; with it, it should match.
    html = """
    <html><head>
      <title>Amazon Online Shopping for Electronics Apparel</title>
      <meta name="description" content="WateLves Barefoot Water Shoes for Women and Men, minimalist comfortable design"/>
    </head><body></body></html>
    """
    matches, score = check_identity(
        "WateLves Barefoot Water Shoes Women Men Minimalist Comfortable", html
    )
    assert matches is True


def test_identity_prefix_match_succeeds_when_only_first_tokens_present():
    # Whole-set score is intentionally below 0.5 (candidate has many
    # unrelated tokens diluting it); prefix score should rescue it because
    # the brand + product type at the start of the Giftful name appears
    # verbatim in the candidate.
    html = """
    <html><head>
      <title>Beats Powerbeats Pro at MyShop - everyday low prices on a wide range of electronics from major brands worldwide</title>
    </head></html>
    """
    matches, score = check_identity(
        "Beats Powerbeats Pro 2 Wireless Noise Cancelling Workout Earbuds",
        html,
    )
    assert matches is True


def test_identity_prefix_match_does_not_save_genuinely_wrong_product():
    # Real iPhone page; Giftful item is unrelated. Prefix tokens of giftful
    # name should not appear -> still rejects.
    html = """
    <html><head>
      <title>Apple iPhone 15 Pro Max - 256GB - Apple Store</title>
      <meta property="og:title" content="iPhone 15 Pro Max" />
    </head><body>
      <h1>iPhone 15 Pro Max</h1>
      <button>Add to Cart</button>
      <p>The iPhone 15 Pro Max features a 6.7-inch display.</p>
    </body></html>
    """
    matches, score = check_identity("Vintage Brown Suede Loafers Cowhide", html)
    assert matches is False


def test_identity_passes_on_press_and_hold_challenge():
    # PerimeterX / DataDome flavor used by some retailers (Finish Line uses similar)
    html = """
    <html><head><title>Please verify you are a human</title></head>
    <body><p>Press and hold the button to verify you are human.</p></body></html>
    """
    matches, score = check_identity("Men's Birkenstock Essentials Arizona", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_access_denied_page():
    html = """
    <html><head><title>Access Denied</title></head>
    <body><h1>Access Denied</h1><p>Your request was blocked.</p></body></html>
    """
    matches, score = check_identity("Some Real Product Name Here", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_short_brand_only_title():
    # <title>ASOS</title> is too short to identify the product. Don't claim
    # mismatch — the page didn't really load anything to compare against.
    html = "<html><head><title>ASOS</title></head><body></body></html>"
    matches, score = check_identity("ASOS DESIGN baggy jeans in light wash blue", html)
    assert matches is True
    assert score == 0.0


def test_identity_passes_on_empty_titles_and_no_h1():
    html = "<html><head><title></title></head><body><p>nothing</p></body></html>"
    matches, score = check_identity("Some Product", html)
    assert matches is True
    assert score == 0.0


def test_identity_still_rejects_genuinely_different_product():
    # Long, well-formed product page for an iPhone — Giftful name is for
    # a totally unrelated item. This SHOULD be flagged as mismatch.
    html = """
    <html><head>
      <title>Apple iPhone 15 Pro Max - 256GB - Apple Store</title>
      <meta property="og:title" content="iPhone 15 Pro Max" />
    </head><body>
      <h1>iPhone 15 Pro Max</h1>
      <div class="price">$1199</div>
      <button>Add to Cart</button>
      <p>The iPhone 15 Pro Max features a 6.7-inch display with ProMotion technology.</p>
    </body></html>
    """
    matches, score = check_identity("Vintage Brown Suede Loafers", html)
    assert matches is False
    assert score < 0.5


# ---------- check_sold_out ----------


def test_sold_out_via_schema_outofstock():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"X","offers":{"availability":"https://schema.org/OutOfStock","price":"99"}}
    </script>
    </head></html>
    """
    assert check_sold_out(html) is True


def test_sold_out_via_schema_soldout():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","offers":{"availability":"SoldOut"}}
    </script></head></html>
    """
    assert check_sold_out(html) is True


def test_sold_out_via_in_stock_schema_returns_false():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","offers":{"availability":"https://schema.org/InStock","price":"99"}}
    </script></head></html>
    """
    assert check_sold_out(html) is False


def test_sold_out_via_visible_text():
    html = """
    <html><body>
      <h1>Cool Sneaker</h1>
      <div class="price">$99</div>
      <button class="cta" disabled>Sold Out</button>
    </body></html>
    """
    assert check_sold_out(html) is True


def test_sold_out_returns_false_for_normal_page():
    html = """
    <html><body>
      <h1>Cool Sneaker</h1>
      <div class="price">$99</div>
      <button>Add to Cart</button>
    </body></html>
    """
    assert check_sold_out(html) is False


def test_sold_out_ignores_phrase_in_unrelated_text():
    # "out of stock" appears in a customer review, not as the page state
    html = """
    <html><body>
      <h1>Widget</h1>
      <div class="price">$50</div>
      <button>Add to Cart</button>
      <div class="review">"Was sold out for weeks but I finally grabbed one!"</div>
    </body></html>
    """
    # Review text shouldn't fail the page; require a stronger signal
    assert check_sold_out(html) is False


def test_sold_out_handles_empty_html():
    assert check_sold_out("") is False
