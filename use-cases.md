# PLM ↔ MES AI Orchestration — Use Cases

> Source: "From Integration to Orchestration" conference session (April 2026)
>
> **Core thesis**: Integrations move data. AI orchestration understands and acts on it.
> MCP does not replace existing integrations — it gives AI the ability to reason across them.

---

## The Three Themes

| Theme | Description | Use Cases |
|-------|-------------|-----------|
| **Augment Intelligence** | Add AI reasoning to change management and quality workflows. Stop relying on manual cross-referencing. | #1 Change Impact Analysis, #3 Root Cause Analysis |
| **Adapt Execution** | Respond to real-time shop floor variability and supplier exceptions static pipelines cannot handle. | #2 Work Instruction Generation, #4 Supplier Exception Handling |
| **Unlock Access** | Make every question answerable without a BI ticket. Any stakeholder, any data, in natural language. | #5 Natural Language Intelligence Layer |

---

## Use Case 01 — Intelligent Change Impact Analysis
**Flow**: Engineering → Manufacturing → Supply Chain

### The Problem
> "A design change just dropped. Three active work orders, two suppliers, and a firmware dependency — how long will it take your team to figure that out?"

- BOM update propagates — consequences do not
- Downstream impact assessment is manual
- Unstructured ECOs, notes, and drawings are invisible to MES

### The AI Orchestration
1. Agent receives an ECO number or part number from the user
2. Calls `get_item_by_number` (PLM) to fetch the ECO/part details
3. Calls `get_released_parts` (PLM) to find parts in the affected BOM
4. Calls `find_orders_by_product_code` (MES) to find active production orders for those parts
5. Calls `list_purchase_orders` (MES) to identify open supplier orders for affected components
6. Agent synthesizes: "This change affects 3 active WOs, 2 open POs — estimated 5-day delay risk"

### MCP Tools Required
| Tool | Server | Purpose |
|------|--------|---------|
| `get_workspace_item` | fusion-manage-mcp | Fetch the ECO or changed part |
| `search_workspace_items` | fusion-manage-mcp | Find all parts referencing the changed component |
| `get_items_changed_since` | fusion-manage-mcp | Find items modified in a date range (for correlation) |
| `get_released_parts` | fusion-manage-mcp | Get all currently released parts/assemblies |
| `find_orders_by_product_code` | fusion-operations-mcp | Find active WOs for a part number |
| `list_purchase_orders` | fusion-operations-mcp | Find open supplier POs for affected components |
| `list_suppliers` | fusion-operations-mcp | Identify affected supplier contacts |

### Expected Output
```
Change Impact Report — ECO-2024-087 (Bracket Tolerance Update)

Affected Parts (PLM):
  - ASSY-001: Widget Assembly (in BOM at qty 2)
  - ASSY-003: Sub-Assembly B (in BOM at qty 1)

Active Production Orders (MES):
  - PO-2024-112: 200 units, due 2024-11-30, 45% complete — AT RISK
  - PO-2024-118: 100 units, due 2024-12-05, not started — DELAY LIKELY
  - PO-2024-125: 50 units, due 2024-12-15, not started — MONITOR

Open Purchase Orders (MES):
  - PUR-2024-044: Parts Inc — 500x BRACKET-L, expected 2024-11-28 — SPEC CONFLICT
  - PUR-2024-051: FastenCo — 1000x BOLT-M6, expected 2024-12-01 — OK

Estimated Risk: 5-day delay on PO-2024-112. Recommend: hold PUR-2024-044 pending supplier re-quote.
```

---

## Use Case 02 — Dynamic Work Instruction Generation & Adaptation
**Flow**: PLM → MES → Operator

### The Problem
> "Three defects this shift. Different operator than yesterday. Machine just flagged a torque anomaly. Your work instructions say nothing about any of this."

- MES delivers static, version-controlled instructions
- Updates require formal change processes
- Real-time shop floor context is completely out of scope

### The AI Orchestration
1. Agent fetches current BOM and routing from PLM for the part being produced
2. Calls `get_product` (MES) to get the MES-side product setup
3. Calls `get_production_summary` (MES) to pull recent defect history for this part/line
4. Agent synthesizes adaptive instructions:
   - Adds inspection steps where defects have occurred
   - Adjusts language/format for operator context

### MCP Tools Required
| Tool | Server | Purpose |
|------|--------|---------|
| `get_workspace_item` | fusion-manage-mcp | Fetch part BOM and routing/process steps |
| `list_item_attachments` | fusion-manage-mcp | Get engineering drawings and process docs |
| `get_product` | fusion-operations-mcp | Get MES product configuration |
| `get_production_summary` | fusion-operations-mcp | Recent defect counts and failure modes |
| `list_production_orders` | fusion-operations-mcp | Current and recent WOs for context |

### Expected Output
```
Adaptive Work Instructions — ASSY-001 Widget Assembly
Work Order: PO-2024-112 | Station 4 | Operator: J. Hernandez

Standard Steps:
  1. Verify incoming BRACKET-L (COMP-002) against drawing REV-C
  2. Install 4x BOLT-M6 at 12 Nm torque ± 0.5 Nm
  3. ...

⚠ Adaptive Additions (based on recent defect history):
  Step 2a [ADDED]: Measure bracket slot width before installation.
    Reason: 3 defects this week for out-of-tolerance slot width.
  Step 3a [ADDED]: Verify torque with secondary gauge.
    Reason: Machine torque sensor flagged anomaly on 2024-11-15.

Operator Note: Visual reference for step 2 attached (drawing D-0042-REV-C).
```

---

## Use Case 03 — Cross-System Root Cause Analysis
**Flow**: Quality · MES · IoT · PLM

### The Problem
> "Defect rate on Line 3 is up 18% this week. Four systems hold the relevant data. Your team is spending two days pulling it together manually."

- Integration exists, but correlation is pre-defined and brittle
- Analysts manually cross-reference 4+ systems
- New failure modes require new integration logic to surface

### The AI Orchestration
1. Agent receives defect rate alert or user query
2. Calls `get_production_summary` (MES) to get defect details for the time period/line
3. Calls `find_orders_by_product_code` (MES) to get the WOs involved
4. Calls `get_items_changed_since` (PLM) to find engineering changes in the same date range
5. Calls `list_purchase_orders` (MES) to identify supplier batch timing
6. Agent correlates and ranks hypotheses

### MCP Tools Required
| Tool | Server | Purpose |
|------|--------|---------|
| `get_production_summary` | fusion-operations-mcp | Defect counts, rates, failure modes by period |
| `find_orders_by_product_code` | fusion-operations-mcp | WOs in the analysis period |
| `list_inventory_movements` | fusion-operations-mcp | Incoming material batch tracking |
| `get_items_changed_since` | fusion-manage-mcp | Engineering changes in the defect period |
| `search_workspace_items` | fusion-manage-mcp | Find related ECOs, NCRs, supplier CAPAs |
| `get_workflow_history` | fusion-manage-mcp | Timeline of part/ECO approvals |

### Expected Output
```
Root Cause Analysis — Line 3 Defect Spike (Week of 2024-11-11)

Defect Summary (MES):
  - 23 defects on ASSY-001, up from 12 prior week (+92%)
  - Primary failure mode: bracket slot width out of tolerance

Correlated Events:
  [HIGH] 2024-11-13: ECO-2024-085 released — bracket tolerance tightened from ±0.3mm to ±0.2mm
         → 3 WOs started AFTER this change, all show elevated defect rate
  [HIGH] 2024-11-12: Inventory movement from Supplier B batch #441 (BRACKET-L)
         → All defective units traceable to this batch
  [LOW]  2024-11-10: Machine calibration — torque wrench recalibrated (no correlation found)

Hypothesis Ranking:
  1. (85% confidence) Supplier B batch #441 was manufactured to old tolerance spec
  2. (70% confidence) New ECO tolerance not yet reflected in supplier drawing revision
  3. (15% confidence) Machine calibration side-effect

Recommended Actions:
  1. Quarantine remaining Supplier B batch #441 inventory
  2. Issue SCAR to Supplier B referencing ECO-2024-085
  3. Confirm drawing REV-D distributed to supplier before next batch
```

---

## Use Case 04 — Supplier Collaboration & Exception Handling
**Flow**: ERP/PLM ↔ External Systems

### The Problem
> "Supplier just emailed: they can't meet the spec. The message is in plain English. Your EDI system has no idea it exists."

- EDI and IPaaS handle standard, structured transactions
- Exceptions break the pipeline and land in inboxes
- Ambiguous messages require human interpretation and follow-up

### The AI Orchestration
1. Agent ingests unstructured supplier communication (email/PDF text)
2. Extracts: affected part number, spec conflict, proposed alternative
3. Calls `list_suppliers` (MES) to verify supplier identity
4. Calls `search_workspace_items` (PLM) to find approved alternates or specs
5. Calls `list_purchase_orders` (MES) to find open orders at risk
6. Agent generates a structured exception response + recommended alternates

### MCP Tools Required
| Tool | Server | Purpose |
|------|--------|---------|
| `list_suppliers` | fusion-operations-mcp | Verify supplier and find contacts |
| `list_purchase_orders` | fusion-operations-mcp | Find open orders from this supplier |
| `update_purchase_order` | fusion-operations-mcp | Update PO status/notes with exception info |
| `search_workspace_items` | fusion-manage-mcp | Find approved alternates in approved supplier list |
| `get_workspace_item` | fusion-manage-mcp | Get spec details (drawings, tolerance data) |
| `get_workflow_history` | fusion-manage-mcp | Verify current approval status of specs |

---

## Use Case 05 — Natural Language Manufacturing Intelligence Layer
**Flow**: PLM · MES · ERP · Data Lakes (unified)

### The Problem
> "Your VP just asked: 'Why did line 3 efficiency drop last week after the design change?' How many people and how many days does it take to answer that today?"

- Dashboards are pre-built for anticipated questions
- New queries require BI team involvement and sprint cycles
- Non-technical users cannot access cross-system context

### The AI Orchestration
This use case is the emergent result of all the tools in both servers working together. The AI decomposes any natural language question into targeted tool calls, pulls structured data in parallel, and returns a synthesized, cited answer.

**Example query flow:**
1. User: "Why did line 3 efficiency drop last week after the design change?"
2. Agent decomposes:
   - "What design change?" → `get_items_changed_since` (PLM, last 2 weeks)
   - "What's line 3 efficiency?" → `get_production_summary` (MES, last week vs prior week)
   - "What WOs were running?" → `find_orders_by_product_code` (MES)
   - "Is there an ECO in PLM?" → `search_workspace_items` (PLM)
3. Agent synthesizes across all results and returns a cited narrative

### MCP Tools Required
All tools from both servers. This use case requires the full breadth of both MCP servers working as a unified intelligence layer.

---

## Cross-System Data Flow Map

```
                    FUSION MANAGE (PLM)
                    ┌─────────────────────────────────┐
                    │ Workspaces (Items/Parts/ECOs)    │
                    │ Released BOMs                    │
                    │ Workflow states & history        │
                    │ Attachments (drawings, specs)    │
                    │ Reports                          │
                    └───────────┬─────────────────────┘
                                │
                    AI AGENT (Claude + MCP)
                    Reasons across both systems
                                │
                    ┌───────────┴─────────────────────┐
                    │ FUSION OPERATIONS (MES)          │
                    │ Production Orders (WOs)          │
                    │ Products + BOMs                  │
                    │ Sales & Purchase Orders          │
                    │ Inventory Movements              │
                    │ Clients & Suppliers              │
                    └─────────────────────────────────┘

KEY CROSS-SYSTEM FLOWS:
  PLM → MES:  Released BOM → MES Product creation
  PLM → MES:  ECO impact → Active WO identification & notification
  PLM → MES:  Part number / routing → Work instruction base
  MES → PLM:  Production defects → ECO / CAPA correlation
  MES → PLM:  Actual production data → PLM item field writeback
  BOTH:       Date-range correlation for root cause analysis
```

---

## Implementation Priority

| Priority | Use Case | Complexity | Business Value |
|----------|----------|------------|----------------|
| 1 | BOM Sync (PLM → MES) | Medium | High — foundational for all others |
| 2 | Change Impact Analysis | Medium | High — immediate pain point |
| 3 | Root Cause Analysis | High | Very High — multi-day manual effort today |
| 4 | Work Instruction Generation | Medium | High — safety and quality impact |
| 5 | Supplier Exception Handling | High | Medium — requires external data ingestion |
| 6 | Natural Language Layer | Low (emergent) | Very High — unlocks all use cases for all users |

> BOM Sync is Priority 1 because MES products must mirror PLM parts before any other cross-system flow works reliably.
