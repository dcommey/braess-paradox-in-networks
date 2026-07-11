#!/usr/bin/env python3
"""Run topology-derived SFC/NFV experiments and generate paper artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from security_braess.topology_sfc import (
    aggregate_claims,
    evaluate_topology_suite,
    experiment_parameters,
    run_sensitivity_suite,
    summarize_evaluations,
)
from security_braess.robustness import (
    run_monte_carlo,
    run_nonlinear_suite,
    run_trace_calibrated_case,
    summarize_monte_carlo,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=str(ROOT / "experiments" / "results"))
    parser.add_argument(
        "--summary-table",
        default=str(ROOT / "paper" / "tables" / "topology_summary.tex"),
    )
    parser.add_argument(
        "--policy-table",
        default=str(ROOT / "paper" / "tables" / "policy_comparison.tex"),
    )
    parser.add_argument(
        "--attack-table",
        default=str(ROOT / "paper" / "tables" / "attack_stress_summary.tex"),
    )
    parser.add_argument(
        "--parameter-table",
        default=str(ROOT / "paper" / "tables" / "experiment_parameters.tex"),
    )
    parser.add_argument(
        "--sensitivity-table",
        default=str(ROOT / "paper" / "tables" / "sensitivity_summary.tex"),
    )
    parser.add_argument(
        "--queueing-table",
        default=str(ROOT / "paper" / "tables" / "queueing_robustness.tex"),
    )
    parser.add_argument(
        "--figure-dir",
        default=str(ROOT / "paper" / "figures"),
    )
    parser.add_argument("--max-safe-penalty", type=float, default=0.02)
    parser.add_argument("--monte-carlo-instances", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    evaluations = evaluate_topology_suite(max_penalty=args.max_safe_penalty)
    rows = summarize_evaluations(evaluations)
    claims = aggregate_claims(rows)
    sensitivity_rows = run_sensitivity_suite(max_penalty=args.max_safe_penalty)
    parameter_rows = experiment_parameters()
    monte_carlo_rows = run_monte_carlo(
        instances=args.monte_carlo_instances, seed=args.seed,
        max_penalty=args.max_safe_penalty,
    )
    monte_carlo_summary = summarize_monte_carlo(monte_carlo_rows)
    nonlinear_rows = run_nonlinear_suite(max_penalty=args.max_safe_penalty)
    trace_rows = run_trace_calibrated_case(max_penalty=args.max_safe_penalty)

    _write_csv(outdir / "summary.csv", rows)
    _write_csv(outdir / "sensitivity.csv", sensitivity_rows)
    _write_json(outdir / "summary.json", rows)
    _write_json(outdir / "sensitivity.json", sensitivity_rows)
    _write_json(outdir / "claims.json", claims)
    _write_csv(outdir / "monte_carlo_instances.csv", monte_carlo_rows)
    _write_json(outdir / "monte_carlo_summary.json", monte_carlo_summary)
    _write_csv(outdir / "nonlinear_equilibrium.csv", nonlinear_rows)
    _write_json(outdir / "nonlinear_equilibrium.json", nonlinear_rows)
    _write_csv(outdir / "trace_calibrated_case.csv", trace_rows)
    _write_json(outdir / "trace_calibrated_case.json", trace_rows)
    _write_summary_table(Path(args.summary_table), rows)
    _write_policy_table(Path(args.policy_table), rows)
    _write_attack_table(Path(args.attack_table), rows)
    _write_parameter_table(Path(args.parameter_table), parameter_rows)
    _write_sensitivity_table(Path(args.sensitivity_table), sensitivity_rows)
    _write_queueing_table(Path(args.queueing_table), rows)
    _write_monte_carlo_table(ROOT / "paper" / "tables" / "monte_carlo_summary.tex", monte_carlo_summary)
    _write_nonlinear_table(ROOT / "paper" / "tables" / "nonlinear_equilibrium.tex", nonlinear_rows)
    _write_resilience_table(ROOT / "paper" / "tables" / "resilience_metrics.tex", rows)
    _write_trace_table(ROOT / "paper" / "tables" / "trace_calibrated_case.tex", trace_rows)
    _write_figures(Path(args.figure_dir), rows, sensitivity_rows)

    print(f"wrote {outdir / 'summary.csv'}")
    print(f"wrote {outdir / 'sensitivity.csv'}")
    print(f"wrote {outdir / 'summary.json'}")
    print(f"wrote {outdir / 'sensitivity.json'}")
    print(f"wrote {outdir / 'claims.json'}")
    print(f"wrote Monte Carlo, nonlinear-equilibrium, and trace-calibrated artifacts in {outdir}")
    print(f"wrote {args.summary_table}")
    print(f"wrote {args.policy_table}")
    print(f"wrote {args.attack_table}")
    print(f"wrote {args.parameter_table}")
    print(f"wrote {args.sensitivity_table}")
    print(f"wrote {args.queueing_table}")
    print(f"wrote figures in {args.figure_dir}")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _write_summary_table(path: Path, rows: list[dict[str, object]]) -> None:
    grouped = _group(rows)
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table*}[t]",
        "\\centering",
        "\\caption{Topology-derived SFC/NFV results. Paradox-aware values use pre-deployment screening and constrained use of the added gateway.}",
        "\\label{tab:topology-summary}",
        "\\begin{tabular}{lrrrrrrr}",
        "\\toprule",
        "Topology & Nodes & Edges & Requests & Naive penalty & Naive SBR & Aware penalty & Aware gain \\\\",
        "\\midrule",
    ]
    for topology, group in grouped.items():
        baseline = group["baseline"]
        naive = group["naive_expansion"]
        aware = group["paradox_aware"]
        aware_gain = (
            float(naive["average_cost"]) - float(aware["average_cost"])
        ) / float(naive["average_cost"])
        lines.append(
            "{} & {} & {} & {} & {:.3f} & {:.3f} & {:.3f} & {:.1f}\\% \\\\".format(
                _tex(topology),
                int(baseline["nodes"]),
                int(baseline["edges"]),
                int(baseline["requests"]),
                float(naive["paradox_penalty"]),
                float(naive["security_braess_ratio"]),
                float(aware["paradox_penalty"]),
                100.0 * aware_gain,
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""])
    _write_text(path, "\n".join(lines))


def _write_policy_table(path: Path, rows: list[dict[str, object]]) -> None:
    selected = [
        row
        for row in rows
        if row["policy"] in {
            "baseline",
            "naive_expansion",
            "load_aware_cap_0.50",
            "risk_aware_surcharge",
            "minmax_utilization_cap",
            "system_optimum_expansion",
            "paradox_aware",
        }
    ]
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table*}[t]",
        "\\centering",
        "\\scriptsize",
        "\\caption{Policy comparison under the same adaptive equilibrium model.}",
        "\\label{tab:policy-comparison}",
        "\\begin{tabular}{llrrrrrr}",
        "\\toprule",
        "Topology & Policy & Cost & Penalty & Risk conc. & Attack loss & Max util. & Gateway share \\\\",
        "\\midrule",
    ]
    for row in selected:
        lines.append(
            "{} & {} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.2f} \\\\".format(
                _tex(str(row["topology"])),
                _policy(str(row["policy"])),
                float(row["average_cost"]),
                float(row["paradox_penalty"]),
                float(row["risk_concentration"]),
                float(row["expected_attack_loss"]),
                float(row["max_utilization"]),
                float(row["gateway_share"]),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""])
    _write_text(path, "\n".join(lines))


def _write_attack_table(path: Path, rows: list[dict[str, object]]) -> None:
    grouped = _group(rows)
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Post-equilibrium attack stress tests. DDoS targets the most loaded resource; weighted loss randomizes targets proportional to utilization and exposure.}",
        "\\label{tab:attack-stress}",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Topology & DDoS-B & DDoS-N & DDoS-A & W-N & W-A \\\\",
        "\\midrule",
    ]
    for topology, group in grouped.items():
        lines.append(
            "{} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} \\\\".format(
                _tex(topology),
                float(group["baseline"]["ddos_service_loss"]),
                float(group["naive_expansion"]["ddos_service_loss"]),
                float(group["paradox_aware"]["ddos_service_loss"]),
                float(group["naive_expansion"]["weighted_attack_loss"]),
                float(group["paradox_aware"]["weighted_attack_loss"]),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    _write_text(path, "\n".join(lines))


def _write_parameter_table(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Default experiment parameters.}",
        "\\label{tab:experiment-parameters}",
        "\\begin{tabular}{ll}",
        "\\toprule",
        "Parameter & Value \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(f"{row['parameter']} & {row['value']} \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    _write_text(path, "\n".join(lines))


def _write_sensitivity_table(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table*}[t]",
        "\\centering",
        "\\caption{One-factor sensitivity analysis on the NSFNET-style topology.}",
        "\\label{tab:sensitivity}",
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Parameter & Value & Naive penalty & Aware penalty & Aware gain & Naive attack & Cap \\\\",
        "\\midrule",
    ]
    for row in rows:
        lines.append(
            "{} & {} & {:.3f} & {:.3f} & {:.1f}\\% & {:.3f} & {:.2f} \\\\".format(
                _sensitivity_name(str(row["parameter"])),
                _format_value(row["value"]),
                float(row["naive_penalty"]),
                float(row["aware_penalty"]),
                100.0 * float(row["aware_gain"]),
                float(row["naive_attack_loss"]),
                float(row["cap_fraction"]),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""])
    _write_text(path, "\n".join(lines))


def _write_queueing_table(path: Path, rows: list[dict[str, object]]) -> None:
    grouped = _group(rows)
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{Robustness under nonlinear delay evaluation.}",
        "\\label{tab:queueing-robustness}",
        "\\begin{tabular}{lrrr}",
        "\\toprule",
        "Topology & Baseline & Naive & Aware \\\\",
        "\\midrule",
    ]
    for topology, group in grouped.items():
        lines.append(
            "{} & {:.3f} & {:.3f} & {:.3f} \\\\".format(
                _tex(topology),
                float(group["baseline"]["queueing_curve_cost"]),
                float(group["naive_expansion"]["queueing_curve_cost"]),
                float(group["paradox_aware"]["queueing_curve_cost"]),
            )
        )
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    _write_text(path, "\n".join(lines))


def _write_monte_carlo_table(path: Path, summary: dict[str, object]) -> None:
    prevalence_ci = summary["paradox_prevalence_ci95"]
    success_ci = summary["mitigation_success_ci95"]
    runtime_ci = summary["mean_screen_runtime_ci95"]
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table*}[t]", "\\centering", "\\small",
        "\\caption{Monte Carlo robustness study (95\\% confidence intervals).}",
        "\\label{tab:monte-carlo}", "\\begin{tabular}{rrrr}", "\\toprule",
        "Converged & Paradox prevalence & Threshold compliance & Mean screen runtime \\\\", "\\midrule",
        "{} / {} & {:.1f}\\% [{:.1f}, {:.1f}] & {:.1f}\\% [{:.1f}, {:.1f}] & {:.1f} ms [{:.1f}, {:.1f}] \\\\".format(
            int(summary["instances"]), int(summary["instances_attempted"]),
            100 * float(summary["paradox_prevalence"]), 100 * prevalence_ci[0], 100 * prevalence_ci[1],
            100 * float(summary["mitigation_success"]), 100 * success_ci[0], 100 * success_ci[1],
            float(summary["mean_screen_runtime_ms"]), runtime_ci[0], runtime_ci[1],
        ),
        "\\bottomrule", "\\end{tabular}", "\\end{table*}", "",
    ]
    _write_text(path, "\n".join(lines))


def _write_nonlinear_table(path: Path, rows: list[dict[str, object]]) -> None:
    lines = [
        "% Auto-generated by scripts/run_experiments.py",
        "\\begin{table}[t]", "\\centering",
        "\\caption{Recomputed Wardrop equilibria under nonlinear BPR delays and positive gateway slope $a_g=0.25$.}",
        "\\label{tab:nonlinear-equilibrium}", "\\begin{tabular}{lrrrr}", "\\toprule",
        "Topology & Baseline & Naive pen. & Aware pen. & Cap \\\\", "\\midrule",
    ]
    for row in rows:
        lines.append("{} & {:.3f} & {:.3f} & {:.3f} & {:.2f} \\\\".format(
            _tex(str(row["topology"])), float(row["baseline_cost"]),
            float(row["naive_penalty"]), float(row["aware_penalty"]),
            float(row["cap_fraction"])))
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    _write_text(path, "\n".join(lines))


def _write_resilience_table(path: Path, rows: list[dict[str, object]]) -> None:
    grouped = _group(rows)
    lines = [
        "% Auto-generated by scripts/run_experiments.py", "\\begin{table*}[t]",
        "\\centering", "\\caption{Standard concentration and resilience metrics; lower is safer except entropy.}",
        "\\label{tab:resilience-metrics}", "\\begin{tabular}{lrrrrrrrr}", "\\toprule",
        "& \\multicolumn{2}{c}{HHI} & \\multicolumn{2}{c}{Entropy} & \\multicolumn{2}{c}{Max share} & \\multicolumn{2}{c}{Removal loss} \\\\",
        "Topology & N & A & N & A & N & A & N & A \\\\", "\\midrule",
    ]
    for topology, group in grouped.items():
        n, a = group["naive_expansion"], group["paradox_aware"]
        lines.append("{} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} \\\\".format(
            _tex(topology), float(n["load_hhi"]), float(a["load_hhi"]),
            float(n["load_entropy"]), float(a["load_entropy"]),
            float(n["max_affected_share"]), float(a["max_affected_share"]),
            float(n["single_resource_removal_loss"]), float(a["single_resource_removal_loss"])))
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""])
    _write_text(path, "\n".join(lines))


def _write_trace_table(path: Path, rows: list[dict[str, object]]) -> None:
    row = rows[0]
    lines = [
        "% Auto-generated by scripts/run_experiments.py", "\\begin{table}[t]", "\\centering",
        "\\caption{Trace-calibrated demand-profile case with positive gateway congestion.}",
        "\\label{tab:trace-case}", "\\begin{tabular}{lr}", "\\toprule",
        "Measure & Result \\\\", "\\midrule",
        f"Requests & {int(row['requests'])} \\\\",
        f"Naive penalty & {float(row['naive_penalty']):.3f} \\\\",
        f"Aware penalty & {float(row['aware_penalty']):.3f} \\\\",
        f"Selected cap & {float(row['cap_fraction']):.2f} \\\\",
        "\\bottomrule", "\\end{tabular}", "\\end{table}", "",
    ]
    _write_text(path, "\n".join(lines))


def _write_figures(
    figure_dir: Path,
    rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))
    os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
    figure_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - optional artifact nicety
        print(f"skipped figures: {exc}")
        return

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 160,
            "savefig.bbox": "tight",
        }
    )
    grouped = _group(rows)
    topologies = list(grouped)
    labels = [_tex_plain(name) for name in topologies]

    _plot_policy_penalties(plt, figure_dir / "policy_penalties.pdf", grouped, labels)
    _plot_attack_loss(plt, figure_dir / "attack_loss.pdf", grouped, labels)
    _plot_sensitivity(plt, figure_dir / "sensitivity_phase.pdf", sensitivity_rows)


def _plot_policy_penalties(plt: object, path: Path, grouped: dict[str, dict[str, dict[str, object]]], labels: list[str]) -> None:
    policies = [
        ("naive_expansion", "Naive"),
        ("load_aware_cap_0.50", "50% cap"),
        ("risk_aware_surcharge", "Risk-aware"),
        ("minmax_utilization_cap", "Min-max util."),
        ("paradox_aware", "Paradox-aware"),
    ]
    colors = ["#9d2f2f", "#d17a22", "#6e5aa8", "#287c8e", "#2f7d32"]
    width = 0.15
    xs = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    ax.set_axisbelow(True)
    for offset, ((policy, label), color) in enumerate(zip(policies, colors)):
        values = [float(grouped[topology][policy]["paradox_penalty"]) for topology in grouped]
        positions = [x + (offset - 2) * width for x in xs]
        bars = ax.bar(positions, values, width=width, label=label, color=color)
        for rect, value in zip(bars, values):
            ax.annotate(
                f"{value:.3f}",
                xy=(rect.get_x() + rect.get_width() / 2, max(0.0, value)),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=5.5,
                rotation=90,
                color="#333333",
            )
    ax.axhline(0.02, color="#333333", linewidth=0.9, linestyle="--", label=r"$\tau=0.02$")
    ax.set_ylabel("Paradox penalty")
    ax.set_ylim(top=0.36)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    handles, labels_ = ax.get_legend_handles_labels()
    desired = [label for _, label in policies] + [r"$\tau=0.02$"]
    order = [labels_.index(label) for label in desired]
    ax.legend(
        [handles[i] for i in order],
        [labels_[i] for i in order],
        ncol=6,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.22),
        columnspacing=1.1,
        handlelength=1.4,
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    fig.savefig(path)
    plt.close(fig)


def _plot_attack_loss(plt: object, path: Path, grouped: dict[str, dict[str, dict[str, object]]], labels: list[str]) -> None:
    policies = [
        ("baseline", "No expansion"),
        ("naive_expansion", "Naive"),
        ("risk_aware_surcharge", "Risk-aware"),
        ("paradox_aware", "Paradox-aware"),
    ]
    colors = ["#666666", "#9d2f2f", "#6e5aa8", "#2f7d32"]
    width = 0.18
    xs = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(3.45, 2.75))
    ax.set_axisbelow(True)
    for offset, ((policy, label), color) in enumerate(zip(policies, colors)):
        values = [float(grouped[topology][policy]["expected_attack_loss"]) for topology in grouped]
        positions = [x + (offset - 1.5) * width for x in xs]
        bars = ax.bar(positions, values, width=width, label=label, color=color)
        for rect, value in zip(bars, values):
            ax.annotate(
                f"{value:.2f}",
                xy=(rect.get_x() + rect.get_width() / 2, value),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=5.0,
                rotation=90,
                color="#333333",
            )
    ax.set_yscale("log")
    ax.set_ylim(0.05, 22.0)
    ax.set_ylabel("Attack-loss proxy (log)")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.legend(
        ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.28),
        columnspacing=0.8, handlelength=1.2,
    )
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    fig.savefig(path)
    plt.close(fig)


def _plot_sensitivity(plt: object, path: Path, rows: list[dict[str, object]]) -> None:
    selected = [row for row in rows if row["parameter"] in {"gateway_delay", "shared_slope_factor", "tau"}]
    groups: dict[str, list[dict[str, object]]] = {}
    for row in selected:
        groups.setdefault(str(row["parameter"]), []).append(row)
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.35))
    names = {
        "gateway_delay": r"Gateway delay $b_g$",
        "shared_slope_factor": r"Load sensitivity scale",
        "tau": r"Cap threshold $\tau$",
    }
    xlabels = {
        "gateway_delay": r"$b_g$",
        "shared_slope_factor": r"$a_s$ scale",
        "tau": r"$\tau$",
    }
    for ax, key in zip(axes, ["gateway_delay", "shared_slope_factor", "tau"]):
        ax.set_axisbelow(True)
        group = sorted(groups[key], key=lambda row: float(row["value"]))
        xs = [float(row["value"]) for row in group]
        naive = [float(row["naive_penalty"]) for row in group]
        aware = [float(row["aware_penalty"]) for row in group]
        ax.plot(xs, naive, marker="o", markersize=4, color="#9d2f2f", label="Naive")
        ax.plot(xs, aware, marker="s", markersize=4, color="#2f7d32", label="Paradox-aware")
        ax.axhline(0.0, color="#333333", linewidth=0.7)
        if key == "tau":
            ax.plot(
                xs,
                xs,
                color="#333333",
                linewidth=0.7,
                linestyle=":",
                label=r"$y=\tau$ bound",
            )
        else:
            ax.axhline(
                0.02,
                color="#333333",
                linewidth=0.7,
                linestyle="--",
                label=r"$\tau=0.02$",
            )
        ax.set_title(names[key])
        ax.set_xlabel(xlabels[key])
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    axes[0].set_ylabel("Paradox penalty")
    handles, labels_ = axes[-1].get_legend_handles_labels()
    extra_h, extra_l = axes[0].get_legend_handles_labels()
    for handle, label in zip(extra_h, extra_l):
        if label not in labels_:
            handles.append(handle)
            labels_.append(label)
    fig.legend(
        handles,
        labels_,
        ncol=4,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        columnspacing=1.2,
        handlelength=1.6,
    )
    fig.savefig(path)
    plt.close(fig)


def _group(rows: list[dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    grouped: dict[str, dict[str, dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row["topology"]), {})[str(row["policy"])] = row
    return grouped


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _tex(value: str) -> str:
    return {
        "fat_tree_k4": "Fat-tree",
        "nsfnet": "NSFNET",
        "geant": "GEANT",
        "edge_fog": "Edge/fog",
    }.get(value, value.replace("_", "\\_"))


def _policy(value: str) -> str:
    return {
        "baseline": "No expansion",
        "naive_expansion": "Naive expansion",
        "load_aware_cap_0.50": "Load-aware cap",
        "risk_aware_surcharge": "Risk-aware",
        "minmax_utilization_cap": "Min-max util.",
        "system_optimum_expansion": "System optimum",
        "paradox_aware": "Paradox-aware",
    }.get(value, _tex(value))


def _sensitivity_name(value: str) -> str:
    return {
        "gateway_delay": "$b_g$",
        "gateway_capacity_factor": "$u_g$ factor",
        "shared_slope_factor": "$a_s$ factor",
        "tau": "$\\tau$",
        "gateway_risk_exposure_scale": "$\\rho_g,\\chi_g$ scale",
    }.get(value, _tex(value))


def _format_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return _tex(str(value))


def _tex_plain(value: str) -> str:
    return {
        "fat_tree_k4": "Fat-tree",
        "nsfnet": "NSFNET",
        "geant": "GEANT",
        "edge_fog": "Edge/fog",
    }.get(value, value.replace("_", " "))


if __name__ == "__main__":
    main()
