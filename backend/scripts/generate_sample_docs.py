"""Generate the bundled sample corpus (md / docx / txt / pdf) and the labelled eval questions.

All content is fictional ("Acme Corp"). Run:  python scripts/generate_sample_docs.py
Outputs: data/sample_docs/*  and  data/eval/questions.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "sample_docs"
EVAL = ROOT / "data" / "eval"

# --------------------------------------------------------------------------- content
HANDBOOK_MD = """# Acme Corp Employee Handbook

This handbook describes how Acme Corp works with its employees. It applies to all full-time and part-time staff.

## Paid Time Off

Full-time employees accrue 20 days of paid time off (PTO) per calendar year, which is 1.67 days per month. Part-time employees accrue PTO in proportion to their scheduled hours.

Up to 5 unused PTO days carry over into the next year. Any balance above 5 days expires on January 31. Requests for more than 3 consecutive days must be submitted in Workday at least 2 weeks in advance.

## Remote and Hybrid Work

Acme follows a hybrid model. Employees are expected to work from the office at least 2 days per week, and Tuesday and Thursday are the anchor days for team collaboration. Fully remote arrangements require written approval from a Vice President.

New remote employees receive a one-time home office stipend of $500. Working from another country is allowed for a maximum of 20 days per calendar year and requires prior review by Legal and Tax.

## Expense Reimbursement

Submit expense reports in Expensify within 30 days of the purchase. Receipts are required for every expense over $25. Meals while traveling are reimbursed up to $75 per day. Flights shorter than 6 hours must be booked in economy class; premium economy is allowed for longer flights.

Expenses above $500 need manager approval, and anything above $5,000 also needs approval from Finance.

## Parental Leave

The primary caregiver receives 16 weeks of fully paid parental leave, and the secondary caregiver receives 8 weeks. Leave must begin within 12 months of the birth or adoption of the child.

## Learning and Development

Every employee has an annual learning budget of $1,500 that can be spent on courses, books, and conferences. Unused budget does not roll over.

## Code of Conduct and Reporting Concerns

Acme expects respectful and honest behavior from everyone. Concerns can be reported to your manager, to HR, or anonymously through the ethics hotline at 1-800-555-0142. Retaliation against anyone who reports a concern in good faith is strictly prohibited.
"""

SECURITY_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Passwords and Authentication",
        [
            "Passwords must be at least 14 characters long. Passwords are not rotated on a fixed schedule; "
            "they must be changed immediately when a compromise is suspected.",
            "Multi-factor authentication (MFA) is mandatory for every corporate system. Access to production "
            "systems and administrator consoles additionally requires a FIDO2 hardware security key.",
        ],
    ),
    (
        "Data Classification",
        [
            "Company data is classified as Public, Internal, Confidential, or Restricted. Restricted data "
            "includes customer personal information and payment data.",
            "Restricted data must be encrypted with AES-256 at rest and with TLS 1.2 or higher in transit. "
            "Restricted data must never be copied to personal devices or personal cloud storage.",
        ],
    ),
    (
        "Security Incident Reporting",
        [
            "Any suspected security incident must be reported to security@acme.example within 1 hour of discovery.",
            "If a confirmed breach involves personal data of EU residents, Acme must notify the supervisory "
            "authority and affected customers within 72 hours as required by GDPR.",
        ],
    ),
    (
        "Device Security",
        [
            "All laptops must use full-disk encryption, lock automatically after 5 minutes of inactivity, "
            "and be enrolled in Jamf mobile device management.",
            "A lost or stolen device must be reported within 4 hours so that it can be remotely wiped.",
        ],
    ),
    (
        "Vendor Risk and Access Reviews",
        [
            "New vendors must pass a security review before use. Vendors that handle Confidential or Restricted "
            "data must provide a current SOC 2 Type II report, and are re-reviewed every year.",
            "User access is reviewed quarterly by system owners. Access for terminated employees is revoked "
            "within 24 hours of their departure. This policy is tracked as SEC-POL-014.",
        ],
    ),
]

FAQ_TXT = """ACME CLOUDSYNC - PRODUCT FAQ

PLANS AND PRICING
CloudSync has three plans. The Starter plan costs $12 per user per month, supports up to 10 users, and includes 100 GB of storage. The Business plan costs $29 per user per month and adds single sign-on (SSO), 1 TB of storage per user, and audit logs. The Enterprise plan has custom pricing and adds SAML provisioning, a dedicated support engineer, and a 99.99% uptime SLA. Every plan includes a free 14-day trial.

API RATE LIMITS
API requests are rate limited per workspace. Starter allows 60 requests per minute, Business allows 600 requests per minute, and Enterprise allows 6,000 requests per minute. When the limit is exceeded the API returns HTTP 429 together with a Retry-After header that tells the client how many seconds to wait.

SERVICE LEVEL AGREEMENT
The Business plan is covered by a 99.9% monthly uptime SLA. If uptime falls below 99.9% the customer receives a service credit of 10% of the monthly fee, and if uptime falls below 99.0% the credit is 25% of the monthly fee. Credits must be requested within 30 days.

DATA RETENTION AND RECOVERY
Deleted files stay recoverable for 30 days on the Starter plan and for 90 days on the Business plan. After that they are permanently removed. Customers can export all of their data as CSV or JSON at any time.

SUPPORT
Starter customers get email support with a 48 hour response target. Business customers get chat support Monday to Friday with a 4 hour response target. Enterprise customers get 24/7 support, with a 1 hour response target for Severity 1 issues.

REGIONS
Workspaces can be hosted in US-East, EU-Frankfurt, or AP-Singapore. The region is chosen at workspace creation and cannot be changed afterwards.
"""

RUNBOOK_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Severity Levels",
        [
            "SEV-1 is a full outage or data loss. The on-call engineer is paged immediately, an incident "
            "commander must be assigned within 10 minutes, and the public status page must be updated within 15 minutes.",
            "SEV-2 is a major degradation with a workaround and requires a response within 30 minutes. "
            "SEV-3 is a minor issue and is handled on the next business day.",
        ],
    ),
    (
        "On-Call Rotation",
        [
            "On-call rotates weekly with a primary and a secondary engineer. The handoff happens every Monday at "
            "10:00 UTC and is coordinated in PagerDuty.",
        ],
    ),
    (
        "Rollback Procedure",
        [
            "To roll back a bad release run: kubectl rollout undo deployment/api-gateway -n production. "
            "New releases are first deployed to a 5% canary for 15 minutes before full rollout.",
        ],
    ),
    (
        "Common Error Codes",
        [
            "ERR-5031 means the database connection pool is exhausted. Raise DB_POOL_MAX to 200 and restart the "
            "affected pods.",
            "ERR-4290 indicates a misconfigured rate limiter. ERR-7002 means the message queue backlog is above "
            "10,000 messages; scale the worker deployment to clear it.",
        ],
    ),
    (
        "Backups and Recovery",
        [
            "Postgres uses point-in-time recovery with WAL archived every 5 minutes, plus a daily snapshot kept "
            "for 35 days. The recovery time objective (RTO) is 4 hours and the recovery point objective (RPO) is 5 minutes. "
            "Restore drills run every quarter.",
        ],
    ),
    (
        "Postmortems",
        [
            "A blameless postmortem is required for every SEV-1 and SEV-2 incident and must be published within "
            "5 business days. If customer data was exposed, the Security team must also follow the incident "
            "reporting steps in the Security Policy.",
        ],
    ),
]

# id, question, ground_truth, relevant_docs, evidence (substring that must be present in a relevant chunk)
QUESTIONS = [
    ("q01", "How many PTO days do full-time employees get each year?", "20 days per calendar year.",
     ["employee_handbook.md"], ["20 days"]),
    ("q02", "How many weeks of paid parental leave does the primary caregiver get?",
     "16 weeks of fully paid leave.", ["employee_handbook.md"], ["16 weeks"]),
    ("q03", "What is the daily meal allowance when I am traveling?", "$75 per day.",
     ["employee_handbook.md"], ["$75 per day"]),
    ("q04", "How long do I have to submit an expense report?", "Within 30 days of the purchase.",
     ["employee_handbook.md"], ["within 30 days"]),
    ("q05", "How many days per year can I work from another country?", "A maximum of 20 days per calendar year.",
     ["employee_handbook.md"], ["maximum of 20 days"]),
    ("q06", "What is the minimum password length?", "14 characters.",
     ["security_policy.docx"], ["14 characters"]),
    ("q07", "How quickly must a suspected security incident be reported?", "Within 1 hour of discovery.",
     ["security_policy.docx"], ["within 1 hour"]),
    ("q08", "What encryption is required for Restricted data?",
     "AES-256 at rest and TLS 1.2 or higher in transit.", ["security_policy.docx"], ["AES-256"]),
    ("q09", "How soon is access revoked after an employee leaves the company?", "Within 24 hours.",
     ["security_policy.docx"], ["within 24 hours"]),
    ("q10", "How much does the Business plan cost per user?", "$29 per user per month.",
     ["product_faq.txt"], ["$29 per user per month"]),
    ("q11", "What is the API rate limit on the Enterprise plan?", "6,000 requests per minute.",
     ["product_faq.txt"], ["6,000 requests per minute"]),
    ("q12", "What SLA credit is given if uptime drops below 99.9%?", "A 10% service credit.",
     ["product_faq.txt"], ["credit of 10%"]),
    ("q13", "How long can deleted files be recovered on the Business plan?", "90 days.",
     ["product_faq.txt"], ["90 days on the Business plan"]),
    ("q14", "What does error ERR-5031 mean and how do I fix it?",
     "The database connection pool is exhausted; raise DB_POOL_MAX to 200 and restart the affected pods.",
     ["incident_runbook.pdf"], ["ERR-5031"]),
    ("q15", "What are the RTO and RPO for database recovery?", "RTO is 4 hours and RPO is 5 minutes.",
     ["incident_runbook.pdf"], ["recovery time objective"]),
    ("q16", "Within how many minutes must an incident commander be assigned for a SEV-1?", "Within 10 minutes.",
     ["incident_runbook.pdf"], ["within 10 minutes"]),
    ("q17", "Which command rolls back the api-gateway deployment?",
     "kubectl rollout undo deployment/api-gateway -n production",
     ["incident_runbook.pdf"], ["kubectl rollout undo"]),
    ("q18", "If a SEV-1 incident exposes EU customer data, what must happen and by when?",
     "Follow the Security Policy incident reporting steps: notify the authority and affected customers within 72 hours (GDPR); "
     "the runbook also requires a blameless postmortem within 5 business days.",
     ["security_policy.docx", "incident_runbook.pdf"], ["within 72 hours", "within 5 business days"]),
]


# Harder retrieval cases. "paraphrase": little word overlap with the source text (dense retrieval should win).
# "keyword": exact identifiers / codes (BM25 should win). Same tuple layout as QUESTIONS.
PARAPHRASE_QUESTIONS = [
    ("p01", "What is the yearly vacation allowance for permanent employees?", "20 days per calendar year.",
     ["employee_handbook.md"], ["20 days of paid time off"]),
    ("p02", "How long can a new mother stay at home on full salary after having a baby?",
     "16 weeks of fully paid parental leave for the primary caregiver.", ["employee_handbook.md"],
     ["16 weeks of fully paid parental leave"]),
    ("p03", "What are the rules about coming into the office?",
     "At least 2 days per week, with Tuesday and Thursday as anchor days.", ["employee_handbook.md"],
     ["at least 2 days per week"]),
    ("p04", "How much money do I get to set up my workspace at home?", "A one-time home office stipend of $500.",
     ["employee_handbook.md"], ["home office stipend of $500"]),
    ("p05", "What is the shortest secret phrase allowed for logging in?", "Passwords need at least 14 characters.",
     ["security_policy.docx"], ["at least 14 characters long"]),
    ("p06", "How fast must I tell the security team when something suspicious happens?", "Within 1 hour of discovery.",
     ["security_policy.docx"], ["within 1 hour of discovery"]),
    ("p07", "What happens to a former colleague's system privileges after they depart?",
     "Their access is revoked within 24 hours of departure.", ["security_policy.docx"],
     ["within 24 hours of their departure"]),
    ("p08", "Which subscription tier includes single sign-on?", "The Business plan (Enterprise adds SAML provisioning).",
     ["product_faq.txt"], ["single sign-on (sso)"]),
    ("p09", "How can I get compensation if the service is unavailable too often?",
     "A service credit of 10% of the monthly fee if uptime falls below 99.9%.", ["product_faq.txt"],
     ["service credit of 10%"]),
    ("p10", "Who is the first person paged when production breaks completely?",
     "The on-call engineer is paged immediately for a SEV-1.", ["incident_runbook.pdf"],
     ["on-call engineer is paged immediately"]),
]

KEYWORD_QUESTIONS = [
    ("k01", "What does SEC-POL-014 refer to?", "The tracking ID of the Information Security Policy.",
     ["security_policy.docx"], ["SEC-POL-014"]),
    ("k02", "What does ERR-7002 mean?",
     "The message queue backlog is above 10,000 messages; scale the worker deployment.",
     ["incident_runbook.pdf"], ["ERR-7002"]),
    ("k03", "What is ERR-4290?", "A misconfigured rate limiter.", ["incident_runbook.pdf"], ["ERR-4290"]),
    ("k04", "What is DB_POOL_MAX used for?",
     "Raising it to 200 fixes ERR-5031, an exhausted database connection pool.", ["incident_runbook.pdf"],
     ["DB_POOL_MAX"]),
    ("k05", "What is 1-800-555-0142?", "Acme's anonymous ethics hotline.", ["employee_handbook.md"],
     ["1-800-555-0142"]),
    ("k06", "What is FIDO2 needed for?", "Production and administrator access requires a FIDO2 hardware security key.",
     ["security_policy.docx"], ["FIDO2 hardware security key"]),
    ("k07", "Is AP-Singapore a supported region?",
     "Yes - workspaces can be hosted in US-East, EU-Frankfurt, or AP-Singapore.", ["product_faq.txt"],
     ["AP-Singapore"]),
    ("k08", "What is Jamf used for?", "Mobile device management enrollment for laptops.", ["security_policy.docx"],
     ["Jamf"]),
]


# --------------------------------------------------------------------------- writers
def write_docx(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    from docx import Document

    doc = Document()
    doc.add_heading(title, level=0)
    for heading, paras in sections:
        doc.add_heading(heading, level=1)
        for p in paras:
            doc.add_paragraph(p)
    doc.save(path)


def write_pdf(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for i, (heading, paras) in enumerate(sections):
        story.append(Paragraph(heading, styles["Heading2"]))
        for p in paras:
            story.append(Paragraph(p.replace("&", "&amp;"), styles["BodyText"]))
            story.append(Spacer(1, 6))
        if i == 2:  # force a second page so page metadata is exercised
            story.append(PageBreak())
    SimpleDocTemplate(str(path), pagesize=A4, title=title, author="Acme Corp").build(story)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    (DOCS / "employee_handbook.md").write_text(HANDBOOK_MD, encoding="utf-8")
    (DOCS / "product_faq.txt").write_text(FAQ_TXT, encoding="utf-8")
    write_docx(DOCS / "security_policy.docx", "Acme Corp Information Security Policy", SECURITY_SECTIONS)
    write_pdf(DOCS / "incident_runbook.pdf", "Acme Corp Incident Response Runbook", RUNBOOK_SECTIONS)
    payload = [
        {"id": q[0], "category": cat, "question": q[1], "ground_truth": q[2], "relevant_docs": q[3], "evidence": q[4]}
        for cat, group in (("standard", QUESTIONS), ("paraphrase", PARAPHRASE_QUESTIONS), ("keyword", KEYWORD_QUESTIONS))
        for q in group
    ]
    (EVAL / "questions.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(list(DOCS.iterdir()))} documents and {len(payload)} eval questions")


if __name__ == "__main__":
    main()
