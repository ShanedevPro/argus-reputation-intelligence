from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_demo_script_prepares_frontend_database_before_startup():
    script = (ROOT / "scripts" / "run_argus_local_demo.sh").read_text()

    assert "build_postgres_url" in script
    assert 'export POSTGRES_URL="${POSTGRES_URL:-$(build_postgres_url)}"' in script
    assert "pnpm exec tsx lib/db/migrate.ts" in script

    migration_index = script.index("pnpm exec tsx lib/db/migrate.ts")
    backend_index = script.index('HOST="$BACKEND_HOST" PORT="$BACKEND_PORT"')
    frontend_index = script.index('pnpm dev')

    assert migration_index < backend_index
    assert migration_index < frontend_index


def test_local_demo_script_uses_wsl_safe_temp_directory_for_node_tools():
    script = (ROOT / "scripts" / "run_argus_local_demo.sh").read_text()

    assert 'RUNTIME_TMPDIR="${ARGUS_TMPDIR:-/tmp}"' in script
    assert 'export TMPDIR="$RUNTIME_TMPDIR"' in script
    assert 'export TMP="$RUNTIME_TMPDIR"' in script
    assert 'export TEMP="$RUNTIME_TMPDIR"' in script

    temp_index = script.index('RUNTIME_TMPDIR="${ARGUS_TMPDIR:-/tmp}"')
    migration_index = script.index("pnpm exec tsx lib/db/migrate.ts")
    frontend_index = script.index("pnpm dev")

    assert temp_index < migration_index
    assert temp_index < frontend_index
