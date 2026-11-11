# Mineshop.eu product feed for ChatGPT

Product feed for Mineshop.eu (Mining Hardware Limited) in ChatGPT, in the
[OpenAI product feed format](https://developers.openai.com/commerce/specs/file-upload/products).

- Feed (imported by ChatGPT): https://mineshop007.github.io/chatgpt-product-feed/mineshop-openai.jsonl.gz
- Same feed, uncompressed: https://mineshop007.github.io/chatgpt-product-feed/mineshop-openai.jsonl
- Source: the shop's public Google Merchant feed, https://mineshop.eu/google-shopping-feed.xml
- Rebuilt daily at 02:20 UTC by GitHub Actions (`build_feed.py`).
- Contents: in-stock computer hardware (GPUs, CPUs, memory, storage, motherboards, power supplies,
  cooling, cases, networking, AI systems). Crypto-mining products are not included.
- Prices: the shop's ex-VAT EUR prices. VAT, shipping and any import charges are added at checkout on
  [mineshop.eu](https://mineshop.eu).
