#!/usr/bin/env python3
"""Build the Mineshop.eu product feed for ChatGPT (OpenAI Business Hub, hosted-URL import).

Source: the shop's public Google Merchant feed, https://mineshop.eu/google-shopping-feed.xml
Prices: the shop's ex-VAT EUR prices, unchanged (owner decision, 2026-11-11).
Scope: in-stock / pre-order computer hardware only. OpenAI's Commerce Policies do not allow
crypto-mining products, so ASIC miners, mining rigs, frames, boards, PSUs, software and other
mining accessories are left out.

Usage: build_feed.py --out DIR [--source URL_OR_PATH] [--min-items N]
Writes DIR/mineshop-openai.jsonl and DIR/summary.json. Exits non-zero (keeping the last good
deployment) when the source is unreadable or yields fewer than --min-items products.
"""
import argparse, datetime, html, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal
from html.parser import HTMLParser

G = '{http://base.google.com/ns/1.0}'
SOURCE = 'https://mineshop.eu/google-shopping-feed.xml'
SELLER = 'Mineshop.eu'
SELLER_URL = 'https://mineshop.eu'
RETURN_POLICY = 'https://mineshop.eu/page/return-policy'
FEED_FILE = 'mineshop-openai.jsonl'

MINING = re.compile(r"""\b(
    asic|miners?|mining|antminer|whatsminer|avalon|canaan|bitmain|microbt|bitaxe|nerd\w*axe|nerdminer|
    iceriver|goldshell|elphapex|volcminer|innosilicon|ibelink|jasminer|bitdeer|sealminer|fluminer|magicminer|
    netpeer|lucky\s?miner|bitchimney|heatbit|hammer|braiins|hiveos|simplemining|nicehash|
    hashrate|hash\s?board|hashboard|th/s|gh/s|mh/s|kh/s|h/s|
    bitcoin|btc|ltc|doge|kaspa|kas|alephium|alph|zcash|monero|xmr|ethereum|eth|crypto\w*|chia|
    rig|rigs|minebox|riser|risers|breakout|apw\d*|pdu|immersion|hydro|fpga|
    control\s?board|s19\w*|s21\w*|s23\w*|t21|l7|l9|ks\d|ka3|al\d|dg\d|e9|z15\w*|m\d\ds\w*
)\b""", re.I | re.X)

KNOWN_BRANDS = ['NVIDIA', 'AMD', 'Intel', 'Corsair', 'Kingston', 'Samsung', 'ASUS', 'ASRock', 'MSI', 'GIGABYTE',
                'Palit', 'PNY', 'EVGA', 'Seasonic', 'be quiet!', 'Noctua', 'Transcend', 'Apacer', 'MikroTik', 'Delta',
                'ZOTAC', 'Sapphire', 'Crucial', 'Seagate', 'ARCTIC', 'Lian Li', 'Fractal Design', 'NZXT', 'Cooler Master',
                'Thermaltake', 'DeepCool', 'Phanteks', 'HP', 'Dell', 'Lenovo', 'Supermicro', 'Inno3D', 'XFX', 'PowerColor',
                'Biostar', 'TP-Link', 'Ubiquiti', 'APC', 'Eaton', 'CyberPower', 'Snowman', 'Mineshop']
AVAILABILITY = {'in_stock': 'in_stock', 'out_of_stock': 'out_of_stock', 'preorder': 'pre_order', 'backorder': 'backorder'}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.skip += 1
        if tag in ('br', 'p', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'tr'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip: self.skip -= 1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def plain(s):
    p = _Text(); p.feed(html.unescape(s or '')); t = ''.join(p.parts)
    t = re.sub(r'[ \t\r\f\v]+', ' ', t); t = re.sub(r'\n\s*\n+', '\n', t)
    return t.strip()


def gtin_ok(v):
    if not v or not v.isdigit() or len(v) not in (8, 12, 13, 14): return False
    d = [int(c) for c in v]; body = d[:-1][::-1]
    total = sum(x * (3 if i % 2 == 0 else 1) for i, x in enumerate(body))
    return (10 - total % 10) % 10 == d[-1]


def brand_for(title, brand):
    if brand: return brand.strip()
    t = title.lower()
    for b in KNOWN_BRANDS:
        if t.startswith(b.lower() + ' ') or t.startswith('*used* ' + b.lower() + ' '):
            return b
    return ''


def load(source):
    if re.match(r'https?://', source):
        req = urllib.request.Request(source, headers={'User-Agent': 'Mozilla/5.0 (compatible; MineshopChatGPTFeed/1.0; +https://mineshop.eu)'})
        return urllib.request.urlopen(req, timeout=120).read()
    with open(source, 'rb') as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=SOURCE)
    ap.add_argument('--out', required=True)
    ap.add_argument('--min-items', type=int, default=40)
    a = ap.parse_args()
    items = ET.fromstring(load(a.source)).findall('./channel/item')
    counts = {'source_items': len(items), 'mining_excluded': 0, 'out_of_stock_excluded': 0,
              'no_brand_excluded': 0, 'no_price_excluded': 0, 'invalid_gtin_dropped': 0}
    rows = []
    for it in items:
        g = lambda t: (it.findtext(G + t) or '').strip()
        title, link, cat = re.sub(r'\s+', ' ', g('title')), g('link'), g('google_product_category')
        desc = plain(g('description'))
        if not title or not link or not g('image_link'):
            continue
        if MINING.search(' '.join([title, desc[:600], link, cat])):
            counts['mining_excluded'] += 1; continue
        avail = AVAILABILITY.get(g('availability'), 'unknown')
        if avail not in ('in_stock', 'pre_order', 'backorder'):
            counts['out_of_stock_excluded'] += 1; continue
        m = re.match(r'^\s*([0-9]+(?:\.[0-9]{1,2})?)\s+EUR\s*$', g('price'))
        if not m or Decimal(m.group(1)) <= 0:
            counts['no_price_excluded'] += 1; continue
        brand = brand_for(title, g('brand'))
        if not brand:
            counts['no_brand_excluded'] += 1; continue
        row = {
            'item_id': g('id'), 'title': title[:150], 'description': (desc or title)[:5000], 'url': link,
            'brand': brand, 'seller_name': SELLER, 'seller_url': SELLER_URL, 'image_url': g('image_link'),
            'price': f"{Decimal(m.group(1)):.2f} EUR", 'availability': avail, 'condition': g('condition') or 'new',
            'is_eligible_search': True, 'accepts_returns': True, 'return_deadline_in_days': 14,
            'return_policy': RETURN_POLICY,
        }
        if cat: row['product_category'] = cat
        extra = [e.text.strip() for e in it.findall(G + 'additional_image_link') if (e.text or '').strip()]
        if extra: row['additional_image_urls'] = extra[:10]
        gt = re.sub(r'\D', '', g('gtin'))
        if gt:
            if gtin_ok(gt): row['gtin'] = gt
            else: counts['invalid_gtin_dropped'] += 1
        if g('mpn'): row['mpn'] = g('mpn')
        rows.append(row)
    counts['products'] = len(rows)
    if len(rows) < a.min_items:
        print(f'ERROR: only {len(rows)} products (minimum {a.min_items}); keeping the previous feed', file=sys.stderr)
        print(json.dumps(counts), file=sys.stderr)
        sys.exit(2)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, FEED_FILE), 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    counts['generated_at'] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    with open(os.path.join(a.out, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(counts, f, indent=1)
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
