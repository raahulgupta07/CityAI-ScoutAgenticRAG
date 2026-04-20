"""
SOP Template Builder — Predefined and custom templates per department/industry.
Templates define which sections are required, their order, and field descriptions.
"""
from __future__ import annotations

# ── Predefined Templates ─────────────────────────────────────────────────────

TEMPLATES = {
    "itsm": {
        "name": "ITSM / IT Service Management",
        "description": "ITIL-aligned template for IT operations: incidents, changes, problems, service requests",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True, "description": "McKinsey-style conclusion-first summary"},
            {"id": "purpose", "name": "Purpose & Scope", "required": True, "description": "Why this SOP exists and what it covers"},
            {"id": "kpis", "name": "KPIs & SLA Targets", "required": True, "description": "Measurable metrics with targets and frequencies"},
            {"id": "raci", "name": "RACI Matrix", "required": True, "description": "Responsible, Accountable, Consulted, Informed per activity"},
            {"id": "definitions", "name": "Definitions & Terminology", "required": True, "description": "ITIL terms, acronyms, service definitions"},
            {"id": "prerequisites", "name": "Prerequisites", "required": False, "description": "Tools, access, permissions needed"},
            {"id": "procedure", "name": "Procedure", "required": True, "description": "Step-by-step with Input→Activity→Output→Verification (Accenture ADM)"},
            {"id": "escalation", "name": "Escalation Matrix", "required": True, "description": "Triggers, actions, severity levels, timeframes"},
            {"id": "references", "name": "References", "required": False, "description": "ITIL guides, related SOPs, ISO standards"},
        ],
        "extra_fields": ["sla_table", "incident_categories", "change_types"],
    },
    "hr": {
        "name": "HR / Human Resources",
        "description": "Template for HR processes: onboarding, leave, performance, compliance",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True, "description": "Policy overview"},
            {"id": "purpose", "name": "Purpose & Scope", "required": True, "description": "Policy intent and applicability"},
            {"id": "policy_statement", "name": "Policy Statement", "required": True, "description": "The core policy rules and requirements"},
            {"id": "definitions", "name": "Definitions", "required": True, "description": "HR terms, employee categories"},
            {"id": "eligibility", "name": "Eligibility", "required": True, "description": "Who this applies to"},
            {"id": "procedure", "name": "Procedure", "required": True, "description": "Step-by-step process"},
            {"id": "forms", "name": "Required Forms", "required": False, "description": "Forms to be filled"},
            {"id": "compliance", "name": "Compliance & Legal", "required": True, "description": "Legal requirements, penalties"},
            {"id": "references", "name": "References", "required": False, "description": "Labor laws, related policies"},
        ],
        "extra_fields": ["approval_chain", "form_links"],
    },
    "safety": {
        "name": "Safety / EHS",
        "description": "Environment, Health & Safety template: emergency response, equipment handling, PPE",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True, "description": "Safety overview"},
            {"id": "purpose", "name": "Purpose & Scope", "required": True, "description": "What hazards this addresses"},
            {"id": "hazard_assessment", "name": "Hazard Assessment", "required": True, "description": "Identified risks and severity"},
            {"id": "ppe_requirements", "name": "PPE Requirements", "required": True, "description": "Required protective equipment"},
            {"id": "definitions", "name": "Definitions", "required": False, "description": "Safety terms"},
            {"id": "procedure", "name": "Procedure", "required": True, "description": "Safety steps with warnings prominently marked"},
            {"id": "emergency", "name": "Emergency Procedures", "required": True, "description": "What to do in case of accident/spill/injury"},
            {"id": "first_aid", "name": "First Aid", "required": False, "description": "Immediate response actions"},
            {"id": "incident_reporting", "name": "Incident Reporting", "required": True, "description": "How to report safety incidents"},
            {"id": "references", "name": "References", "required": False, "description": "OSHA regs, safety standards"},
        ],
        "extra_fields": ["risk_matrix", "ppe_table", "emergency_contacts"],
    },
    "manufacturing": {
        "name": "Manufacturing / Operations",
        "description": "Template for production lines, quality control, equipment operation",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True, "description": "Process overview"},
            {"id": "purpose", "name": "Purpose & Scope", "required": True, "description": "What product/process this covers"},
            {"id": "equipment", "name": "Equipment & Materials", "required": True, "description": "Required machines, tools, raw materials"},
            {"id": "definitions", "name": "Definitions", "required": False, "description": "Technical terms"},
            {"id": "quality_standards", "name": "Quality Standards", "required": True, "description": "Acceptance criteria, tolerances"},
            {"id": "procedure", "name": "Procedure", "required": True, "description": "Production steps with quality checkpoints"},
            {"id": "quality_control", "name": "Quality Control Checks", "required": True, "description": "Inspection points and pass/fail criteria"},
            {"id": "troubleshooting", "name": "Troubleshooting", "required": False, "description": "Common issues and fixes"},
            {"id": "references", "name": "References", "required": False, "description": "ISO standards, machine manuals"},
        ],
        "extra_fields": ["bom_table", "quality_checklist", "machine_specs"],
    },
    "general": {
        "name": "General Purpose",
        "description": "Standard document template suitable for any department",
        "sections": [
            {"id": "executive_summary", "name": "Executive Summary", "required": True, "description": "Overview"},
            {"id": "purpose", "name": "Purpose & Scope", "required": True, "description": "Why and what"},
            {"id": "definitions", "name": "Definitions", "required": False, "description": "Key terms"},
            {"id": "raci", "name": "RACI Matrix", "required": False, "description": "Roles and responsibilities"},
            {"id": "procedure", "name": "Procedure", "required": True, "description": "Step-by-step instructions"},
            {"id": "references", "name": "References", "required": False, "description": "Related documents"},
        ],
        "extra_fields": [],
    },
}


def get_templates() -> dict:
    """Return all available templates."""
    return {k: {"name": v["name"], "description": v["description"], "sections": len(v["sections"])} for k, v in TEMPLATES.items()}


def get_template(template_id: str) -> dict | None:
    """Return full template definition."""
    return TEMPLATES.get(template_id)


def get_template_for_department(department: str) -> str:
    """Auto-detect best template based on department name."""
    dept = department.lower()
    if any(w in dept for w in ["it", "itsm", "service", "technology", "digital", "network", "system", "software"]):
        return "itsm"
    if any(w in dept for w in ["hr", "human", "people", "talent", "recruit", "payroll"]):
        return "hr"
    if any(w in dept for w in ["safety", "ehs", "environment", "health", "hazard"]):
        return "safety"
    if any(w in dept for w in ["manufacturing", "production", "factory", "plant", "assembly", "quality"]):
        return "manufacturing"
    return "general"


def get_template_prompt_section(template_id: str) -> str:
    """Generate AI prompt instructions for a specific template."""
    template = TEMPLATES.get(template_id, TEMPLATES["general"])
    sections_desc = []
    for s in template["sections"]:
        req = "REQUIRED" if s["required"] else "optional"
        sections_desc.append(f"- {s['name']} ({req}): {s['description']}")
    return f"""DOCUMENT TEMPLATE: {template['name']}
Required sections for this template:
{chr(10).join(sections_desc)}

Extra fields if applicable: {', '.join(template.get('extra_fields', [])) or 'none'}
"""
