"""Visual system and browser hydration for Argus report artifacts."""

ARGUS_CSS = """
/* Tokens */
:root {
  --argus-color-canvas: #eef2f6;
  --argus-color-paper: #ffffff;
  --argus-color-ink: #111827;
  --argus-color-muted: #5b6472;
  --argus-color-subtle: #8b93a1;
  --argus-color-hairline: #d7dde6;
  --argus-color-accent: #155e8a;
  --argus-color-accent-soft: #e8f3fa;
  --argus-color-risk: #9a3412;
  --argus-color-warning: #a16207;
  --argus-color-success: #166534;
  --argus-color-down: #b91c1c;
  --argus-space-xs: 6px;
  --argus-space-sm: 10px;
  --argus-space-md: 16px;
  --argus-space-lg: 24px;
  --argus-space-xl: 36px;
  --argus-space-section: 48px;
  --argus-layout-max: 1180px;
  --argus-radius-card: 8px;
  --argus-radius-soft: 4px;
  --argus-shadow-paper: 0 18px 60px rgba(15, 23, 42, 0.10);
}

/* Base */
* { box-sizing: border-box; }
html { background: var(--argus-color-canvas); }
body {
  margin: 0;
  background: var(--argus-color-canvas);
  color: var(--argus-color-ink);
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
  font-size: 16px;
  line-height: 1.68;
  text-rendering: optimizeLegibility;
}
a { color: var(--argus-color-accent); }
img { max-width: 100%; height: auto; }

/* Report shell */
.argus-report {
  max-width: var(--argus-layout-max);
  margin: 0 auto;
  padding: 34px 28px 72px;
}
.argus-paper {
  overflow: hidden;
  background: var(--argus-color-paper);
  border: 1px solid var(--argus-color-hairline);
  box-shadow: var(--argus-shadow-paper);
}
.argus-cover {
  padding: 58px 64px 44px;
  border-bottom: 1px solid var(--argus-color-hairline);
  background:
    linear-gradient(90deg, rgba(21, 94, 138, 0.08), transparent 44%),
    linear-gradient(180deg, #ffffff, #f8fafc);
}
.argus-label {
  color: var(--argus-color-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.argus-title {
  max-width: 920px;
  margin: 16px 0 12px;
  font-size: 46px;
  line-height: 1.08;
  font-weight: 780;
  letter-spacing: 0;
}
.argus-subtitle {
  max-width: 760px;
  margin: 0 0 var(--argus-space-md);
  color: var(--argus-color-muted);
  font-size: 18px;
}
.argus-tagline {
  max-width: 760px;
  margin: 0 0 var(--argus-space-sm);
  color: var(--argus-color-accent);
  font-weight: 720;
}
.argus-cover-summary {
  max-width: 780px;
  margin: 0 0 var(--argus-space-lg);
  color: var(--argus-color-ink);
  font-size: 17px;
}
.argus-hero-highlights,
.argus-hero-actions {
  display: grid;
  gap: var(--argus-space-sm);
  max-width: 860px;
  margin: var(--argus-space-lg) 0;
  padding: 0;
  list-style: none;
}
.argus-hero-highlights li,
.argus-hero-actions li {
  position: relative;
  padding-left: 20px;
  color: var(--argus-color-ink);
}
.argus-hero-highlights li::before,
.argus-hero-actions li::before {
  position: absolute;
  top: 0.7em;
  left: 0;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--argus-color-accent);
  content: "";
}
.argus-hero-actions {
  padding-top: var(--argus-space-md);
  border-top: 1px solid var(--argus-color-hairline);
}
.argus-hero-actions li::before { background: var(--argus-color-success); }
.argus-meta, .argus-muted { color: var(--argus-color-muted); }
.argus-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--argus-space-xs);
  margin-top: var(--argus-space-lg);
  font-size: 13px;
}
.argus-meta-item {
  display: inline-flex;
  max-width: 100%;
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-soft);
  background: rgba(255, 255, 255, 0.72);
  padding: 4px 8px;
}
.argus-toc {
  border-bottom: 1px solid var(--argus-color-hairline);
  background: #fbfdff;
  padding: 34px 64px 36px;
}
.argus-toc-links {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px 16px;
  margin-top: var(--argus-space-md);
}
.argus-toc a {
  display: grid;
  gap: 4px;
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  background: #ffffff;
  padding: 13px 15px;
  color: var(--argus-color-muted);
  text-decoration: none;
}
.argus-toc a:hover {
  border-color: rgba(21, 94, 138, 0.32);
  color: var(--argus-color-accent);
}
.argus-toc-title {
  color: inherit;
  font-weight: 680;
}
.argus-toc-description {
  color: var(--argus-color-subtle);
  font-size: 12px;
  line-height: 1.45;
}
.argus-content {
  min-width: 0;
  padding: 40px 64px 64px;
}
.argus-section {
  margin: 0 0 var(--argus-space-section);
  scroll-margin-top: 24px;
}
.argus-footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--argus-space-sm);
  border-top: 1px solid var(--argus-color-hairline);
  padding: 24px 64px 36px;
  color: var(--argus-color-muted);
  font-size: 13px;
}

/* Prose */
.argus-section h2,
.argus-prose h2 {
  margin: 0 0 18px;
  font-size: 28px;
  line-height: 1.18;
  font-weight: 760;
  letter-spacing: 0;
}
.argus-prose h3 {
  margin: 34px 0 14px;
  font-size: 21px;
  line-height: 1.28;
  font-weight: 740;
  letter-spacing: 0;
}
.argus-prose h4 {
  margin: 26px 0 10px;
  font-size: 17px;
  line-height: 1.36;
  font-weight: 720;
  letter-spacing: 0;
}
.argus-prose p {
  margin: 0 0 16px;
  max-width: 76ch;
  font-size: 16px;
}
.argus-prose ul,
.argus-prose ol {
  margin: 0 0 18px;
  padding-left: 1.35em;
}
.argus-prose li {
  margin: 6px 0;
  padding-left: 2px;
}
.argus-prose blockquote {
  margin: 24px 0;
  border-left: 4px solid var(--argus-color-accent);
  background: var(--argus-color-accent-soft);
  padding: 16px 20px;
  color: var(--argus-color-ink);
}
.argus-prose figure {
  margin: 24px 0;
}
.argus-prose figcaption {
  margin-bottom: var(--argus-space-sm);
  color: var(--argus-color-muted);
  font-size: 13px;
}
.argus-prose pre {
  overflow-x: auto;
  border: 1px solid #1f2937;
  border-radius: var(--argus-radius-card);
  background: #111827;
  color: #f8fafc;
  padding: 16px;
  font-size: 13px;
  line-height: 1.58;
}
.argus-prose code {
  border-radius: var(--argus-radius-soft);
  background: #eef2f7;
  padding: 2px 5px;
  font-size: 0.92em;
}
.argus-prose pre code {
  background: transparent;
  padding: 0;
}

/* Components */
.argus-heading-anchor {
  display: block;
  height: 0;
}
.argus-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--argus-space-md);
  margin: var(--argus-space-lg) 0;
}
.argus-kpi {
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  background: #ffffff;
  padding: 17px;
}
.argus-kpi-label {
  color: var(--argus-color-muted);
  font-size: 13px;
  font-weight: 680;
}
.argus-kpi-value {
  margin-top: 8px;
  color: var(--argus-color-ink);
  font-size: 30px;
  font-weight: 760;
  line-height: 1;
}
.argus-kpi-unit {
  margin-left: 4px;
  color: var(--argus-color-muted);
  font-size: 14px;
  font-weight: 560;
}
.argus-kpi-delta {
  margin-top: 10px;
  color: var(--argus-color-muted);
  font-size: 13px;
  font-weight: 680;
}
.argus-kpi.argus-tone-up,
.argus-kpi.argus-tone-success { border-top: 3px solid var(--argus-color-success); }
.argus-kpi.argus-tone-warning { border-top: 3px solid var(--argus-color-warning); }
.argus-kpi.argus-tone-risk,
.argus-kpi.argus-tone-down { border-top: 3px solid var(--argus-color-risk); }
.argus-tone-up,
.argus-tone-success { color: var(--argus-color-success); }
.argus-tone-warning { color: var(--argus-color-warning); }
.argus-tone-risk,
.argus-tone-down { color: var(--argus-color-risk); }
.argus-tone-neutral { color: var(--argus-color-muted); }
.argus-callout {
  margin: var(--argus-space-lg) 0;
  border: 1px solid var(--argus-color-hairline);
  border-left: 4px solid var(--argus-color-accent);
  border-radius: var(--argus-radius-card);
  background: var(--argus-color-accent-soft);
  padding: 17px 20px;
}
.argus-callout-title {
  display: block;
  margin-bottom: 6px;
  color: var(--argus-color-ink);
  font-size: 15px;
}
.argus-callout p:last-child { margin-bottom: 0; }
.argus-callout-info,
.argus-callout-note { border-left-color: var(--argus-color-accent); }
.argus-callout-success { border-left-color: var(--argus-color-success); background: #eef8f2; }
.argus-callout-warning { border-left-color: var(--argus-color-warning); background: #fff8e6; }
.argus-callout-risk { border-left-color: var(--argus-color-risk); background: #fff1ed; }
.argus-callout-neutral { border-left-color: var(--argus-color-subtle); background: #f8fafc; }
.argus-table-wrap {
  width: 100%;
  margin: var(--argus-space-lg) 0;
  overflow-x: auto;
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  background: #ffffff;
}
.argus-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 560px;
}
.argus-table caption {
  caption-side: top;
  padding: 12px 14px 6px;
  color: var(--argus-color-muted);
  text-align: left;
  font-size: 13px;
}
.argus-table-cell {
  border-top: 1px solid var(--argus-color-hairline);
  padding: 12px 14px;
  color: var(--argus-color-ink);
  text-align: left;
  vertical-align: top;
}
.argus-table-cell p:last-child { margin-bottom: 0; }
.argus-table-header-row .argus-table-cell {
  background: #f3f6f9;
  font-weight: 700;
  color: #1f2937;
}
.argus-chart-frame {
  margin: var(--argus-space-lg) 0;
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  background: #ffffff;
  padding: 18px 18px 14px;
}
.argus-chart-title {
  margin: 0 0 var(--argus-space-md);
  color: var(--argus-color-ink);
  font-size: 14px;
}
.argus-chart-viewport {
  position: relative;
  height: 320px;
  min-height: 260px;
}
.argus-echart {
  display: block;
  width: 100%;
  height: 100%;
}
.argus-chart-error {
  margin-top: 10px;
  color: var(--argus-color-risk);
  font-size: 13px;
}
.argus-chart-error:empty { display: none; }
.argus-chart-empty-message,
.argus-chart-error-state .argus-chart-error {
  border: 1px dashed var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  background: #f8fafc;
  padding: 28px 18px;
  color: var(--argus-color-muted);
  text-align: center;
  font-size: 13px;
}
.argus-chart-error-state .argus-chart-error {
  color: var(--argus-color-risk);
}
.argus-analysis-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--argus-space-md);
  margin: var(--argus-space-lg) 0;
}
.argus-analysis-card {
  border: 1px solid var(--argus-color-hairline);
  border-radius: var(--argus-radius-card);
  padding: 16px;
  background: #ffffff;
}
.argus-analysis-card-title {
  color: var(--argus-color-accent);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.argus-analysis-card-item {
  margin: 12px 0 0;
  color: var(--argus-color-ink);
}

/* Responsive */
@media (max-width: 820px) {
  .argus-report { padding: 0; }
  .argus-paper { border-left: 0; border-right: 0; }
  .argus-cover, .argus-toc, .argus-content, .argus-footer { padding-left: 22px; padding-right: 22px; }
  .argus-cover { padding-top: 34px; padding-bottom: 28px; }
  .argus-title { font-size: 34px; line-height: 1.12; }
  .argus-subtitle { font-size: 16px; }
  .argus-meta { display: grid; }
  .argus-kpi-grid,
  .argus-analysis-grid { grid-template-columns: minmax(0, 1fr); }
  .argus-toc {
    padding-top: 24px;
    padding-bottom: 24px;
  }
  .argus-toc-links {
    grid-template-columns: minmax(0, 1fr);
  }
  .argus-table { min-width: 520px; }
  .argus-chart-viewport { height: 280px; }
}

@page {
  size: A4;
  margin: 16mm 14mm 18mm;
}

@media print {
  * {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  html,
  body {
    background: #ffffff !important;
  }
  .argus-report {
    max-width: none;
    padding: 0 !important;
    background: #ffffff !important;
  }
  .argus-paper {
    overflow: visible;
    width: auto;
    max-width: none;
    margin: 0;
    border: 0;
    box-shadow: none;
  }
  .argus-cover,
  .argus-toc,
  .argus-content,
  .argus-footer {
    padding-left: 0;
    padding-right: 0;
  }
  h2,
  h3,
  .argus-section h2,
  .argus-prose h2,
  .argus-prose h3 {
    break-after: avoid;
  }
  .argus-section,
  .argus-card,
  .argus-kpi,
  .argus-callout,
  .argus-analysis-card,
  .argus-table-wrap,
  .argus-chart-frame {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  thead {
    display: table-header-group;
  }
  tr {
    break-inside: avoid;
  }
  .argus-table-wrap {
    overflow: visible !important;
  }
  .argus-table {
    width: 100% !important;
    min-width: 0;
    table-layout: fixed;
  }
  .argus-table th,
  .argus-table td,
  .argus-table-cell {
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .argus-chart-frame,
  .argus-chart-viewport,
  .argus-echart,
  .argus-chart-viewport canvas {
    max-width: 100% !important;
  }
}
""".strip()

ARGUS_CHART_HYDRATION_JS = """
(function () {
  var charts = [];

  window.__ARGUS_PRINT_READY__ = false;

  function writeError(node, message) {
    var frame = node.closest && node.closest('.argus-chart-frame');
    var error = frame && frame.querySelector('.argus-chart-error');
    if (error) error.textContent = message;
  }

  function markPrintReady() {
    window.__ARGUS_PRINT_READY__ = true;
  }

  function boot() {
    if (!window.echarts) {
      document.querySelectorAll('.argus-echart[data-argus-chart-id]').forEach(function (node) {
        writeError(node, '图表运行时不可用，原始图表数据仍保留在报告中。');
      });
      markPrintReady();
      return;
    }
    document.querySelectorAll('.argus-echart[data-argus-chart-id]').forEach(function (node) {
      var chartId = node.getAttribute('data-argus-chart-id');
      var script = document.getElementById('argus-echart-option-' + chartId);
      if (!script) {
        writeError(node, '图表配置缺失：' + chartId);
        return;
      }
      try {
        var option = JSON.parse(script.textContent || '{}');
        var chart = echarts.init(node, null, { renderer: 'canvas' });
        chart.setOption(option);
        charts.push(chart);
      } catch (error) {
        writeError(node, '图表暂无法渲染：' + error.message);
      }
    });
    requestAnimationFrame(function () {
      charts.forEach(function (chart) {
        try { chart.resize(); } catch (error) {}
      });
      markPrintReady();
    });
  }
  window.addEventListener('resize', function () {
    charts.forEach(function (chart) {
      try { chart.resize(); } catch (error) {}
    });
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
""".strip()
