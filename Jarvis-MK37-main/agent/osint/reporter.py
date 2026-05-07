"""
OSINTReporter — génère un rapport HTML (+ PDF optionnel) depuis un OSINTReport.

Voir [[Features/OSINT-Reporter]].

Dépendances :
  - jinja2     (HTML, obligatoire)
  - weasyprint (PDF, optionnel)
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agent.osint.engine import OSINTReport

try:
    from jinja2 import Environment, BaseLoader
    _HAS_JINJA = True
except ImportError:
    _HAS_JINJA = False

try:
    from weasyprint import HTML as _WeasyHTML
    _HAS_WEASY = True
except ImportError:
    _HAS_WEASY = False

# ── Template HTML inline ─────────────────────────────────────────────────────
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OSINT Report — {{ target }}</title>
<style>
  :root{--accent:#00d4ff;--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--muted:#8b949e}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:2rem}
  h1{color:var(--accent);font-size:1.6rem;margin-bottom:.25rem}
  h2{color:var(--accent);font-size:1.1rem;margin:1.5rem 0 .5rem;border-bottom:1px solid var(--border);padding-bottom:.3rem}
  h3{font-size:.95rem;color:var(--text);margin:.75rem 0 .25rem}
  .meta{color:var(--muted);font-size:.85rem;margin-bottom:1.5rem}
  .card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:1rem;margin-bottom:.75rem}
  .badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.75rem;font-weight:600;margin-right:.3rem}
  .badge-ok{background:#1a4731;color:#3fb950}
  .badge-fail{background:#4a1e1e;color:#f85149}
  .badge-type{background:#1a2940;color:var(--accent)}
  .badge-src{background:#2d1f52;color:#d2a8ff}
  table{width:100%;border-collapse:collapse;font-size:.85rem}
  th{text-align:left;color:var(--muted);padding:.4rem .6rem;border-bottom:1px solid var(--border)}
  td{padding:.35rem .6rem;border-bottom:1px solid var(--border);word-break:break-all}
  tr:last-child td{border-bottom:none}
  .stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin:1rem 0}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:.75rem;text-align:center}
  .stat-val{font-size:1.8rem;font-weight:700;color:var(--accent)}
  .stat-lbl{font-size:.75rem;color:var(--muted);margin-top:.2rem}
  .section{margin-bottom:2rem}
  .analyzer-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
  @media(max-width:700px){.analyzer-grid{grid-template-columns:1fr}}
  pre{background:#0a0e14;border:1px solid var(--border);border-radius:6px;padding:.75rem;font-size:.78rem;overflow-x:auto;white-space:pre-wrap}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  .conf{color:var(--muted);font-size:.78rem}
</style>
</head>
<body>
<h1>JARVIS OSINT Report</h1>
<div class="meta">
  Target: <strong>{{ target }}</strong> &nbsp;|&nbsp;
  Type: <strong>{{ target_type }}</strong> &nbsp;|&nbsp;
  Mode: <strong>{{ mode }}</strong> &nbsp;|&nbsp;
  {{ findings_count }} findings &nbsp;|&nbsp;
  {{ duration_s }}s &nbsp;|&nbsp;
  {{ generated_at }}
  {% if cancelled %}&nbsp;|&nbsp;<span style="color:#f85149">CANCELLED</span>{% endif %}
</div>

<!-- STATS -->
<div class="stat-grid">
  <div class="stat"><div class="stat-val">{{ findings_count }}</div><div class="stat-lbl">Findings</div></div>
  <div class="stat"><div class="stat-val">{{ sources_used|length }}</div><div class="stat-lbl">Sources</div></div>
  <div class="stat"><div class="stat-val">{{ sources_failed|length }}</div><div class="stat-lbl">Errors</div></div>
  <div class="stat"><div class="stat-val">{{ targets_count }}</div><div class="stat-lbl">Targets pivoted</div></div>
  <div class="stat"><div class="stat-val">{{ duration_s }}</div><div class="stat-lbl">Seconds</div></div>
</div>

<!-- FINDINGS par type -->
<div class="section">
<h2>Findings</h2>
{% for ftype, flist in findings_by_type.items() %}
<h3>
  <span class="badge badge-type">{{ ftype }}</span>
  <span class="conf">({{ flist|length }})</span>
</h3>
<div class="card">
<table>
<tr>
  <th>Source</th><th>URL</th><th>Extracted</th><th>Conf.</th>
</tr>
{% for f in flist %}
<tr>
  <td><span class="badge badge-src">{{ f.source }}</span></td>
  <td>{% if f.url %}<a href="{{ f.url }}" target="_blank">link</a>{% endif %}</td>
  <td><pre>{{ f.extracted | tojson(indent=2) }}</pre></td>
  <td class="conf">{{ "%.0f"|format(f.confidence * 100) }}%</td>
</tr>
{% endfor %}
</table>
</div>
{% endfor %}
</div>

<!-- ANALYZERS -->
{% if analyzers %}
<div class="section">
<h2>Analysis</h2>
<div class="analyzer-grid">
{% if analyzers.behavior %}
<div class="card">
<h3>Behavior</h3>
<table>
{% for k,v in analyzers.behavior.items() %}
<tr><td style="color:var(--muted);width:40%">{{ k }}</td><td>{{ v }}</td></tr>
{% endfor %}
</table>
</div>
{% endif %}
{% if analyzers.metadata %}
<div class="card">
<h3>Metadata</h3>
<table>
<tr><th>GPS points</th><td>{{ analyzers.metadata.gps_points|length }}</td></tr>
<tr><th>Devices</th><td>{{ analyzers.metadata.devices.keys()|list|join(', ') }}</td></tr>
<tr><th>Serial reuse</th><td>{{ analyzers.metadata.serial_reuse|length }}</td></tr>
<tr><th>Stega signals</th><td>{{ analyzers.metadata.stega_signals|length }}</td></tr>
</table>
</div>
{% endif %}
{% if analyzers.historical %}
<div class="card">
<h3>Timeline</h3>
<table>
<tr><th>Earliest</th><td>{{ analyzers.historical.earliest or '–' }}</td></tr>
<tr><th>Latest</th><td>{{ analyzers.historical.latest or '–' }}</td></tr>
<tr><th>Events</th><td>{{ analyzers.historical.total_events }}</td></tr>
<tr><th>Wayback</th><td>{{ analyzers.historical.wayback_count }}</td></tr>
</table>
</div>
{% endif %}
{% if analyzers.network %}
<div class="card">
<h3>Network</h3>
<table>
<tr><th>Nodes</th><td>{{ analyzers.network.nodes|length }}</td></tr>
<tr><th>Edges</th><td>{{ analyzers.network.edges|length }}</td></tr>
<tr><th>Triangulations</th><td>{{ analyzers.network.triangulations|length }}</td></tr>
<tr><th>Geo clusters</th><td>{{ analyzers.network.geo_clusters|length }}</td></tr>
</table>
</div>
{% endif %}
</div>
</div>
{% endif %}

<!-- SOURCES -->
<div class="section">
<h2>Sources</h2>
<div class="card">
{% for s in sources_used %}
<span class="badge badge-ok">{{ s }}</span>
{% endfor %}
{% for s, err in sources_failed %}
<span class="badge badge-fail" title="{{ err }}">{{ s }}</span>
{% endfor %}
</div>
</div>

<div class="meta" style="margin-top:2rem">Generated by JARVIS MK37 OSINT Engine</div>
</body>
</html>
"""

# ── Reporter ─────────────────────────────────────────────────────────────────

class OSINTReporter:
    """Génère rapport HTML (+ JSON) depuis un OSINTReport."""

    def build(
        self,
        report: "OSINTReport",
        output_dir: Optional[Path] = None,
        pdf: bool = False,
    ) -> Path:
        """
        Écrit `report_<hash>_<ts>.html` (+ .json) dans output_dir.
        Retourne le chemin du fichier HTML.
        """
        if output_dir is None:
            output_dir = Path("memory") / "osint_reports"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ts  = int(report.started_at)
        tag = f"{report.target.hash()}_{ts}"
        html_path = output_dir / f"report_{tag}.html"
        json_path = output_dir / f"report_{tag}.json"

        # JSON brut
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        # HTML
        html_content = self._render_html(report)
        html_path.write_text(html_content, encoding="utf-8")

        # PDF optionnel
        if pdf:
            self._render_pdf(html_content, output_dir / f"report_{tag}.pdf")

        return html_path

    def _render_html(self, report: "OSINTReport") -> str:
        if not _HAS_JINJA:
            return self._fallback_html(report)

        from collections import defaultdict
        findings_by_type: dict = defaultdict(list)
        for f in report.findings:
            findings_by_type[f.type].append(f)

        env = Environment(loader=BaseLoader())
        env.filters["tojson"] = lambda v, indent=None: json.dumps(
            v, ensure_ascii=False, indent=indent, default=str
        )
        tpl = env.from_string(_HTML_TEMPLATE)
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        duration_s = round((report.completed_at - report.started_at), 1)

        return tpl.render(
            target          = report.target.normalized,
            target_type     = report.target.type.value,
            mode            = report.mode,
            findings_count  = len(report.findings),
            findings_by_type= dict(findings_by_type),
            sources_used    = report.sources_used,
            sources_failed  = report.sources_failed,
            targets_count   = len(report.targets_explored),
            duration_s      = duration_s,
            generated_at    = generated,
            cancelled       = report.cancelled,
            analyzers       = report.analyzers or {},
        )

    @staticmethod
    def _render_pdf(html_content: str, path: Path) -> None:
        if not _HAS_WEASY:
            return
        try:
            _WeasyHTML(string=html_content).write_pdf(str(path))
        except Exception:
            pass

    @staticmethod
    def _fallback_html(report: "OSINTReport") -> str:
        """HTML minimal si Jinja2 absent."""
        lines = [
            "<!DOCTYPE html><html><body>",
            f"<h1>OSINT Report — {report.target.normalized}</h1>",
            f"<p>Findings: {len(report.findings)} | "
            f"Sources: {len(report.sources_used)} | "
            f"Duration: {round(report.completed_at - report.started_at, 1)}s</p>",
            "<pre>",
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str)[:50000],
            "</pre></body></html>",
        ]
        return "\n".join(lines)


_REPORTER_SINGLETON: Optional[OSINTReporter] = None


def get_reporter() -> OSINTReporter:
    global _REPORTER_SINGLETON
    if _REPORTER_SINGLETON is None:
        _REPORTER_SINGLETON = OSINTReporter()
    return _REPORTER_SINGLETON
