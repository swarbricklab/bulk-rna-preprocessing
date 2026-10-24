"""Universal entry-point dispatcher for workflow stages.

VENDORED from swarbricklab/spotty (src/spotty/_dispatch.py @ 006747fc),
the proving ground for a shared "workflow / CLI / library trinity" that is
intended to become a standalone package (working name `trident`). See
docs/dev/dispatch-provenance.md in this repo for the running inventory of
what in here is generic vs. what is still spotty-specific. Changes made on
vendoring are marked ``# [vendor]``; the only behavioural one is a
format-agnostic (YAML or JSON) CLI config loader — spotty hardcoded JSON.

Each workflow stage exposes one typed `run(...)` function in
`<package>._steps.<stage>`. The dispatcher resolves that function's
parameters from either the Snakemake-injected ``snakemake`` global or
from click-parsed CLI args, validates inputs/outputs, and emits a verbose
telemetry banner so the parameter binding is visible in logs rather than
hidden in shim plumbing.

Special parameter names:
  * ``config: dict`` is bound to ``snakemake.config`` (the whole config dict).
  * ``log_path: Path | None`` is bound to ``snakemake.log[0]`` if any.
  * any other parameter is looked up in ``input``, then ``output``, then
    ``wildcards``, then ``params`` — first hit wins.

The dispatcher classifies inputs vs outputs by *source namespace*
(``input`` → input, ``output`` → output), not by name heuristics, so the
pre-flight + output-existence checks are unambiguous.
"""

from __future__ import annotations

import inspect
import sys
import time
import traceback
import types
import typing as t
from datetime import datetime
from pathlib import Path


def _load_config_file(path) -> dict:
    """Load a workflow config file as a dict (YAML or JSON, by extension).

    [vendor] spotty's CLI loaded config as JSON only; this repo's configs are
    YAML. ``.yaml``/``.yml`` → yaml.safe_load; anything else → json.loads.
    A generic, format-agnostic loader is a candidate for the shared package.
    """
    text = Path(path).read_text(encoding="utf-8")
    if str(path).lower().endswith((".yaml", ".yml")):
        import yaml

        return yaml.safe_load(text) or {}
    import json

    return json.loads(text)


def dispatch(fn, runtime_globals: dict | None = None) -> None:
    """Run ``fn`` from Snakemake (if ``snakemake`` is in ``runtime_globals``)
    or fail with a clear error pointing at the ``spotty`` CLI.

    Call as ``dispatch(run, globals())`` from a workflow shim — the
    ``globals()`` dict is how Snakemake's ``script:`` directive injects
    its ``snakemake`` object into the shim's module.
    """
    runtime_globals = runtime_globals or {}
    snake = runtime_globals.get("snakemake")
    if snake is not None:
        kwargs, sources = _resolve_snakemake_kwargs(fn, snake)
        rule_name = getattr(snake, "rule", fn.__name__)
        _run_with_telemetry(fn, kwargs, sources, rule_name=rule_name, context="snakemake")
        return

    raise RuntimeError(
        "dispatch() called outside Snakemake. Use the package CLI "
        "(`python -m bulk_rna_preprocessing ...`); or invoke the "
        "underlying _steps.*.run function directly."
    )


def as_click_command(fn, *, name: str | None = None):
    """Build a ``click.Command`` from ``fn``'s typed signature.

    Each non-special parameter becomes a ``--kebab-case`` option whose
    click type is derived from the annotation. Common parameters also get a
    one-letter alias (``-i`` / ``-o`` / ``-g`` / …) that does not replace the
    long name. ``config`` is exposed as ``-c`` / ``--config-json PATH``;
    ``log_path`` is exposed as ``-l`` / ``--log PATH``. Required parameters
    have ``required=True``; defaults flow through verbatim.

    When invoked, the callback runs through the same ``_run_with_telemetry``
    pipeline as the Snakemake path, with sources tagged ``--option-name``.
    """
    import click  # local import — click is in the [workflow] extras only

    sig = inspect.signature(fn)
    hints = _safe_get_type_hints(fn)
    options = []
    used_shorts: set[str] = set()

    for name_, param in sig.parameters.items():
        if name_ == "config":
            options.append(
                click.Option(
                    # [vendor] spotty exposed this as --config-json (JSON only);
                    # generalised to --config accepting YAML or JSON by extension,
                    # since this repo's configs are YAML.
                    _flag_names("--config", "-c", used_shorts),
                    type=click.Path(exists=True, dir_okay=False, path_type=Path),
                    required=False,
                    default=None,
                    help="YAML or JSON file with the workflow config (the dict otherwise passed via snakemake.config).",
                )
            )
            continue
        if name_ == "log_path":
            options.append(
                click.Option(
                    _flag_names("--log", "-l", used_shorts),
                    type=click.Path(path_type=Path),
                    required=False,
                    default=None,
                    help="Path to log file (banner + run messages mirrored to stderr).",
                )
            )
            continue

        annotation = hints.get(name_, param.annotation)
        unwrapped = _unwrap_optional(annotation)
        is_list = _is_list_annotation(unwrapped)
        inner = _list_inner(unwrapped) if is_list else unwrapped
        required = param.default is inspect.Parameter.empty
        default = None if required else param.default

        click_type, is_flag = _click_type_for(inner)

        option_kwargs: dict[str, t.Any] = {
            "required": required,
            "default": default,
            "show_default": not required,
        }
        if is_list:
            option_kwargs["multiple"] = True
            option_kwargs["type"] = click_type
            if default in (None, []):
                option_kwargs["default"] = ()
            else:
                option_kwargs["default"] = tuple(default)
        elif is_flag:
            option_kwargs["is_flag"] = True
        else:
            option_kwargs["type"] = click_type

        long = "--" + name_.replace("_", "-")
        names = _flag_names(long, _SHORT_BY_PARAM.get(name_), used_shorts)
        options.append(click.Option(names, **option_kwargs))

    def callback(**raw):
        kwargs: dict[str, t.Any] = {}
        sources: dict[str, str] = {}
        for name__, param_ in sig.parameters.items():
            if name__ == "config":
                cfg_path = raw.get("config")
                kwargs["config"] = _load_config_file(cfg_path) if cfg_path else {}
                sources["config"] = "--config"
                continue
            if name__ == "log_path":
                log = raw.get("log")
                kwargs["log_path"] = Path(log) if log else None
                sources["log_path"] = "--log"
                continue

            value = raw.get(name__)
            annotation = hints.get(name__, param_.annotation)
            unwrapped = _unwrap_optional(annotation)
            if _is_list_annotation(unwrapped):
                value = list(value) if value else []
                value = [_coerce(v, _list_inner(unwrapped)) for v in value]
            elif value is not None:
                value = _coerce(value, unwrapped)
            kwargs[name__] = value
            sources[name__] = f"--{name__.replace('_', '-')}"

        rule_label = name or fn.__module__.rsplit(".", 1)[-1]
        _run_with_telemetry(fn, kwargs, sources, rule_name=rule_label, context="cli")

    return click.Command(
        name=name or fn.__module__.rsplit(".", 1)[-1].replace("_", "-"),
        params=options,
        callback=callback,
        help=(fn.__doc__ or "").strip(),
    )


def _unwrap_optional(annotation):
    """``Path | None`` → ``Path``; pass through anything else."""
    if annotation is inspect.Parameter.empty:
        return str
    origin = t.get_origin(annotation)
    if origin is types.UnionType or origin is t.Union:
        non_none = [a for a in t.get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _is_list_annotation(annotation) -> bool:
    return t.get_origin(annotation) in (list, tuple)


def _list_inner(annotation):
    args = t.get_args(annotation)
    return args[0] if args else str


def _click_type_for(inner):
    """Return ``(click_type, is_flag)`` for a scalar annotation."""
    import click

    if inner is Path:
        return click.Path(path_type=Path), False
    if inner is int:
        return click.INT, False
    if inner is float:
        return click.FLOAT, False
    if inner is bool:
        return None, True
    return click.STRING, False


# GNU / bioinformatics short flags for auto-generated CLI options.
# Long names are unchanged; a short form is added when it does not collide.
# [vendor] This table is spotty's domain vocabulary (gussid, dashboard,
# summary_json, in_h5ad, ...). It is inert for param names this repo doesn't
# use, so it is kept verbatim; in the shared package it should become
# caller-registrable rather than a hardcoded dict.
_SHORT_BY_PARAM: dict[str, str] = {
    "in_h5ad": "-i",
    "h5ads": "-i",
    "out_h5ad": "-o",
    "out_csv": "-o",
    "out_dir": "-o",
    "gussid": "-g",
    "dashboard": "-d",
    "sample_sheet": "-s",
    "summary_json": "-j",
}


def _flag_names(long: str, short: str | None, used: set[str]) -> list[str]:
    if short and short not in used:
        used.add(short)
        return [short, long]
    return [long]


# ─── snakemake → kwargs ───────────────────────────────────────────────────────


_MISSING: t.Any = object()


def _resolve_snakemake_kwargs(fn, snake) -> tuple[dict, dict]:
    """Map ``fn``'s parameters from the snakemake namespaces.

    Returns ``(kwargs, sources)`` where ``sources[name]`` is one of
    ``"input"``, ``"output"``, ``"wildcards"``, ``"params"``, ``"config"``,
    ``"log[0]"``, or ``"default"`` — used by the telemetry banner.
    """
    sig = inspect.signature(fn)
    hints = _safe_get_type_hints(fn)
    kwargs: dict[str, t.Any] = {}
    sources: dict[str, str] = {}

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        if name == "config":
            kwargs[name] = dict(getattr(snake, "config", {}) or {})
            sources[name] = "config"
            continue
        if name == "log_path":
            log_list = list(getattr(snake, "log", None) or [])
            kwargs[name] = Path(log_list[0]) if log_list else None
            sources[name] = "log[0]"
            continue

        value, src = _lookup_in_snakemake_namespaces(name, snake)
        if value is _MISSING:
            if param.default is inspect.Parameter.empty:
                raise KeyError(
                    f"dispatch: required parameter {name!r} not found in any "
                    "snakemake namespace (input / output / wildcards / params)."
                )
            kwargs[name] = param.default
            sources[name] = "default"
            continue

        kwargs[name] = _coerce(value, annotation)
        sources[name] = src

    return kwargs, sources


def _safe_get_type_hints(fn) -> dict[str, t.Any]:
    """Resolve PEP-563 string annotations into runtime classes.

    Falls back to the raw signature annotations if ``get_type_hints``
    can't resolve a name (e.g. forward references defined inside a
    function scope).
    """
    try:
        return t.get_type_hints(fn)
    except (NameError, TypeError):
        sig = inspect.signature(fn)
        return {name: param.annotation for name, param in sig.parameters.items()}


def _lookup_in_snakemake_namespaces(name: str, snake) -> tuple[t.Any, str | None]:
    """Look up ``name`` across input → output → wildcards → params."""
    for ns_name in ("input", "output", "wildcards", "params"):
        ns = getattr(snake, ns_name, None)
        if ns is None:
            continue
        try:
            if not hasattr(ns, name):
                continue
        except (AttributeError, TypeError):
            continue
        value = getattr(ns, name)
        if value is None:
            # Treat None as "not set" so callers with `param: T | None = None`
            # can still receive their default. Required-without-default
            # params will fall through to the KeyError path below.
            continue
        return value, ns_name
    return _MISSING, None


def _coerce(value, annotation):
    """Coerce ``value`` (str, list-of-str, ...) to ``annotation``."""
    if annotation is inspect.Parameter.empty:
        return value

    origin = t.get_origin(annotation)
    args = t.get_args(annotation)

    if origin is types.UnionType or origin is t.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _coerce(value, non_none[0])
        return value

    if origin in (list, tuple):
        inner = args[0] if args else str
        if isinstance(value, (str, Path)):
            value = [value]
        coerced = [_coerce(v, inner) for v in value]
        return coerced if origin is list else tuple(coerced)

    if annotation is Path:
        return Path(value)
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if annotation is str:
        return str(value)
    if annotation is dict and isinstance(value, dict):
        return value
    return value


# ─── run + telemetry ──────────────────────────────────────────────────────────


def _run_with_telemetry(fn, kwargs, sources, *, rule_name: str, context: str) -> None:
    log_path = kwargs.get("log_path")
    logmsg = _make_logmsg(log_path, tag=rule_name)
    started = time.perf_counter()

    logmsg(f"{__package__ or 'workflow'} dispatcher v{_pkg_version()}")
    logmsg(f"context: {context} (rule={rule_name})")
    logmsg(f"target: {fn.__module__}.{fn.__qualname__}")
    logmsg("resolved kwargs:")
    for line in _format_kwargs(fn, kwargs, sources):
        logmsg("  " + line)

    inputs = _paths_from_sources(kwargs, sources, "input")
    outputs = _paths_from_sources(kwargs, sources, "output")
    _preflight(inputs, logmsg)

    logmsg("starting run()")
    try:
        fn(**kwargs)
    except BaseException as exc:
        elapsed = time.perf_counter() - started
        logmsg(f"FAILED after {_fmt_elapsed(elapsed)}: {type(exc).__name__}: {exc}")
        logmsg("traceback:")
        for line in traceback.format_exc().splitlines():
            logmsg("  " + line)
        if outputs:
            logmsg("declared output state at failure:")
            for path in outputs:
                mark = "OK " if path.exists() else "MISS"
                logmsg(f"  {mark} {path}")
        raise

    elapsed = time.perf_counter() - started
    logmsg(f"completed in {_fmt_elapsed(elapsed)}")
    if outputs:
        logmsg("outputs:")
        for path in outputs:
            if path.exists():
                logmsg(f"  OK  {path}  ({_fmt_size(path.stat().st_size)})")
            else:
                logmsg(f"  MISSING  {path}")


def _make_logmsg(log_path: Path | None, *, tag: str):
    """Return a ``logmsg(line)`` that appends timestamped lines to both
    ``log_path`` (if given) and stderr."""
    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def logmsg(line: str) -> None:
        stamp = datetime.now().isoformat(sep=" ", timespec="seconds")
        formatted = f"[{stamp}] [{tag}] {line}\n"
        sys.stderr.write(formatted)
        sys.stderr.flush()
        if log_path is not None:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(formatted)

    return logmsg


def _format_kwargs(fn, kwargs, sources):
    sig = inspect.signature(fn)
    hints = _safe_get_type_hints(fn)
    name_w = max((len(p) for p in sig.parameters), default=0)
    src_w = max((len(sources.get(p, "")) for p in sig.parameters), default=0)
    out = []
    for name, param in sig.parameters.items():
        src = sources.get(name, "")
        value = kwargs.get(name)
        ann = _format_annotation(hints.get(name, param.annotation))
        out.append(f"{name:<{name_w}}  ({src:<{src_w}})  {ann:<12} = {_format_value(name, value)}")
    return out


def _format_annotation(annotation) -> str:
    if annotation is inspect.Parameter.empty:
        return "?"
    name = getattr(annotation, "__name__", None)
    if name:
        return name
    return str(annotation).replace("typing.", "")


def _format_value(name: str, value) -> str:
    if name == "config" and isinstance(value, dict):
        keys = list(value.keys())
        preview = ", ".join(keys[:7])
        more = "..." if len(keys) > 7 else ""
        return f"(dict, {len(keys)} keys: {preview}{more})"
    if isinstance(value, list):
        if not value:
            return "[]"
        if len(value) <= 3:
            return repr([str(v) for v in value])
        return f"[{value[0]}, ..., {value[-1]}]  ({len(value)} items)"
    if isinstance(value, Path):
        return str(value)
    return repr(value)


def _paths_from_sources(kwargs, sources, kind: str) -> list[Path]:
    """Collect Path-valued kwargs whose role is ``kind`` ("input" or "output").

    In Snakemake mode the source namespace tells us directly (``input`` vs
    ``output``). In CLI mode sources are tagged ``--option-name``; we fall
    back to naming convention there:

      * input  — name starts with ``in_``
      * output — name starts with ``out_`` or ends with ``_json``, ``_pdf``,
                 ``_csv``, ``_dashboard``, or equals ``dashboard``
    """
    out: list[Path] = []
    for name, value in kwargs.items():
        src = sources.get(name, "")
        is_match = (
            src == kind
            or (src.startswith("--") and _classify_by_name(name) == kind)
        )
        if not is_match:
            continue
        if isinstance(value, Path):
            out.append(value)
        elif isinstance(value, list):
            out.extend(v for v in value if isinstance(v, Path))
    return out


def _classify_by_name(name: str) -> str:
    """Heuristic for CLI-mode I/O classification.

    [vendor] The output suffixes (_pdf, _dashboard, dashboard) are spotty's
    output vocabulary; harmless here (this repo's outputs are typed Paths bound
    from snakemake.output in the Snakemake path). Only affects the CLI-mode
    telemetry's input/output labelling, not correctness.
    """
    if name.startswith("in_"):
        return "input"
    if (
        name.startswith("out_")
        or name == "dashboard"
        or name.endswith(("_json", "_pdf", "_csv", "_dashboard"))
    ):
        return "output"
    return "other"


def _preflight(inputs: list[Path], logmsg) -> None:
    missing = [p for p in inputs if not p.exists()]
    if missing:
        for p in missing:
            logmsg(f"pre-flight: MISSING input {p}")
        raise FileNotFoundError(
            f"dispatch pre-flight: missing input(s): {[str(p) for p in missing]}"
        )
    logmsg(f"pre-flight: {len(inputs)} input(s) exist + readable")


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _fmt_size(num_bytes: int) -> str:
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if num_bytes >= scale:
            return f"{num_bytes / scale:.1f} {unit}"
    return f"{num_bytes} B"


def _pkg_version() -> str:
    try:
        from bulk_rna_preprocessing import __version__
    except ImportError:
        return "?"
    return __version__
