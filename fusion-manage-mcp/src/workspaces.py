"""
Fusion Manage workspace ID registry for tenant: the reference tenant

All tool functions reference workspace IDs from here rather than hardcoding
magic numbers inline. Update this file if workspace IDs ever change.

Verified against live tenant via GET /api/rest/v1/workspaces (2026-03-31).
"""

# ── Core Engineering ──────────────────────────────────────────────────────────
ITEMS = 57                    # Parts & Assemblies — Revision Controlled. Primary BOM source.
DOCUMENTS = 71                # Engineering Documents — Revision Controlled
MANUFACTURER_PN = 63          # Manufacturer Part Numbers

# ── Change Management ─────────────────────────────────────────────────────────
CHANGE_ORDERS = 84            # Change Orders / ECOs — Revisioning Workspace
CHANGE_REQUESTS = 83          # Change Requests — Basic with workflow
CHANGE_TASKS = 80             # Change Tasks
QUICK_RELEASES = 78           # Quick Releases — Revisioning Workspace
DOCUMENT_CHANGE_ORDER = 70    # Document Change Orders — Revisioning Workspace

# ── Quality Management ────────────────────────────────────────────────────────
NON_CONFORMANCES = 98         # NCRs — Basic with workflow
CAPAS = 100                   # Corrective / Preventative Actions
QUALITY_INSPECTION_PLANS = 99
QUALITY_INSPECTIONS = 101
PROBLEM_REPORTS = 82
AUDITS = 22
CLAIMS = 91

# ── Product Portfolio ─────────────────────────────────────────────────────────
PRODUCTS = 95                 # Product Portfolio items
PRODUCT_LINES = 92
PRODUCT_CATEGORIES = 109

# ── Projects / NPI ───────────────────────────────────────────────────────────
PROJECTS = 86
PROJECT_PHASES = 87
PROJECT_TASKS = 90
PROJECT_TEMPLATES = 85
ENGINEERING_PROJECTS = 213
ENGINEERING_PROJECT_ACTIVITIES = 211
ENGINEERING_PROJECT_TEMPLATES = 212

# ── Requirements ──────────────────────────────────────────────────────────────
REQUIREMENTS = 143
REQUIREMENT_SPECIFICATIONS = 142
REQUIREMENT_APPROVALS = 145
REQUIREMENT_VALIDATIONS = 144

# ── Supplier Management ───────────────────────────────────────────────────────
SUPPLIERS = 14
SUPPLIER_PACKAGES = 147
SUPPLIER_PROPOSALS = 148
SUPPLIER_DELIVERABLES = 146

# ── Reviews & Approvals ───────────────────────────────────────────────────────
DESIGN_REVIEWS = 76
DESIGN_REVIEW_TASKS = 77
APPROVAL_LISTS = 64

# ── Convenience lookups ───────────────────────────────────────────────────────
LABEL_TO_ID: dict[str, int] = {
    "Items": ITEMS,
    "Documents": DOCUMENTS,
    "Manufacturer P/N": MANUFACTURER_PN,
    "Change Orders": CHANGE_ORDERS,
    "Change Requests": CHANGE_REQUESTS,
    "Non Conformances": NON_CONFORMANCES,
    "Corrective / Preventative Actions": CAPAS,
    "Products": PRODUCTS,
    "Projects": PROJECTS,
    "Suppliers": SUPPLIERS,
    "Design Reviews": DESIGN_REVIEWS,
    "Requirements": REQUIREMENTS,
}

ID_TO_LABEL: dict[int, str] = {v: k for k, v in LABEL_TO_ID.items()}
