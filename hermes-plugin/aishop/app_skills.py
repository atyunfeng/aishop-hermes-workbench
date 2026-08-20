import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .execution_domain import ActionType, ExecutionStep

PLACEHOLDER = re.compile(r"^\{\{([a-z][a-z0-9_]*)\}\}$")
MANIFEST_KEYS = {
    "id",
    "name",
    "version",
    "package_aliases",
    "supported_app_versions",
    "fixture_version",
    "page_markers",
    "required_capabilities",
    "workflows",
}
WORKFLOW_KEYS = {"description", "risk_action", "required_inputs", "steps"}
STEP_KEYS = {"id", "action", "arguments", "timeout_seconds", "evidence_required"}


@dataclass(frozen=True, slots=True)
class AppSkill:
    skill_id: str
    name: str
    version: str
    package_aliases: tuple[str, ...]
    supported_app_versions: dict[str, dict[str, str | None]]
    fixture_version: int
    page_markers: dict[str, dict[str, Any]]
    required_capabilities: tuple[str, ...]
    workflows: dict[str, dict[str, Any]]


class AppSkillRegistry:
    def __init__(self, skills: dict[str, AppSkill]):
        self.skills = skills

    @classmethod
    def load(cls, root: str | Path) -> "AppSkillRegistry":
        skills: dict[str, AppSkill] = {}
        for path in sorted(Path(root).glob("*/manifest.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            unknown = set(raw) - MANIFEST_KEYS
            if unknown:
                raise ValueError(f"{path}: unknown manifest keys {sorted(unknown)}")
            if not MANIFEST_KEYS.issubset(raw):
                raise ValueError(f"{path}: missing manifest keys")
            if raw["id"] in skills:
                raise ValueError(f"duplicate app skill id {raw['id']}")
            if not raw["package_aliases"] or not raw["required_capabilities"]:
                raise ValueError(f"{path}: packages and capabilities must be non-empty")
            if set(raw["supported_app_versions"]) != set(raw["package_aliases"]):
                raise ValueError(f"{path}: every package alias needs a version range")
            for package_name, bounds in raw["supported_app_versions"].items():
                if set(bounds) != {"min", "max"} or not bounds["min"]:
                    raise ValueError(f"{path}: invalid version range for {package_name}")
                cls._version_tuple(bounds["min"])
                if bounds["max"] is not None:
                    cls._version_tuple(bounds["max"])
                if bounds["max"] is not None and not cls._version_in_range(
                    bounds["max"], bounds["min"], None
                ):
                    raise ValueError(f"{path}: inverted version range for {package_name}")
            if raw["fixture_version"] < 1 or not raw["page_markers"]:
                raise ValueError(f"{path}: fixture metadata is required")
            workflows = raw["workflows"]
            if not workflows:
                raise ValueError(f"{path}: workflows must be non-empty")
            for workflow_id, workflow in workflows.items():
                if set(workflow) != WORKFLOW_KEYS:
                    raise ValueError(f"{path}: invalid workflow {workflow_id} keys")
                for step in workflow["steps"]:
                    if set(step) != STEP_KEYS:
                        raise ValueError(f"{path}: invalid step keys")
                    ActionType(step["action"])
                    if {"x", "y", "coordinates", "shell", "script"}.intersection(step["arguments"]):
                        raise ValueError(f"{path}: unsafe step arguments")
            skills[raw["id"]] = AppSkill(
                raw["id"],
                raw["name"],
                raw["version"],
                tuple(raw["package_aliases"]),
                raw["supported_app_versions"],
                raw["fixture_version"],
                raw["page_markers"],
                tuple(raw["required_capabilities"]),
                workflows,
            )
            fixtures = sorted(path.parent.glob("fixtures/*.json"))
            if not fixtures:
                raise ValueError(f"{path}: at least one selector fixture is required")
            for fixture_path in fixtures:
                cls._validate_fixture(skills[raw["id"]], fixture_path)
        if not skills:
            raise ValueError("no App Skill manifests found")
        return cls(skills)

    @staticmethod
    def _validate_fixture(skill: AppSkill, fixture_path: Path) -> None:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        if fixture.get("fixture_version") != skill.fixture_version:
            raise ValueError(f"{fixture_path}: fixture version mismatch")
        if fixture.get("package_name") not in skill.package_aliases:
            raise ValueError(f"{fixture_path}: fixture package is not an alias")
        page = fixture.get("page")
        if page not in skill.page_markers:
            raise ValueError(f"{fixture_path}: unknown page marker")
        nodes = fixture.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError(f"{fixture_path}: fixture nodes are required")
        marker = skill.page_markers[page]
        matches = 0
        for node in nodes:
            matches_marker = (
                any(node.get("text") == value for value in marker.get("text_any", []))
                or any(
                node.get("content_description") == value
                for value in marker.get("description_any", [])
                )
                or any(
                    node.get("view_id") == value
                    for value in marker.get("view_id_any", [])
                )
            )
            if matches_marker:
                matches += 1
        if matches != 1:
            raise ValueError(f"{fixture_path}: page marker must match exactly one node")

    def supports_app_version(
        self, skill_id: str, package_name: str, version_name: str
    ) -> bool:
        skill = self.get(skill_id)
        if package_name not in skill.package_aliases:
            return False
        bounds = skill.supported_app_versions[package_name]
        return self._version_in_range(version_name, bounds["min"], bounds.get("max"))

    @classmethod
    def _version_in_range(
        cls, value: str, minimum_value: str, maximum_value: str | None
    ) -> bool:
        versions = [cls._version_tuple(value), cls._version_tuple(minimum_value)]
        if maximum_value is not None:
            versions.append(cls._version_tuple(maximum_value))
        width = max(len(version) for version in versions)
        padded = [version + (0,) * (width - len(version)) for version in versions]
        value_version, minimum = padded[:2]
        maximum = padded[2] if maximum_value is not None else None
        return value_version >= minimum and (maximum is None or value_version <= maximum)

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        parts = value.split(".")
        if not parts or any(not part.isdecimal() for part in parts):
            raise ValueError("app versions must use numeric dotted form")
        return tuple(int(part) for part in parts)

    def get(self, skill_id: str) -> AppSkill:
        try:
            return self.skills[skill_id]
        except KeyError as error:
            raise ValueError(f"unknown App Skill {skill_id}") from error

    def compile(
        self,
        skill_id: str,
        workflow_id: str,
        inputs: dict[str, Any],
        task_id: str,
        mode: str = "DEVICE",
    ) -> dict[str, Any]:
        skill = self.get(skill_id)
        try:
            workflow = skill.workflows[workflow_id]
        except KeyError as error:
            raise ValueError(f"unknown workflow {skill_id}.{workflow_id}") from error
        required = set(workflow["required_inputs"])
        missing = required - set(inputs)
        unknown = set(inputs) - required
        if missing or unknown:
            raise ValueError(f"workflow inputs missing={sorted(missing)} unknown={sorted(unknown)}")
        package_name = inputs.get("package_name")
        if package_name is not None and package_name not in skill.package_aliases:
            raise ValueError("package_name is not a declared alias")
        safe_inputs = {key: self._safe_input(value) for key, value in inputs.items()}
        steps = []
        for ordinal, template in enumerate(workflow["steps"]):
            arguments = self._expand(template["arguments"], safe_inputs)
            step = ExecutionStep(
                step_id=f"{task_id}:{template['id']}",
                ordinal=ordinal,
                action=ActionType(template["action"]),
                arguments=arguments,
                timeout_seconds=template["timeout_seconds"],
                evidence_required=template["evidence_required"],
            )
            steps.append(
                {
                    "step_id": step.step_id,
                    "ordinal": step.ordinal,
                    "action": step.action,
                    "arguments": step.arguments,
                    "timeout_seconds": step.timeout_seconds,
                    "evidence_required": step.evidence_required,
                }
            )
        return {
            "job_id": str(uuid4()),
            "task_id": task_id,
            "app_skill_id": skill.skill_id,
            "skill_version": skill.version,
            "required_packages": list(skill.package_aliases),
            "supported_app_versions": skill.supported_app_versions,
            "required_capabilities": list(skill.required_capabilities),
            "mode": mode,
            "risk_action": workflow["risk_action"],
            "steps": steps,
        }

    @staticmethod
    def _safe_input(value: Any) -> Any:
        if not isinstance(value, str) or not 1 <= len(value) <= 2000:
            raise ValueError("App Skill inputs must be strings of 1 to 2000 characters")
        return value

    @classmethod
    def _expand(cls, value: Any, inputs: dict[str, Any]) -> Any:
        if isinstance(value, str):
            match = PLACEHOLDER.fullmatch(value)
            if match:
                key = match.group(1)
                if key not in inputs:
                    raise ValueError(f"undeclared placeholder {key}")
                return inputs[key]
            if "{{" in value or "}}" in value:
                raise ValueError("placeholders must occupy the complete string")
            return value
        if isinstance(value, list):
            return [cls._expand(item, inputs) for item in value]
        if isinstance(value, dict):
            return {key: cls._expand(item, inputs) for key, item in value.items()}
        return value
