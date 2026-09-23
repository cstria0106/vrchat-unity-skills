"""Validate shared payload, catalog paths, manifests and portable documentation."""
import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]

def validate():
    plugin = ROOT / "plugins/avatar-head-transplant"
    manifests = [json.loads((plugin / p).read_text(encoding="utf8")) for p in
                 ["plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]]
    for field in ("name", "version", "description", "author", "license", "repository"):
        assert all(m[field] == manifests[0][field] for m in manifests), field
    assert manifests[0]["name"] == plugin.name
    catalogs = [json.loads((ROOT / p).read_text(encoding="utf8")) for p in
                [".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"]]
    assert catalogs[0]["name"] == catalogs[1]["name"] == "vrchat-unity-skills"
    for catalog in catalogs:
        entry, = catalog["plugins"]
        source = entry["source"]
        path = source["path"] if isinstance(source, dict) else source
        assert (ROOT / path).resolve() == plugin
        assert entry["name"] == manifests[0]["name"]
        if "version" in entry:
            assert entry["version"] == manifests[0]["version"]
    assert catalogs[0]["plugins"][0]["policy"] == {"installation":"AVAILABLE", "authentication":"ON_INSTALL"}
    skill = plugin / "skills/transplant-avatar-head"
    text = (skill / "SKILL.md").read_text(encoding="utf8")
    front = yaml.safe_load(text.split("---", 2)[1])
    assert front["name"] == skill.name and front["description"]
    assert "pause the transplant workflow" in text
    assert "user's language" in text
    for file in skill.rglob("*"):
        if not file.is_file() or file.suffix not in (".md", ".py", ".yaml"):
            continue
        body = file.read_text(encoding="utf8")
        assert not re.search(r"[\uac00-\ud7a3]", body), file
        assert not re.search(r"[A-Za-z]:[/\\](?:Users|Program Files)", body), file
        if file.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", body):
                if "://" not in target and not target.startswith("#"):
                    assert (file.parent / target.split("#")[0]).is_file(), (file, target)
    print("Distribution validation passed: shared skill, both hosts, English payload, relative links.")

if __name__ == "__main__":
    validate()
