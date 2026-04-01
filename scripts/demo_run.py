#!/usr/bin/env python3
"""
Demo Run Script

Executes the full automation pipeline and prints a rich, colored report.
Ideal for recording a demo video.

Usage:
    python scripts/demo_run.py
    python scripts/demo_run.py --provider local --email test@gmail.com
    python scripts/demo_run.py --dry-run   # Validate config without running

Options:
    --provider    Device farm provider (local|browserstack|aws_device_farm)
    --email       Google account email
    --scenarios   Comma-separated list of scenarios to run
    --budget      Total time budget in seconds (default: 180)
    --dry-run     Validate config and print plan without running
    --verbose     Enable verbose logging
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


def print_banner() -> None:
    """Print the demo banner."""
    console.print(Panel.fit(
        "[bold indigo]Mobile Automation Pipeline[/bold indigo]\n"
        "[dim]Google Login → Play Store → MLBB → Google Pay[/dim]",
        border_style="indigo",
        padding=(1, 4),
    ))
    console.print()


def print_config_summary(config) -> None:
    """Print a summary of the run configuration."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Key", style="dim", width=20)
    table.add_column("Value", style="bold white")

    table.add_row("Provider", str(config.provider.provider_type.value))
    table.add_row("Device", config.device.device_name)
    table.add_row("Time budget", f"{config.total_budget_seconds}s")
    table.add_row("Scenarios", ", ".join(config.scenarios))
    table.add_row("Test payment mode", "✓" if config.google_pay_test_mode else "✗ (LIVE)")
    table.add_row("Run ID", config.run_id[:8] + "...")

    console.print(Panel(table, title="[bold]Run Configuration[/bold]", border_style="blue"))
    console.print()


def print_scenario_result(scenario) -> None:
    """Print result for a single scenario."""
    from orchestrator.models import StepStatus

    status_colors = {
        "completed": "green",
        "failed": "red",
        "timeout": "yellow",
        "skipped": "dim",
        "running": "blue",
    }
    color = status_colors.get(scenario.status.value, "white")

    console.print(f"\n  [{color}]{'▶' if scenario.status.value == 'running' else '●'}[/{color}] "
                  f"[bold]{scenario.scenario_name.replace('_', ' ').title()}[/bold] "
                  f"[{color}]{scenario.status.value.upper()}[/{color}]"
                  + (f" [dim]({scenario.duration_ms / 1000:.1f}s)[/dim]" if scenario.duration_ms else ""))

    for step in scenario.steps:
        step_color = status_colors.get(step.status.value, "dim")
        locator_info = ""
        if step.locator_attempts:
            successful = next((a for a in step.locator_attempts if a.succeeded), None)
            if successful:
                locator_info = f" [dim]via {successful.layer.value}[/dim]"

        console.print(
            f"    [dim]{'✓' if step.status.value == 'completed' else '✗'}[/dim] "
            f"[{step_color}]{step.step_name.replace('_', ' ')}[/{step_color}]"
            + (f" [dim]{step.duration_ms:.0f}ms[/dim]" if step.duration_ms else "")
            + locator_info
        )
        if step.error_message:
            console.print(f"      [red dim]{step.error_message[:100]}[/red dim]")


def print_final_report(result) -> None:
    """Print the final timing and success report."""
    from orchestrator.models import RunStatus

    console.print()
    status_color = {
        RunStatus.COMPLETED: "green",
        RunStatus.FAILED: "red",
        RunStatus.TIMEOUT: "yellow",
    }.get(result.status, "white")

    # Summary panel
    timing = result.timing
    total_s = (timing.total_ms or 0) / 1000

    content = (
        f"Status:       [{status_color}]{result.status.value.upper()}[/{status_color}]\n"
        f"Total time:   [bold]{total_s:.2f}s[/bold] / {result.config.total_budget_seconds}s budget\n"
        f"Success rate: [bold]{result.success_rate * 100:.0f}%[/bold] "
        f"({sum(1 for s in result.scenarios if s.status.value == 'completed')}/{len(result.scenarios)} scenarios)\n"
        f"Budget used:  [bold]{min(100, total_s / result.config.total_budget_seconds * 100):.0f}%[/bold]"
        + (f"\n[red]Budget exceeded: YES[/red]" if result.budget_exceeded else "")
    )

    console.print(Panel(
        content,
        title=f"[bold]Run {result.run_id[:8]} Complete[/bold]",
        border_style=status_color,
    ))

    # Timing breakdown table
    if timing.total_ms:
        table = Table(
            title="Timing Breakdown",
            box=box.SIMPLE,
            show_header=True,
        )
        table.add_column("Phase", style="dim")
        table.add_column("Time", justify="right")
        table.add_column("Budget", justify="right", style="dim")

        budgets = {
            "device_connect": 30,
            "google_login": 30,
            "play_store_install": 40,
            "mlbb_registration": 40,
            "google_pay_purchase": 30,
            "cleanup": 10,
        }
        phase_times = [
            ("Device Connect", timing.device_connect_ms, budgets["device_connect"]),
            ("Google Login", timing.google_login_ms, budgets["google_login"]),
            ("Play Store Install", timing.play_store_install_ms, budgets["play_store_install"]),
            ("MLBB Registration", timing.mlbb_registration_ms, budgets["mlbb_registration"]),
            ("Google Pay Purchase", timing.google_pay_purchase_ms, budgets["google_pay_purchase"]),
            ("Cleanup", timing.cleanup_ms, budgets["cleanup"]),
        ]

        for name, ms, budget in phase_times:
            if ms:
                s = ms / 1000
                over = s > budget
                time_str = f"[red]{s:.1f}s[/red]" if over else f"[green]{s:.1f}s[/green]"
                table.add_row(name, time_str, f"{budget}s")

        table.add_row("─" * 20, "─" * 8, "─" * 8, style="dim")
        table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_s:.1f}s[/bold]", "180s")
        console.print(table)

    # Locator layer analytics
    if result.locator_success_by_layer:
        total = sum(result.locator_success_by_layer.values())
        console.print(f"\n[dim]Locator Analytics ({total} successful finds):[/dim]")
        for layer, count in sorted(
            result.locator_success_by_layer.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            pct = count / total * 100 if total > 0 else 0
            bar = "█" * int(pct / 5)
            console.print(f"  [dim]{layer:20s}[/dim] {bar:20s} {count:3d}x ({pct:.0f}%)")

    # Artifacts
    artifacts = result.all_artifacts()
    if artifacts:
        console.print(f"\n[dim]Artifacts saved: {len(artifacts)} files[/dim]")
        for a in artifacts[:5]:
            console.print(f"  [dim]{a.artifact_type:12s} {a.file_path}[/dim]")
        if len(artifacts) > 5:
            console.print(f"  [dim]... and {len(artifacts) - 5} more[/dim]")


def run_demo(args: argparse.Namespace) -> int:
    """Execute the demo run and return exit code."""
    from orchestrator.config import get_settings
    from orchestrator.engine import ScenarioOrchestrator
    from orchestrator.models import (
        DeviceConfig,
        ProviderConfig,
        ProviderType,
        RunConfig,
    )

    settings = get_settings()

    try:
        provider_type = ProviderType(args.provider)
    except ValueError:
        console.print(f"[red]Invalid provider: {args.provider}[/red]")
        return 1

    scenarios = args.scenarios.split(",") if args.scenarios else [
        "google_login",
        "play_store_install",
        "mlbb_registration",
        "google_pay_purchase",
    ]

    config = RunConfig(
        device=DeviceConfig(
            provider=provider_type,
            device_name=os.environ.get("BROWSERSTACK_DEVICE", "Pixel 7"),
            platform_version="13.0",
        ),
        provider=ProviderConfig(
            provider_type=provider_type,
            bs_username=os.environ.get("BROWSERSTACK_USERNAME"),
            bs_access_key=os.environ.get("BROWSERSTACK_ACCESS_KEY"),
            appium_host=settings.local_appium_host,
            appium_port=settings.local_appium_port,
        ),
        google_email=args.email or os.environ.get("GOOGLE_ACCOUNT_EMAIL", ""),
        google_password=args.password or os.environ.get("GOOGLE_ACCOUNT_PASSWORD", ""),
        google_pay_test_mode=not args.live_payment,
        scenarios=scenarios,
        total_budget_seconds=args.budget,
    )

    print_banner()
    print_config_summary(config)

    if args.dry_run:
        console.print("[yellow]Dry run — not executing. Config looks valid.[/yellow]")
        return 0

    if not config.google_email:
        console.print("[red]GOOGLE_ACCOUNT_EMAIL not set. Use --email or set env var.[/red]")
        return 1

    console.print("[bold]Starting pipeline...[/bold]\n")

    orchestrator = ScenarioOrchestrator(config)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running pipeline...", total=None)

        start = time.monotonic()
        result = orchestrator.run()
        elapsed = time.monotonic() - start

        progress.update(task, description=f"Complete in {elapsed:.1f}s")

    # Print per-scenario results
    console.print("[bold]Scenario Results:[/bold]")
    for scenario in result.scenarios:
        print_scenario_result(scenario)

    print_final_report(result)

    return 0 if result.status.value == "completed" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mobile Automation Pipeline — Demo Run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("DEVICE_PROVIDER", "local"),
        choices=["local", "browserstack", "aws_device_farm"],
        help="Device farm provider",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("GOOGLE_ACCOUNT_EMAIL", ""),
        help="Google account email",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("GOOGLE_ACCOUNT_PASSWORD", ""),
        help="Google account password",
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario names to run",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=180,
        help="Total time budget in seconds (default: 180)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config without running",
    )
    parser.add_argument(
        "--live-payment",
        action="store_true",
        help="Disable test payment mode (CAUTION: real charges!)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    exit_code = run_demo(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
