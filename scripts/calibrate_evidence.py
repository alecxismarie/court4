import argparse
import sys
from pathlib import Path

from app.services.evidence_calibration import (
    CalibrationManifestError,
    evaluate_manifest,
    load_calibration_manifest,
    write_calibration_reports,
)
from app.services.evidence_calibration.dataset import (
    incomplete_review_fields,
    render_balance_summary,
    samples_requiring_insight_review,
    summarize_dataset_balance,
    unresolved_candidate_mappings,
    write_sample_template,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and evaluate Court4 real-video calibration manifests."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a calibration manifest.")
    validate.add_argument("manifest", type=Path)

    validate_sample = subparsers.add_parser(
        "validate-sample",
        help="Validate a manifest and confirm one sample is present.",
    )
    validate_sample.add_argument("manifest", type=Path)
    validate_sample.add_argument("sample_id")

    template = subparsers.add_parser(
        "template",
        help="Write a safe, editable schema-v2 sample template.",
    )
    template.add_argument("sample_id")
    template.add_argument("--output", type=Path, required=True)
    template.add_argument(
        "--force",
        action="store_true",
        help="Explicitly permit overwriting the template output path.",
    )

    summarize = subparsers.add_parser(
        "summarize",
        help="Summarize deterministic dataset-balance coverage.",
    )
    summarize.add_argument("manifest", type=Path)

    review_status = subparsers.add_parser(
        "review-status",
        help="List incomplete review fields for each sample.",
    )
    review_status.add_argument("manifest", type=Path)

    artifact_status = subparsers.add_parser(
        "artifact-status",
        help="List missing, stale, and incompatible artifacts.",
    )
    artifact_status.add_argument("manifest", type=Path)
    artifact_status.add_argument("--repository-root", type=Path, default=Path.cwd())

    mappings = subparsers.add_parser(
        "unresolved-mappings",
        help="List unresolved candidate-to-player mappings.",
    )
    mappings.add_argument("manifest", type=Path)

    insight_status = subparsers.add_parser(
        "insight-review-status",
        help="List samples that still require per-insight review.",
    )
    insight_status.add_argument("manifest", type=Path)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate reusable artifacts and generate JSON and Markdown reports.",
    )
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used to resolve repository-relative artifact references.",
    )
    evaluate.add_argument(
        "--json-output",
        type=Path,
        default=Path("calibration-results.json"),
        help="Machine-readable output path.",
    )
    evaluate.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("CALIBRATION_REPORT.md"),
        help="Human-readable output path.",
    )
    evaluate.add_argument(
        "--disagreements-output",
        type=Path,
        default=Path("CALIBRATION_DISAGREEMENTS.md"),
        help="Focused disagreement report path.",
    )
    evaluate.add_argument(
        "--allow-expensive-recomputation",
        action="store_true",
        help=(
            "Explicitly permit a configured recomputation hook. The current repository "
            "has no automatic inference hook, so enabling this flag does not itself run inference."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            write_sample_template(args.output, args.sample_id, overwrite=args.force)
            print(f"Sample template: {args.output}")
            return 0

        loaded = load_calibration_manifest(args.manifest)
        if args.command == "validate":
            print(
                f"Valid calibration manifest: {loaded.manifest.dataset_id} "
                f"({len(loaded.manifest.samples)} samples, schema "
                f"{loaded.manifest.schema_version})"
            )
            return 0
        if args.command == "validate-sample":
            validated_sample = next(
                (item for item in loaded.manifest.samples if item.sample_id == args.sample_id),
                None,
            )
            if validated_sample is None:
                raise ValueError(f"Sample ID not found: {args.sample_id}")
            print(
                f"Valid calibration sample: {validated_sample.sample_id} "
                f"(manifest schema {loaded.manifest.schema_version})"
            )
            return 0
        if args.command == "summarize":
            print(render_balance_summary(summarize_dataset_balance(loaded.manifest)))
            return 0
        if args.command == "review-status":
            for sample in loaded.manifest.samples:
                missing = incomplete_review_fields(sample)
                status = ", ".join(missing) if missing else "complete"
                print(f"{sample.sample_id}: {status}")
            return 0
        if args.command == "unresolved-mappings":
            for sample in loaded.manifest.samples:
                unresolved = unresolved_candidate_mappings(sample)
                print(f"{sample.sample_id}: " + (", ".join(unresolved) if unresolved else "none"))
            return 0
        if args.command == "insight-review-status":
            sample_ids = samples_requiring_insight_review(loaded.manifest)
            print("\n".join(sample_ids) if sample_ids else "No samples require insight review.")
            return 0
        if args.command == "artifact-status":
            results = evaluate_manifest(
                loaded,
                repository_root=args.repository_root,
            )
            for result_sample in results.samples:
                print(f"{result_sample.sample_id}: {result_sample.artifact_readiness.value}")
                for artifact in result_sample.artifacts:
                    if artifact.compatibility.value != "READY":
                        print(
                            f"  {artifact.artifact}: {artifact.compatibility.value} "
                            f"({artifact.status.value})"
                        )
            print("Expensive inference runs: 0")
            return 0

        results = evaluate_manifest(
            loaded,
            repository_root=args.repository_root,
            allow_expensive_recomputation=args.allow_expensive_recomputation,
        )
        write_calibration_reports(
            results,
            json_path=args.json_output,
            markdown_path=args.markdown_output,
            disagreements_path=args.disagreements_output,
            manifest_path=args.manifest,
        )
    except (CalibrationManifestError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Evaluated {results.sample_count} samples; "
        f"{results.expensive_inference_runs} expensive inference runs performed."
    )
    print(f"JSON report: {args.json_output}")
    print(f"Markdown report: {args.markdown_output}")
    print(f"Disagreement report: {args.disagreements_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
