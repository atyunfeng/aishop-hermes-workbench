import importlib.util
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/atyunfeng/aishop-hermes-workbench"
COMMUNITY_FILES = (
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "PRIVACY.md",
    "CHANGELOG.md",
    "TRADEMARKS.md",
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/pull_request_template.md",
)


def load_release_module():
    script = ROOT / "scripts" / "package-release.py"
    spec = importlib.util.spec_from_file_location("aishop_package_release", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agpl_license_and_package_metadata_are_consistent():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 19 November 2007" in license_text

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == "AGPL-3.0-only"
    assert pyproject["project"]["urls"]["Repository"] == SOURCE_URL

    for package_file in (ROOT / "package.json", ROOT / "desktop-plugin" / "package.json"):
        package = json.loads(package_file.read_text(encoding="utf-8"))
        assert package["license"] == "AGPL-3.0-only"
        assert package["repository"]["url"] == f"git+{SOURCE_URL}.git"


def test_third_party_notice_attributes_hermes_agent():
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "NousResearch/hermes-agent" in notice
    assert "MIT License" in notice
    assert "Copyright (c) 2025 Nous Research" in notice


def test_public_community_files_and_truth_boundary_exist():
    for relative in COMMUNITY_FILES:
        assert (ROOT / relative).is_file(), relative

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert SOURCE_URL in readme
    assert "Alpha" in readme
    assert "SIMULATED" in readme
    assert "尚未完成真实设备与平台账号验收" in readme


def test_release_bundle_inputs_include_corresponding_source_and_notices():
    module = load_release_module()
    included = set(module.INCLUDE_ROOTS)
    assert {
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "SECURITY.md",
        "PRIVACY.md",
        "pyproject.toml",
        "uv.lock",
        "package-lock.json",
        "hermes-plugin",
        "desktop-plugin",
        "android-worker",
        "packages",
    }.issubset(included)
    assert module.RELEASE_METADATA == {
        "product": "AIShop Hermes Workbench",
        "version": "0.1.0-alpha",
        "license": "AGPL-3.0-only",
        "source_url": SOURCE_URL,
    }


def test_apk_checksum_is_portable():
    verifier = (ROOT / "scripts" / "verify-android-worker.sh").read_text(encoding="utf-8")
    assert '"$(basename "$apk_target")" > "$apk_target.sha256"' in verifier


def test_interactive_clients_expose_source_url():
    desktop = (ROOT / "desktop-plugin" / "src" / "plugin.tsx").read_text(encoding="utf-8")
    android = (
        ROOT
        / "android-worker/app/src/main/java/com/aishop/worker/ui/WorkerScreen.kt"
    ).read_text(encoding="utf-8")
    assert SOURCE_URL in desktop
    assert SOURCE_URL in android


def test_github_workflows_pin_actions_and_use_explicit_permissions():
    workflows = tuple((ROOT / ".github" / "workflows").glob("*.yml"))
    assert {path.name for path in workflows} == {"ci.yml", "codeql.yml", "release.yml"}
    for workflow in workflows:
        content = workflow.read_text(encoding="utf-8")
        assert "permissions:" in content
        for reference in re.findall(r"^\s*uses:\s*([^\s#]+)", content, flags=re.MULTILINE):
            if reference.startswith("./"):
                continue
            assert re.search(r"@[0-9a-f]{40}$", reference), (workflow.name, reference)


def test_dependabot_covers_all_package_ecosystems():
    content = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    for ecosystem in ("pip", "npm", "gradle", "github-actions"):
        assert f'package-ecosystem: "{ecosystem}"' in content
