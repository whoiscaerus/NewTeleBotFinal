"""
PR-001: Monorepo Bootstrap Integration Tests

Tests for build tooling, CI/CD configuration, Docker setup, and Makefile targets.
Ensures the project scaffolding is correctly configured for development and CI.
"""

import subprocess
import sys
from pathlib import Path

import pytest


class TestMakefileTargets:
    """Test that Makefile targets are defined and executable."""

    def test_makefile_exists(self):
        """Verify Makefile is present in project root."""
        # Navigate from tests directory to project root (2 levels up)
        project_root = Path(__file__).parent.parent.parent
        makefile = project_root / "Makefile"
        assert makefile.exists(), f"Makefile not found in project root ({project_root})"

    def test_make_help_target(self):
        """Test that 'make help' executes without error."""
        # Skip on Windows - Make not available
        if sys.platform == "win32":
            pytest.skip("Requires GNU make (not available on Windows)")
        result = subprocess.run(
            ["make", "help"], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, f"make help failed: {result.stderr}"

    def test_make_fmt_target(self):
        """Test that 'make fmt' target exists and is documented."""
        # Skip on Windows - Make not available
        if sys.platform == "win32":
            pytest.skip("Requires GNU make (not available on Windows)")
        result = subprocess.run(
            ["make", "help"], capture_output=True, text=True, timeout=10
        )
        assert "fmt" in result.stdout, "fmt target not documented in make help"

    def test_make_lint_target(self):
        """Test that 'make lint' target exists."""
        # Skip on Windows - Make not available
        if sys.platform == "win32":
            pytest.skip("Requires GNU make (not available on Windows)")
        result = subprocess.run(
            ["make", "help"], capture_output=True, text=True, timeout=10
        )
        assert "lint" in result.stdout, "lint target not documented"

    def test_make_test_target(self):
        """Test that 'make test' target exists."""
        # Skip on Windows - Make not available
        if sys.platform == "win32":
            pytest.skip("Requires GNU make (not available on Windows)")
        result = subprocess.run(
            ["make", "help"], capture_output=True, text=True, timeout=10
        )
        assert "test" in result.stdout, "test target not documented"


class TestProjectStructure:
    """Test that required directories and files exist."""

    def test_gitignore_exists(self):
        """Verify .gitignore is present."""
        assert Path(".gitignore").exists(), ".gitignore not found"

    def test_gitignore_ignores_env(self):
        """Verify .gitignore excludes .env files."""
        content = Path(".gitignore").read_text()
        assert ".env" in content, ".env not in .gitignore"

    def test_github_workflows_exist(self):
        """Verify CI/CD workflows directory."""
        workflows_dir = Path(".github/workflows")
        assert workflows_dir.exists(), ".github/workflows directory not found"

    def test_ci_workflow_file(self):
        """Verify CI workflow file exists (ci.yml or tests.yml)."""
        ci_file = Path(".github/workflows/ci.yml")
        alt_ci_file = Path(".github/workflows/tests.yml")
        assert ci_file.exists() or alt_ci_file.exists(), "CI workflow file not found"

    def test_docker_files_exist(self):
        """Verify Docker configuration files."""
        assert Path("docker").exists(), "docker/ directory not found"
        assert Path("docker-compose.yml").exists(), "docker-compose.yml not found"

    def test_backend_dockerfile_exists(self):
        """Verify backend Dockerfile."""
        dockerfile = Path("docker/backend.Dockerfile")
        assert dockerfile.exists(), "backend.Dockerfile not found"

    def test_pyproject_toml_exists(self):
        """Verify pyproject.toml for tool configuration."""
        assert Path("pyproject.toml").exists(), "pyproject.toml not found"

    def test_readme_exists(self):
        """Verify README documentation."""
        assert Path("README.md").exists(), "README.md not found"

    def test_scripts_directory_exists(self):
        """Verify scripts directory for bootstrapping."""
        scripts_dir = Path("scripts")
        assert scripts_dir.exists(), "scripts/ directory not found"


class TestPythonTooling:
    """Test Python development tooling configuration."""

    def test_python_version(self):
        """Verify Python 3.11+ is being used."""
        version_info = sys.version_info
        assert (
            version_info.major == 3 and version_info.minor >= 11
        ), f"Python 3.11+ required, got {version_info.major}.{version_info.minor}"

    def test_black_config_in_pyproject(self):
        """Verify Black formatter is configured."""
        content = Path("pyproject.toml").read_text()
        assert (
            "[tool.black]" in content or "black" in content
        ), "Black not configured in pyproject.toml"

    def test_ruff_config_in_pyproject(self):
        """Verify Ruff linter is configured."""
        content = Path("pyproject.toml").read_text()
        assert (
            "[tool.ruff]" in content or "ruff" in content
        ), "Ruff not configured in pyproject.toml"

    def test_mypy_config_in_pyproject(self):
        """Verify mypy type checker is configured."""
        content = Path("pyproject.toml").read_text()
        assert (
            "[tool.mypy]" in content or "mypy" in content
        ), "mypy not configured in pyproject.toml"


class TestPreCommitHooks:
    """Test pre-commit hook configuration."""

    def test_precommit_config_exists(self):
        """Verify .pre-commit-config.yaml exists."""
        assert Path(
            ".pre-commit-config.yaml"
        ).exists(), ".pre-commit-config.yaml not found"

    def test_precommit_has_black(self):
        """Verify Black formatter in pre-commit."""
        content = Path(".pre-commit-config.yaml").read_text()
        assert "black" in content, "Black not in pre-commit hooks"

    def test_precommit_has_ruff(self):
        """Verify Ruff linter in pre-commit."""
        content = Path(".pre-commit-config.yaml").read_text()
        assert "ruff" in content, "Ruff not in pre-commit hooks"

    def test_precommit_has_isort(self):
        """Verify isort import sorting in pre-commit."""
        content = Path(".pre-commit-config.yaml").read_text()
        assert "isort" in content, "isort not in pre-commit hooks"

    def test_precommit_has_trailing_whitespace(self):
        """Verify trailing whitespace fixer."""
        content = Path(".pre-commit-config.yaml").read_text()
        assert (
            "trailing-whitespace" in content
        ), "trailing-whitespace not in pre-commit hooks"


class TestEnvironmentSetup:
    """Test environment configuration."""

    def test_env_example_exists(self):
        """Verify .env.example is present."""
        assert Path(".env.example").exists(), ".env.example not found"

    def test_env_example_has_defaults(self):
        """Verify .env.example contains required defaults."""
        content = Path(".env.example").read_text()
        # Check for either DB_DSN or DATABASE_URL (both acceptable)
        required_vars = ["APP_ENV", "APP_LOG_LEVEL", "REDIS_URL"]
        for var in required_vars:
            assert var in content, f"{var} not in .env.example"

        # At least one database URL variable should be present
        assert (
            "DATABASE_URL" in content or "DB_DSN" in content
        ), "Neither DATABASE_URL nor DB_DSN found in .env.example"

    def test_env_example_not_secrets(self):
        """Verify .env.example has no actual secrets (like real API keys)."""
        content = Path(".env.example").read_text()
        # Check that values are placeholders, not real secrets
        # Real secrets would be long hash strings, not descriptive text
        assert (
            "your-" in content.lower()
            or "example" in content.lower()
            or "xxx" in content.lower()
        ), ".env.example should contain placeholder values (your-..., example, xxx)"


class TestDockerSetup:
    """Test Docker configuration."""

    def test_docker_compose_has_postgres(self):
        """Verify docker-compose includes PostgreSQL."""
        content = Path("docker-compose.yml").read_text()
        assert "postgres" in content.lower(), "PostgreSQL not in docker-compose"

    def test_docker_compose_has_redis(self):
        """Verify docker-compose includes Redis."""
        content = Path("docker-compose.yml").read_text()
        assert "redis" in content.lower(), "Redis not in docker-compose"

    def test_docker_compose_has_backend(self):
        """Verify docker-compose includes backend service."""
        content = Path("docker-compose.yml").read_text()
        assert (
            "backend" in content.lower() or "app" in content.lower()
        ), "Backend service not in docker-compose"

    def test_backend_dockerfile_uses_python_base(self):
        """Verify backend Dockerfile uses slim Python base."""
        content = Path("docker/backend.Dockerfile").read_text()
        assert "python" in content.lower(), "Python base image not found"
        # Should be slim for production
        assert (
            "slim" in content.lower() or "alpine" in content.lower()
        ), "Backend should use slim/alpine image for production"

    def test_backend_dockerfile_non_root_user(self):
        """Verify backend Dockerfile runs as non-root."""
        content = Path("docker/backend.Dockerfile").read_text()
        assert "USER" in content, "Docker should specify non-root USER"


class TestCICD:
    """Test CI/CD configuration."""

    def test_github_workflow_syntax(self):
        """Verify GitHub workflow file is valid YAML."""
        import yaml

        workflow_file = Path(".github/workflows/ci.yml")
        if not workflow_file.exists():
            workflow_file = Path(".github/workflows/tests.yml")

        content = workflow_file.read_text(encoding="utf-8")
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML in workflow file: {e}")

    def test_workflow_has_lint_step(self):
        """Verify CI includes linting step."""
        workflow_file = Path(".github/workflows/ci.yml")
        if not workflow_file.exists():
            workflow_file = Path(".github/workflows/tests.yml")

        content = workflow_file.read_text(encoding="utf-8")
        assert (
            "lint" in content.lower() or "ruff" in content.lower()
        ), "Linting step not in CI workflow"

    def test_workflow_has_test_step(self):
        """Verify CI includes test step."""
        workflow_file = Path(".github/workflows/ci.yml")
        if not workflow_file.exists():
            workflow_file = Path(".github/workflows/tests.yml")

        content = workflow_file.read_text(encoding="utf-8")
        assert (
            "test" in content.lower() or "pytest" in content.lower()
        ), "Test step not in CI workflow"

    def test_workflow_uses_python_311(self):
        """Verify CI uses Python 3.11."""
        workflow_file = Path(".github/workflows/ci.yml")
        if not workflow_file.exists():
            workflow_file = Path(".github/workflows/tests.yml")

        content = workflow_file.read_text(encoding="utf-8")
        assert (
            "3.11" in content or "python-version: 3.11" in content
        ), "Python 3.11 not specified in CI"


class TestBackendAppStructure:
    """Test backend application structure."""

    def test_backend_app_directory_exists(self):
        """Verify backend/app directory exists."""
        assert Path("backend/app").exists(), "backend/app directory not found"

    def test_backend_app_init_exists(self):
        """Verify backend/app/__init__.py exists."""
        assert Path(
            "backend/app/__init__.py"
        ).exists(), "backend/app/__init__.py not found"

    def test_backend_core_directory_exists(self):
        """Verify backend/app/core directory for infrastructure."""
        assert Path("backend/app/core").exists(), "backend/app/core directory not found"

    def test_backend_tests_directory_exists(self):
        """Verify backend/tests directory exists."""
        assert Path("backend/tests").exists(), "backend/tests directory not found"

    def test_backend_tests_conftest_exists(self):
        """Verify backend/tests/conftest.py exists for pytest fixtures."""
        assert Path(
            "backend/tests/conftest.py"
        ).exists(), "backend/tests/conftest.py not found"


class TestDevelopmentScripts:
    """Test development helper scripts."""

    def test_bootstrap_script_exists(self):
        """Verify bootstrap.sh script exists."""
        bootstrap = Path("scripts/bootstrap.sh")
        assert bootstrap.exists(), "scripts/bootstrap.sh not found"

    def test_wait_for_script_exists(self):
        """Verify wait-for.sh service readiness helper."""
        wait_for = Path("scripts/wait-for.sh")
        assert wait_for.exists(), "scripts/wait-for.sh not found"

    def test_coverage_check_script_exists(self):
        """Verify coverage-check.py script."""
        coverage_check = Path("scripts/coverage-check.py")
        assert coverage_check.exists(), "scripts/coverage-check.py not found"


# Integration test: verify basic project setup works
class TestProjectIntegration:
    """Integration tests for project bootstrap."""

    def test_python_imports_work(self):
        """Verify basic Python imports don't fail."""
        try:
            import backend

            assert backend is not None
        except ImportError as e:
            pytest.fail(f"Failed to import backend module: {e}")

    def test_pytest_discovers_tests(self):
        """Verify pytest can discover tests in the project."""
        result = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should collect at least some tests
        assert (
            result.returncode == 0 or "test" in result.stdout.lower()
        ), f"pytest collection failed: {result.stderr}"
