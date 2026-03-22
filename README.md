# apple-health-mcp

MCP server that loads your Apple Health export into an in-memory SQLite database and exposes it to LLMs via the [Model Context Protocol](https://modelcontextprotocol.io/).

## Quick start

```bash
uvx apple-health-mcp --input ~/Downloads/export.zip
```

Or install it permanently:

```bash
uv tool install apple-health-mcp
apple-health-mcp --input ~/Downloads/export.zip
```

## Exporting your data from Apple Health

1. Open the **Health** app on your iPhone
2. Tap your profile picture (top-right)
3. Scroll down and tap **Export All Health Data**
4. Confirm — this may take a few minutes
5. Save or AirDrop the resulting `export.zip` to your Mac

## Claude Desktop integration

Add this to your `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "apple-health": {
      "command": "uvx",
      "args": [
        "apple-health-mcp",
        "--input",
        "/absolute/path/to/export.zip"
      ]
    }
  }
}
```

Restart Claude Desktop. The tools will appear in the tools menu.

## MCP tools

### `list_metrics()`

Returns every distinct record type and its count.

### `list_workout_types()`

Returns every distinct workout activity type and its count.

### `summary(metric, period)`

Aggregates a metric by `day`, `week`, or `month`. Returns count, avg, min, max, and sum.

```
summary("StepCount", "week")
summary("HeartRate", "month")
```

### `query(sql)`

Run arbitrary read-only SQL against the database. Only `SELECT` statements are allowed.

**Schema:**

```sql
records(type, source_name, unit, value, start_date, end_date)
workouts(activity_type, source_name, duration, duration_unit,
         total_energy_kcal, total_distance, distance_unit, start_date, end_date)
```

**Examples:**

```sql
-- Daily step totals for the last 30 days
SELECT substr(start_date, 1, 10) AS day, sum(CAST(value AS REAL)) AS steps
FROM records WHERE type = 'StepCount'
GROUP BY day ORDER BY day DESC LIMIT 30;

-- Longest runs
SELECT start_date, duration, total_distance, distance_unit
FROM workouts WHERE activity_type = 'Running'
ORDER BY total_distance DESC LIMIT 10;
```

## Environment variable

Instead of `--input`, you can set:

```bash
export HEALTH_EXPORT_PATH=~/Downloads/export.zip
```

## Local development

```bash
git clone https://github.com/smarzola/apple-health-mcp
cd apple-health-mcp
uv sync
uv run apple-health-mcp --input ~/Downloads/export.zip
```

### Lint & typecheck

```bash
uv run ruff check src/             # lint
uv run ruff format --check src/    # format check
uv run mypy src/                   # typecheck
```

To auto-fix lint and formatting issues:

```bash
uv run ruff check --fix src/       # auto-fix lint
uv run ruff format src/            # auto-format
```

## Cutting a release

```bash
# Tag and push — GitHub Actions publishes to PyPI automatically
gh release create v0.1.0 --generate-notes
```

Before the first publish, configure a [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) on PyPI:

1. Go to [pypi.org](https://pypi.org) → your account → Publishing
2. Add a new pending publisher with:
   - PyPI project name: `apple-health-mcp`
   - Owner: `smarzola`
   - Repository: `apple-health-mcp`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

## License

MIT
