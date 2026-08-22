"""Tests for resume_document_check.py."""

from lambdas.match.resume_document_check import verify_is_resume

RESUME_SAMPLE = (
    "Raj Kumar | raj.kumar@email.com | +91 9988776655\n"
    "Education: B.Tech Engineering\n"
    "Experience: Software intern at Tech Corp. Skills: Python, AWS.\n"
)

INVOICE_SAMPLE = (
    "TAX INVOICE\nInvoice Number: INV-99\nBill To: Client\n"
    "Amount Due: 5000\nGSTIN: 29AAAAA0000A1Z5\n"
)


def test_heuristic_accepts_resume():
    ok, reason = verify_is_resume(RESUME_SAMPLE)
    assert ok is True
    assert reason


def test_heuristic_rejects_invoice():
    ok, reason = verify_is_resume(INVOICE_SAMPLE)
    assert ok is False
    assert reason


def test_groq_classifier_rejects_non_resume():
    def fake_groq(messages):
        return '{"isResume": false, "documentType": "invoice", "reason": "Tax invoice"}'

    ok, _ = verify_is_resume("Some ambiguous document text without clear signals.", fake_groq)
    assert ok is False
