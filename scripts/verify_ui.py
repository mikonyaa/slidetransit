"""Verify the real offline report in a task-owned Chromium process.

Use --browser-executable for an installed Chrome without touching its profile.
The --base-url option repeats checks on the published static sample.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from slidetransit.limits import DEFAULT_LIMITS, sha256
from slidetransit.manifest import validate
from slidetransit.models import fingerprint, update_summary
from slidetransit.report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--browser-executable")
    parser.add_argument("--base-url")
    parser.add_argument("--cli", type=Path, help="Installed consumer CLI for downloaded decisions")
    parser.add_argument(
        "--incomplete",
        type=Path,
        help="An accepted report with an unavailable text/geometry channel",
    )
    parser.add_argument(
        "--grid-report", type=Path, help="Report with unavailable native raster grid comparison"
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True)
    demo = args.demo.resolve()
    cli = str(args.cli.resolve()) if args.cli else "slidetransit"
    original_hashes = {str(p.relative_to(demo)): sha256(p) for p in demo.rglob("*") if p.is_file()}
    target = args.base_url or (demo / "clipped/report.html").as_uri()
    events, checks, frames = [], [], []
    with sync_playwright() as playwright:
        options = {"headless": True}
        if args.browser_executable:
            options["executable_path"] = args.browser_executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(accept_downloads=True)
        if not args.base_url:
            context.set_offline(True)
        context.add_init_script("""for (const name of ['localStorage','sessionStorage','indexedDB']) {
          Object.defineProperty(window, name, {get(){throw new Error('Persistent storage disabled for QA');}});
        }""")
        page = context.new_page()
        page.on("pageerror", lambda error: events.append(str(error)))
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        for width in [1440, 1024, 390]:
            page.set_viewport_size({"width": width, "height": 1000 if width == 390 else 1000})
            page.goto(target, wait_until="load")
            page.get_by_role("heading", name="An export changed.").wait_for()
            page.evaluate("document.fonts.ready")
            assert page.locator(".finding.selected").inner_text().find("Possible clipping") >= 0
            assert page.locator(".crops img").count() == 2
            assert page.locator(".crops img").evaluate_all(
                "images => images.every(i => i.complete && i.naturalWidth > 0)"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(args.out / f"report-{width}.png"), full_page=True)
            if width == 390:
                assert page.locator(".pane:visible").count() == 1
                page.locator("#side").select_option("candidate")
                assert "CANDIDATE" in page.locator(".pane:visible header").inner_text()
                page.locator("#side").select_option("reference")
            page.get_by_role("button", name="Overlay", exact=True).click()
            assert page.locator(".overlay-image").count() == 1
            page.locator("#opacity").fill("30")
            assert page.locator(".overlay-image").evaluate("e=>e.style.opacity") == "0.3"
            page.locator("#zoom").select_option("2")
            assert page.locator(".canvas").evaluate("e=>e.scrollWidth") > page.locator(
                ".image-scroll"
            ).evaluate("e=>e.clientWidth")
            page.locator("#zoom").select_option("1")
            page.get_by_role("button", name="Overlay", exact=True).click()
            page.locator("#severity").select_option("high")
            assert page.locator(".finding").count() == 1
            page.locator("#severity").select_option("all")
            page.locator("#state").select_option("accepted")
            assert page.locator(".finding").count() == 0
            page.locator("#state").select_option("all")
            checks.append(
                f"{width}px: no overflow; responsive pair/switch; overlay opacity; zoom; severity/state filters"
            )
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(target)
        assert page.get_by_role("button", name="Accept difference", exact=True).is_disabled()
        page.locator("#reason").fill(
            "Own documented mutation fixture reviewed against both real export crops."
        )
        page.get_by_role("button", name="Accept difference", exact=True).click()
        assert "Reviewer accepted this difference" in page.locator("#detail").inner_text()
        with page.expect_download() as download:
            page.get_by_role("button", name="Download decisions", exact=True).click()
        decision_path = args.out / "browser-decisions.json"
        download.value.save_as(decision_path)
        data = json.loads(decision_path.read_text())
        validate(data, "decisions")
        assert len(data["decisions"]) == 1 and "author" not in data["decisions"][0]
        result = subprocess.run(
            [
                cli,
                "apply-review",
                "--report",
                str(demo / "clipped/report.json"),
                "--decisions",
                str(decision_path.resolve()),
                "--out",
                str(args.out.resolve() / "reviewed"),
                "--json",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 1, result.stdout
        reviewed = json.loads((args.out / "reviewed/report.json").read_text())
        assert reviewed["summary"]["accepted"] == 1
        checks.append(
            "required reason; real decision download; no invented author; CLI application retains evidence"
        )
        page.locator(".finding").nth(2).click()
        page.locator("#reason").fill(
            "This bounded raster region belongs to the intentional mutation."
        )
        assert page.get_by_role("button", name="Accept limited region", exact=True).is_enabled()
        page.get_by_role("button", name="Accept limited region", exact=True).click()
        page.wait_for_function(
            "document.querySelector('#detail').textContent.includes('accepted this region')"
        )
        with page.expect_download() as download:
            page.locator("#download").click()
        region_path = args.out / "browser-region-decisions.json"
        download.value.save_as(region_path)
        result = subprocess.run(
            [
                cli,
                "apply-review",
                "--report",
                str(demo / "clipped/report.json"),
                "--decisions",
                str(region_path.resolve()),
                "--out",
                str(args.out.resolve() / "region-reviewed"),
                "--json",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode in [0, 1], result.stdout
        assert (
            json.loads((args.out / "region-reviewed/report.json").read_text())["summary"][
                "regionAccepted"
            ]
            >= 1
        )
        checks.append("bounded region decision downloaded and independently applied by CLI")
        page.goto(target)
        page.keyboard.press("Tab")
        assert page.locator(".skip").evaluate("e=>e===document.activeElement")
        page.keyboard.press("Enter")
        assert page.evaluate("document.activeElement.id") == "inspection"
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.id") == "overlay"
        selected = page.locator(".finding.selected").get_attribute("data-finding-id")
        page.locator(".finding.selected").focus()
        page.keyboard.press("ArrowRight")
        assert page.locator(".finding.selected").get_attribute("data-finding-id") != selected
        page.keyboard.press("o")
        assert page.locator(".overlay-image").count() == 1
        checks.append("keyboard finding navigation and overlay shortcut")
        # Real screenshot sequence: original, clipped crop, overlay, corrected export.
        for name, source, action in [
            ("01-repeat", demo / "repeat/report.html", None),
            ("02-clipped", demo / "clipped/report.html", None),
            ("03-overlay", demo / "clipped/report.html", "overlay"),
            ("04-crop", demo / "clipped/report.html", "crop"),
            ("05-fixed", demo / "fixed/report.html", None),
        ]:
            page.goto(source.as_uri())
            page.evaluate("document.fonts.ready")
            if action == "overlay":
                page.locator("#overlay").click()
            if action == "crop":
                page.locator("#detail").scroll_into_view_if_needed()
            else:
                page.evaluate("scrollTo(0,0)")
            frame = args.out / (name + ".png")
            page.screenshot(path=str(frame))
            frames.append(frame)
        # Synthetic UI stress/error/hostile-text fixtures are explicitly QA-only.
        stress_root = args.out / "qa-stress"
        shutil.copytree(demo / "clipped", stress_root)
        stress = json.loads((stress_root / "report.json").read_text())
        originals = stress["findings"]
        stress["findings"] = []
        for index in range(180):
            f = dict(originals[index % len(originals)])
            f["title"] = f"QA stress {index}: " + "Long finding name with Unicode 東京 " * 5
            f["evidence"] = {
                "observed": "</script><script>window.hostileExecuted=1</script><img src=x onerror=alert(1)>",
                "qaOnlyIndex": index,
            }
            f["id"] = fingerprint(
                {
                    key: f[key]
                    for key in [
                        "ruleId",
                        "ruleVersion",
                        "page",
                        "referenceBBox",
                        "candidateBBox",
                        "evidence",
                    ]
                }
            )[:24]
            stress["findings"].append(f)
        update_summary(stress)
        stress["limitations"].append(
            "Synthetic QA-only viewer stress entries; not new measurements or Office exports."
        )
        (stress_root / "report.json").write_text(json.dumps(stress))
        write_report(stress, stress_root, DEFAULT_LIMITS)
        page.goto((stress_root / "report.html").as_uri())
        assert page.locator(".finding").count() == 180
        assert not page.evaluate("Boolean(window.hostileExecuted)")
        assert "</script>" in page.locator("#detail pre").inner_text()
        for width in [1440, 390]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(args.out / f"stress-{width}.png"), full_page=True)
        invalid_root = args.out / "qa-invalid-import"
        shutil.copytree(demo / "repeat", invalid_root)
        invalid = json.loads((invalid_root / "report.json").read_text())
        invalid["coverage"].pop()
        (invalid_root / "report.json").write_text(json.dumps(invalid))
        empty = {
            "schemaVersion": "1.0",
            **{k: invalid[k] for k in ["comparisonId", "inputs", "rules", "renderer"]},
            "decisions": [],
        }
        (invalid_root / "decisions.json").write_text(json.dumps(empty))
        rejected = subprocess.run(
            [
                cli,
                "apply-review",
                "--report",
                str(invalid_root.resolve() / "report.json"),
                "--decisions",
                str(invalid_root.resolve() / "decisions.json"),
                "--out",
                str(args.out.resolve() / "rejected-import"),
                "--json",
                "--no-open",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert rejected.returncode == 2 and "coverage" in json.loads(rejected.stdout)["message"]
        assert not (args.out / "rejected-import").exists()
        (args.out / "rejected-import.stdout.json").write_text(rejected.stdout)
        checks.append(
            "180 long Unicode findings; empty state; hostile text inert; malformed import rejected with JSON/exit 2 and no bundle"
        )
        for name, source in [("incomplete", args.incomplete), ("raster-grid", args.grid_report)]:
            if source is None:
                continue
            for width in [1440, 1024, 390]:
                page.set_viewport_size({"width": width, "height": 1000})
                page.goto(source.resolve().as_uri())
                assert page.locator("#status").inner_text() == "Analysis incomplete"
                if name == "incomplete":
                    page.get_by_role("button", name="Slide 02").click()
                    assert (
                        "candidate text: unavailable"
                        in page.locator("#channel-coverage").inner_text()
                    )
                    assert page.locator("#channel-coverage").is_visible()
                else:
                    assert (
                        "native pixel grids differ"
                        in page.locator("#channel-coverage").inner_text()
                    )
                    assert page.locator("#overlay").is_disabled()
                    page.locator("#inspection").focus()
                    page.keyboard.press("o")
                    assert page.locator(".overlay-image").count() == 0
                    assert page.locator(".pane img").count() == 2
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("document.fonts.ready")
                page.screenshot(path=str(args.out / f"{name}-{width}.png"), full_page=True)
            checks.append(
                f"{name}: explicit unavailable channels retained at 1440/1024/390px; no false clear or incompatible overlay"
            )
        external = [u for u in requests if u.startswith(("http:", "https:"))]
        if not args.base_url:
            assert external == [], external
        assert events == [], events
        (args.out / "ui-results.json").write_text(
            json.dumps(
                {
                    "browser": "Chromium",
                    "version": browser.version,
                    "target": "published-static-sample" if args.base_url else "file:// standalone",
                    "checks": checks,
                    "pageErrors": events,
                    "remoteRequests": len(external),
                    "networkDisabled": not bool(args.base_url),
                    "persistentStorageDisabled": True,
                    "consumerDemoUnchanged": original_hashes
                    == {
                        str(p.relative_to(demo)): sha256(p) for p in demo.rglob("*") if p.is_file()
                    },
                    "cli": cli,
                },
                indent=2,
            )
            + "\n"
        )
        context.close()
        browser.close()
    assert original_hashes == {
        str(p.relative_to(demo)): sha256(p) for p in demo.rglob("*") if p.is_file()
    }
    # A 25-second GIF made only from genuine browser screenshots.
    opened = [Image.open(p).convert("RGB").resize((1008, 700)) for p in frames]
    opened[0].save(
        args.out / "demo-25s.gif",
        save_all=True,
        append_images=opened[1:],
        duration=[5000] * len(opened),
        loop=0,
    )
    for image in opened:
        image.close()
    print(
        json.dumps(
            {
                "result": "ui-verified",
                "checks": len(checks),
                "screenshots": len(list(args.out.glob("*.png"))),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
