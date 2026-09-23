from __future__ import annotations

import argparse
import asyncio
import json

from fitness_bot.domain.body.measurement import (
    FIXED_MEASUREMENT_SITES,
    MeasurementGuide,
    MeasurementSite,
    default_guide_for,
)


class OfflineMeasurementGuideModel:
    """Deterministic guides for local C1 without calling Timeweb.

    Uses ``default_guide_for`` — never embeds technical site codes like
    ``(biceps)`` into user-facing instructions.
    """

    async def complete(self, *, system: str, user: str) -> str:
        _ = system
        code = "site"
        name = "точка"
        lines = [ln.strip() for ln in user.splitlines()]
        try:
            code_idx = lines.index("Site code:")
            code = lines[code_idx + 1]
            name_idx = lines.index("Site name:")
            name = lines[name_idx + 1]
        except (ValueError, IndexError):
            pass
        instruction = default_guide_for(code, name)
        return json.dumps({"instruction": instruction[:500]}, ensure_ascii=False)


async def _force_offline_defaults() -> int:
    """Overwrite fixed-site guide text with DEFAULT_MEASUREMENT_GUIDES."""
    container = __import__(
        "fitness_bot.presentation.wiring.container",
        fromlist=["build_container"],
    ).build_container()
    uow = container.uow()
    updated = 0
    async with uow.transaction() as repos:
        for code, name in FIXED_MEASUREMENT_SITES:
            site = await repos.measurements.get_fixed_site_by_code(code)
            if site is None:
                site = await repos.measurements.add_site(MeasurementSite.fixed(code, name))
            await repos.measurements.upsert_guide(
                MeasurementGuide(site_id=site.id, instruction=default_guide_for(code, name)),
            )
            updated += 1
    print(f"force-updated={updated} (offline defaults, no site codes)")
    return 0


async def _run_seed(*, offline: bool, force: bool) -> int:
    from fitness_bot.presentation.wiring.container import build_container, build_mediator
    from fitness_bot.service.models.commands.body import (
        EnsureFixedMeasurementSitesCommand,
        SeedMeasurementGuidesCommand,
    )

    if force and offline:
        return await _force_offline_defaults()

    container = build_container()
    if offline:
        container.language_model.override(OfflineMeasurementGuideModel())
    mediator = build_mediator(container)
    await mediator.send(EnsureFixedMeasurementSitesCommand())
    result = await mediator.send(SeedMeasurementGuidesCommand())
    print(f"seeded={result.seeded} skipped={result.skipped}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="C1: seed fixed measurement guides")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use deterministic Russian instructions without LanguageModel API",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --offline: overwrite existing fixed-site instructions with defaults",
    )
    args = parser.parse_args(argv)
    raise SystemExit(asyncio.run(_run_seed(offline=args.offline, force=args.force)))


if __name__ == "__main__":
    main()
