# LiquidityLab

LiquidityLab is a read-only academic tool for comparing traded volume with displayed liquidity. It uses SSI FastConnect Data according to the instructor's updated requirement. The public web app shows OHLCV, indices, relative volume and saved order-book observations. The local manual calculator works with user-supplied books and simulates a buy or sell across up to three visible levels.

## Run and verify

From this folder, use Python 3.12+ and a current Node.js runtime:

```sh
python run.py --port 8792
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
node scripts/build_vercel_demo.mjs
```

Open `http://127.0.0.1:8792`. The local server and calculator need only the Python standard library. On Windows, `MO_LIQUIDITY_LAB.cmd` also opens the app. `LiquidityLab` / `123456789` is the public demo form, with no user authentication or account access. A clean copy can run the calculator and synthetic tests. Historical SSI panels require the corresponding saved data folders. Missing-source panels must be read as unavailable.

For authorized SSI collection, install `requirements-ssi.txt` and configure the variables in `.env.example` through the environment or a private `.env`. The production workflows use GitHub Secrets and the public demo reads the market API on Vercel. REST collection is restricted to the five market-data endpoints in `src/ssi_client.py`; the SDK also authenticates and subscribes to the SSI DATA feed.

## Data and provenance

| Component | What it uses |
| --- | --- |
| `src/`, `scripts/` | SSI mapping and validation, candle publication, book capture, finance and research |
| `web/`, `api/`, `demo/` | Local and Vercel UI, read-only production API, browser adapter |
| `config/` | Historical snapshot pointer, pilot protocol, SSI unit-contract template |
| `data_sample/` | Synthetic SSI-shaped catalogue for HTTP/SSE tests only |
| `data/` | Local SSI snapshots and research archives outside Git |

Production OHLCV uses closed SSI minute observations. M15 refreshes at market checkpoints and the chart aggregates other periods from observed data. Daily and longer charts may include a provisional current observation, and the official EOD history is published separately. The chart watch has an independent schedule. The book collector preserves one-second sampled states and SSI event logs where available. A saved checkpoint carries the most recent observed books, with lower time granularity than those logs.

Check any saved archive directory that also contains its manifest by running:

```sh
python -m scripts.audit_book_archives data/research_exports
```

The archive audit checks hashes and reports per-symbol coverage in continuous trading windows. Collector freshness and session flags do not certify SSI units or research eligibility. Keep externally sourced datasets separate until provenance, permitted use, timestamp semantics and quality have been verified. SSI data may be subject to redistribution terms.

The offline research runner currently reads event logs prepared in `data/live_snapshots/`. The archive inventory remains a separate check before selecting those inputs. The archive contains both capture timestamps (`sampled_at`, one-second sampling grid) and, where available, source and receive timestamps (`event_time`, `received_at`). Quote prices and quantities remain in SSI source units until the unit contract has supporting evidence. Checkpoints cannot recover the quote sequence between saved times.

## Financial interpretation

- Relative volume divides current observed volume by the previous 20 completed sessions' mean. Values such as 2× and 0.5× identify double or half the recent reference for description. An intraday numerator is provisional and is compared with full-day historical volume.
- The exit scenario uses 100,000 shares and participation of 5% as explicit scenario inputs. Estimated sessions equal shares divided by the product of average volume and participation. At 2.5%, 5% or 10% the scenario respectively gives twice, the same or half the 5% estimate for a fixed average volume. It does not measure displayed depth.
- The 60-second observation rule uses a prior 10th-percentile depth reference and checks whether low depth persists for 15 seconds. These are pilot choices for a low-tail and a persistence filter. Candidate quantiles and time windows must be compared on development days and finalized before evaluating reserved days. The protocol and SSI unit contract have separate gates.
- Manual sweep uses the best displayed opposite-side prices first. VWAP uses the filled quantity. The UI pairs full-order midpoint slippage with snapshot fill fraction and suppresses full-order slippage when shares remain. It does not estimate fill frequency, queue priority, fees, round-lot constraints or the market response to a real order.

The production data notes and limitations are in [docs/production-ssi-coverage.md](docs/production-ssi-coverage.md). Treat the application as an academic analysis tool, not investment advice. The research evaluation remains a pilot and H1 is `NOT_TESTED` until the data, unit contract and locked protocol support a defensible out-of-sample comparison.

### Dependencies and notices

- [KaTeX](https://github.com/KaTeX/KaTeX), [bundled licence](web/vendor/katex/LICENSE.txt)
- [Apache ECharts](https://echarts.apache.org/), [bundled licence](web/vendor/echarts-LICENSE.txt) and [NOTICE](web/vendor/echarts-NOTICE.txt)
- [Lightweight Charts](https://github.com/tradingview/lightweight-charts), [bundled licence](web/vendor/lightweight-charts-LICENSE.txt) for the retained vendor file
- SSI FastConnect Python SDK (`ssi-sdk`), version in `requirements-ssi.txt`. Consult the provider for SDK and data usage terms.
