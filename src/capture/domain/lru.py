"""Diccionario acotado que expulsa la clave usada hace más tiempo."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar('K', bound=Hashable)
V = TypeVar('V')


class LruDict(Generic[K, V]):
    """Memoria acotada para el estado por flujo.

    Un ataque que abre muchas conexiones nuevas no puede hacerla crecer sin límite.
    """

    __slots__ = ('_data', 'max_size')

    def __init__(self, max_size: int):
        self._data: OrderedDict[K, V] = OrderedDict()
        self.max_size = max_size

    def __contains__(self, key: K) -> bool:
        # Consultar no renueva la clave.
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: K, default: V | None = None) -> V | None:
        return self._data.get(key, default)

    def put(self, key: K, value: V) -> None:
        self._data[key] = value
        self._data.move_to_end(key)

        self._evict()

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        value = self._data.get(key)

        if value is not None:
            self._data.move_to_end(key)
            return value

        value = factory()
        self._data[key] = value

        self._evict()

        return value

    def _evict(self) -> None:
        if len(self._data) > self.max_size:
            self._data.popitem(last=False)
