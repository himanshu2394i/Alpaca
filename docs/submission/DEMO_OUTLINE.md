# Demo video + slides outline (record after competition account is live)

## Video (2–3 minutes)

| Time | Shot | Say |
|------|------|-----|
| 0:00–0:20 | Title + dashboard URL | Autonomous options agent on Alpaca paper for lablab.ai |
| 0:20–0:50 | Architecture diagram / README | Ingest → screener/MTF → Claude → gates → MCP orders; CLI for ops |
| 0:50–1:20 | Dashboard | Equity, positions, recent decisions |
| 1:20–1:50 | Decision log / code snippet of gates | Risk cannot be bypassed by the model |
| 1:50–2:20 | Terminal: `ops/cli_demo.sh` | Account + positions via Alpaca CLI |
| 2:20–2:50 | Optional live tick or replay | Opportunity → contract → limit → fill |
| 2:50–3:00 | Close | Repo link + paper-only disclaimer |

**Tips:** Record after a real decision if possible; otherwise use a recent decision log + dry-run narration. Keep audio dry and factual.

## Slides (8 max)

1. Problem — autonomous options agents need risk + brokerage glue  
2. Solution one-liner + live URL  
3. Strategy — momentum + MTF + optional Claude  
4. Risk gates table  
5. Alpaca stack — API / MCP / CLI diagram  
6. Execution — fill poll, reconcile, no ghost entries  
7. Competition setup — fresh $100k paper account  
8. Results / what we’d improve next  

Export to PDF for the lablab “slide presentation” field.
