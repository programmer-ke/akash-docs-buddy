"""Command/event to handler mappings"""

from typing import Callable
from docs_buddy.services import commands, events, handlers

COMMAND_HANDLER_MAP: dict[type[commands.Command], Callable[..., None]] = {
    commands.SyncRepo: handlers.sync_repository,
    commands.UpdateDocumentArtifacts: handlers.update_document_artifacts,
    commands.UpdateDocumentIndex: handlers.index_document_chunks,
}

EVENT_HANDLER_MAP: dict[type[events.Event], list[Callable[..., None]]] = {
    events.RepositorySynced: [handlers.notify_repository_synced],
    events.DocumentArtifactsUpdated: [handlers.notify_document_artifacts_update],
    events.DocumentIndexUpdated: [handlers.notify_index_updated],
}
