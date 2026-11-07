import csv
import json
from pathlib import Path

import pytest

from src.redam.pipeline import (clean, count, demo, digest, kappa, prepare,
                                pseudonym, release, timestamp, validate, write_json)
from src.redam.collect import validate_url


def test_privacy_and_nullable_metadata():
    result = clean("  Halo @andi 🔥 a@b.id +62 812-1234-5678 https://example.com/a  ")
    assert result == "Halo [USER] 🔥 [EMAIL] [PHONE] [URL]"
    assert timestamp("3j") is None
    assert timestamp("2026-01-01T12:00:00") is None
    assert timestamp("2026-01-01T07:00:00+07:00") == "2026-01-01T00:00:00+00:00"
    assert count(None) is None and count("0") == 0 and count("-1") is None
    assert pseudonym("x", "case1", "andi") != pseudonym("x", "case2", "andi")


def test_demo_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("REDAM_DATASET_SECRET", "a" * 32)
    source, package = tmp_path / "source", tmp_path / "package"
    result = demo(source)
    assert result["cases"] == 12 and not result["human_annotated"]
    checksum = digest(source / "repetition.json")
    report = prepare(source / "manifest.json", package)
    assert report["comments"] == 509
    assert digest(source / "repetition.json") == checksum
    comments = json.loads((package / "comments.json").read_text())
    repeated = [c for c in comments if c["case_id"] == "repetition"]
    assert len(repeated) == 30 and len({c["text"] for c in repeated}) == 1
    assert all(c["created_at"] is None for c in comments if c["case_id"] == "no_time")
    assert all(c["account_ref"] is None for c in comments if c["case_id"] == "no_account")
    assert any(c["truncated"] for c in comments)
    result, _ = validate(package)
    assert not result["ready_for_training"] and result["errors"]
    with pytest.raises(FileExistsError):
        prepare(source / "manifest.json", package)


def test_dedup_is_identity_based(tmp_path, monkeypatch):
    monkeypatch.setenv("REDAM_DATASET_SECRET", "a" * 32)
    source = tmp_path / "source"
    demo(source)
    raw = source / "organic.json"
    rows = json.loads(raw.read_text())
    rows.append(rows[0].copy())
    rows.append({**rows[0], "comment_id": "another"})
    raw.write_text(json.dumps(rows))
    package = tmp_path / "package"
    report = prepare(source / "manifest.json", package)
    assert report["excluded"] == 1
    assert report["comments"] == 510


def test_synthetic_cannot_be_live(tmp_path, monkeypatch):
    monkeypatch.setenv("REDAM_DATASET_SECRET", "a" * 32)
    demo(tmp_path / "source")
    p = tmp_path / "source/manifest.json"
    manifest = json.loads(p.read_text())
    manifest["cases"][0]["source_type"] = "live"
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Sintetis"):
        prepare(p, tmp_path / "package")


def test_missing_secret_and_source_conflict(tmp_path, monkeypatch):
    monkeypatch.delenv("REDAM_DATASET_SECRET", raising=False)
    demo(tmp_path / "source")
    with pytest.raises(ValueError, match="SECRET"):
        prepare(tmp_path / "source/manifest.json", tmp_path / "package")
    monkeypatch.setenv("REDAM_DATASET_SECRET", "a" * 32)
    path = tmp_path / "source/organic.json"
    rows = json.loads(path.read_text())
    rows.append({**rows[0], "text": "conflicting version"})
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="ID sama"):
        prepare(tmp_path / "source/manifest.json", tmp_path / "package")


@pytest.mark.parametrize("url", ["http://www.instagram.com/p/abc/", "https://localhost/p/x",
    "https://www.instagram.com.evil.com/p/x", "https://u:p@www.instagram.com/p/x", "https://www.instagram.com:88/p/x",
    "https://www.instagram.com/accounts/login/"])
def test_browser_url_guard(url):
    with pytest.raises(ValueError):
        validate_url(url, "instagram", resolve=False)


def test_url_and_kappa():
    assert validate_url("https://www.instagram.com/p/abc/?tracking=x", "instagram", False) == "https://www.instagram.com/p/abc/"
    assert kappa(["none", "strong"], ["none", "strong"], ["none", "uncertain", "strong"], True) == 1
    assert kappa([True], [True], [False, True]) is None


def test_release_with_realistic_review_workflow(tmp_path, monkeypatch):
    """Manufactured test records only; never presented as actual human annotation."""
    monkeypatch.setenv("REDAM_DATASET_SECRET", "a" * 32)
    source = tmp_path / "source"
    source.mkdir()
    specs = []
    words = ["apel", "becak", "catur", "domba", "elang", "fisika", "gudang", "hutan", "ikan", "jerami"]
    for i, word in enumerate(words):
        write_json(source / f"{word}.json", [{"comment_id": str(j), "text": f"{word} {j}"} for j in range(20)])
        specs.append({"case_id": word, "input": f"{word}.json", "topic_group": word, "platform": "instagram",
                      "period": f"2026-{i+1:02}-01", "rights_reference": "TEST ONLY", "retention_until": "2099-01-01T00:00:00Z",
                      "source_type": "demo", "origin": "licensed"})
    write_json(source / "manifest.json", {"cases": specs})
    package = tmp_path / "package"
    prepare(source / "manifest.json", package)
    with (package / "annotations.csv").open(newline="") as f:
        reader = csv.DictReader(f); fields = reader.fieldnames; annotations = list(reader)
    for i, row in enumerate(annotations):
        positive = i // 2 % 2 == 1
        row.update(label="uncertain" if positive else "none", evidence_labels="exact_text_repetition" if positive else "",
                   evidence_refs="c_0001" if positive else "", note="Manufactured unit test annotation")
    with (package / "annotations.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(annotations)
    assert validate(package)[0]["annotations_valid"]
    audit = tmp_path / "audit.json"
    write_json(audit, {"reviewer": "TEST ONLY", "pii_review_passed": True, "rights_review_passed": True,
                       "package_sha256": digest(package / "checksums.json")})
    output = tmp_path / "release"
    release(package, output, audit)
    assignment = json.loads((output / "split_manifest.json").read_text())
    assert set(assignment.values()) == {"train", "validation", "test"}
    assert all((output / f"{s}.jsonl").stat().st_size for s in set(assignment.values()))
    # Reproduce a leak in otherwise valid input, with a fresh integrity manifest.
    comments_path = package / "comments.json"
    comments = json.loads(comments_path.read_text())
    comments[-1]["text"] = comments[0]["text"]
    comments_path.write_text(json.dumps(comments))
    checksums_path = package / "checksums.json"
    checksums = json.loads(checksums_path.read_text())
    checksums["comments.json"] = digest(comments_path)
    checksums_path.write_text(json.dumps(checksums))
    audit_data = json.loads(audit.read_text())
    audit_data["package_sha256"] = digest(checksums_path)
    audit.write_text(json.dumps(audit_data))
    with pytest.raises(ValueError, match="Kebocoran"):
        release(package, tmp_path / "leaked_release", audit)
    assert not (tmp_path / "leaked_release").exists()
    # Accidental edits are detected before export.
    (package / "comments.json").write_text("[]")
    assert not validate(package)[0]["ready_for_training"]
