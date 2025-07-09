from abc import ABC, abstractmethod, abstractproperty
from typing import Any

from pydantic import BaseModel

from apps.mdm.models import Device, Fleet


class MDM(ABC):
    """Abstract base class for MDM implementations."""

    @abstractproperty
    def name(self):
        pass

    @abstractproperty
    def is_configured(self):
        pass

    def __bool__(self):
        return self.is_configured

    def __str__(self):
        return self.name

    @abstractmethod
    def pull_devices(self, fleet: Fleet, **kwargs):
        pass

    @abstractmethod
    def push_device_config(self, device: Device):
        pass

    @abstractmethod
    def sync_fleet(self, fleet: Fleet, push_config: bool = True):
        pass

    @abstractmethod
    def sync_fleets(self, push_config: bool = True):
        pass

    @abstractmethod
    def create_group(self, fleet: Fleet):
        pass

    @abstractmethod
    def add_group_to_policy(self, fleet: Fleet):
        pass

    @abstractmethod
    def get_enrollment_qr_code(self, fleet: Fleet):
        pass

    @abstractmethod
    def delete_group(self, fleet: Fleet) -> bool:
        pass


class MDMAPIError(BaseModel):
    method: str | None = None
    url: str
    status_code: int | None = None
    error_data: Any = None

    def __str__(self):
        error = f"Status {self.status_code}"
        if self.error_data:
            error += f": {self.error_data}"
        return error
