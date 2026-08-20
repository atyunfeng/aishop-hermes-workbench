import hashlib
from datetime import datetime

from .execution_domain import RiskLevel
from .execution_repository import ApprovalConflict, ExecutionRepository

HUMAN_ONLY_SIGNALS = frozenset({"captcha", "login_failure", "unknown_page"})
APPROVAL_ACTIONS = frozenset(
    {"money", "account", "delete", "add_contact", "bulk_send", "refund", "return_goods"}
)
LOW_RISK_ACTIONS = frozenset({"read", "query", "reply", "send_test_message"})


class PolicyDenied(PermissionError):
    pass


class PolicyEngine:
    def __init__(self, repository: ExecutionRepository, allowed_recipients: set[str]):
        self.repository = repository
        self.allowed_recipients = allowed_recipients

    def classify(self, action: str, context: dict[str, object]) -> RiskLevel:
        signals = set(context.get("signals", []))
        if signals.intersection(HUMAN_ONLY_SIGNALS):
            return RiskLevel.HUMAN_ONLY
        if action in APPROVAL_ACTIONS:
            return RiskLevel.APPROVAL_REQUIRED
        if action in LOW_RISK_ACTIONS and context.get("recipient") in self.allowed_recipients:
            return RiskLevel.LOW
        return RiskLevel.HUMAN_ONLY

    def authorize(
        self,
        action: str,
        context: dict[str, object],
        approval_token: str | None,
        now: datetime,
    ) -> RiskLevel:
        risk = self.classify(action, context)
        if risk is RiskLevel.LOW:
            return risk
        if risk is RiskLevel.HUMAN_ONLY:
            raise PolicyDenied("action requires human takeover")
        if approval_token is None:
            raise PolicyDenied("action requires scoped approval")
        try:
            self.repository.consume_approval(
                hashlib.sha256(approval_token.encode()).hexdigest(), action, context, now
            )
        except ApprovalConflict as error:
            raise PolicyDenied(str(error)) from error
        return risk
