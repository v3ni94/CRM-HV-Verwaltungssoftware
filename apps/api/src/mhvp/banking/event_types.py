"""Domain event types of the banking module (ADR 0014, plan M12 S0).

One place for the names so producers (routers, services) and the consumer
(``mhvp.banking.events_consumer``) cannot drift apart. Events are written in the same
transaction as the change (``mhvp.core.events.emit``); nothing here posts or pays.
"""

# Bank rule lifecycle (6.9.4). ``superseded`` and ``downgraded`` are produced by the learning
# module (S5) and the runner (S6); they are named here so the consumer and the audit export
# know them from the start.
BANK_RULE_PROPOSED = "bank_rule.proposed"
BANK_RULE_APPROVED = "bank_rule.approved"
BANK_RULE_ACTIVATED = "bank_rule.activated"
BANK_RULE_DISABLED = "bank_rule.disabled"
BANK_RULE_SUPERSEDED = "bank_rule.superseded"
BANK_RULE_DOWNGRADED = "bank_rule.downgraded"

# Transactions and decisions (S1).
BANK_TRANSACTION_BOOKED = "bank_transaction.booked"
BANK_TRANSACTION_IGNORED = "bank_transaction.ignored"
BANK_TRANSACTION_REOPENED = "bank_transaction.reopened"
BANK_TRANSACTION_REVIEWED = "bank_transaction.reviewed"
BANK_TRANSACTION_PROPOSAL_REJECTED = "bank_transaction.proposal_rejected"
BANK_TRANSACTION_POSTING_REVERSED = "bank_transaction.posting_reversed"
POSTING_DECISIONS_COMPUTED = "posting_decision.computed"

# Tenant switches.
TENANT_LEARNING_BOOKKEEPER_CHANGED = "tenant.learning_bookkeeper_changed"

# Events of other modules the banking consumer reads (never imported from there: no import of
# banking into accounting, plan 3.1 no. 9).
JOURNAL_ENTRY_REVERSED = "journal_entry.reversed"
CONTACT_DELETED = "contact.deleted"
INVOICE_UPDATED = "invoice.updated"
