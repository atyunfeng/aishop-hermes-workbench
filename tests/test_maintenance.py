from datetime import UTC, datetime, timedelta

from aishop.execution_domain import EvidenceSource
from aishop.execution_repository import ExecutionRepository
from aishop.maintenance import MaintenanceService
from aishop.repository import TaskRepository
from aishop.service import TaskService

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_diagnostics_cleanup_and_redacted_export(tmp_path):
    database = tmp_path / "aishop.db"
    tasks = TaskService(TaskRepository(database))
    tasks.create_task("real:1", "we-chat", "reply")
    execution = ExecutionRepository(database, tmp_path / "evidence")
    execution.store_evidence(
        "task", "job", "step", EvidenceSource.SIMULATED, "text/plain", b"old",
        "old", NOW - timedelta(days=8),
    )
    maintenance = MaintenanceService(database, execution)
    before = maintenance.diagnostics()
    assert before["counts"]["tasks"] == 1
    assert before["evidence_bytes"] == 3
    result = maintenance.run(NOW)
    assert result["evidence"]["removed"] == 1
    exported = maintenance.export_redacted()
    assert exported["tables"]["tasks"][0]["title"] == "reply"
    assert "token_digest" not in str(exported)
