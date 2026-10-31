# Demo video plan (under 3 minutes, narration by Amazon Polly)

Target: 2:30. English narration, generated with Amazon Polly (neural voice). No music.
Captions burned in. All visuals are our own (generated site, screenshots, terminal, diagrams).

| # | Time | Visual | Narration |
|---|---|---|---|
| 1 | 0:00-0:15 | Full Example City site on a phone frame, video background playing | When a flood warning goes out, everyone opens the city website at once, on the same congested network. This one weighs twenty-eight megabytes. |
| 2 | 0:15-0:30 | Throttled load: full site still loading at 3G, timer running | On a congested 3G connection, it still has not finished loading after three minutes. The shelter list is at the very bottom. |
| 3 | 0:30-0:45 | Title card "Brownout" + one-line pitch | This is Brownout, an agent built with the Strands Agents SDK. As the alert level rises, it makes the site lighter instead of letting it go down. |
| 4 | 0:45-1:05 | Architecture diagram, highlight path step by step | An alert event goes through EventBridge to the agent on Amazon Bedrock AgentCore Runtime. A Curator agent decides which facts matter. A Writer agent writes the page. |
| 5 | 1:05-1:25 | Code: PublishGuard hook, then a refusal message in the log | Before anything is published, a Strands hook checks the page: size budget, every required fact, no unsafe shelter. If it fails, the agent gets exact feedback and tries again. |
| 6 | 1:25-1:50 | Live demo: terminal `alert.py flood 4`, phone view switches to Level 4 page; then level 5 | Only a checked page goes to S3. Then one write to CloudFront KeyValueStore switches the whole site at the edge. No deployment, no cache invalidation. |
| 7 | 1:50-2:15 | Results tables (correctness, speed) | Stripping images is light but wrong: it still lists the riverside hall during a flood. With the guard, every run was correct, and each page is under one kilobyte. It loads in one second, even on 2G. |
| 8 | 2:15-2:30 | Level 1 event, site returns to full; end card with repo URL | When the danger passes, the site comes back. Brownout: lighter when it matters most. |

## Assets to produce

- Phone-frame screen recordings (Playwright video): full site, throttled loading, live switch 1 -> 4 -> 5 -> 1
- Architecture diagram image (from the README mermaid)
- Code close-up of PublishGuard and a refusal log line
- Results table cards
- Polly audio per scene, then ffmpeg to assemble (as in earlier projects)
