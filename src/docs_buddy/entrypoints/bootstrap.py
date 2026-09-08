"""Composition root for dependency injection"""

import functools
from pathlib import Path
import typing

from docs_buddy import services, adapters
from docs_buddy.services import commands, events, handlers, mappings
from docs_buddy.common import PathLike

frontmatter_annotate_document = functools.partial(
    services.annotate_document,
    metadata_extractor=adapters.frontmatter_metadata_extractor,
)


def compose_message_bus(
    repository_storage_path: PathLike,
    chunks_storage_path: PathLike,
    lexical_index_storage_path: PathLike,
    doc_extensions: tuple[str, ...],
) -> handlers.MessageBus:
    """Create and configure the application message bus with all dependencies.

    Args:
        repository_storage_path: Path to the cloned repository storage.
        chunks_storage_path: Path where processed document chunks are stored.
        lexical_index_storage_path: Path where the Whoosh lexical index is stored.

    Returns:
        A configured InMemoryMessageBus with registered command and event handlers.
    """

    message_bus = adapters.InMemoryMessageBus()

    dependency_pool = {
        services.RepoStorage: adapters.FileSystemRepoStorage(repository_storage_path),
        handlers.MessageBus: message_bus,
        services.DocsArtifactStorage: adapters.FileSystemDocsStorage(
            repository_storage_path, chunks_storage_path, doc_extensions
        ),
        services.DocumentChunksPipeline: adapters.FileSystemDocumentChunksPipeline(
            chunks_storage_path, lexical_index_storage_path
        ),
        services.DocumentIndexBuilder: adapters.WhooshIndexBuilder(),
        handlers.RepoSyncedNotifier: adapters.log_repository_synced,
        handlers.DocumentArtifactsUpdatedNotifier: adapters.log_document_artifacts_updated,
        handlers.IndexUpdatedNotifier: adapters.log_index_updated,
        handlers.DocumentArtifactsProcessor: services.composed_processor(
            services.process_raw_document,
            frontmatter_annotate_document,
            services.chunk_document,
        ),
    }
    for command, handler in mappings.COMMAND_HANDLER_MAP.items():
        type_hints = typing.get_type_hints(handler)
        kwargs = {
            name: dependency_pool[type_]
            for name, type_ in type_hints.items()
            if not name in ("return", "command")  # ignore return type and command arg
        }
        materialized_handler = functools.partial(handler, **kwargs)
        message_bus.register_command_handler(command, materialized_handler)

    for event, event_handlers in mappings.EVENT_HANDLER_MAP.items():
        for handler in event_handlers:
            type_hints = typing.get_type_hints(handler)
            kwargs = {
                name: dependency_pool[type_]
                for name, type_ in type_hints.items()
                if not name in ("return", "event")  # ignore return type and event arg
            }
            materialized_handler = functools.partial(handler, **kwargs)
            message_bus.register_event_handler(event, materialized_handler)

    return message_bus
