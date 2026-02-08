from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExternalRecord:
    source_identifier: str
    title: str
    rights_status: str
    source_locator: str


class ExternalConnector(ABC):
    name: str

    @abstractmethod
    def fetch(self, query: str, limit: int = 25) -> list[ExternalRecord]:
        """Return records from an external source.

        M2 defers concrete connector implementations. This interface defines
        compatibility requirements for future milestones.
        """

