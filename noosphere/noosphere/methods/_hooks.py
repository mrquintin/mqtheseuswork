from __future__ import annotations

from typing import Any, Callable

from noosphere.models import Method, MethodInvocation

PreHook = Callable[[Method, MethodInvocation, Any], None]
PostHook = Callable[[Method, MethodInvocation, Any, Any], None]
FailureHook = Callable[[Method, MethodInvocation, Any, BaseException], None]

_PRE_HOOKS: list[tuple[str, PreHook]] = []
_POST_HOOKS: list[tuple[str, PostHook]] = []
_FAILURE_HOOKS: list[tuple[str, FailureHook]] = []


def _replace_or_append(
    lst: list[tuple[str, Callable]], name: str, hook: Callable
) -> None:
    for i, (n, _) in enumerate(lst):
        if n == name:
            lst[i] = (name, hook)
            return
    lst.append((name, hook))


def register_pre_hook(name: str, hook: PreHook) -> None:
    _replace_or_append(_PRE_HOOKS, name, hook)


def register_post_hook(name: str, hook: PostHook) -> None:
    _replace_or_append(_POST_HOOKS, name, hook)


def register_failure_hook(name: str, hook: FailureHook) -> None:
    _replace_or_append(_FAILURE_HOOKS, name, hook)


def unregister_hook(name: str) -> None:
    for lst in (_PRE_HOOKS, _POST_HOOKS, _FAILURE_HOOKS):
        lst[:] = [(n, h) for n, h in lst if n != name]
