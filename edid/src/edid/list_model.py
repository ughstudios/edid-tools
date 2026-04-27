from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass
class EditableList(Generic[T]):
    """Editable list model with undo/redo, reorder, copy, and paste."""

    items: list[T] = field(default_factory=list)
    max_items: int | None = None
    _undo: list[list[T]] = field(default_factory=list, init=False, repr=False)
    _redo: list[list[T]] = field(default_factory=list, init=False, repr=False)
    _clipboard: T | None = field(default=None, init=False, repr=False)

    def __len__(self) -> int:
        return len(self.items)

    def snapshot(self) -> list[T]:
        return deepcopy(self.items)

    def _push_undo(self) -> None:
        self._undo.append(self.snapshot())
        self._redo.clear()

    def _check_capacity(self, adding: int = 1) -> None:
        if self.max_items is not None and len(self.items) + adding > self.max_items:
            raise ValueError(f"List cannot contain more than {self.max_items} items.")

    def add(self, item: T) -> None:
        self._check_capacity()
        self._push_undo()
        self.items.append(deepcopy(item))

    def insert(self, index: int, item: T) -> None:
        self._check_capacity()
        self._push_undo()
        self.items.insert(index, deepcopy(item))

    def edit(self, index: int, item: T) -> None:
        self._push_undo()
        self.items[index] = deepcopy(item)

    def delete(self, index: int) -> T:
        self._push_undo()
        return self.items.pop(index)

    def delete_all(self) -> None:
        self._push_undo()
        self.items.clear()

    def move_up(self, index: int) -> int:
        if index <= 0:
            return index
        return self.exchange(index, index - 1)

    def move_down(self, index: int) -> int:
        if index >= len(self.items) - 1:
            return index
        return self.exchange(index, index + 1)

    def exchange(self, first: int, second: int) -> int:
        self._push_undo()
        self.items[first], self.items[second] = self.items[second], self.items[first]
        return second

    def copy(self, index: int) -> None:
        self._clipboard = deepcopy(self.items[index])

    def paste(self, index: int | None = None) -> None:
        if self._clipboard is None:
            raise ValueError("Clipboard is empty.")
        self._check_capacity()
        self._push_undo()
        item = deepcopy(self._clipboard)
        if index is None:
            self.items.append(item)
        else:
            self.items.insert(index, item)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self.items = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.items = self._redo.pop()
        return True
