from django.http import HttpRequest
from pydantic import BaseModel
from typing import Optional

from django.urls import reverse


class Link(BaseModel):
    label: str
    viewname: str
    args: list[int | str] | None = None
    namespace: str = "publish_mdm"

    def __str__(self):
        return self.label

    @property
    def path(self):
        return reverse(f"{self.namespace}:{self.viewname}", args=self.args)


class Breadcrumbs(BaseModel):
    crumbs: list[Link]

    def __iter__(self):
        return iter(self.crumbs)

    @classmethod
    def from_items(cls, request: HttpRequest, items: list[tuple[str, str, Optional[list[str]]]]):
        base_args = [request.organization.slug] if request.organization else []
        if request.odk_project:
            base_args.append(request.odk_project.pk)
        crumbs = []
        for item in items:
            # Optionally add URL args to the base_args if provided
            args = base_args + item[2] if len(item) == 3 else base_args
            crumbs.append(Link(label=item[0], viewname=item[1], args=args))
        return cls(crumbs=crumbs)
