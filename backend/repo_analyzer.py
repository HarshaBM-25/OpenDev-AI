"""
repo_analyzer.py — AI-powered repository code understanding.

Scans cloned repo to understand:
  - Primary language & framework
  - Project type (web app, API, library, CLI, mobile, etc.)
  - Tech stack detected from config files
  - Code quality signals
  - File structure summary
  - Dependencies
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", ".next", "__pycache__", "node_modules",
    ".venv", "venv", "dist", "build", "coverage",
    ".cache", ".parcel-cache",
})

# Framework detection rules: file/dir presence → framework name
FRAMEWORK_SIGNATURES: list[tuple[list[str], str]] = [
    (["next.config.js", "next.config.ts"],              "Next.js"),
    (["nuxt.config.js", "nuxt.config.ts"],              "Nuxt.js"),
    (["svelte.config.js"],                              "SvelteKit"),
    (["angular.json"],                                   "Angular"),
    (["vue.config.js"],                                  "Vue.js"),
    (["remix.config.js"],                               "Remix"),
    (["gatsby-config.js"],                              "Gatsby"),
    (["vite.config.js", "vite.config.ts"],              "Vite"),
    (["astro.config.mjs"],                              "Astro"),
    (["manage.py", "django.py"],                        "Django"),
    (["app.py", "wsgi.py"],                             "Flask/FastAPI"),
    (["fastapi", "uvicorn"],                            "FastAPI"),  # checked via deps
    (["Cargo.toml"],                                    "Rust"),
    (["go.mod"],                                        "Go"),
    (["pom.xml"],                                       "Java/Maven"),
    (["build.gradle"],                                  "Java/Gradle"),
    (["pubspec.yaml"],                                  "Flutter/Dart"),
    (["Package.swift"],                                 "Swift"),
    (["*.csproj"],                                      ".NET"),
    (["Gemfile"],                                       "Ruby on Rails"),
    (["mix.exs"],                                       "Elixir/Phoenix"),
    (["composer.json"],                                 "PHP"),
    (["docker-compose.yml", "docker-compose.yaml"],    "Docker Compose"),
    (["terraform"],                                     "Terraform"),
]

PROJECT_TYPE_RULES: list[tuple[list[str], str]] = [
    (["pages", "app", "src/pages"],                     "Web Application"),
    (["api", "routes", "controllers"],                   "API / Backend Service"),
    (["lib", "src/lib", "index.ts", "index.js"],        "Library / Package"),
    (["cli", "bin", "cmd"],                             "CLI Tool"),
    (["mobile", "ios", "android", "pubspec.yaml"],      "Mobile App"),
    (["lambda", "functions", "serverless.yml"],         "Serverless Functions"),
    (["infra", "terraform", "pulumi"],                  "Infrastructure / IaC"),
    (["tests", "test", "spec", "__tests__"],            "Test Suite"),
    (["docs", "documentation"],                         "Documentation"),
]

EXT_LANG: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
    ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".swift": "Swift",
    ".kt": "Kotlin", ".dart": "Dart", ".ex": "Elixir",
    ".vue": "Vue", ".svelte": "Svelte", ".sol": "Solidity",
}


def analyze_repository(repo_path: Path) -> dict[str, Any]:
    """
    Deep-scan a cloned repo and return a structured analysis.

    Returns:
    {
        "primary_language":  str,
        "languages":         dict[str, int],   # lang → file count
        "frameworks":        list[str],
        "project_type":      str,
        "tech_stack":        list[str],
        "dependencies":      list[str],        # top-level dep names
        "has_tests":         bool,
        "has_docker":        bool,
        "has_ci":            bool,
        "file_count":        int,
        "directory_count":   int,
        "key_files":         list[str],        # notable config/entry files
        "structure_summary": str,              # human-readable summary
        "code_quality":      dict,
        "readme_excerpt":    str,
    }
    """
    lang_counts: dict[str, int] = {}
    file_count = 0
    dir_count = 0
    all_files: list[Path] = []

    for path in repo_path.rglob("*"):
        rel = path.relative_to(repo_path)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if path.is_dir():
            dir_count += 1
        else:
            file_count += 1
            lang = EXT_LANG.get(path.suffix.lower())
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
            all_files.append(path)

    # Primary language
    primary_language = max(lang_counts, key=lambda k: lang_counts[k]) if lang_counts else "Unknown"

    # Frameworks
    frameworks: list[str] = []
    for files_to_check, fw_name in FRAMEWORK_SIGNATURES:
        for fname in files_to_check:
            if "*" in fname:
                if any(p.match(fname) for p in all_files):
                    frameworks.append(fw_name)
                    break
            elif (repo_path / fname).exists():
                frameworks.append(fw_name)
                break

    # Project type
    project_type = "Unknown"
    for dirs_to_check, ptype in PROJECT_TYPE_RULES:
        for d in dirs_to_check:
            if (repo_path / d).exists():
                project_type = ptype
                break
        if project_type != "Unknown":
            break

    # Key files
    key_file_names = [
        "README.md", "README.rst", "package.json", "pyproject.toml",
        "requirements.txt", "Cargo.toml", "go.mod", "Gemfile",
        "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
        ".github/workflows", "terraform", "serverless.yml",
        "next.config.js", "vite.config.ts", "angular.json",
        "manage.py", "app.py", "main.py", "index.ts", "index.js",
    ]
    key_files: list[str] = []
    for kf in key_file_names:
        if (repo_path / kf).exists():
            key_files.append(kf)

    # Dependencies
    dependencies = _extract_dependencies(repo_path)

    # Tech stack = frameworks + deps-derived technologies
    tech_stack = list(set(frameworks + _infer_tech_from_deps(dependencies)))

    # Quality signals
    has_tests = any(
        (repo_path / d).exists() for d in ["tests", "test", "spec", "__tests__", "pytest.ini"]
    )
    has_docker = any(
        (repo_path / f).exists()
        for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
    )
    has_ci = (repo_path / ".github" / "workflows").exists() or any(
        (repo_path / f).exists() for f in [".travis.yml", ".circleci", "Jenkinsfile", ".gitlab-ci.yml"]
    )

    # README excerpt
    readme_excerpt = _read_readme(repo_path)

    # Code quality
    code_quality = _assess_code_quality(repo_path, all_files, has_tests, has_docker, has_ci)

    # Structure summary
    structure_summary = _build_structure_summary(
        repo_path, primary_language, frameworks, project_type, file_count, has_tests
    )

    result = {
        "primary_language": primary_language,
        "languages": dict(sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)),
        "frameworks": frameworks,
        "project_type": project_type,
        "tech_stack": tech_stack,
        "dependencies": dependencies[:30],
        "has_tests": has_tests,
        "has_docker": has_docker,
        "has_ci": has_ci,
        "file_count": file_count,
        "directory_count": dir_count,
        "key_files": key_files,
        "structure_summary": structure_summary,
        "code_quality": code_quality,
        "readme_excerpt": readme_excerpt[:600] if readme_excerpt else "",
    }

    logger.info(
        "repo_analyzer: %s project | lang=%s | frameworks=%s | files=%d",
        project_type, primary_language, frameworks, file_count,
    )
    return result


def _extract_dependencies(repo_path: Path) -> list[str]:
    deps: list[str] = []

    # package.json
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps += list(data.get("dependencies", {}).keys())
            deps += list(data.get("devDependencies", {}).keys())
        except Exception:
            pass

    # requirements.txt
    req = repo_path / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pkg_name = line.split(">=")[0].split("==")[0].split("[")[0].strip()
                if pkg_name:
                    deps.append(pkg_name)

    # pyproject.toml
    pyproj = repo_path / "pyproject.toml"
    if pyproj.exists():
        content = pyproj.read_text(encoding="utf-8", errors="ignore")
        import re
        deps += re.findall(r'"([a-zA-Z0-9_\-]+)[>=<\[]', content)

    return list(dict.fromkeys(deps))  # dedupe, preserve order


def _infer_tech_from_deps(deps: list[str]) -> list[str]:
    dep_lower = {d.lower() for d in deps}
    tech: list[str] = []
    mappings = {
        "react": "React", "vue": "Vue.js", "angular": "Angular",
        "express": "Express.js", "fastapi": "FastAPI", "django": "Django",
        "flask": "Flask", "rails": "Ruby on Rails",
        "prisma": "Prisma ORM", "mongoose": "MongoDB/Mongoose",
        "firebase": "Firebase", "supabase": "Supabase",
        "postgresql": "PostgreSQL", "mysql": "MySQL", "redis": "Redis",
        "graphql": "GraphQL", "apollo": "Apollo",
        "tailwindcss": "Tailwind CSS", "bootstrap": "Bootstrap",
        "jest": "Jest", "pytest": "pytest", "mocha": "Mocha",
        "webpack": "Webpack", "vite": "Vite",
        "stripe": "Stripe", "twilio": "Twilio",
        "openai": "OpenAI", "anthropic": "Anthropic",
        "tensorflow": "TensorFlow", "torch": "PyTorch",
        "celery": "Celery", "redis": "Redis",
        "docker": "Docker", "kubernetes": "Kubernetes",
    }
    for dep_key, tech_name in mappings.items():
        if dep_key in dep_lower:
            tech.append(tech_name)
    return tech


def _read_readme(repo_path: Path) -> str:
    for name in ["README.md", "readme.md", "README.rst", "README.txt", "README"]:
        p = repo_path / name
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")[:1500]
            except OSError:
                pass
    return ""


def _assess_code_quality(
    repo_path: Path,
    all_files: list[Path],
    has_tests: bool,
    has_docker: bool,
    has_ci: bool,
) -> dict[str, Any]:
    score = 50
    signals: list[str] = []

    if has_tests:
        score += 15
        signals.append("✓ Test suite present")
    else:
        signals.append("✗ No tests detected")

    if has_ci:
        score += 10
        signals.append("✓ CI/CD configured")
    else:
        signals.append("✗ No CI/CD found")

    if has_docker:
        score += 5
        signals.append("✓ Docker configured")

    if (repo_path / ".gitignore").exists():
        score += 5
        signals.append("✓ .gitignore present")
    else:
        score -= 5
        signals.append("✗ No .gitignore")

    if (repo_path / ".env").exists():
        score -= 15
        signals.append("✗ .env committed (security risk)")

    if (repo_path / "node_modules").exists():
        score -= 10
        signals.append("✗ node_modules committed")

    if any(p.name == "LICENSE" or p.name == "LICENSE.md" for p in all_files):
        score += 5
        signals.append("✓ License file present")

    score = max(0, min(100, score))
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "F"

    return {"score": score, "grade": grade, "signals": signals}


def _build_structure_summary(
    repo_path: Path,
    primary_language: str,
    frameworks: list[str],
    project_type: str,
    file_count: int,
    has_tests: bool,
) -> str:
    fw_str = " + ".join(frameworks[:3]) if frameworks else primary_language
    test_str = "with test coverage" if has_tests else "no tests detected"
    return (
        f"A {project_type.lower()} built with {fw_str}. "
        f"Contains {file_count} files ({test_str})."
    )
