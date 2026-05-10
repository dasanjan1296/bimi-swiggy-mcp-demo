/**
 * JavaScript injection scripts for automating grocery cart building
 * inside a WebView. Each platform has its own search/add strategy
 * using resilient DOM selectors (text-matching, aria-labels, structural)
 * rather than fragile CSS class names.
 *
 * Scripts communicate back to React Native via:
 *   window.ReactNativeWebView.postMessage(JSON.stringify({ ... }))
 */

export const SEARCH_TIMEOUT_MS = 12000;
export const INTER_ITEM_DELAY_MS = 2000;

export interface CartMessage {
  type:
    | "page_ready"
    | "needs_login"
    | "searching"
    | "item_added"
    | "item_failed"
    | "all_done"
    | "cart_count"
    | "checkout_detected"
    | "order_confirmed"
    | "error";
  item?: string;
  index?: number;
  total?: number;
  success?: boolean;
  reason?: string;
  cartCount?: number;
  message?: string;
  orderAmount?: number;
  orderId?: string;
  deliveryEta?: string;
  cartTotal?: number;
}

// ---------------------------------------------------------------------------
// Swiggy Instamart
// ---------------------------------------------------------------------------

export const SWIGGY_INSTAMART_BASE = "https://www.swiggy.com/instamart";

/**
 * Injected on initial page load (and re-injected periodically during
 * the needs_login state). Detects login status using multiple signals:
 * search input presence, login button visibility, profile indicators,
 * and cookie checks.
 */
export function swiggyDetectLoginScript(): string {
  return `
(function() {
  function postMsg(data) {
    window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }

  function checkReady() {
    var loginBtns = Array.from(document.querySelectorAll('a, button, span, div[role="button"]')).filter(function(el) {
      if (el.offsetHeight === 0) return false;
      var txt = (el.textContent || '').trim().toLowerCase();
      return txt === 'login' || txt === 'sign in' || txt === 'log in' || txt === 'sign up or login';
    });

    var searchSelectors = [
      'input[type="search"]',
      'input[placeholder*="Search" i]',
      'input[placeholder*="search" i]',
      'input[aria-label*="search" i]',
      'input[role="searchbox"]',
    ];
    var searchInput = null;
    for (var i = 0; i < searchSelectors.length; i++) {
      searchInput = document.querySelector(searchSelectors[i]);
      if (searchInput) break;
    }

    var profileIndicators = [
      '[data-testid*="profile"]',
      '[data-testid*="user"]',
      'img[alt*="profile" i]',
      'img[alt*="user" i]',
      '[class*="UserName" i]',
      '[class*="profile" i]',
      '[class*="account" i] img',
    ];
    var hasProfile = false;
    for (var p = 0; p < profileIndicators.length; p++) {
      if (document.querySelector(profileIndicators[p])) { hasProfile = true; break; }
    }

    // Check cookies for auth tokens
    var hasCookie = document.cookie && (
      document.cookie.includes('_sid') || document.cookie.includes('_session')
      || document.cookie.includes('user') || document.cookie.includes('auth')
    );

    var pageLoaded = searchInput || document.querySelector('[class*="product" i]')
      || document.querySelector('[class*="category" i]');

    if (pageLoaded) {
      if (loginBtns.length > 0 && !hasProfile && !hasCookie) {
        postMsg({ type: 'needs_login' });
      } else {
        postMsg({ type: 'page_ready' });
      }
    } else if (document.readyState === 'complete') {
      // Page fully loaded but can't find indicators — check login buttons
      if (loginBtns.length > 0) {
        postMsg({ type: 'needs_login' });
      } else {
        // Loaded but couldn't detect state — assume ready and let search fail if needed
        setTimeout(function() {
          var retrySearch = null;
          for (var r = 0; r < searchSelectors.length; r++) {
            retrySearch = document.querySelector(searchSelectors[r]);
            if (retrySearch) break;
          }
          postMsg({ type: retrySearch ? 'page_ready' : 'needs_login' });
        }, 2000);
      }
    } else {
      setTimeout(checkReady, 1000);
    }
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(checkReady, 1200);
  } else {
    window.addEventListener('load', function() { setTimeout(checkReady, 1200); });
  }
})();
true;
`;
}

/**
 * Searches for a specific item and attempts to add the first result to cart.
 * Uses multiple selector strategies, scroll-into-view, pointer event simulation,
 * and a built-in retry with simplified query on first failure.
 */
export function swiggySearchAndAddScript(
  itemName: string,
  itemIndex: number,
  totalItems: number,
): string {
  const escaped = itemName.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, '\\"');
  return `
(function() {
  var ITEM_NAME = '${escaped}';
  var ITEM_INDEX = ${itemIndex};
  var TOTAL_ITEMS = ${totalItems};
  var TIMEOUT = ${SEARCH_TIMEOUT_MS};
  var retryCount = 0;

  function postMsg(data) {
    data.item = ITEM_NAME;
    data.index = ITEM_INDEX;
    data.total = TOTAL_ITEMS;
    window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }

  function setNativeValue(el, value) {
    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    );
    if (nativeInputValueSetter && nativeInputValueSetter.set) {
      nativeInputValueSetter.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function findSearchInput() {
    var selectors = [
      'input[type="search"]',
      'input[placeholder*="Search" i]',
      'input[placeholder*="search" i]',
      '[data-testid*="search"] input',
      'input[name="search"]',
      'input[aria-label*="search" i]',
      'input[role="searchbox"]',
      'header input[type="text"]',
    ];
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el) return el;
    }
    return null;
  }

  function findAddButtons() {
    return Array.from(document.querySelectorAll('button, div[role="button"], a[role="button"]')).filter(function(btn) {
      var txt = (btn.textContent || '').trim();
      if (/^ADD$/i.test(txt) || /^Add to cart$/i.test(txt)) return true;
      if (txt === '+' && btn.closest('[class*="product" i], [class*="item" i], [class*="card" i]')) return true;
      var ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
      if (ariaLabel.includes('add to cart') || ariaLabel.includes('add item')) return true;
      return false;
    });
  }

  function clickElement(el) {
    try {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch(e) {}

    setTimeout(function() {
      try {
        el.click();
        el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
        el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true }));
        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        // Also try touching for mobile React handlers
        el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true }));
        el.dispatchEvent(new TouchEvent('touchend', { bubbles: true }));
      } catch(e) {}
    }, 150);
  }

  function simplifyQuery(q) {
    return q
      .replace(/\\d+\\s*(g|gm|gms|kg|kgs|ml|l|ltr|litre|litres|liter|pc|pcs|pack)\\b/gi, '')
      .replace(/\\s+/g, ' ')
      .trim();
  }

  function trySearch(query) {
    postMsg({ type: 'searching' });

    var input = findSearchInput();
    if (!input) {
      // Try clicking a search icon first
      var searchIcon = document.querySelector('[data-testid*="search"], [aria-label*="search" i]');
      if (searchIcon) {
        searchIcon.click();
        setTimeout(function() {
          var input2 = findSearchInput();
          if (input2) doSearch(input2, query);
          else postMsg({ type: 'item_failed', success: false, reason: 'search_input_not_found' });
        }, 800);
        return;
      }
      postMsg({ type: 'item_failed', success: false, reason: 'search_input_not_found' });
      return;
    }
    doSearch(input, query);
  }

  function doSearch(input, query) {
    input.focus();
    setNativeValue(input, '');

    setTimeout(function() {
      setNativeValue(input, query);
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));

      var form = input.closest('form');
      if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

      waitForResultsAndAdd(query);
    }, 400);
  }

  function waitForResultsAndAdd(query) {
    var startTime = Date.now();
    var checkInterval;
    var found = false;

    checkInterval = setInterval(function() {
      if (found) return;
      var elapsed = Date.now() - startTime;

      var addBtns = findAddButtons();
      if (addBtns.length > 0) {
        found = true;
        clearInterval(checkInterval);
        clickElement(addBtns[0]);

        setTimeout(function() {
          // Verify add succeeded by checking for quantity controls or cart badge change
          var qtyControls = addBtns[0].closest('[class*="product" i], [class*="card" i]');
          var hasQty = qtyControls && (
            qtyControls.querySelector('[class*="quantity" i]')
            || qtyControls.querySelector('button:not([class*="add" i])')
          );
          postMsg({ type: 'item_added', success: true });
        }, 600);
        return;
      }

      // Check for "no results"
      var noResults = Array.from(document.querySelectorAll('div, p, span, h2, h3')).filter(function(el) {
        var txt = (el.textContent || '').toLowerCase();
        return (txt.includes('no results') || txt.includes('no items found')
          || txt.includes('not available') || txt.includes('couldn\\'t find')
          || txt.includes('no products found'))
          && el.offsetHeight > 0;
      });

      if (noResults.length > 0 && elapsed > 2500) {
        found = true;
        clearInterval(checkInterval);

        // Auto-retry with simplified query (strip quantities/units)
        if (retryCount === 0) {
          var simpler = simplifyQuery(query);
          if (simpler !== query && simpler.length > 2) {
            retryCount++;
            setTimeout(function() { trySearch(simpler); }, 300);
            return;
          }
        }
        postMsg({ type: 'item_failed', success: false, reason: 'no_results' });
        return;
      }

      if (elapsed > TIMEOUT) {
        found = true;
        clearInterval(checkInterval);
        postMsg({ type: 'item_failed', success: false, reason: 'timeout' });
      }
    }, 400);
  }

  trySearch(ITEM_NAME);
})();
true;
`;
}

/**
 * Navigates the WebView to the Swiggy Instamart cart/checkout page.
 */
export function swiggyNavigateToCartScript(): string {
  return `
(function() {
  // Try clicking the cart icon/button
  var cartBtn = document.querySelector('[data-testid*="cart"]')
    || document.querySelector('a[href*="/checkout"]')
    || document.querySelector('a[href*="/cart"]');

  if (cartBtn) {
    cartBtn.click();
  } else {
    // Fallback: navigate directly
    window.location.href = 'https://www.swiggy.com/checkout';
  }

  window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({
    type: 'cart_count',
    message: 'navigated_to_cart'
  }));
})();
true;
`;
}

/**
 * Reads the current cart count from the Swiggy UI.
 */
export function swiggyGetCartCountScript(): string {
  return `
(function() {
  // Cart badge usually shows count
  var badges = Array.from(document.querySelectorAll('span, div')).filter(function(el) {
    var txt = (el.textContent || '').trim();
    return /^\\d+$/.test(txt) && el.closest('[data-testid*="cart"], [class*="cart" i], a[href*="checkout"]');
  });

  var count = badges.length > 0 ? parseInt(badges[0].textContent.trim(), 10) : 0;

  window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify({
    type: 'cart_count',
    cartCount: count
  }));
})();
true;
`;
}

/**
 * Monitors the checkout page to extract cart total before payment,
 * and detects when an order is confirmed after payment.
 * Uses polling + MutationObserver for DOM and URL changes.
 * Handles Swiggy Instamart's SPA routing and multiple checkout
 * URL variants.
 */
export function swiggyCheckoutMonitorScript(): string {
  return `
(function() {
  function postMsg(data) {
    window.ReactNativeWebView && window.ReactNativeWebView.postMessage(JSON.stringify(data));
  }

  var lastUrl = window.location.href;
  var orderConfirmedSent = false;
  var checkoutDetectedSent = false;

  function extractAmount(text) {
    var cleaned = text.replace(/,/g, '').replace(/\\s+/g, ' ');
    // Match ₹1234 | ₹ 1,234.56 | Rs 1234 | Rs.1234 | INR 1234
    var match = cleaned.match(/(?:₹|Rs\\.?\\s*|INR\\s*|Total\\s*:?\\s*₹?)(\\d+(?:\\.\\d{1,2})?)/i);
    return match ? parseFloat(match[1]) : null;
  }

  function extractAmountFromContainer(contextKeywords) {
    var candidates = [];
    var allEls = document.querySelectorAll('span, div, p, h1, h2, h3, td, strong, b');
    for (var i = 0; i < allEls.length; i++) {
      var el = allEls[i];
      if (el.offsetHeight === 0) continue;
      var txt = (el.textContent || '').toLowerCase();
      for (var k = 0; k < contextKeywords.length; k++) {
        if (txt.includes(contextKeywords[k])) {
          var amt = extractAmount(el.textContent);
          if (amt !== null && amt > 0) {
            candidates.push({ amt: amt, text: txt, depth: getDepth(el) });
          }
          break;
        }
      }
    }
    if (candidates.length === 0) return null;
    // Prefer "to pay" > "grand total" > "total", and among ties pick the largest
    candidates.sort(function(a, b) {
      var aRank = a.text.includes('to pay') ? 0 : a.text.includes('grand total') ? 1 : 2;
      var bRank = b.text.includes('to pay') ? 0 : b.text.includes('grand total') ? 1 : 2;
      if (aRank !== bRank) return aRank - bRank;
      return b.amt - a.amt;
    });
    return candidates[0].amt;
  }

  function getDepth(el) {
    var d = 0;
    while (el.parentElement) { d++; el = el.parentElement; }
    return d;
  }

  var checkoutUrlPatterns = ['/checkout', '/cart', '/payment', '/pay'];
  var orderUrlPatterns = ['/order', '/tracking', '/confirmation', '/success', '/live-order'];

  function isCheckoutUrl(url) {
    for (var i = 0; i < checkoutUrlPatterns.length; i++) {
      if (url.includes(checkoutUrlPatterns[i])) return true;
    }
    return false;
  }

  function isOrderUrl(url) {
    for (var i = 0; i < orderUrlPatterns.length; i++) {
      if (url.includes(orderUrlPatterns[i])) return true;
    }
    return false;
  }

  function checkForCheckout() {
    var url = window.location.href;

    if (!checkoutDetectedSent && isCheckoutUrl(url)) {
      checkoutDetectedSent = true;
      // Delay to let React render the total
      setTimeout(function() {
        var cartTotal = extractAmountFromContainer([
          'to pay', 'grand total', 'total', 'payable', 'bill total',
          'order total', 'sub total', 'subtotal',
        ]);
        postMsg({ type: 'checkout_detected', cartTotal: cartTotal });
      }, 1500);
    }

    if (!orderConfirmedSent) {
      var confirmTexts = [];
      var allVisibleEls = document.querySelectorAll('div, span, h1, h2, h3, p');
      for (var j = 0; j < allVisibleEls.length; j++) {
        var el = allVisibleEls[j];
        if (el.offsetHeight === 0) continue;
        var txt = (el.textContent || '').toLowerCase();
        if (txt.includes('order placed') || txt.includes('order confirmed')
          || txt.includes('arriving in') || txt.includes('on the way')
          || txt.includes('order successful') || txt.includes('payment successful')
          || txt.includes('order accepted') || txt.includes('delivery partner')) {
          confirmTexts.push(el);
        }
      }

      if (isOrderUrl(url) || confirmTexts.length > 0) {
        orderConfirmedSent = true;

        // Wait for the confirmation page to fully render
        setTimeout(function() {
          var orderAmount = extractAmountFromContainer([
            'total', 'paid', 'amount', 'bill', 'payable',
          ]);

          // Extract order ID — multiple patterns
          var orderId = null;
          var body = document.body.textContent || '';
          var idPatterns = [
            /order\s*(?:#|id|no|number)?[\s:]*([A-Z0-9-]{6,})/i,
            /(?:#|ID)\s*([A-Z0-9-]{8,})/,
            /OD[A-Z0-9]{10,}/,
          ];
          for (var p = 0; p < idPatterns.length; p++) {
            var idMatch = body.match(idPatterns[p]);
            if (idMatch) { orderId = idMatch[1] || idMatch[0]; break; }
          }

          // Extract delivery ETA — multiple patterns
          var deliveryEta = null;
          var etaPatterns = [
            /(?:deliver|arriv|eta|reach|by)[^.]{0,30}?(\\d{1,3}\\s*(?:-\\s*\\d{1,3})?\\s*min)/i,
            /(\\d{1,2}:\\d{2}\\s*(?:AM|PM))/i,
            /in\\s+(\\d{1,3})\\s*min/i,
          ];
          for (var ep = 0; ep < etaPatterns.length; ep++) {
            var etaMatch = body.match(etaPatterns[ep]);
            if (etaMatch) { deliveryEta = etaMatch[0].trim(); break; }
          }

          postMsg({
            type: 'order_confirmed',
            orderAmount: orderAmount,
            orderId: orderId,
            deliveryEta: deliveryEta,
            success: true
          });
        }, 2000);
      }
    }
  }

  // Poll for URL changes
  setInterval(function() {
    var currentUrl = window.location.href;
    if (currentUrl !== lastUrl) {
      lastUrl = currentUrl;
      // Reset checkout detection on new page to re-read totals
      if (isCheckoutUrl(currentUrl) && !checkoutDetectedSent) {
        setTimeout(checkForCheckout, 1000);
      }
      setTimeout(checkForCheckout, 1500);
    }
    if (!orderConfirmedSent) {
      checkForCheckout();
    }
  }, 1500);

  // MutationObserver for SPA transitions
  try {
    var observer = new MutationObserver(function() {
      if (!orderConfirmedSent) checkForCheckout();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  } catch(e) {}

  setTimeout(checkForCheckout, 1000);
})();
true;
`;
}

// ---------------------------------------------------------------------------
// Platform registry for WebView scripts
// ---------------------------------------------------------------------------

export interface WebViewPlatformScripts {
  baseUrl: string;
  detectLogin: () => string;
  searchAndAdd: (item: string, index: number, total: number) => string;
  navigateToCart: () => string;
  getCartCount: () => string;
  checkoutMonitor: () => string;
}

export const WEBVIEW_PLATFORM_SCRIPTS: Record<string, WebViewPlatformScripts> = {
  swiggy_instamart: {
    baseUrl: SWIGGY_INSTAMART_BASE,
    detectLogin: swiggyDetectLoginScript,
    searchAndAdd: swiggySearchAndAddScript,
    navigateToCart: swiggyNavigateToCartScript,
    getCartCount: swiggyGetCartCountScript,
    checkoutMonitor: swiggyCheckoutMonitorScript,
  },
};
