from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from ...utils.errors import UserInputError


class JobBaseProto(Protocol):
    request_id: str
    user_id: int


TJob = TypeVar("TJob", bound=JobBaseProto)


def default_retry_policy_factory(
    user_error_type: type[Exception] = UserInputError,
) -> Callable[[JobBaseProto, Exception, int], bool]:
    """Create a retry policy that avoids retry for user input errors.

    Returns a callable(job, exc, attempt) -> bool where False means don't retry.
    """

    def _policy(job: JobBaseProto, exc: Exception, attempt: int) -> bool:
        return not isinstance(exc, user_error_type)

    return _policy


def failure_notifier_factory(
    notify_fn: Callable[[int, str], Awaitable[None] | None],
    *,
    user_error_type: type[Exception] = UserInputError,
    service_name: str = "job",
) -> Callable[[JobBaseProto, Exception, int, bool], Awaitable[None] | None]:
    """Create a failure callback that DMs users on failures.

    - Notifies immediately on first user-error failure.
    - Notifies on final failure for other exceptions.
    - Requires a notifier (e.g., cog.notify_user). Job type must provide user_id and request_id.
    """

    async def _callback(job: JobBaseProto, exc: Exception, attempt: int, will_retry: bool) -> None:
        logger = logging.getLogger(__name__)
        user_id = job.user_id
        request_id = job.request_id

        if isinstance(exc, user_error_type):
            if attempt == 1:
                logger.info(
                    "Job user error: service=%s uid=%s req=%s attempt=%d retry=%s error=%s",
                    service_name,
                    user_id,
                    request_id,
                    attempt,
                    will_retry,
                    str(exc),
                )
                res = notify_fn(
                    user_id,
                    f"{service_name.capitalize()} failed: {exc!s} (req={request_id})",
                )
                if res is not None:
                    await res
            return

        if not will_retry:
            logger.info(
                "Job final failure: service=%s uid=%s req=%s attempt=%d error=%s",
                service_name,
                user_id,
                request_id,
                attempt,
                str(exc),
            )
            res = notify_fn(
                user_id,
                (
                    f"An error occurred processing your {service_name} "
                    f"(req={request_id}). Please try again later."
                ),
            )
            if res is not None:
                await res

    return _callback
