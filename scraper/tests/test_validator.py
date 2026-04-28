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


def test_identity_rejects_when_page_has_no_title_or_h1():
    html = "<html><body><p>some text</p></body></html>"
    matches, score = check_identity("Cool Sneaker", html)
    assert matches is False


def test_identity_handles_empty_html():
    matches, score = check_identity("Cool Sneaker", "")
    assert matches is False
    assert score == 0.0


def test_identity_handles_empty_giftful_name():
    html = "<html><head><title>x</title></head></html>"
    matches, score = check_identity("", html)
    assert matches is False


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
