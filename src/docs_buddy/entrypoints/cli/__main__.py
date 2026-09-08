"""This module implements the CLI functionality"""

from pathlib import Path
import os
import argparse
import logging
import sys
import textwrap

from docs_buddy import adapters, services, domain, common
from docs_buddy.services import commands
from docs_buddy.entrypoints import bootstrap
from docs_buddy._vendor.dotconfig import Config

log = logging.getLogger(__name__)

CONFIG_FILE_NAME = ".docs_buddy.yaml"
DEFAULT_FILE_EXTENSIONS = ("mdx", "md")


def _configure_logging(log_level: int) -> None:
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _get_data_dir() -> Path:
    """Return the XDG data directory"""
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        base = Path(xdg_data_home)
    else:
        base = Path.home() / ".local" / "share"
    return base / "docs-buddy"


def _init_config() -> None:
    """Create a .docs_buddy.yaml config file from the template in the current directory."""
    template = Path(__file__).parent / "data" / "docs_buddy_template.yaml"
    target = Path.cwd() / CONFIG_FILE_NAME
    if target.exists():
        print(f"Config file already exists: {target}", file=sys.stderr)
        sys.exit(1)
    target.write_text(template.read_text())
    print(f"Created config file: {target}. Update the git source(s)")


def _find_config() -> Path | None:
    """Walk up from cwd to home, return first .docs_buddy.yaml found."""
    current = Path.cwd().resolve()
    home = Path.home().resolve()
    while current >= home:
        candidate = current / CONFIG_FILE_NAME
        if candidate.exists():
            return candidate
        if current == home:
            break
        current = current.parent
    return None


def _load_config() -> Config:
    """Load the config file found by _find_config."""
    config_path = _find_config()
    if config_path is None:
        print(
            f"No {CONFIG_FILE_NAME} found. Run --init first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Config.from_yaml(config_path)


def _derive_repo_id(repo_url: str) -> str:
    """Strip protocol from URL to obtain a filesystem-friendly repo ID."""
    return repo_url.split("://", 1)[-1]


def main() -> None:
    """CLI main entrypoint"""

    parser = argparse.ArgumentParser(description="Docs Buddy CLI")

    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="The log level to use",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--update-sources",
        action="store_true",
        help="Update document sources from repository and recreate index",
    )
    group.add_argument(
        "--init",
        action="store_true",
        help="Create a .docs_buddy.yaml config file from template in the current directory",
    )
    group.add_argument(
        "--current-config",
        action="store_true",
        help="Show location of the current config file in use",
    )
    group.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Query string to search the documentation",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level)
    _configure_logging(log_level)

    data_dir = _get_data_dir()

    if args.init:
        _init_config()
    elif args.current_config:
        config_path = _find_config()
        if config_path:
            print(config_path)
        else:
            print(
                f"No {CONFIG_FILE_NAME} found from current directory up to home.",
                file=sys.stderr,
            )
            sys.exit(1)
    elif args.update_sources:
        config = _load_config()
        for entry in config.repositories:  # type: ignore[attr-defined]
            repo_url = entry.repo_url
            branch = entry.branch
            repo_id = _derive_repo_id(repo_url)

            try:
                doc_extensions = entry.file_extensions
            except AttributeError:
                doc_extensions = DEFAULT_FILE_EXTENSIONS

            message_bus = bootstrap.compose_message_bus(
                repository_storage_path=data_dir / "repos" / repo_id,
                doc_extensions=tuple(doc_extensions),
                chunks_storage_path=data_dir / "chunks" / repo_id,
                lexical_index_storage_path=data_dir / "whoosh" / repo_id,
            )

            sync_repo_command = commands.SyncRepo(url=repo_url, branch=branch)

            try:
                message_bus.send(sync_repo_command)
            except common.DocsBuddyError as exc:
                msg = f"Error encountered updating sources: {exc}"
                log.exception(msg)
                sys.exit(1)

    elif args.query:
        config = _load_config()
        tools = []
        for repo_config in config.repositories:  # type: ignore[attr-defined]
            repo_url = repo_config.repo_url
            repo_id = _derive_repo_id(repo_url)

            index_path = data_dir / "whoosh" / repo_id
            if not index_path.exists():
                log.warning("No index found for %s. Skipping.", repo_id)
                continue

            file_prefix = repo_config.formatted_file_prefix
            document_index = adapters.WhooshIndexSearcher(index_path, file_prefix)

            content_description = repo_config.repo_content_description
            tool_id = common.sanitize_to_python_id(repo_id)
            tools.append(
                adapters.make_search_tool(document_index, tool_id, content_description)
            )

        if not tools:
            log.error(
                "No valid documentation indexes found. Please sync repositories first."
            )
            sys.exit(1)

        try:
            query = domain.Query(args.query)
        except domain.InvalidQueryError as exc:
            log.error("Invalid query detected: %s", exc)
            sys.exit(1)

        try:
            research_user_query = adapters.make_openai_research_agent(
                config.system_prompt, config.model_name, config.openai_base_url
            )
        except adapters.AgentError:
            log.exception("Something went wrong while configuring the agent")
            sys.exit(1)

        response = services.find_answer(query, research_user_query, tools)

        print("Docs Buddy Response:\n")
        print(response.answer)
        print("\nReferences:\n")
        for path in response.citations:
            print(path + "\n")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
