# Brownout

**When disaster strikes, a city website should get lighter, not go down.**

Brownout is an AI agent built with the [Strands Agents SDK](https://strandsagents.com/) that rewrites a heavy city website into a tiny emergency page as the alert level rises, and switches the live site at the edge in seconds.

The name comes from operations: a *brownout* keeps a system alive by turning features off instead of failing completely.

> Example City is fictional. Every name, address and phone number in this repository is made up.

## Live demo

- Example City (follows the current alert level): https://d3u5pnxb6mo4pr.cloudfront.net/
  Between alerts this is the full site, about 28 MB.
- Brownout pages written for a flood: [Level 3](https://d3u5pnxb6mo4pr.cloudfront.net/level-3/index.html), [Level 4](https://d3u5pnxb6mo4pr.cloudfront.net/level-4/index.html), [Level 5](https://d3u5pnxb6mo4pr.cloudfront.net/level-5/index.html)

Alerts are simulated; only the project owner can send them.

## The problem

City websites are built for good days: video backgrounds, photo carousels, maps, web fonts. During a flood or an earthquake, the same site is what people need most, at the moment when mobile networks are congested and phones are on low battery. The people hit hardest are those with the weakest connections: older residents, people on prepaid low-data plans, and anyone in a damaged area.

Example City's normal homepage pulls in **about 28 MB**. On a congested 3G or a 2G connection it does not finish loading within three minutes, and the shelter list sits at the bottom, under the video.

Stripping the media is not enough. A mechanically stripped page is light, but it still says "No alerts at the moment", lists a riverside hall as a shelter during a flood, and mixes festival news with evacuation orders.

## What Brownout does

Brownout follows Japan's five-level evacuation alert system. At each level it publishes a smaller page:

| Alert level | Page | Budget (gzip) |
|---|---|---|
| 1-2 | full site | none |
| 3 - elderly and others evacuate | light | 500 KB |
| 4 - evacuate | lite | 50 KB |
| 5 - emergency safety | survival | 14 KB (fits in the first network round trip) |

1. An `AlertLevelChanged` event reaches Amazon EventBridge.
2. A thin AWS Lambda adapter invokes the Brownout agent on **Amazon Bedrock AgentCore Runtime**.
3. The **Curator** agent (a specialist called as a tool) decides which facts matter for this hazard and level, for example which shelters are safe in a flood.
4. The **Writer** agent writes one self-contained HTML page from the official city data only, and calls `publish_page`.
5. **PublishGuard**, a Strands hook, blocks `publish_page` unless the page passes two layers of checks. Deterministic code: the byte budget, every required fact present, no unsafe shelter, and no phone number, address or place name that is not in the city data. Then a **Verifier** agent lists any sentence the city data does not support (for example general safety tips the agent added on its own); a word-overlap check drops flags that are just paraphrases. Refusals go back to the agent as concrete feedback, up to six attempts.
6. Only a page that passed is written to Amazon S3, and only then is the alert level written to **CloudFront KeyValueStore**.
7. A **CloudFront Function** reads that value on every request and routes all URLs to the page for the current level. No deployment and no cache invalidation are needed to switch.

```mermaid
flowchart LR
  EB[EventBridge<br/>AlertLevelChanged] --> L[Lambda adapter]
  L --> RT[AgentCore Runtime<br/>Brownout agent]
  RT --> C[Curator agent]
  RT -->|publish_page| G{PublishGuard hook<br/>code checks + Verifier agent}
  G -->|refused + feedback| RT
  G -->|passed| S3[(S3)]
  RT -->|level| KVS[(CloudFront<br/>KeyValueStore)]
  U[Phone] --> CF[CloudFront + Function] --> S3
  CF -.reads level.-> KVS
```

## Results

### Is the page right? (`scripts/evaluate.py`)

Six scenarios (flood and earthquake, levels 3 to 5). Each agent variant ran 3 times per scenario. A page passes only if it fits the budget, keeps every required fact, shows no unsafe shelter, contains no phone number, address or place that is not in the city data, and contains no sentence the judge finds unsupported by the data.

| Variant | Pass rate | Required facts kept | Unsafe shelter shown | Unsupported sentences | Size (gzip) |
|---|---|---|---|---|---|
| Mechanical stripping | 0 of 6 | 75% | 3 of 6 | 6 of 6 | 1,266 B |
| Agent without PublishGuard | 13 of 18 (72%) | 96% | 0 of 18 | 5 of 18 | 515-940 B |
| **Brownout** (agent + PublishGuard) | **18 of 18 (100%)** | **100%** | **0 of 18** | **0 of 18** | 616-970 B |

Brownout published on the first try in 15 of 18 runs. Model: Amazon Nova 2 Lite on Amazon Bedrock. The judge for unsupported sentences is the same model and prompt as the Verifier inside PublishGuard, applied to every variant's final page; see Limits. Raw results: `results/eval-nova2lite-3trials.json`.

### Is the page fast? (`scripts/loadtest.py`)

Chrome with DevTools network emulation, cache disabled.

| Network | Full site, fully loaded | Brownout pages, fully loaded |
|---|---|---|
| Congested 3G (400 kbit/s, 400 ms RTT) | did not finish in 180 s | 0.5 s |
| 2G (50 kbit/s, 500 ms RTT) | did not finish in 180 s | 1.0 s |

Raw results: `results/loadtest.json`.

### How fast does the live site switch? (`scripts/alert.py`)

From sending the event to the live CloudFront URL showing the new page: 24 to 55 seconds over four runs. The agent itself takes about 5.5 s; Lambda including a new AgentCore Runtime session 11 to 13 s; the rest is KeyValueStore propagation to the edge. Raw results: `results/switch-times.json`.

## Limits

- Example City, its data and its alerts are simulated. The required-facts checklist is written by hand per hazard and level.
- The Verifier and the evaluation judge use the same model and prompt, so the "unsupported sentences" column shows what the other variants publish without that check, not an independent audit of Brownout. Required facts, unsafe shelters and invented numbers or places are checked by plain code.
- Load times were measured locally with Chrome network emulation, not on a real disaster network.
- Brownout replaces the whole site with one page per level; a real city site would need the same treatment for more pages.

## Repository layout

| Path | What it is |
|---|---|
| `content/town.json` | The only source of facts (fictional city data) |
| `content/must_have.json` | Required and forbidden facts per hazard and level, plus byte budgets |
| `brownout/agent.py` | Curator + Writer agents and the PublishGuard hook |
| `brownout/facts.py` | Shared checks (budget, required facts) |
| `brownout/baseline.py` | Mechanical stripping, for comparison |
| `brownout/edge.py` | Publish to S3, flip the level in CloudFront KeyValueStore |
| `runtime/main.py` | AgentCore Runtime entrypoint |
| `infra/` | CloudFront Function router, edge and trigger setup scripts |
| `scripts/` | Site generator, measurement, evaluation, load test, alert simulator |

## Run it

Requirements: Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js (for the AgentCore CLI), ffmpeg, an AWS account with Amazon Bedrock access to Amazon Nova in us-east-1.

```bash
uv sync
uv run python scripts/build_full_site.py           # generate the heavy site (about 28 MB)
uv run python scripts/measure.py site/full/index.html
PYTHONPATH=. uv run python scripts/evaluate.py --trials 3

# AWS
uv run python infra/deploy_infra.py                 # S3, CloudFront, KeyValueStore, Function
PYTHONPATH=. uv run python -c "from pathlib import Path; from brownout.edge import upload_dir, set_level; upload_dir(Path('site/full'), 'full'); set_level(1)"
scripts/deploy_runtime.sh                           # AgentCore Runtime (agentcore CLI)
uv run python infra/deploy_trigger.py <runtime-arn> # EventBridge -> Lambda -> Runtime
PYTHONPATH=. uv run python scripts/alert.py flood 4 # raise the alert and time the switch
```

The AgentCore project in `deploy/brownoutrt` was created with `agentcore create --template empty` and `agentcore add runtime --name Brownout --language python`, passing the bucket and KeyValueStore ARN as environment variables and `infra/runtime-policy.json` as an additional policy.

## Credits and license

- Code: Apache License 2.0 (see `LICENSE`). Copyright ikenyal.
- Font in the generated full site: Noto Sans JP, SIL Open Font License 1.1.
- All images, the map and the video are generated by `scripts/build_full_site.py`.
